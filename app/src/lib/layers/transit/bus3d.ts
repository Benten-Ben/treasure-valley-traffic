import type { SceneInstance } from '#lib/scene/index.js';
import { circumferenceAt } from '#lib/overlay/project.js';
import type { Selection } from '../types.js';
import { UNKNOWN_COLOR } from './transit.js';

/**
 * 3D buses (docs/14 §14.4 "Buses and stops"; WP10). Scale sets the look:
 *
 * | Zoom (43.6° N) | A bus is | Drawn as |
 * |---|---|---|
 * | below about 15 | 3.5–7 px long | a disc with its number, in the overlay |
 * | about 15–17 | 28 px long, at up to 4× real size | a model in the scene layer, with a number plate above it |
 * | about 17 and up | true scale | the model and its plate |
 *
 * A model appears once it can be at least 28 px long at up to 4× real size,
 * and the disc and the model crossfade over 0.3 zoom (the model dithers in,
 * the disc fades out). The plate rides above the model in the overlay at
 * every zoom from there.
 *
 * - Models are the route color on a flat, high-ambient light; a stale bus
 *   takes the route's ghost body (and a hollow plate); an unknown-route bus
 *   is `#8a857c` (with "?"). While another route is spotlit, a bus takes its
 *   ghost body too (form, not opacity: a dithered model would speckle).
 * - The heading follows the path: the playback's path tangent (±8 m), with
 *   a shorter low-pass than the 2D arrow so a turning model stays within a
 *   few degrees of its path.
 * - Models sit on the drawn terrain (the scene's ground) and pitch with its
 *   slope sampled ahead and behind: 6 m at true scale, 6 m × the model's
 *   scale when it's drawn larger, so an oversized model's ends follow the
 *   ground too. The slope is read again only when the bus has moved 2 m or
 *   turned 3°, or the terrain changed (two terrain reads each time).
 * - This module is pure apart from the slope's terrain reads: the Transit
 *   module calls it once per rendered frame, from the scene's update.
 */

/** The bus mesh's size (metres; `BUS` in #lib/scene/meshes, which this chunk doesn't load). */
export const BUS_LENGTH_M = 12.2;
export const BUS_HEIGHT_M = 3.1;
/** A model is drawn at least this long (px), at up to MAX_MODEL_SCALE × real size. */
export const MIN_MODEL_PX = 28;
export const MAX_MODEL_SCALE = 4;
/** Sized 1% over the minimum, so float32 and the latitude across the screen never take a model under it. */
export const LENGTH_MARGIN = 1.01;
/** The disc-to-model crossfade, in zoom levels. */
export const FADE_ZOOMS = 0.3;
/** The model's heading low-pass (ms); the 2D arrow's is 300 ms. */
export const MODEL_TAU_MS = 120;
/** Slope reach at true scale (m) and the steepest pitch drawn (degrees). */
export const SLOPE_REACH_M = 6;
export const MAX_PITCH_DEG = 15;
/** Re-read the slope after the bus moves this far (m) or turns this much (degrees): two terrain reads each time. */
export const SLOPE_MOVE_M = 2;
export const SLOPE_TURN_DEG = 3;
/** The plate floats this far above the roof (m). */
export const PLATE_GAP_M = 0.8;
/** The scene's selection lift (m) and scale (§14.3); the plate follows them. */
export const SELECT_LIFT_M = 2;
export const SELECT_SCALE = 1.2;

/** The unknown-route bus body when stale. */
export const UNKNOWN_GHOST = '#cbc7bf';

const DEG = Math.PI / 180;
const R = 6371008.8;
const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));

/** Ground metres per CSS pixel (512 px tiles). */
export const metresPerPx = (zoom: number, lat: number) => circumferenceAt(lat) / (512 * 2 ** zoom);

/** The zoom at which a model 4× real size is MIN_MODEL_PX long (with the margin): about 15 at 43.6° N. */
export const modelZoom = (lat: number) => Math.log2((MIN_MODEL_PX * LENGTH_MARGIN * circumferenceAt(lat)) / (512 * BUS_LENGTH_M * MAX_MODEL_SCALE));

/** The model's scale: MIN_MODEL_PX long (with the margin), at most MAX_MODEL_SCALE × real size, true size once that's long enough. */
export function modelScale(zoom: number, lat: number): number {
	const px = BUS_LENGTH_M / metresPerPx(zoom, lat);
	return clamp((MIN_MODEL_PX * LENGTH_MARGIN) / px, 1, MAX_MODEL_SCALE);
}

/** The model's share of the crossfade: 0 below modelZoom, 1 from FADE_ZOOMS above it. */
export function modelFade(zoom: number, lat: number): number {
	return clamp((zoom - modelZoom(lat)) / FADE_ZOOMS, 0, 1);
}

/** What one frame shows, for every bus (computed once per frame). */
export interface Lod {
	zoom: number;
	/** 0: discs only; 1: models only (with plates). */
	fade: number;
	/** The disc layer's share (1 − fade). */
	disc: number;
	scale: number;
	/** The plate's height above the drawn ground (m), before any selection lift. */
	plateAlt: number;
	/** Extra screen clearance (px) so the plate clears the model's footprint seen from above. */
	clearance: number;
}

/**
 * The frame's level of detail. `models` says whether models can be drawn
 * (the scene is running); without them, buses stay discs at every zoom.
 */
export function lodAt(zoom: number, lat: number, pitchDeg: number, models: boolean): Lod {
	const fade = models ? modelFade(zoom, lat) : 0;
	const scale = modelScale(zoom, lat);
	const halfPx = (BUS_LENGTH_M * scale) / 2 / metresPerPx(zoom, lat);
	return {
		zoom,
		fade,
		disc: 1 - fade,
		scale,
		plateAlt: BUS_HEIGHT_M * scale + PLATE_GAP_M,
		clearance: Math.min(30, halfPx * Math.cos(pitchDeg * DEG))
	};
}

/** The plate's height for one bus: above its roof, lifted with the model when it's selected. */
export function plateAltitude(lod: Lod, selected: boolean): number {
	return selected ? lod.plateAlt + SELECT_LIFT_M + BUS_HEIGHT_M * lod.scale * (SELECT_SCALE - 1) : lod.plateAlt;
}

/** A ghost of a color for a bus whose route isn't in the network: 60% of the way to the clay surface. */
export function ghostOf(hex: string): string {
	const n = parseInt(hex.replace('#', ''), 16);
	const s = [0xf3, 0xed, 0xe2];
	const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v, i) => Math.round(v + (s[i] - v) * 0.6));
	return `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

/** A bus's body color: the route color; its ghost when stale or while another route is spotlit; gray for unknown routes. */
export function bodyColor(o: { routeId: string | null; color: string | null; ghost: string | null; stale: boolean; dimmed: boolean }): string {
	if (!o.routeId) return o.stale || o.dimmed ? UNKNOWN_GHOST : UNKNOWN_COLOR;
	const color = o.color ?? UNKNOWN_COLOR;
	return o.stale || o.dimmed ? (o.ghost ?? ghostOf(color)) : color;
}

/** The point `metres` along a compass `heading` from (lng, lat). */
export function along(lng: number, lat: number, heading: number, metres: number): [number, number] {
	const h = heading * DEG;
	const dLat = (metres * Math.cos(h)) / R;
	const dLng = (metres * Math.sin(h)) / (R * Math.cos(lat * DEG));
	return [lng + dLng / DEG, lat + dLat / DEG];
}

/** The drawn ground at a point (MapLibre's `queryTerrainElevation`), or null without terrain. */
export type GroundAt = (p: [number, number]) => number | null;

/**
 * The drawn ground's slope along a heading, sampled `reach` metres ahead and
 * behind: degrees, nose up, at most ±MAX_PITCH_DEG; 0 without terrain.
 */
export function slopeAt(ground: GroundAt, lng: number, lat: number, heading: number, reach = SLOPE_REACH_M): number {
	const a = ground(along(lng, lat, heading, reach));
	const b = ground(along(lng, lat, heading, -reach));
	if (a === null || b === null) return 0;
	return clamp(Math.atan2(a - b, 2 * reach) / DEG, -MAX_PITCH_DEG, MAX_PITCH_DEG);
}

/** Turn `from` toward `to` (degrees) with a low-pass of `tauMs` over `dtMs`. */
export function turn(from: number | null, to: number | null, dtMs: number, tauMs = MODEL_TAU_MS): number | null {
	if (to === null) return from;
	if (from === null || !(dtMs > 0) || dtMs > 2000) return to;
	const diff = ((((to - from) % 360) + 540) % 360) - 180;
	return (from + diff * (1 - Math.exp(-dtMs / tauMs)) + 360) % 360;
}

/** One bus's model and what it remembers between frames. */
export interface BusModel {
	inst: SceneInstance;
	/** The model's heading (degrees), low-passed; null until the bus has one. */
	heading: number | null;
	turnedAt: number;
	/** Where the slope was last read, and what it was. */
	slope: { lng: number; lat: number; heading: number; reach: number; epoch: number; pitch: number } | null;
}

export function busModel(vid: string, pick: Selection | null, old?: BusModel): BusModel {
	const inst: SceneInstance = old?.inst ?? { id: vid, mesh: 'bus', lng: 0, lat: 0, heading: 0, pitch: 0, scale: 1, color: UNKNOWN_COLOR, opacity: 0, shadow: true };
	inst.pick = pick;
	return { inst, heading: old?.heading ?? null, turnedAt: old?.turnedAt ?? 0, slope: old?.slope ?? null };
}

/** What a frame says about one bus. */
export interface ModelFrame {
	lng: number;
	lat: number;
	/** The path heading to turn toward (degrees), or null to keep the model's. */
	heading: number | null;
	color: string;
	/** 0–1: the crossfade times the playback's own (a gap's fade-jump); 0 hides it. */
	opacity: number;
	scale: number;
	/** performance.now() (ms). */
	now: number;
	/** Terrain epoch: bumped when terrain data or settings change (re-read the slope). */
	epoch: number;
	ground: GroundAt | null;
}

/** Move one model to this frame (in place): position, heading, slope, look. */
export function placeModel(m: BusModel, f: ModelFrame): SceneInstance {
	const inst = m.inst;
	m.heading = turn(m.heading, f.heading, f.now - m.turnedAt);
	m.turnedAt = f.now;
	inst.lng = f.lng;
	inst.lat = f.lat;
	inst.heading = m.heading ?? 0;
	inst.scale = f.scale;
	inst.color = f.color;
	inst.opacity = f.opacity;
	if (f.opacity > 0) {
		const reach = SLOPE_REACH_M * f.scale;
		const h = inst.heading;
		const s = m.slope;
		const fresh =
			s &&
			s.epoch === f.epoch &&
			Math.abs(s.reach - reach) < 0.1 * reach &&
			Math.abs(((((h - s.heading) % 360) + 540) % 360) - 180) < SLOPE_TURN_DEG &&
			Math.abs(s.lat - f.lat) * 111_000 < SLOPE_MOVE_M &&
			Math.abs(s.lng - f.lng) * 111_000 * Math.cos(f.lat * DEG) < SLOPE_MOVE_M;
		if (!fresh) m.slope = { lng: f.lng, lat: f.lat, heading: h, reach, epoch: f.epoch, pitch: f.ground ? slopeAt(f.ground, f.lng, f.lat, h, reach) : 0 };
		inst.pitch = m.slope!.pitch;
	}
	return inst;
}
