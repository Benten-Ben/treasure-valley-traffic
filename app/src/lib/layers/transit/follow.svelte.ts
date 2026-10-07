import type { Map } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import { ESC, onEscape } from '#lib/ui/keys.js';

/**
 * Follow a bus (docs/14 §14.3, "Hover, selection and picking"): the bus
 * card's Follow keeps the bus at the centre of the view; any drag ends it,
 * as does Esc.
 *
 * The follow API is WP3's (`#lib/state/follow.svelte.ts`, with the
 * "Following bus 2213 · Esc" banner), built in the same wave as this
 * package. It's found with a glob, so this works before and after the two
 * are merged: with WP3's module present, its `followOf(app)` is used; until
 * then, the small stand-in below does the same (re-centre after each
 * rendered frame, a drag or Esc stops it).
 */
export interface FollowTarget {
	kind: string;
	id: string;
	label: string;
	position(): [number, number] | null;
}

export interface FollowLike {
	readonly current: FollowTarget | null;
	start(target: FollowTarget, o?: { zoom?: number }): boolean;
	stop(): void;
	is(kind: string, id: string): boolean;
}

type FollowModule = { followOf(app: AppCtx): FollowLike };

const found = import.meta.glob<FollowModule>('../../state/follow.svelte.ts');

/** The stand-in, used only until WP3's follow is merged. */
class StandIn implements FollowLike {
	current = $state.raw<FollowTarget | null>(null);
	#app: AppCtx;
	#map: Map | null = null;
	#unescape: (() => void) | null = null;

	constructor(app: AppCtx) {
		this.#app = app;
	}

	is(kind: string, id: string): boolean {
		return this.current?.kind === kind && this.current.id === id;
	}

	start(target: FollowTarget, o: { zoom?: number } = {}): boolean {
		const map = this.#app.map;
		if (!map || this.#app.modes.current !== 'explore') return false;
		this.stop();
		this.current = target;
		this.#map = map;
		map.on('render', this.#onRender);
		map.on('dragstart', this.#onDrag);
		this.#app.loop.want('follow', 4);
		this.#unescape = onEscape(ESC.follow, () => {
			if (!this.current) return false;
			this.stop();
			return true;
		});
		const at = target.position();
		if (at) map.jumpTo({ center: at, ...(o.zoom !== undefined ? { zoom: o.zoom } : {}) });
		return true;
	}

	stop(): void {
		if (!this.current) return;
		this.current = null;
		this.#map?.off('render', this.#onRender);
		this.#map?.off('dragstart', this.#onDrag);
		this.#app.loop.want('follow', null);
		this.#unescape?.();
		this.#unescape = null;
	}

	#onDrag = () => this.stop();

	#onRender = () => {
		const map = this.#map;
		const t = this.current;
		if (!map || !t) return;
		if (this.#app.modes.current !== 'explore') return this.stop();
		const at = t.position();
		if (!at) return;
		const p = map.project(at);
		const c = map.project(map.getCenter());
		if (Math.hypot(p.x - c.x, p.y - c.y) > 0.5) map.jumpTo({ center: at });
	};
}

const standIns = new WeakMap<object, StandIn>();

/** The app's follow: WP3's when it's there, else the stand-in. */
export async function followFor(app: AppCtx): Promise<FollowLike> {
	const load = Object.values(found)[0];
	if (load) return (await load()).followOf(app);
	let s = standIns.get(app);
	if (!s) standIns.set(app, (s = new StandIn(app)));
	return s;
}
