import type { FeatureCollection } from 'geojson';
import type { SlottedLayer } from '#lib/map/order.js';
import type { ImageSize, Pose } from '#lib/calibration/solver.js';

/**
 * The Cameras layer's pure parts (docs/14 §14.6, "What a camera looks like";
 * ported from the Cameras lens by WP2, icons and footprints by WP12). Camera
 * icons are told apart by shape as well as color (never color alone):
 *
 * - **calibrated:** a teal disc with a white ring and a check (an image:
 *   the basemap's glyphs have no ✓); from z14 its
 *   view footprint is draped on the ground in teal (fill 0.10, line 0.8;
 *   0.22 and 1.0 on hover);
 * - **not calibrated:** a hollow amber ring with "?";
 * - **no image on 511:** a small gray dot;
 * - **recorded** (the key cameras the capture services keep): a small ink
 *   notch on top of the icon;
 * - **moved:** when a calibrated camera's solved position is more than 3 m
 *   from ACHD's point, a faint dashed ground line joins them (from z16).
 *
 * The 3D poles, heads and cones from z15 are WP13's. The ground drape of the
 * reference frames ("Camera images on the map") is gone from the main map;
 * it stays only inside calibration, as a check.
 */
export type CameraStatus = 'calibrated' | 'uncalibrated' | 'no_image';
export interface CameraProps {
	id: number;
	name: string;
	achdCamId: number | null;
	views: number;
	status: CameraStatus;
}

/** A calibrated view's cone, as /api/calibrations reports it. */
export interface Calibration {
	calibrationId: number;
	viewId: number;
	cameraId: number;
	pose: Pose;
	size: ImageSize;
	groundZ: number;
	frame: string;
}

export type CameraCounts = Record<CameraStatus, number>;

export const SOURCE = 'cameras';
export const CONES = 'cones';
export const MOVES = 'camera-moves';
export const NOTCH_IMAGE = 'camera-notch';
export const CHECK_IMAGE = 'camera-check';
export const CREDIT = 'ITD 511 / ACHD';
/** The clickable icon layers. */
export const CAMERA_LAYERS = ['cameras-no-image', 'cameras-uncalibrated', 'cameras-calibrated'];
/** Every layer the Cameras layer shows. */
export const ALL_LAYERS = [
	'cones-fill',
	'cones-line',
	'cameras-moved',
	...CAMERA_LAYERS,
	'cameras-calibrated-check',
	'cameras-uncalibrated-mark',
	'cameras-recorded'
];

/** Footprints are drawn from this zoom (§14.6). */
export const FOOTPRINT_MINZOOM = 14;
/** A solved position further than this from ACHD's point gets the ground line, m. */
export const MOVED_M = 3;

export const TEAL = '#2c8c99';
export const AMBER = '#f2a20c';
export const INK = '#2b2a33';
export const CREAM = '#fffbf4';

export const STATUS_TEXT: Record<CameraStatus, string> = {
	calibrated: 'Calibrated',
	uncalibrated: 'Needs calibration',
	no_image: 'Not on 511 Idaho'
};

/** ● calibrated, ◌ not calibrated, ■ no image: status is never color alone. */
export const STATUS_SHAPE: Record<CameraStatus, string> = { calibrated: '●', uncalibrated: '◌', no_image: '■' };

export function counts(cameras: readonly CameraProps[]): CameraCounts {
	const c: CameraCounts = { calibrated: 0, uncalibrated: 0, no_image: 0 };
	for (const p of cameras) c[p.status]++;
	return c;
}

const M_PER_DEG = 111_320;

/** Ground distance between two lon/lat points, m (equirectangular: fine at camera scale). */
export function metres(a: readonly [number, number], b: readonly [number, number]): number {
	const k = Math.cos((((a[1] + b[1]) / 2) * Math.PI) / 180);
	return Math.hypot((a[0] - b[0]) * k * M_PER_DEG, (a[1] - b[1]) * M_PER_DEG);
}

/**
 * The faint ground lines from ACHD's point to each calibrated view's solved
 * position, where they're more than 3 m apart.
 */
export function movedLines(poles: ReadonlyMap<number, readonly [number, number]>, cals: readonly Calibration[]): FeatureCollection {
	const features: FeatureCollection['features'] = [];
	for (const c of cals) {
		const pole = poles.get(c.cameraId);
		if (!pole || !c.pose) continue;
		const at: [number, number] = [c.pose.lon, c.pose.lat];
		const d = metres(pole, at);
		if (!(d > MOVED_M)) continue;
		features.push({
			type: 'Feature',
			id: c.calibrationId,
			geometry: { type: 'LineString', coordinates: [[pole[0], pole[1]], at] },
			properties: { cameraId: c.cameraId, metres: Math.round(d * 10) / 10 }
		});
	}
	return { type: 'FeatureCollection', features };
}

/**
 * The recorded notch: a small ink tab with a cream edge, drawn at `ratio`
 * device pixels per CSS pixel (RGBA, for map.addImage).
 */
export function notchImage(ratio = 2): { width: number; height: number; data: Uint8Array } {
	const w = 7 * ratio;
	const h = 5 * ratio;
	const data = new Uint8Array(w * h * 4);
	const ink = [0x2b, 0x2a, 0x33, 255];
	const cream = [0xff, 0xfb, 0xf4, 255];
	for (let y = 0; y < h; y++) {
		for (let x = 0; x < w; x++) {
			const edgeX = Math.min(x, w - 1 - x);
			const edgeY = Math.min(y, h - 1 - y);
			// Rounded: the outermost corner pixels stay clear.
			if (edgeX + edgeY < Math.max(1, ratio - 1)) continue;
			const c = edgeX < ratio || edgeY < ratio ? cream : ink;
			data.set(c, (y * w + x) * 4);
		}
	}
	return { width: w, height: h, data };
}

/** Distance from (px, py) to the segment (ax, ay)–(bx, by). */
function segDist(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
	const dx = bx - ax;
	const dy = by - ay;
	const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)));
	return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}

/**
 * The calibrated icon's check: a cream tick on a clear 10 × 10 CSS px square,
 * antialiased, at `ratio` device pixels per CSS pixel (RGBA with straight
 * alpha, for map.addImage). Drawn here because the basemap's glyphs have no ✓.
 */
export function checkImage(ratio = 2): { width: number; height: number; data: Uint8Array } {
	const size = 10 * ratio;
	const data = new Uint8Array(size * size * 4);
	const pts = [
		[2.4, 5.3],
		[4.3, 7.3],
		[7.7, 3.1]
	].map(([x, y]) => [x * ratio, y * ratio]);
	const half = 0.95 * ratio;
	for (let y = 0; y < size; y++) {
		for (let x = 0; x < size; x++) {
			const cx = x + 0.5;
			const cy = y + 0.5;
			const d = Math.min(segDist(cx, cy, pts[0][0], pts[0][1], pts[1][0], pts[1][1]), segDist(cx, cy, pts[1][0], pts[1][1], pts[2][0], pts[2][1]));
			const a = Math.max(0, Math.min(1, half + 0.5 - d));
			if (a <= 0) continue;
			data.set([0xff, 0xfb, 0xf4, Math.round(a * 255)], (y * size + x) * 4);
		}
	}
	return { width: size, height: size, data };
}

/** Icon radius by zoom (CSS px). */
const RADIUS = ['interpolate', ['linear'], ['zoom'], 10, 4, 14, 7, 18, 11];
/** The "?" on uncalibrated icons by zoom (text px). */
const MARK_SIZE = ['interpolate', ['linear'], ['zoom'], 12, 8, 14, 10, 18, 14];
/** The check on calibrated icons by zoom (its image is 10 px at 1). */
const CHECK_SIZE = ['interpolate', ['linear'], ['zoom'], 12, 0.6, 14, 0.9, 18, 1.4];

const hover = (on: number, off: number) => ['case', ['boolean', ['feature-state', 'hover'], false], on, off];

/**
 * The layers, each with its slot (docs/14 §14.8 "Layer order"): footprints
 * and the moved lines in `footprints` (draped), icons and their marks in
 * `points`. All start hidden.
 */
export function cameraLayers(): SlottedLayer[] {
	const hidden = { visibility: 'none' as const };
	const calibrated = ['==', ['get', 'status'], 'calibrated'];
	const uncalibrated = ['==', ['get', 'status'], 'uncalibrated'];
	const num = (v: unknown) => v as number;
	const filter = (v: unknown) => v as ['==', string, string];
	return [
		{ slot: 'footprints', layer: { id: 'cones-fill', type: 'fill', source: CONES, minzoom: FOOTPRINT_MINZOOM, layout: hidden,
			paint: { 'fill-color': TEAL, 'fill-opacity': num(hover(0.22, 0.1)) } } },
		{ slot: 'footprints', layer: { id: 'cones-line', type: 'line', source: CONES, minzoom: FOOTPRINT_MINZOOM, layout: hidden,
			paint: { 'line-color': TEAL, 'line-width': 1.5, 'line-opacity': num(hover(1, 0.8)) } } },
		{ slot: 'footprints', layer: { id: 'cameras-moved', type: 'line', source: MOVES, minzoom: 16, layout: { ...hidden, 'line-cap': 'round' },
			paint: { 'line-color': INK, 'line-opacity': 0.45, 'line-width': 1.2, 'line-dasharray': [2, 2] } } },
		{ slot: 'points', layer: { id: 'cameras-no-image', type: 'circle', source: SOURCE, filter: ['==', ['get', 'status'], 'no_image'], layout: hidden,
			paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 18, 6], 'circle-color': '#9a958c',
				'circle-stroke-color': CREAM, 'circle-stroke-width': 1 } } },
		{ slot: 'points', layer: { id: 'cameras-uncalibrated', type: 'circle', source: SOURCE, filter: filter(uncalibrated), layout: hidden,
			paint: { 'circle-radius': num(RADIUS), 'circle-color': 'rgba(255,251,244,0.85)', 'circle-stroke-color': AMBER,
				'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 2, 16, 3.5] } } },
		{ slot: 'points', layer: { id: 'cameras-calibrated', type: 'circle', source: SOURCE, filter: filter(calibrated), layout: hidden,
			paint: { 'circle-radius': num(RADIUS), 'circle-color': TEAL, 'circle-stroke-color': CREAM, 'circle-stroke-width': 2 } } },
		{ slot: 'points', layer: { id: 'cameras-calibrated-check', type: 'symbol', source: SOURCE, filter: filter(calibrated), minzoom: 12,
			layout: { ...hidden, 'icon-image': CHECK_IMAGE, 'icon-size': num(CHECK_SIZE), 'icon-allow-overlap': true, 'icon-ignore-placement': true } } },
		{ slot: 'points', layer: { id: 'cameras-uncalibrated-mark', type: 'symbol', source: SOURCE, filter: filter(uncalibrated), minzoom: 12,
			layout: { ...hidden, 'text-field': '?', 'text-size': num(MARK_SIZE), 'text-font': ['Noto Sans Medium'], 'text-allow-overlap': true,
				'text-ignore-placement': true },
			paint: { 'text-color': INK } } },
		{ slot: 'points', layer: { id: 'cameras-recorded', type: 'symbol', source: SOURCE, filter: ['!=', ['get', 'status'], 'no_image'],
			layout: { ...hidden, 'icon-image': NOTCH_IMAGE, 'icon-anchor': 'bottom', 'icon-allow-overlap': true, 'icon-ignore-placement': true,
				'icon-offset': ['interpolate', ['linear'], ['zoom'], 10, ['literal', [0, -3]], 14, ['literal', [0, -6.5]], 18, ['literal', [0, -10.5]]] as unknown as [number, number] },
			paint: { 'icon-opacity': ['case', ['boolean', ['feature-state', 'recorded'], false], 1, 0] } } }
	];
}
