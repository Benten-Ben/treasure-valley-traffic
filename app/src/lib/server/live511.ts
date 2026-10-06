/**
 * The on-demand 511 fetcher (docs/14 §14.6, "Live images"): 511 Idaho's
 * republished image for a camera we don't record, fetched by the server only
 * while someone has it open, looked through or in calibration. In memory
 * only, and single-flight:
 *
 * - only images of views in core.camera_view (the caller checks; see frames.ts);
 * - each image at most once per 55 s, and concurrent callers share one fetch;
 * - at most 2 upstream requests at a time;
 * - at most 12 distinct images per 10 minutes;
 * - refreshing stops 3 minutes after the last client asked;
 * - robots.txt is checked before every request (robots.ts), and Crawl-delay
 *   honored; a disallow, or a robots.txt that can't be read, means "blocked";
 * - frames are kept in an LRU of 64, in memory only. Nothing is written to
 *   disk; "Use this frame" (frames.ts) copies one out when asked.
 *
 * Age is "seen" time: when our server first got those bytes. A repeat (same
 * sha256) keeps its first time.
 */
import { createHash } from 'node:crypto';
import { isJpeg, jpegSize } from './archive.js';
import type { RobotsVerdict } from './robots.js';

/** 511 Idaho's republished camera images: the allowed route (docs/11 §11.2). */
export const imageUrl = (imageId: number) => `https://511.idaho.gov/map/Cctv/${imageId}`;

export const LIVE_LIMITS = {
	/** Per image, between upstream requests. */
	minIntervalMs: 55_000,
	maxConcurrent: 2,
	/** Distinct images per window. */
	capImages: 12,
	capWindowMs: 10 * 60_000,
	/** Refreshing stops this long after the last ask. */
	keepWarmMs: 3 * 60_000,
	lruSize: 64,
	/** How often the refresher looks for images due again. */
	refreshEveryMs: 5_000,
	/** How long a first ask waits for the first picture before answering "waiting". */
	firstWaitMs: 2_500
};

export type LiveLimits = typeof LIVE_LIMITS;

/** A frame held in memory. */
export interface MemFrame {
	sha: string;
	bytes: Uint8Array;
	image: number;
	/** When our server first got these bytes, epoch s. */
	firstSeenAt: number;
	width: number;
	height: number;
}

export interface LiveOutcome {
	state: 'ok' | 'waiting' | 'blocked' | 'capped' | 'error';
	frame: MemFrame | null;
	reason?: string;
}

export interface LiveFetcherOptions {
	/** Gets the image's current bytes (511, or the seeded fixture in fixture mode). Throws on failure. */
	fetchImage: (image: number, viewId: number) => Promise<Uint8Array>;
	/** robots.txt check before each request; null skips it (fixture mode, which makes no request). */
	robots: ((url: string) => Promise<RobotsVerdict>) | null;
	/** Clock, ms. */
	now?: () => number;
	limits?: Partial<LiveLimits>;
	log?: (message: string) => void;
}

interface ImageState {
	viewId: number;
	lastAsked: number;
	/** When the last upstream request started (or was refused by robots.txt). */
	lastAttempt?: number;
	inflight?: Promise<void>;
	/** sha of the newest frame. */
	latest?: string;
	blocked?: string;
	capped?: string;
	error?: string;
}

const sha256 = (b: Uint8Array) => createHash('sha256').update(b).digest('hex');
const mmss = (ms: number) => {
	const s = Math.max(0, Math.ceil(ms / 1000));
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

export class LiveFetcher {
	/** Upstream image requests made, and the most at once (for tests and logs). */
	readonly counts = { upstream: 0, maxActive: 0 };
	readonly limits: LiveLimits;
	private readonly fetchImage: LiveFetcherOptions['fetchImage'];
	private readonly robots: LiveFetcherOptions['robots'];
	private readonly now: () => number;
	private readonly log: (message: string) => void;
	private images = new Map<number, ImageState>();
	private lru = new Map<string, MemFrame>();
	/** image → when its last upstream request started, for the distinct-images cap. */
	private window = new Map<number, number>();
	private active = 0;
	private queue: (() => void)[] = [];
	private hostReadyAt = 0;
	private timer: ReturnType<typeof setInterval> | null = null;

	constructor(opts: LiveFetcherOptions) {
		this.fetchImage = opts.fetchImage;
		this.robots = opts.robots;
		this.now = opts.now ?? Date.now;
		this.limits = { ...LIVE_LIMITS, ...opts.limits };
		this.log = opts.log ?? (() => {});
	}

	/**
	 * A client wants this image: note the ask, fetch if it's due and allowed,
	 * and answer with the newest frame. A first ask waits briefly for the first
	 * picture.
	 */
	async request(image: number, viewId: number, waitMs = this.limits.firstWaitMs): Promise<LiveOutcome> {
		const now = this.now();
		let s = this.images.get(image);
		if (!s) {
			s = { viewId, lastAsked: now };
			this.images.set(image, s);
		}
		s.lastAsked = now;
		s.viewId = viewId;
		this.startTimer();
		this.maybeStart(image, s, now);
		if (!this.current(s) && s.inflight && waitMs > 0) await this.within(s.inflight, waitMs);
		return this.outcome(s);
	}

	/** A frame by sha, while it's in memory (refreshes its place in the LRU). */
	frame(sha: string): MemFrame | null {
		const f = this.lru.get(sha);
		if (!f) return null;
		this.lru.delete(sha);
		this.lru.set(sha, f);
		return f;
	}

	/** Refresh every image asked for within the last 3 minutes that's due again. The timer calls this. */
	tick() {
		const now = this.now();
		let warm = 0;
		for (const [image, s] of this.images) {
			if (now - s.lastAsked > this.limits.keepWarmMs) continue;
			warm++;
			this.maybeStart(image, s, now);
		}
		if (!warm) this.stopTimer();
	}

	/** Stop refreshing (tests, shutdown). */
	stop() {
		this.stopTimer();
	}

	private startTimer() {
		if (this.timer) return;
		this.timer = setInterval(() => this.tick(), this.limits.refreshEveryMs);
		(this.timer as { unref?: () => void }).unref?.();
	}

	private stopTimer() {
		if (this.timer) clearInterval(this.timer);
		this.timer = null;
	}

	private current(s: ImageState): MemFrame | null {
		return s.latest ? this.frame(s.latest) : null;
	}

	private outcome(s: ImageState): LiveOutcome {
		const frame = this.current(s);
		if (s.blocked) return { state: 'blocked', frame, reason: s.blocked };
		if (s.capped) return { state: 'capped', frame, reason: s.capped };
		if (frame) return { state: 'ok', frame };
		if (s.inflight) return { state: 'waiting', frame: null };
		if (s.error) return { state: 'error', frame: null, reason: s.error };
		return { state: 'waiting', frame: null };
	}

	private pruneWindow(now: number) {
		for (const [image, at] of this.window) if (now - at >= this.limits.capWindowMs) this.window.delete(image);
	}

	private maybeStart(image: number, s: ImageState, now: number) {
		if (s.inflight) return;
		if (s.lastAttempt !== undefined && now - s.lastAttempt < this.limits.minIntervalMs) return;
		this.pruneWindow(now);
		if (!this.window.has(image) && this.window.size >= this.limits.capImages) {
			const oldest = Math.min(...this.window.values());
			s.capped =
				`On-demand limit reached (${this.limits.capImages} cameras per ${this.limits.capWindowMs / 60_000} minutes); ` +
				`next slot in ${mmss(oldest + this.limits.capWindowMs - now)}`;
			return;
		}
		s.capped = undefined;
		s.lastAttempt = now;
		const before = this.window.get(image);
		this.window.set(image, now); // reserved now, so two images can't both take the last slot
		s.inflight = this.attempt(image, s, before).finally(() => {
			s.inflight = undefined;
		});
	}

	private async attempt(image: number, s: ImageState, windowBefore: number | undefined) {
		const url = imageUrl(image);
		if (this.robots) {
			let verdict: RobotsVerdict;
			try {
				verdict = await this.robots(url);
			} catch (err) {
				verdict = { allowed: false, decision: 'unavailable', crawlDelayS: null, reason: String(err) };
			}
			if (!verdict.allowed) {
				s.blocked = "robots.txt doesn't allow it right now";
				this.log(`blocked: ${verdict.reason ?? url}`);
				// No request was made, so it doesn't count toward the cap.
				if (windowBefore === undefined) this.window.delete(image);
				else this.window.set(image, windowBefore);
				return;
			}
			s.blocked = undefined;
			if (verdict.crawlDelayS) {
				const wait = this.hostReadyAt - this.now();
				this.hostReadyAt = Math.max(this.now(), this.hostReadyAt) + verdict.crawlDelayS * 1000;
				if (wait > 0) await new Promise((r) => setTimeout(r, wait));
			}
		}
		await this.slot();
		try {
			s.lastAttempt = this.now();
			this.counts.upstream++;
			const bytes = await this.fetchImage(image, s.viewId);
			if (!isJpeg(bytes)) throw new Error('not a complete JPEG');
			const size = jpegSize(bytes);
			if (!size) throw new Error('not a readable JPEG');
			const sha = sha256(bytes);
			if (!this.frame(sha)) this.put({ sha, bytes, image, firstSeenAt: this.now() / 1000, ...size });
			s.latest = sha;
			s.error = undefined;
		} catch (err) {
			s.error = `511 image ${image}: ${err instanceof Error ? err.message : String(err)}`;
			this.log(s.error);
		} finally {
			this.release();
		}
	}

	private put(f: MemFrame) {
		this.lru.set(f.sha, f);
		while (this.lru.size > this.limits.lruSize) this.lru.delete(this.lru.keys().next().value!);
	}

	private async slot() {
		if (this.active < this.limits.maxConcurrent) this.active++;
		else await new Promise<void>((r) => this.queue.push(r)); // handed over by release()
		this.counts.maxActive = Math.max(this.counts.maxActive, this.active);
	}

	private release() {
		const next = this.queue.shift();
		if (next) next();
		else this.active--;
	}

	private async within(p: Promise<unknown>, ms: number) {
		let t: ReturnType<typeof setTimeout> | undefined;
		await Promise.race([p, new Promise((r) => (t = setTimeout(r, ms)))]);
		clearTimeout(t);
	}
}
