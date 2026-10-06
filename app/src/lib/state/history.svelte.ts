import type { FlyToOptions, Map } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import type { CameraView } from './view.svelte.js';

/**
 * The view history (docs/14 §14.3, "Hover, selection and picking"; WP3).
 *
 * - Every programmatic fly pushes the view it left (10 deep). The history
 *   wraps the map's own `flyTo`, so a fly from anywhere counts: the H and O
 *   keys, the camera widget, a camera click (WP12), `fitBounds`. A fly that
 *   interrupts another one doesn't push the half-way view, and nothing is
 *   pushed outside Explore (modes save and restore their own snapshot).
 *   `fly()` does the same under reduced motion, where it jumps instead.
 * - After each push a "↩ Back to previous view" chip shows for 8 s
 *   (ViewHistoryChip); Backspace or the chip pops the stack and flies back.
 * - User gestures (drag, wheel, keys that ease) never push.
 */
export const HISTORY_DEPTH = 10;
export const CHIP_MS = 8000;

const EPS_DEG = 1e-7;

export function sameView(a: CameraView, b: CameraView): boolean {
	return (
		Math.abs(a.center[0] - b.center[0]) < EPS_DEG &&
		Math.abs(a.center[1] - b.center[1]) < EPS_DEG &&
		Math.abs(a.zoom - b.zoom) < 1e-4 &&
		Math.abs(((((a.bearing - b.bearing) % 360) + 540) % 360) - 180) < 1e-3 &&
		Math.abs(a.pitch - b.pitch) < 1e-3
	);
}

/** Push onto a bounded stack, unless it equals the top. */
export function pushView(stack: readonly CameraView[], v: CameraView, depth = HISTORY_DEPTH): CameraView[] | null {
	const top = stack.at(-1);
	if (top && sameView(top, v)) return null;
	return [...stack, v].slice(-depth);
}

export interface HistoryOptions {
	/** Whether a fly may push now (the map is in Explore). */
	canPush?: () => boolean;
	reducedMotion?: () => boolean;
	now?: () => number;
}

type Flight = 'none' | 'fly' | 'back';

export class ViewHistory {
	/** Views to go back to, oldest first ($state.raw). */
	stack = $state.raw<CameraView[]>([]);
	/** The chip shows until this time (epoch ms). */
	chipUntil = $state(0);

	#map: Map | null = null;
	#flight: Flight = 'none';
	/** The next flyTo is our own way back. */
	#backing = false;
	#o: Required<HistoryOptions>;

	constructor(o: HistoryOptions = {}) {
		this.#o = {
			canPush: o.canPush ?? (() => true),
			reducedMotion: o.reducedMotion ?? (() => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches),
			now: o.now ?? (() => Date.now())
		};
	}

	get attached(): boolean {
		return this.#map !== null;
	}

	/** Start hearing the map's flies (wraps its flyTo). */
	attach(map: Map): void {
		if (this.#map === map) return;
		this.detach();
		this.#map = map;
		const orig = map.flyTo;
		// eslint-disable-next-line @typescript-eslint/no-this-alias
		const self = this;
		const wrapped = function (this: Map, options: FlyToOptions, eventData?: unknown) {
			const back = self.#backing;
			self.#backing = false;
			if (!back) self.#beforeFly(map);
			// Stopping an earlier flight here fires its moveend (which ends that flight).
			const out = orig.call(this, options, eventData);
			self.#flight = map.isMoving() ? (back ? 'back' : 'fly') : 'none';
			return out;
		} as Map['flyTo'];
		map.flyTo = wrapped;
		map.on('moveend', this.#onMoveEnd);
		this.#undo = () => {
			if (map.flyTo === wrapped) Reflect.deleteProperty(map, 'flyTo');
			if (map.flyTo !== orig) map.flyTo = orig;
			map.off('moveend', this.#onMoveEnd);
		};
	}

	#undo: (() => void) | null = null;

	detach(): void {
		this.#undo?.();
		this.#undo = null;
		this.#map = null;
		this.#flight = 'none';
	}

	#current(): CameraView | null {
		const m = this.#map;
		if (!m) return null;
		const c = m.getCenter();
		return { center: [c.lng, c.lat], zoom: m.getZoom(), bearing: m.getBearing(), pitch: m.getPitch() };
	}

	/** Push a view (default: the map's current one) and show the chip. Returns whether it was added. */
	push(view: CameraView | null = this.#current()): boolean {
		if (!view) return false;
		this.chipUntil = this.#o.now() + CHIP_MS;
		const next = pushView(this.stack, view);
		if (!next) return false;
		this.stack = next;
		return true;
	}

	#beforeFly(map: Map) {
		if (!this.#o.canPush()) return;
		// Part of a flight already under way (ours or another fly's): keep the view it started from.
		if (this.#flight !== 'none' && map.isMoving()) return;
		this.push();
	}

	#onMoveEnd = () => {
		this.#flight = 'none';
	};

	/** Fly somewhere, pushing the view it leaves (a jump under reduced motion, still pushed). */
	fly(options: FlyToOptions): void {
		const map = this.#map;
		if (!map) return;
		if (this.#o.reducedMotion()) {
			if (this.#o.canPush()) this.push();
			map.jumpTo(options);
		} else map.flyTo(options);
	}

	/** Go back to the previous view; false when there's none. */
	back(): boolean {
		const map = this.#map;
		const prev = this.stack.at(-1);
		if (!map || !prev) return false;
		this.stack = this.stack.slice(0, -1);
		this.chipUntil = 0;
		const to = { center: prev.center, zoom: prev.zoom, bearing: prev.bearing, pitch: prev.pitch };
		if (this.#o.reducedMotion()) map.jumpTo(to);
		else {
			this.#backing = true;
			map.flyTo(to);
			this.#backing = false;
		}
		return true;
	}

	/** Hide the chip (the stack stays). */
	dismissChip(): void {
		this.chipUntil = 0;
	}

	clear(): void {
		this.stack = [];
		this.chipUntil = 0;
	}
}

declare module '#lib/app/context.js' {
	interface AppCtx {
		/** The view history (WP3): Backspace and the "Back to previous view" chip. */
		readonly history: ViewHistory;
	}
}

declare module '#lib/app/app.svelte.js' {
	interface App {
		readonly history: ViewHistory;
	}
}

const histories = new WeakMap<object, ViewHistory>();

/** The app's view history, created the first time it's asked for (and then `app.history`). */
export function historyOf(app: AppCtx): ViewHistory {
	let h = histories.get(app);
	if (!h) {
		h = new ViewHistory({ canPush: () => app.modes.current === 'explore' });
		histories.set(app, h);
		Object.defineProperty(app, 'history', { value: h, configurable: true, enumerable: false });
	}
	return h;
}
