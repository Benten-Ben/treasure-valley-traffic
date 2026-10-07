/**
 * The ground under 3D objects (docs/14 §14.8, "Drawing").
 *
 * - Poses and heights are true metres, while the map draws terrain
 *   exaggerated: `renderedZ(trueZ, groundTrue) = exag·groundTrue + (trueZ −
 *   groundTrue)`, reading the live exaggeration. With terrain off the map
 *   draws flat ground at 0, which is exaggeration 0.
 * - Things on the ground use `queryTerrainElevation` (the drawn surface).
 *   When DEM tiles refine under a thing that hasn't moved, its height eases
 *   to the new ground over 200 ms instead of jumping.
 */
export const TWEEN_MS = 200;
/** Height changes smaller than this (metres) are applied at once. */
export const SNAP_M = 0.05;

/** Where something `trueZ` metres high (true, absolute) is drawn, over true ground `groundTrue`. */
export function renderedZ(trueZ: number, groundTrue: number, exag: number): number {
	return exag * groundTrue + (trueZ - groundTrue);
}

/** What the scene needs from the map to find the ground. */
export interface GroundSource {
	/** Drawn ground (exaggerated), or null without terrain. */
	queryTerrainElevation(lngLat: [number, number]): number | null;
}

interface Track {
	lng: number;
	lat: number;
	/** True ground being shown (metres). */
	shown: number;
	from: number;
	to: number;
	t0: number;
	/** The frame it was last drawn in. */
	seen: number;
	/** The terrain epoch and exaggeration it was sampled at. */
	epoch: number;
	exag: number;
	/** The terrain-data epoch (DEM tiles arrived or terrain was set) it was last queried in. */
	data: number;
}

/**
 * Per-object true ground, eased over 200 ms when the DEM under a still object
 * changes. `sample` returns the true ground to draw with this frame.
 *
 * The drawn ground only changes when the camera moves, terrain tiles arrive or
 * the exaggeration changes: the scene counts those in an epoch, and an object
 * that hasn't moved within one epoch isn't queried again.
 */
export class GroundTracker {
	#tracks = new Map<string, Track>();
	#frame = 0;
	/** Whether a tween is running (the scene asks the loop for frames while it is). */
	tweening = false;
	/** Terrain queries made this frame (for tests and the ?perf HUD). */
	queries = 0;

	/** Start a frame (objects not drawn for a while are forgotten). */
	begin(): void {
		this.#frame++;
		this.tweening = false;
		this.queries = 0;
		if (this.#frame % 600 === 0) for (const [k, t] of this.#tracks) if (this.#frame - t.seen > 600) this.#tracks.delete(k);
	}

	/**
	 * The true ground last queried under `id` (where it's easing to), if any:
	 * what the scene culls with. Not the eased height, so a model easing up
	 * from off screen isn't culled (and so frozen) halfway. With `data` (≥ 0),
	 * only if it was queried in that terrain-data epoch: a height queried
	 * before the DEM tile under it arrived (MapLibre answers 0 then) isn't
	 * trusted.
	 */
	peek(id: string, data = -1): number | undefined {
		const t = this.#tracks.get(id);
		if (!t || (data >= 0 && t.data !== data)) return undefined;
		return t.to;
	}

	/**
	 * True ground under `id` at (lng, lat): the drawn ground (exaggerated, a
	 * number or a function that queries it) divided by `exag`. A still object
	 * eases to a changed value; one that moved, or wasn't drawn in the last
	 * frame, takes it at once. With the same `epoch` (≥ 0), terrain-data epoch
	 * `data`, exaggeration and position as last time, the ground isn't queried
	 * again.
	 */
	sample(id: string, lng: number, lat: number, drawn: number | (() => number), exag: number, now: number, reducedMotion = false, epoch = -1, data = -1): number {
		const t = this.#tracks.get(id);
		const frame = this.#frame;
		if (t && epoch >= 0 && t.epoch === epoch && t.data === data && t.exag === exag && t.lng === lng && t.lat === lat && frame - t.seen <= 1) {
			t.seen = frame;
			return this.#advance(t, now);
		}
		this.queries++;
		const d = typeof drawn === 'number' ? drawn : drawn();
		const target = exag > 0 ? d / exag : 0;
		if (!t) {
			this.#tracks.set(id, { lng, lat, shown: target, from: target, to: target, t0: now, seen: frame, epoch, exag, data });
			return target;
		}
		const away = frame - t.seen > 1;
		const moved = t.lng !== lng || t.lat !== lat;
		Object.assign(t, { lng, lat, seen: frame, epoch, exag, data });
		if (moved || away || reducedMotion) {
			t.shown = t.from = t.to = target;
			return target;
		}
		if (Math.abs(target - t.to) > SNAP_M) {
			// The DEM under it refined: ease from what's shown now.
			t.from = t.shown;
			t.to = target;
			t.t0 = now;
		} else t.to = target;
		return this.#advance(t, now);
	}

	#advance(t: Track, now: number): number {
		const k = Math.min(1, (now - t.t0) / TWEEN_MS);
		if (k >= 1 || t.from === t.to) t.shown = t.from = t.to;
		else {
			const e = k * k * (3 - 2 * k);
			t.shown = t.from + (t.to - t.from) * e;
			this.tweening = true;
		}
		return t.shown;
	}

	forget(id: string): void {
		this.#tracks.delete(id);
	}

	clear(): void {
		this.#tracks.clear();
	}
}

const R = 6371008.8;

/** The point `metres` along a compass `heading` from (lng, lat). */
export function along(lng: number, lat: number, heading: number, metres: number): [number, number] {
	const h = (heading * Math.PI) / 180;
	const dLat = (metres * Math.cos(h)) / R;
	const dLng = (metres * Math.sin(h)) / (R * Math.cos((lat * Math.PI) / 180));
	return [lng + (dLng * 180) / Math.PI, lat + (dLat * 180) / Math.PI];
}

/**
 * The drawn ground's slope along a heading, sampled `reach` metres ahead and
 * behind (§14.4: models pitch with the slope sampled 6 m ahead and behind).
 * Degrees, nose up; 0 without terrain.
 */
export function slopePitch(src: GroundSource, lng: number, lat: number, heading: number, reach = 6): number {
	const a = src.queryTerrainElevation(along(lng, lat, heading, reach));
	const b = src.queryTerrainElevation(along(lng, lat, heading, -reach));
	if (a === null || b === null) return 0;
	return (Math.atan2(a - b, 2 * reach) * 180) / Math.PI;
}
