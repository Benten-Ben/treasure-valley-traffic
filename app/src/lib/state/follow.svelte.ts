import type { Map } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import type { Loop } from '#lib/map/loop.js';

/**
 * Follow (docs/14 §14.3, "Hover, selection and picking"; WP3): the view
 * tracks something that moves, such as a bus (WP8's bus card has Follow).
 *
 * - `start(target)` eases to the target, then keeps it at the centre of the
 *   view after every rendered frame (the render loop runs at least
 *   `FOLLOW_FPS` while following, so a slow bus is still tracked).
 * - Wheel and pinch zoom stay centred on it while following.
 * - Any drag ends it, as do Esc (its place in the Esc order), leaving
 *   Explore, and `stop()`.
 * - ViewHistoryChip shows "Following bus 2213 · Esc" while it runs.
 *
 * Moving the camera is not a data update: no source changes, nothing
 * re-drapes, and no Svelte state is written per frame.
 */
export interface FollowTarget {
	/** What it is ('bus') and its id: `is(kind, id)`. */
	kind: string;
	id: string;
	/** For the banner: "bus 2213". */
	label: string;
	/** Where it is now, or null when it's not known (the view then holds still). */
	position(): [number, number] | null;
}

/** Frames per second the loop is asked for while following. */
export const FOLLOW_FPS = 4;
/** Re-centre once the target is this far (px) from the centre. */
export const FOLLOW_SLACK_PX = 0.5;
export const FOLLOW_EASE_MS = 600;

export interface FollowOptions {
	canFollow?: () => boolean;
	reducedMotion?: () => boolean;
}

export class Follow {
	current = $state.raw<FollowTarget | null>(null);
	#map: Map | null = null;
	#loop: Pick<Loop, 'want'> | null = null;
	#easing = false;
	#zoomAround: { scroll: boolean; touch: boolean } | null = null;
	#o: Required<FollowOptions>;

	constructor(o: FollowOptions = {}) {
		this.#o = {
			canFollow: o.canFollow ?? (() => true),
			reducedMotion: o.reducedMotion ?? (() => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches)
		};
	}

	attach(map: Map, loop: Pick<Loop, 'want'> | null): void {
		if (this.#map === map) return;
		this.detach();
		this.#map = map;
		this.#loop = loop;
	}

	detach(): void {
		this.stop();
		this.#map = null;
		this.#loop = null;
	}

	is(kind: string, id: string): boolean {
		return this.current?.kind === kind && this.current.id === id;
	}

	/** Follow a target (replacing any other). Returns false when it can't start now. */
	start(target: FollowTarget, o: { zoom?: number } = {}): boolean {
		const map = this.#map;
		if (!map || !this.#o.canFollow()) return false;
		if (this.current) this.#unlisten(map);
		this.current = target;
		map.on('render', this.#onRender);
		map.on('dragstart', this.#onDrag);
		this.#centreZoom(map, true);
		this.#loop?.want('follow', FOLLOW_FPS);
		const at = target.position();
		if (at) {
			if (this.#o.reducedMotion()) map.jumpTo({ center: at, ...(o.zoom !== undefined ? { zoom: o.zoom } : {}) });
			else {
				this.#easing = true;
				map.once('moveend', () => (this.#easing = false));
				map.easeTo({ center: at, duration: FOLLOW_EASE_MS, ...(o.zoom !== undefined ? { zoom: o.zoom } : {}) });
			}
		}
		return true;
	}

	/** Stop following (the view stays where it is). */
	stop(): void {
		const map = this.#map;
		if (!this.current) return;
		this.current = null;
		this.#easing = false;
		if (map) this.#unlisten(map);
	}

	#unlisten(map: Map) {
		map.off('render', this.#onRender);
		map.off('dragstart', this.#onDrag);
		this.#centreZoom(map, false);
		this.#loop?.want('follow', null);
	}

	/** Zoom around the centre (the target) while following; put the old behaviour back after. */
	#centreZoom(map: Map, on: boolean) {
		if (on) {
			if (this.#zoomAround) return;
			this.#zoomAround = { scroll: map.scrollZoom.isEnabled(), touch: map.touchZoomRotate.isEnabled() };
			if (this.#zoomAround.scroll) map.scrollZoom.enable({ around: 'center' });
			if (this.#zoomAround.touch) map.touchZoomRotate.enable({ around: 'center' });
		} else if (this.#zoomAround) {
			if (this.#zoomAround.scroll) map.scrollZoom.enable();
			if (this.#zoomAround.touch) map.touchZoomRotate.enable();
			this.#zoomAround = null;
		}
	}

	#onDrag = () => this.stop();

	#onRender = () => {
		const map = this.#map;
		const t = this.current;
		if (!map || !t || this.#easing) return;
		if (!this.#o.canFollow()) return this.stop();
		const at = t.position();
		if (!at) return;
		const p = map.project(at);
		const c = map.project(map.getCenter());
		if (Math.hypot(p.x - c.x, p.y - c.y) > FOLLOW_SLACK_PX) map.jumpTo({ center: at });
	};
}

declare module '#lib/app/context.js' {
	interface AppCtx {
		/** Follow (WP3): the view tracks a moving thing. */
		readonly follow: Follow;
	}
}

declare module '#lib/app/app.svelte.js' {
	interface App {
		readonly follow: Follow;
	}
}

const follows = new WeakMap<object, Follow>();

/** The app's follow, created the first time it's asked for (and then `app.follow`). */
export function followOf(app: AppCtx): Follow {
	let f = follows.get(app);
	if (!f) {
		f = new Follow({ canFollow: () => app.modes.current === 'explore' });
		follows.set(app, f);
		Object.defineProperty(app, 'follow', { value: f, configurable: true, enumerable: false });
	}
	return f;
}
