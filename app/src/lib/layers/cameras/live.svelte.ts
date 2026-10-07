import type { AppCtx } from '#lib/app/context.js';
import type { CamerasLive, LiveFrame, LiveView } from '#lib/contracts/live.js';
import { Poller, type VisibilitySource } from '#lib/state/poll.svelte.js';

/**
 * The batched live poll (docs/14 §14.6 "Live images", client; WP12): one
 * `GET /api/cameras/live?views=…` for every view that a camera window,
 * look-through or calibration has open, every 15 s, or every 60 s when all of
 * them are slow-cadence (road-weather) views. Paused while the tab is hidden
 * (the Poller makes no request then).
 *
 * - `watch(ids)` adds views (counted, so two watchers of one view share it)
 *   and returns the release. A view that isn't covered yet is asked for at
 *   once rather than at the next tick.
 * - When the last view is released the poll stops at once, aborting a request
 *   in flight: closing the last window ends all traffic for it.
 * - At most 12 views per request (the endpoint's limit); more go in parallel
 *   requests.
 * - `views` holds the newest answer per view ($state.raw, replaced whole);
 *   `ageOf(frame)` is its "seen" age on the server's clock.
 */
export const LIVE_INTERVAL_MS = 15_000;
export const SLOW_INTERVAL_MS = 60_000;
/** The endpoint's limit (MAX_LIVE_VIEWS on the server). */
export const VIEWS_PER_REQUEST = 12;

export interface LiveFeedOptions {
	fetch?: (url: string, init: RequestInit) => Promise<Response>;
	visibility?: VisibilitySource;
	now?: () => number;
	interval?: number;
	slowInterval?: number;
}

/** Split ids into requests of at most `n`. */
export function batches(ids: readonly number[], n = VIEWS_PER_REQUEST): number[][] {
	const out: number[][] = [];
	for (let i = 0; i < ids.length; i += n) out.push(ids.slice(i, i + n));
	return out;
}

export class LiveFeed {
	/** The newest answer per view id. */
	views = $state.raw<Record<number, LiveView>>({});
	/** Server clock minus ours, ms (from each answer's `now`). */
	skew = $state(0);
	/** Requests made (for tests and the console). */
	requests = 0;

	#refs = new Map<number, number>();
	#poller: Poller | null = null;
	#interval: number;
	#o: Required<Omit<LiveFeedOptions, 'visibility'>> & { visibility?: VisibilitySource };
	/** Views asked for by the request in flight (or the last one). */
	#asked = new Set<number>();
	#inflight = false;
	#followUp: ReturnType<typeof setTimeout> | undefined;

	constructor(o: LiveFeedOptions = {}) {
		this.#o = {
			fetch: o.fetch ?? ((url, init) => fetch(url, init)),
			visibility: o.visibility,
			now: o.now ?? (() => Date.now()),
			interval: o.interval ?? LIVE_INTERVAL_MS,
			slowInterval: o.slowInterval ?? SLOW_INTERVAL_MS
		};
		this.#interval = this.#o.interval;
	}

	/** The views being polled, in ascending order. */
	get watching(): number[] {
		return [...this.#refs.keys()].sort((a, b) => a - b);
	}

	get running(): boolean {
		return this.#poller?.running ?? false;
	}

	/** The poll's current interval, ms. */
	get interval(): number {
		return this.#interval;
	}

	/** Poll these views until the returned function is called. */
	watch(ids: readonly number[]): () => void {
		const mine = [...new Set(ids.filter((id) => Number.isInteger(id) && id > 0))];
		if (!mine.length) return () => {};
		let fresh = false;
		for (const id of mine) {
			const n = this.#refs.get(id) ?? 0;
			if (!n) fresh = true;
			this.#refs.set(id, n + 1);
		}
		this.#ensure();
		if (fresh) this.#askSoon();
		let released = false;
		return () => {
			if (released) return;
			released = true;
			for (const id of mine) {
				const n = (this.#refs.get(id) ?? 1) - 1;
				if (n > 0) this.#refs.set(id, n);
				else this.#refs.delete(id);
			}
			if (!this.#refs.size) this.#stop();
			else this.#retune();
		};
	}

	/** The newest answer for a view. */
	view(id: number): LiveView | null {
		return this.views[id] ?? null;
	}

	/** Seconds since our server first saw the picture, on the server's clock. */
	ageOf(frame: Pick<LiveFrame, 'firstSeenAt'>, now = this.#o.now()): number {
		return Math.max(0, (now + this.skew) / 1000 - frame.firstSeenAt);
	}

	/** Stop everything (leaving the map). */
	destroy(): void {
		this.#refs.clear();
		this.#stop();
	}

	// --- inside ------------------------------------------------------------------------

	#ensure() {
		if (this.#poller?.running) return;
		this.#start(true);
	}

	#start(immediate: boolean) {
		this.#poller?.stop();
		this.#poller = new Poller((signal) => this.#poll(signal), {
			interval: this.#interval,
			immediate,
			visibility: this.#o.visibility,
			now: this.#o.now
		});
		this.#poller.start();
	}

	#stop() {
		clearTimeout(this.#followUp);
		this.#followUp = undefined;
		this.#poller?.stop();
		this.#poller = null;
		this.#inflight = false;
		this.#interval = this.#o.interval;
	}

	/**
	 * A view isn't covered yet: ask now. With a request in flight, its end
	 * asks again instead (see #poll), since the poller runs one at a time.
	 */
	#askSoon() {
		if (!this.#poller || this.#inflight) return;
		this.#pokeLater();
	}

	/** Poke on the next turn, once the poller has finished its bookkeeping for the last run. */
	#pokeLater() {
		clearTimeout(this.#followUp);
		this.#followUp = setTimeout(() => {
			this.#followUp = undefined;
			if (!this.#inflight) this.#poller?.poke();
		}, 0);
	}

	/** 60 s when every watched view is a slow-cadence one; 15 s otherwise. */
	#retune() {
		const ids = this.watching;
		const slow = ids.length > 0 && ids.every((id) => this.views[id]?.cadence === 'road_weather');
		const want = slow ? this.#o.slowInterval : this.#o.interval;
		if (want === this.#interval) return;
		this.#interval = want;
		if (this.#poller?.running) this.#start(false);
	}

	async #poll(signal: AbortSignal): Promise<void> {
		const ids = this.watching;
		if (!ids.length) return;
		const asked = new Set(ids);
		this.#asked = asked;
		this.#inflight = true;
		try {
			const answers = await Promise.all(
				batches(ids).map(async (chunk) => {
					this.requests++;
					const res = await this.#o.fetch(`/api/cameras/live?views=${chunk.join(',')}`, { cache: 'no-store', signal });
					if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
					return (await res.json()) as CamerasLive;
				})
			);
			if (signal.aborted) return;
			const next = { ...this.views };
			for (const a of answers) {
				if (typeof a.now === 'number') this.skew = a.now * 1000 - this.#o.now();
				for (const [id, v] of Object.entries(a.views ?? {})) next[Number(id)] = v;
			}
			this.views = next;
			this.#retune();
		} finally {
			// (A request aborted by a stop may end after a newer one started: only the newest counts.)
			if (this.#asked === asked) this.#inflight = false;
			// Someone asked for a view this request didn't carry.
			if (!signal.aborted && this.watching.some((id) => !asked.has(id))) this.#pokeLater();
		}
	}
}

// --- the app's feed -----------------------------------------------------------------

const feeds = new WeakMap<object, LiveFeed>();

/** The app's one live feed, created the first time it's asked for. */
export function liveOf(app: AppCtx | object): LiveFeed {
	let f = feeds.get(app);
	if (!f) {
		f = new LiveFeed();
		feeds.set(app, f);
	}
	return f;
}
