import type { AppCtx } from '#lib/app/context.js';
import { register, type KeyBinding } from '#lib/ui/keys.js';
import { readStored, writeStored } from './persisted.svelte.js';

/**
 * The playhead clock (docs/14 §14.3 "Top bar, clock and time pill"; §14.4
 * "Playback"; WP8).
 *
 * Buses are drawn where they were at the *playhead* T, a little behind live,
 * because a fix reaches the database 37–68 s after it was taken (p50, max)
 * and the client polls every 10 s. Nothing is ever extrapolated: a bus waits
 * at its newest fix.
 *
 * - **Server offset:** the median, over the last 5 polls, of
 *   `server now − (send + receive) / 2`. A client clock that's a minute off
 *   doesn't move anything.
 * - **Live:** `T = Date.now()/1000 + offset − D`, with the delay D (default
 *   90 s; the picker offers 1, 1.5, 2, 3 and 5 min) remembered per viewer.
 * - **Pause** freezes T while the data keeps buffering; **play** carries on
 *   from there, now further behind; **Go live** (L) returns to `now − D`.
 * - **Replay (`?at=<ISO time>`):** the server's clock is pinned to `at` and
 *   runs on in real time from there, so T starts at `at − D`. It's for deep
 *   links and tests; the full replay with a time bar comes later.
 * - The UI reads `tick`, a 1 Hz clock; nothing here is written per frame.
 *   Per-frame code calls `playhead()`.
 */

/** The delays the picker offers, in seconds. */
export const DELAYS = [60, 90, 120, 180, 300] as const;
export const DEFAULT_DELAY = 90;
/** Polls whose offsets make the median. */
export const OFFSET_SAMPLES = 5;
/** No new GPS for this long (s): the pill says the feed has stalled (the chips' ▲ uses the same 2 minutes). */
export const STALL_S = 120;

const DELAY_KEY = 'delay';
const isDelay = (v: unknown): v is number => typeof v === 'number' && (DELAYS as readonly number[]).includes(v);

export type ClockState = 'live' | 'behind' | 'paused' | 'stalled' | 'replay';

export interface ClockOptions {
	/** Wall clock, ms (Date.now). */
	now?: () => number;
	/** A pinned replay start (epoch s), from `?at=`. */
	at?: number | null;
	/** The remembered delay (default: storage, then 90 s). */
	delay?: number;
	/** Run the 1 Hz tick (default true; tests tick by hand). */
	ticking?: boolean;
	/** Called when Go live leaves a replay (drops `?at=` from the URL). */
	onLeaveReplay?: () => void;
}

/** The median of a list of numbers (0 for none). */
export function median(xs: readonly number[]): number {
	if (!xs.length) return 0;
	const s = [...xs].sort((a, b) => a - b);
	const m = s.length >> 1;
	return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** `m:ss` for a number of seconds (rounded down to the second). */
export function minSec(seconds: number): string {
	const s = Math.max(0, Math.floor(seconds + 1e-6));
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** Parse `?at=` (an ISO time, or epoch seconds); null when absent or unreadable. */
export function parseAt(value: string | null | undefined): number | null {
	if (!value) return null;
	if (/^\d{9,11}(\.\d+)?$/.test(value)) return Number(value);
	const ms = Date.parse(value);
	return Number.isFinite(ms) ? ms / 1000 : null;
}

const boise = new Intl.DateTimeFormat('en-US', {
	timeZone: 'America/Boise',
	hour: 'numeric',
	minute: '2-digit',
	second: '2-digit',
	weekday: 'short'
});

/** `5:41:20 PM · Tue` in Boise (§14.3). */
export function clockText(epochS: number): string {
	const parts = Object.fromEntries(boise.formatToParts(new Date(epochS * 1000)).map((p) => [p.type, p.value]));
	return `${parts.hour}:${parts.minute}:${parts.second} ${parts.dayPeriod} · ${parts.weekday}`;
}

const boiseShort = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Boise', hour: 'numeric', minute: '2-digit' });
/** `11:52 PM` in Boise. */
export const timeText = (epochS: number) => boiseShort.format(new Date(epochS * 1000));

const boiseDay = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Boise', month: 'short', day: 'numeric' });
/** `Oct 6` in Boise. */
export const dayText = (epochS: number) => boiseDay.format(new Date(epochS * 1000));

export class Clock {
	/** The delay D behind live, seconds. */
	delay = $state(DEFAULT_DELAY);
	/** The playhead while paused (epoch s), else null. */
	paused = $state<number | null>(null);
	/** Seconds behind the server's now while playing (D when live). */
	lag = $state(DEFAULT_DELAY);
	/** A pinned replay's start (`?at=`), else null. */
	replayAt = $state<number | null>(null);
	/** Server minus client clock, seconds (the median of the last polls). */
	offset = $state(0);
	/** Wall clock (ms) once a second: what the UI reads. */
	tick = $state(0);
	/** The bus feed, as the Transit layer last saw it. */
	feed = $state.raw<{ lastFix: number | null; ok: boolean; at: number } | null>(null);

	#samples: number[] = [];
	#now: () => number;
	#timer: ReturnType<typeof setInterval> | undefined;
	#keys: (() => void) | null = null;
	#keyHolders = 0;
	#onLeaveReplay: (() => void) | undefined;

	constructor(o: ClockOptions = {}) {
		this.#now = o.now ?? (() => Date.now());
		this.#onLeaveReplay = o.onLeaveReplay;
		const d = o.delay ?? readStored(DELAY_KEY, isDelay) ?? DEFAULT_DELAY;
		this.delay = d;
		this.lag = d;
		this.tick = this.#now();
		if (o.at !== undefined && o.at !== null) {
			this.replayAt = o.at;
			// The replay's "server now" starts at `at`.
			this.offset = o.at - this.#now() / 1000;
		}
		if (o.ticking !== false) this.#timer = setInterval(() => (this.tick = this.#now()), 1000);
	}

	destroy(): void {
		clearInterval(this.#timer);
		this.#keys?.();
		this.#keys = null;
	}

	/** The server's clock now (or the replay's), epoch s. */
	serverNow(nowMs = this.#now()): number {
		return nowMs / 1000 + this.offset;
	}

	/** The playhead T, epoch s: where the buses on the map are. */
	playhead(nowMs = this.#now()): number {
		return this.paused ?? this.serverNow(nowMs) - this.lag;
	}

	/** The playhead at the last tick (for the UI). */
	get T(): number {
		return this.playhead(this.tick);
	}

	/** How far behind live the playhead is, seconds (at the last tick). */
	get behind(): number {
		return this.serverNow(this.tick) - this.playhead(this.tick);
	}

	get live(): boolean {
		return this.paused === null && Math.abs(this.lag - this.delay) < 0.5;
	}

	/** Seconds since the newest fix of any bus, at the last tick (null: unknown). */
	get feedAge(): number | null {
		const f = this.feed;
		return f?.lastFix ? Math.max(0, this.serverNow(this.tick) - f.lastFix) : null;
	}

	get state(): ClockState {
		if (this.paused !== null) return 'paused';
		if (this.replayAt !== null) return 'replay';
		if (!this.live) return 'behind';
		const age = this.feedAge;
		return age !== null && age >= STALL_S ? 'stalled' : 'live';
	}

	/**
	 * One poll's clock sample: the server's `now` and when the request went
	 * out and its answer came back (client ms). A replay keeps its own clock.
	 */
	sample(serverNow: number, sendMs: number, receiveMs: number): void {
		if (this.replayAt !== null) return;
		this.#samples.push(serverNow - (sendMs + receiveMs) / 2000);
		if (this.#samples.length > OFFSET_SAMPLES) this.#samples.shift();
		this.offset = median(this.#samples);
	}

	pause(): void {
		if (this.paused === null) this.paused = this.playhead();
	}

	/** Play on from where it was paused (further behind live than before). */
	play(): void {
		if (this.paused === null) return;
		this.lag = Math.max(0, this.serverNow() - this.paused);
		this.paused = null;
	}

	toggle(): void {
		if (this.paused === null) this.pause();
		else this.play();
	}

	/** Back to `now − D`; a replay ends (and `?at=` goes). */
	goLive(): void {
		this.paused = null;
		this.lag = this.delay;
		if (this.replayAt !== null) {
			this.replayAt = null;
			this.#samples = [];
			this.offset = 0;
			this.#onLeaveReplay?.();
		}
	}

	/** Change D (remembered); while live, the playhead jumps to `now − D`. */
	setDelay(seconds: number): void {
		if (!isDelay(seconds)) return;
		const wasLive = this.live;
		this.delay = seconds;
		writeStored(DELAY_KEY, seconds);
		if (wasLive || this.replayAt !== null) {
			if (this.paused === null) this.lag = seconds;
		}
	}

	/** The pill's label: `LIVE −1:30`, `PAUSED −3:05`, `LIVE · no new GPS for 3 min`, `REPLAY …`. */
	get label(): string {
		void this.tick;
		switch (this.state) {
			case 'paused':
				return `PAUSED −${minSec(this.behind)}`;
			case 'replay':
				return `REPLAY · ${dayText(this.T)}`;
			case 'behind':
				return `BEHIND −${minSec(this.behind)}`;
			case 'stalled':
				return `LIVE · no new GPS for ${Math.max(2, Math.floor((this.feedAge ?? 0) / 60))} min`;
			default:
				return `LIVE −${minSec(this.delay)}`;
		}
	}

	/**
	 * Space (pause / play) and L (back to live), through the keymap registry
	 * (§14.3 "Keymap"). Held by whoever shows the clock (the time pill, the
	 * Transit layer); registered once while anyone holds them.
	 */
	holdKeys(): () => void {
		this.#keyHolders++;
		if (!this.#keys) this.#keys = register(clockKeys(this));
		let held = true;
		return () => {
			if (!held) return;
			held = false;
			this.#keyHolders--;
			if (this.#keyHolders <= 0) {
				this.#keyHolders = 0;
				this.#keys?.();
				this.#keys = null;
			}
		};
	}
}

export function clockKeys(clock: Clock): KeyBinding[] {
	return [
		{ id: 'pause', codes: ['Space'], label: 'Space', description: 'Pause / play the buses', group: 'Time', run: () => clock.toggle() },
		{ id: 'live', codes: ['KeyL'], label: 'L', description: 'Back to live', group: 'Time', run: () => clock.goLive() }
	];
}

declare module '#lib/app/context.js' {
	interface AppCtx {
		/** The playhead clock (WP8): where the buses on the map are in time. */
		readonly clock: Clock;
	}
}

declare module '#lib/app/app.svelte.js' {
	interface App {
		readonly clock: Clock;
	}
}

const clocks = new WeakMap<object, Clock>();

/** Drop `?at=` from the address (a replay has ended), without a navigation. */
async function dropAtParam(): Promise<void> {
	const url = new URL(location.href);
	if (!url.searchParams.has('at')) return;
	url.searchParams.delete('at');
	const [{ goto }, { page }] = await Promise.all([import('$app/navigation'), import('$app/state')]);
	await goto(`${url.pathname}${url.search}${url.hash}`, { shallow: true, replace: true, state: page.state }).catch(() => {});
}

/** The app's clock, created the first time it's asked for (and then `app.clock`). */
export function clockOf(app: AppCtx): Clock {
	let c = clocks.get(app);
	if (!c) {
		const at = typeof location === 'undefined' ? null : parseAt(new URL(location.href).searchParams.get('at'));
		c = new Clock({ at, onLeaveReplay: () => void dropAtParam() });
		clocks.set(app, c);
		Object.defineProperty(app, 'clock', { value: c, configurable: true, enumerable: false });
	}
	return c;
}
