/**
 * A visibility-aware poller with backoff (docs/14 §14.8; the `polling` spec
 * in §14.11).
 *
 * - While the page is hidden nothing runs: no timer is pending, so a hidden
 *   tab makes no requests at all.
 * - When the page becomes visible again, a poll that has come due runs at
 *   once; otherwise the remaining wait is kept.
 * - After a failure the wait doubles, up to `maxBackoff`; a success resets it.
 * - A poll never overlaps the previous one.
 *
 * `status`, `failures` and `lastOk` are reactive, so a chip or legend can say
 * how fresh the data is.
 */

/** What the poller needs from `document`; tests pass a fake. */
export interface VisibilitySource {
	readonly visibilityState: string;
	addEventListener(type: 'visibilitychange', listener: () => void): void;
	removeEventListener(type: 'visibilitychange', listener: () => void): void;
}

export interface PollOptions {
	/** Milliseconds between polls while visible and healthy. */
	interval: number;
	/** The longest wait after repeated failures (default 5 minutes). */
	maxBackoff?: number;
	/** Poll as soon as it starts (default true). */
	immediate?: boolean;
	/** Defaults to `document`. */
	visibility?: VisibilitySource;
	/** Defaults to Date.now (vitest's fake timers replace both). */
	now?: () => number;
}

export type PollStatus = 'idle' | 'ok' | 'error';

export class Poller {
	status = $state<PollStatus>('idle');
	failures = $state(0);
	/** When the last successful poll finished (ms since the epoch), or null. */
	lastOk = $state<number | null>(null);
	/** The last failure's message. */
	error = $state<string | null>(null);

	#fn: (signal: AbortSignal) => Promise<unknown>;
	#o: Required<Omit<PollOptions, 'visibility'>> & { visibility: VisibilitySource | null };
	#timer: ReturnType<typeof setTimeout> | undefined;
	#running = false;
	#inflight: AbortController | null = null;
	#lastRun = -Infinity;

	constructor(fn: (signal: AbortSignal) => Promise<unknown>, options: PollOptions) {
		this.#fn = fn;
		this.#o = {
			interval: options.interval,
			maxBackoff: options.maxBackoff ?? 300_000,
			immediate: options.immediate ?? true,
			visibility: options.visibility ?? (typeof document === 'undefined' ? null : document),
			now: options.now ?? (() => Date.now())
		};
	}

	get running(): boolean {
		return this.#running;
	}

	/** The wait before the next poll: the interval, doubled per failure, capped. */
	get delay(): number {
		const { interval, maxBackoff } = this.#o;
		return this.failures ? Math.min(interval * 2 ** this.failures, Math.max(interval, maxBackoff)) : interval;
	}

	#visible(): boolean {
		return this.#o.visibility?.visibilityState !== 'hidden';
	}

	/**
	 * Start polling. The first poll runs at once (unless `immediate` is false);
	 * a restart soon after a poll waits out the rest of the interval instead of
	 * polling again.
	 */
	start(): void {
		if (this.#running) return;
		this.#running = true;
		this.#o.visibility?.addEventListener('visibilitychange', this.#onVisibility);
		if (!this.#visible()) return;
		const due = this.#lastRun + this.delay - this.#o.now();
		if (due <= 0 && this.#o.immediate) void this.#run();
		else this.#schedule(due > 0 ? due : this.#o.interval);
	}

	stop(): void {
		this.#running = false;
		clearTimeout(this.#timer);
		this.#timer = undefined;
		this.#inflight?.abort();
		this.#inflight = null;
		this.#o.visibility?.removeEventListener('visibilitychange', this.#onVisibility);
	}

	/** Poll now (when running and visible), whatever the timer says. */
	poke(): void {
		if (this.#running && this.#visible()) void this.#run();
	}

	#schedule(ms: number) {
		clearTimeout(this.#timer);
		this.#timer = setTimeout(() => void this.#run(), Math.max(0, ms));
	}

	async #run() {
		if (!this.#running || !this.#visible() || this.#inflight) return;
		clearTimeout(this.#timer);
		this.#timer = undefined;
		this.#lastRun = this.#o.now();
		const ac = new AbortController();
		this.#inflight = ac;
		try {
			await this.#fn(ac.signal);
			if (ac.signal.aborted) return;
			this.failures = 0;
			this.error = null;
			this.status = 'ok';
			this.lastOk = this.#o.now();
		} catch (e) {
			if (ac.signal.aborted) return;
			this.failures += 1;
			this.error = e instanceof Error ? e.message : String(e);
			this.status = 'error';
		} finally {
			if (this.#inflight === ac) this.#inflight = null;
		}
		if (this.#running && this.#visible()) this.#schedule(this.delay);
	}

	#onVisibility = () => {
		if (!this.#running) return;
		if (!this.#visible()) {
			clearTimeout(this.#timer);
			this.#timer = undefined;
			return;
		}
		const due = this.#lastRun + this.delay - this.#o.now();
		if (due <= 0) void this.#run();
		else this.#schedule(due);
	};
}
