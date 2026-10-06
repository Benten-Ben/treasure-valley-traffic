/**
 * The render loop scheduler (docs/14 §14.8, "Render loop rules").
 *
 * One scheduler owns continuous rendering. MapLibre redraws by itself when
 * the camera moves or tiles arrive; anything animated on top of that (moving
 * buses, tweens) asks this loop for frames instead of calling
 * `triggerRepaint()` itself:
 *
 * - `want(key, fps)`: keep frames coming at up to `fps` while it stands (the
 *   overlay asks for 2 × the fastest on-screen speed in px/s, so a sprite
 *   moves about half a pixel per frame); `want(key, null)` withdraws it.
 * - `tween(key, ms)`: full rate for a short animation.
 *
 * The target rate is the highest request, clamped to [2, 60]. Nothing runs
 * while nothing is asked for or the tab is hidden, so an idle map costs no
 * frames at all.
 */
export const MIN_FPS = 2;
export const MAX_FPS = 60;

export const clampFps = (fps: number) => Math.min(MAX_FPS, Math.max(MIN_FPS, Number.isFinite(fps) ? fps : MAX_FPS));

/** What the loop needs from the map. */
export interface Repaintable {
	triggerRepaint(): void;
	on(type: 'render', fn: () => void): unknown;
	off(type: 'render', fn: () => void): unknown;
}

export interface LoopOptions {
	visibility?: { readonly visibilityState: string; addEventListener(t: 'visibilitychange', f: () => void): void; removeEventListener(t: 'visibilitychange', f: () => void): void } | null;
	now?: () => number;
	raf?: (fn: (t: number) => void) => number;
	caf?: (id: number) => void;
}

export class Loop {
	#map: Repaintable | null = null;
	#wants = new Map<string, number>();
	#tweens = new Map<string, number>();
	#raf = 0;
	#lastRepaint = -Infinity;
	#o: Required<LoopOptions>;
	/** Frames MapLibre has rendered since attach (any cause). */
	frames = 0;
	/** Repaints this loop asked for. */
	repaints = 0;

	constructor(o: LoopOptions = {}) {
		this.#o = {
			visibility: o.visibility === undefined ? (typeof document === 'undefined' ? null : document) : o.visibility,
			now: o.now ?? (() => performance.now()),
			raf: o.raf ?? ((fn) => requestAnimationFrame(fn)),
			caf: o.caf ?? ((id) => cancelAnimationFrame(id))
		};
	}

	attach(map: Repaintable): void {
		this.#map = map;
		map.on('render', this.#onRender);
		this.#o.visibility?.addEventListener('visibilitychange', this.#onVisibility);
		this.#kick();
	}

	detach(): void {
		this.#map?.off('render', this.#onRender);
		this.#o.visibility?.removeEventListener('visibilitychange', this.#onVisibility);
		this.#map = null;
		this.#stop();
	}

	/** Ask for frames at up to `fps` under `key`; null withdraws the request. */
	want(key: string, fps: number | null): void {
		if (fps === null || fps <= 0) this.#wants.delete(key);
		else this.#wants.set(key, fps);
		this.#kick();
	}

	/** Full-rate frames for `ms` (a short animation). */
	tween(key: string, ms: number): void {
		this.#tweens.set(key, this.#o.now() + ms);
		this.#kick();
	}

	/** The rate asked for right now (0 when nothing is). */
	get targetFps(): number {
		const now = this.#o.now();
		for (const [k, until] of this.#tweens) if (until <= now) this.#tweens.delete(k);
		if (this.#tweens.size) return MAX_FPS;
		if (!this.#wants.size) return 0;
		return clampFps(Math.max(...this.#wants.values()));
	}

	get running(): boolean {
		return this.#raf !== 0;
	}

	#visible(): boolean {
		return this.#o.visibility?.visibilityState !== 'hidden';
	}

	#kick() {
		if (this.#raf || !this.#map || !this.#visible() || this.targetFps === 0) return;
		this.#raf = this.#o.raf(this.#tick);
	}

	#stop() {
		if (this.#raf) this.#o.caf(this.#raf);
		this.#raf = 0;
	}

	#tick = () => {
		this.#raf = 0;
		const fps = this.targetFps;
		if (!this.#map || !this.#visible() || fps === 0) return;
		const now = this.#o.now();
		// A frame is due once its interval has passed (a millisecond early still counts: rAF jitters).
		if (now - this.#lastRepaint >= 1000 / fps - 1) {
			this.#lastRepaint = now;
			this.repaints++;
			this.#map.triggerRepaint();
		}
		this.#raf = this.#o.raf(this.#tick);
	};

	#onRender = () => {
		this.frames++;
	};

	#onVisibility = () => {
		if (this.#visible()) this.#kick();
		else this.#stop();
	};
}
