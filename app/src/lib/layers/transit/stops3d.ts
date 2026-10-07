import type { LngLatBounds } from 'maplibre-gl';
import type { NetworkRoute, NetworkStop } from '#lib/contracts/network.js';
import type { SlottedLayer } from '#lib/map/order.js';
import type { SceneInstance } from '#lib/scene/index.js';
import type { Selection } from '../types.js';
import { metresPerPx } from './bus3d.js';
import { CREAM, INK } from './network.js';

/**
 * 3D stops (docs/14 §14.4 "Buses and stops"; WP10):
 *
 * | Zoom | A stop is |
 * |---|---|
 * | below 14 | hidden |
 * | 14 and up | a cream capsule across the bundle, turned to the street (WP8's symbol layer) |
 * | 16 and up | plus a 3D sign post with a small flag per route, in the scene layer; its name from 17 |
 *
 * - **The capsule stays under the post**, a change from §14.4's table, where
 *   the post replaces it at z16: seen from above a post is a dot, and even in
 *   a tilted view the mesh's pole, cream sign and flags are only a few pixels
 *   across until about z19. The capsule keeps every stop findable and
 *   clickable at any pitch; the post adds the 3D sign in tilted views.
 * - The post dithers in over 15.7–16.
 * - Flags: up to four, running routes first, in route color; a route not
 *   running has its ghost color (the capsule's 45% idea, told by color
 *   rather than a speckled dither).
 * - A post is drawn bigger than life, about 26 px tall (at most 6× real
 *   size) until its true size is that tall: a 2.9 m post is only 3 px tall
 *   at z16.
 * - Only stops near the view are handed to the scene (refreshed as the map
 *   moves), so the scene's frame never walks all 562.
 * - If the scene can't start, none of this happens: the capsules alone mark
 *   the stops, as before.
 */

export const POST_ZOOM = 16;
export const POST_FADE = 0.3;
export const NAME_ZOOM = 17;
/** Drawn about this tall (px) until true size is taller, at most POST_MAX_SCALE × real size. */
export const POST_PX = 26;
export const POST_HEIGHT_M = 2.9;
export const POST_MAX_SCALE = 6;
/** Flag slots on the post mesh. */
export const FLAG_SLOTS = 4;
export const STOP_NAMES = 'transit-stop-names';

const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));

/** The post's share of the crossfade (0 at 15.7, 1 at 16). */
export const postFade = (zoom: number) => clamp((zoom - (POST_ZOOM - POST_FADE)) / POST_FADE, 0, 1);

/** The post's scale at a zoom: about POST_PX tall, never below real size or above POST_MAX_SCALE. */
export function postScale(zoom: number, lat: number): number {
	const px = POST_HEIGHT_M / metresPerPx(zoom, lat);
	return clamp(POST_PX / px, 1, POST_MAX_SCALE);
}

/** A stop's flags: up to four routes, running ones first (route color), then the rest (ghost color). */
export function flagColors(routes: readonly string[], running: ReadonlySet<string>, byId: ReadonlyMap<string, NetworkRoute>): (string | null)[] {
	const known = routes.map((id) => byId.get(id)).filter((r): r is NetworkRoute => Boolean(r));
	const order = [...known.filter((r) => running.has(r.id)), ...known.filter((r) => !running.has(r.id))];
	const out: (string | null)[] = [];
	for (let k = 0; k < FLAG_SLOTS; k++) {
		const r = order[k];
		out.push(r ? (running.has(r.id) ? r.color : r.ghost) : null);
	}
	return out;
}

/** Stop names from z17, beside the post's foot (a 2D label, above the base labels). */
export function stopNameLayer(source: string): SlottedLayer {
	return {
		slot: 'labels',
		layer: {
			id: STOP_NAMES,
			type: 'symbol',
			source,
			minzoom: NAME_ZOOM,
			layout: {
				visibility: 'none',
				'text-field': ['get', 'name'],
				'text-font': ['Noto Sans Medium'],
				'text-size': 12,
				'text-anchor': 'top',
				'text-offset': [0, 0.7],
				'text-max-width': 9,
				'text-optional': true,
				'symbol-sort-key': 1
			},
			paint: { 'text-color': INK, 'text-halo-color': CREAM, 'text-halo-width': 1.5 }
		}
	};
}

/** The stop posts: one scene instance per stop, handed to the scene only near the view. */
export class StopPosts {
	/** Every stop's post (index = network order). */
	readonly all: SceneInstance[] = [];
	/** The ones near the view (the scene's group array, mutated in place). */
	readonly near: SceneInstance[] = [];
	#stops: readonly NetworkStop[] = [];
	#scale = 1;
	#opacity = 0;

	/** Build the posts for a network (`pick(i)`: what a click on stop i selects). */
	build(stops: readonly NetworkStop[], pick: (i: number) => Selection | null): void {
		this.#stops = stops;
		this.all.length = 0;
		stops.forEach((s, i) => {
			this.all.push({
				id: `stop:${s.id}`,
				mesh: 'stop',
				lng: s.lon,
				lat: s.lat,
				heading: s.bearing ?? 0,
				scale: this.#scale,
				opacity: this.#opacity,
				slots: [null, null, null, null],
				pick: pick(i)
			});
		});
	}

	/** Recolor the flags for the routes running now (in place). */
	setRunning(running: ReadonlySet<string>, byId: ReadonlyMap<string, NetworkRoute>): void {
		this.#stops.forEach((s, i) => {
			const inst = this.all[i];
			if (inst) inst.slots = flagColors(s.routes, running, byId);
		});
	}

	/** Size and fade for a zoom (in place); returns whether any post shows. */
	setZoom(zoom: number, lat: number): boolean {
		this.#scale = postScale(zoom, lat);
		this.#opacity = postFade(zoom);
		for (const p of this.near) {
			p.scale = this.#scale;
			p.opacity = this.#opacity;
		}
		return this.#opacity > 0;
	}

	/**
	 * Hand the scene the posts inside `bounds` grown by a quarter of its size
	 * each way and, with `centre`, within `radius` metres of it: in a tilted
	 * view the bounds reach the horizon, where posts are too small to see.
	 */
	setNear(bounds: Pick<LngLatBounds, 'getWest' | 'getEast' | 'getSouth' | 'getNorth'>, centre?: [number, number], radius = Infinity): void {
		const [w, e, s, n] = [bounds.getWest(), bounds.getEast(), bounds.getSouth(), bounds.getNorth()];
		const dx = (e - w) / 4;
		const dy = (n - s) / 4;
		const kx = centre ? 111_320 * Math.cos((centre[1] * Math.PI) / 180) : 0;
		this.near.length = 0;
		for (const p of this.all) {
			if (p.lng < w - dx || p.lng > e + dx || p.lat < s - dy || p.lat > n + dy) continue;
			if (centre && Math.hypot((p.lng - centre[0]) * kx, (p.lat - centre[1]) * 110_574) > radius) continue;
			p.scale = this.#scale;
			p.opacity = this.#opacity;
			this.near.push(p);
		}
	}
}
