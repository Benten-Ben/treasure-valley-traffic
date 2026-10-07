import type { Map } from 'maplibre-gl';
import { axes } from '#lib/calibration/solver.js';
import { viewCone, pxPerMetre } from '#lib/calibration/frustum.js';
import type { LngLatAlt, Scene, SceneCone, SceneInstance, SceneLine } from '#lib/scene/index.js';
import { PRIORITY, type Selection } from '../types.js';
import { AMBER, INK, TEAL, type Calibration, type CameraProps } from './cameras.js';

/**
 * 3D cameras (docs/14 §14.6, "What a camera looks like", the Close column;
 * WP13), drawn by the scene engine from z15:
 *
 * - **calibrated:** a pole from the drawn ground up to the solved height, a
 *   camera head turned to its heading, tilt and roll (at least 12 px), the
 *   teal view cone (an apex and 32 rays, 8 per image edge, each ending on the
 *   ground at the calibration's ground height, or 120 m out when it points
 *   above the horizon), and ink frustum edges from the head to the cone's
 *   corners. One camera model: the head's basis, the cone and the footprint
 *   all come from the solver's `axes()`;
 * - **not calibrated:** an amber pin at ACHD's point with its dashed ring of
 *   about 25 m (the location's uncertainty). No pole and no cone: there's no
 *   height or direction to show;
 * - **no image on 511:** nothing in 3D (the small gray dot stays).
 *
 * The 2D icons stay under the 3D models at every zoom (a change from §14.6's
 * table, like WP10's stop capsules): the icon marks the foot of the pole and
 * stays the click target, and for a camera that isn't calibrated its "?" ring
 * is the plate over the pin. The 3D head is pickable too, through the central
 * picker. Models dither in over 14.7–15.
 *
 * Only cameras near the view are handed to the scene (refreshed when the map
 * stops moving), so the scene never walks every cone's 33 points per frame.
 * Nothing here runs per frame: zooming only changes opacities and the pole's
 * width in place.
 */
export const CAMERAS_3D = 'cameras-3d';
/** Models from this zoom (§14.6: "Close (z15 and up)"), dithered in over the 0.3 zoom before it. */
export const MODELS_ZOOM = 15;
export const MODELS_FADE = 0.3;
/** The head is drawn at least this big (§14.6). */
export const HEAD_MIN_PX = 12;
/** Poles are drawn at least this wide, px (a 0.3 m pole is under a pixel until about z18). */
export const POLE_MIN_PX = 3;
export const POLE_RADIUS_M = 0.15;
/** The head's housing reaches this far below its optical centre, m: the pole stops there. */
export const HEAD_DROP_M = 0.15;
/** Cameras further than this many screen diagonals from the centre aren't handed to the scene. */
const NEAR_DIAGONALS = 1.5;
const CONE_OPACITY = 0.16;
const EDGE_OPACITY = 0.7;

const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));

/** The models' share of the dither-in (0 at 14.7, 1 at 15). */
export const modelFade = (zoom: number) => clamp((zoom - (MODELS_ZOOM - MODELS_FADE)) / MODELS_FADE, 0, 1);

/** How much wider than life a pole is drawn at a zoom, so it's POLE_MIN_PX wide. */
export function poleGirth(zoom: number, lat: number): number {
	const px = 2 * POLE_RADIUS_M * pxPerMetre(zoom, lat);
	return Math.max(1, POLE_MIN_PX / px);
}

export interface Cam3D {
	props: CameraProps;
	/** ACHD's point. */
	at: [number, number];
}

export interface Build3D {
	zoom: number;
	lat: number;
	/** The true ground under a point (metres), or null when unknown (then the calibration's ground height is used). */
	ground: (lng: number, lat: number) => number | null;
	/** What a click on a camera selects. */
	selection: (p: CameraProps, at: [number, number]) => Selection;
	/** Cameras left out (the one being looked through). */
	exclude?: ReadonlySet<number>;
	/** Cameras to draw (near the view); all when unset. */
	near?: (lng: number, lat: number) => boolean;
}

export interface Built3D {
	instances: SceneInstance[];
	cones: SceneCone[];
	lines: SceneLine[];
}

/** The scene's instances, cones and frustum edges for these cameras (pure). */
export function build3d(cams: readonly Cam3D[], cals: readonly Calibration[], o: Build3D): Built3D {
	const fade = modelFade(o.zoom);
	const girth = poleGirth(o.zoom, o.lat);
	const byId = new globalThis.Map(cams.map((c) => [c.props.id, c]));
	const instances: SceneInstance[] = [];
	const cones: SceneCone[] = [];
	const lines: SceneLine[] = [];
	const near = o.near ?? (() => true);
	const calibratedCams = new Set<number>();
	for (const cal of cals) {
		const cam = byId.get(cal.cameraId);
		const pose = cal.pose;
		if (!cam || !pose || o.exclude?.has(cal.cameraId) || !near(pose.lon, pose.lat)) continue;
		calibratedCams.add(cal.cameraId);
		const pick = o.selection(cam.props, cam.at);
		const ground = o.ground(pose.lon, pose.lat) ?? cal.groundZ;
		const height = Math.max(0.5, pose.alt - ground - HEAD_DROP_M);
		instances.push({
			id: `pole-${cal.calibrationId}`,
			mesh: 'pole',
			lng: pose.lon,
			lat: pose.lat,
			groundAlt: ground,
			scale: [girth, girth, height],
			opacity: fade,
			pick
		});
		const [right, down, fwd] = axes(pose.heading, pose.tilt, pose.roll);
		instances.push({
			id: `head-${cal.calibrationId}`,
			mesh: 'head',
			lng: pose.lon,
			lat: pose.lat,
			alt: pose.alt,
			groundAlt: ground,
			basis: [right, down, fwd],
			minPx: HEAD_MIN_PX,
			opacity: fade,
			pick,
			radius: 10
		});
		const cone = viewCone(pose, cal.size, cal.groundZ);
		const apex: LngLatAlt = cone.apex;
		cones.push({ id: `cone-${cal.calibrationId}`, apex, ends: cone.ends, groundAlt: cal.groundZ, color: TEAL, opacity: CONE_OPACITY * fade });
		cone.corners.forEach((corner, k) => {
			lines.push({ id: `edge-${cal.calibrationId}-${k}`, points: [apex, corner], groundAlt: cal.groundZ, color: INK, width: 1.25, opacity: EDGE_OPACITY * fade });
		});
	}
	for (const cam of cams) {
		const p = cam.props;
		if (p.status !== 'uncalibrated' || calibratedCams.has(p.id) || o.exclude?.has(p.id) || !near(cam.at[0], cam.at[1])) continue;
		instances.push({
			id: `pin-${p.id}`,
			mesh: 'pin',
			lng: cam.at[0],
			lat: cam.at[1],
			color: AMBER,
			opacity: fade,
			pick: o.selection(p, cam.at),
			radius: 10
		});
	}
	return { instances, cones, lines };
}

/** Where a calibrated camera's head is, and how high above the true ground (for the window badge in 3D). */
export interface HeadAt {
	lng: number;
	lat: number;
	/** Metres above the ground under it. */
	above: number;
}

export interface Cameras3DOptions {
	selection: (p: CameraProps, at: [number, number]) => Selection;
	/** The live terrain exaggeration (app.exaggeration()). */
	exaggeration: () => number;
}

/**
 * The 3D cameras in the scene: one group, `cameras-3d`, shown from z15 while
 * the Cameras layer is on. Rebuilt when the data changes or the map stops
 * moving; zooming only updates opacities and pole widths in place.
 */
export class Cameras3D {
	#scene: Scene;
	#map: Map;
	#o: Cameras3DOptions;
	#cams: Cam3D[] = [];
	#cals: Calibration[] = [];
	#visible = false;
	#exclude = new Set<number>();
	#built: Built3D = { instances: [], cones: [], lines: [] };
	#shown = false;
	#cleanup: (() => void)[] = [];

	constructor(scene: Scene, map: Map, o: Cameras3DOptions) {
		this.#scene = scene;
		this.#map = map;
		this.#o = o;
		scene.set(CAMERAS_3D, [], { priority: PRIORITY.camera });
		scene.show(CAMERAS_3D, false);
		const onZoom = () => this.#onZoom();
		const onEnd = () => this.rebuild();
		map.on('zoom', onZoom);
		map.on('moveend', onEnd);
		map.on('terrain', onEnd);
		this.#cleanup.push(() => {
			map.off('zoom', onZoom);
			map.off('moveend', onEnd);
			map.off('terrain', onEnd);
		});
	}

	setData(cams: readonly Cam3D[], cals: readonly Calibration[]): void {
		this.#cams = [...cams];
		this.#cals = [...cals];
		this.rebuild();
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		this.#onZoom();
		if (on) this.rebuild();
	}

	/** Leave cameras out (the one being looked through: its own model and cone are hidden). */
	setExcluded(ids: readonly number[]): void {
		this.#exclude = new Set(ids);
		this.rebuild();
	}

	/** The true ground under a point: the drawn ground over the exaggeration, or null without terrain data. */
	#ground = (lng: number, lat: number): number | null => {
		const map = this.#map;
		if (!map.getTerrain()) return null;
		const z = map.queryTerrainElevation([lng, lat]);
		const exag = this.#o.exaggeration();
		return z === null || !(exag > 0) ? null : z / exag;
	};

	/** Cameras within NEAR_DIAGONALS screen diagonals of the centre. */
	#near(): (lng: number, lat: number) => boolean {
		const map = this.#map;
		const c = map.getCenter();
		const canvas = map.getCanvas();
		const mpp = 1 / pxPerMetre(map.getZoom(), c.lat);
		// A tilted view reaches further toward its horizon.
		const reach = 1 + Math.tan((Math.min(map.getPitch(), 80) * Math.PI) / 180);
		const radius = NEAR_DIAGONALS * Math.hypot(canvas.clientWidth, canvas.clientHeight) * mpp * reach;
		const kx = 111_320 * Math.cos((c.lat * Math.PI) / 180);
		return (lng, lat) => Math.hypot((lng - c.lng) * kx, (lat - c.lat) * 111_320) <= radius;
	}

	/** Build the group again (the data, the view or the terrain changed). */
	rebuild(): void {
		const map = this.#map;
		if (!this.#visible || map.getZoom() < MODELS_ZOOM - MODELS_FADE) {
			if (this.#built.instances.length || this.#built.cones.length) {
				this.#built = { instances: [], cones: [], lines: [] };
				this.#push();
			}
			return;
		}
		this.#built = build3d(this.#cams, this.#cals, {
			zoom: map.getZoom(),
			lat: map.getCenter().lat,
			ground: this.#ground,
			selection: this.#o.selection,
			exclude: this.#exclude,
			near: this.#near()
		});
		this.#push();
	}

	#push() {
		const s = this.#scene;
		s.set(CAMERAS_3D, this.#built.instances, { priority: PRIORITY.camera });
		s.setCones(CAMERAS_3D, this.#built.cones);
		s.setLines(CAMERAS_3D, this.#built.lines);
	}

	/** Zooming: show or hide the group, and dither and widen in place (no rebuild). */
	#onZoom() {
		const map = this.#map;
		const zoom = map.getZoom();
		const want = this.#visible && zoom >= MODELS_ZOOM - MODELS_FADE;
		if (want !== this.#shown) {
			this.#shown = want;
			this.#scene.show(CAMERAS_3D, want);
			if (want && !this.#built.instances.length) this.rebuild();
		}
		if (!want) return;
		const fade = modelFade(zoom);
		const girth = poleGirth(zoom, map.getCenter().lat);
		for (const i of this.#built.instances) {
			i.opacity = fade;
			if (i.mesh === 'pole' && Array.isArray(i.scale)) {
				i.scale[0] = girth;
				i.scale[1] = girth;
			}
		}
		for (const c of this.#built.cones) c.opacity = CONE_OPACITY * fade;
		for (const l of this.#built.lines) l.opacity = EDGE_OPACITY * fade;
	}

	/** Whether models are drawn now (the Cameras layer is on and the map is at z15 or closer). */
	get drawn(): boolean {
		return this.#shown && this.#map.getZoom() >= MODELS_ZOOM;
	}

	/** Each calibrated camera's head (the first calibrated view's), for the window badges in 3D. */
	heads(): globalThis.Map<number, HeadAt> {
		const out = new globalThis.Map<number, HeadAt>();
		for (const c of this.#cals) {
			if (out.has(c.cameraId) || !c.pose) continue;
			const ground = this.#ground(c.pose.lon, c.pose.lat) ?? c.groundZ;
			out.set(c.cameraId, { lng: c.pose.lon, lat: c.pose.lat, above: c.pose.alt - ground });
		}
		return out;
	}

	/** For tests and the console: what the group holds. */
	info(): { shown: boolean; instances: { id: string; mesh: string }[]; cones: number; lines: number } {
		return {
			shown: this.#shown,
			instances: this.#built.instances.map((i) => ({ id: i.id, mesh: i.mesh ?? 'bus' })),
			cones: this.#built.cones.length,
			lines: this.#built.lines.length
		};
	}

	destroy(): void {
		for (const f of this.#cleanup.splice(0)) f();
		this.#scene.remove(CAMERAS_3D);
	}
}
