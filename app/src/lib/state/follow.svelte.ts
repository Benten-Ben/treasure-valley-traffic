import type { Map } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import type { Loop } from '#lib/map/loop.js';

/**
 * Follow (docs/14 §14.3, "Hover, selection and picking"; WP3): the view
 * tracks something that moves, such as a bus (WP8's bus card has Follow).
 *
 * - `start(target)` eases to the target, then keeps it at the centre of the
 *   view after every rendered frame (the render loop runs at least
 *   `FOLLOW_FPS` while following, so a slow bus is still tracked). Started
 *   with an `offset` (the bus card's Follow, while the inspect card is open:
 *   §14.3 "Regions"), it keeps the target that far from the centre instead,
 *   in the area the card leaves, for as long as it follows.
 * - Wheel and pinch zoom keep the view's centre still while following: the
 *   target, unless it's kept off centre (then the next frame puts it back).
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
	/** Where the target is kept, from the map's padded centre (px). */
	#offset: [number, number] = [0, 0];
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

	/**
	 * Follow a target (replacing any other), kept `offset` px from the middle
	 * of the map's padding. Returns false when it can't start now.
	 */
	start(target: FollowTarget, o: { zoom?: number; offset?: [number, number] | null } = {}): boolean {
		const map = this.#map;
		if (!map || !this.#o.canFollow()) return false;
		if (this.current) this.#unlisten(map);
		this.current = target;
		this.#offset = o.offset ? [o.offset[0], o.offset[1]] : [0, 0];
		map.on('render', this.#onRender);
		map.on('dragstart', this.#onDrag);
		this.#centreZoom(map, true);
		this.#loop?.want('follow', FOLLOW_FPS);
		const at = target.position();
		if (at) {
			const zoom = o.zoom !== undefined ? { zoom: o.zoom } : {};
			if (this.#o.reducedMotion()) this.#place(map, at, zoom);
			else {
				this.#easing = true;
				map.once('moveend', () => (this.#easing = false));
				map.easeTo({ center: at, duration: FOLLOW_EASE_MS, ...zoom, ...this.#offsetOption() });
			}
		}
		return true;
	}

	#offsetOption(): { offset?: [number, number] } {
		return this.#offset[0] || this.#offset[1] ? { offset: this.#offset } : {};
	}

	/** Put the target where it's kept, at once (a jump; an instant ease when it's kept off centre, since a jump takes no offset). */
	#place(map: Map, at: [number, number], o: { zoom?: number } = {}) {
		const off = this.#offsetOption();
		if (off.offset) map.easeTo({ center: at, ...o, ...off, animate: false });
		else map.jumpTo({ center: at, ...o });
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
		const [dx, dy] = this.#offset;
		if (Math.hypot(p.x - c.x - dx, p.y - c.y - dy) > FOLLOW_SLACK_PX) this.#place(map, at);
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
