import type { SlottedLayer } from '#lib/map/order.js';
import type { ImageSize, Pose } from '#lib/calibration/solver.js';

/**
 * The Cameras layer's pure parts (ported from the Cameras lens by WP2; WP12
 * builds the windows and §14.6's icons on it). Camera nodes are told apart
 * by shape as well as color (never color alone):
 *  - calibrated: solid teal dot with a white ring and a check;
 *  - uncalibrated: hollow amber ring;
 *  - no image yet: small gray dot;
 * plus the view cones of calibrated cameras and, on request, each one's
 * reference frame draped on the ground under its cone.
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
	pose: Pose;
	size: ImageSize;
	groundZ: number;
	frame: string;
}

export type CameraCounts = Record<CameraStatus, number>;

export const SOURCE = 'cameras';
export const CONES = 'cones';
export const CREDIT = 'ITD 511 / ACHD';
export const CAMERA_LAYERS = ['cameras-no-image', 'cameras-uncalibrated', 'cameras-calibrated'];
/** Every layer the Cameras layer shows, besides the drapes. */
export const ALL_LAYERS = [...CAMERA_LAYERS, 'cameras-calibrated-check', 'cones-fill', 'cones-line'];

export const STATUS_TEXT: Record<CameraStatus, string> = {
	calibrated: 'Calibrated',
	uncalibrated: 'Needs calibration',
	no_image: 'No camera image linked yet'
};

/** ● calibrated, ◌ not calibrated, ■ no image: status is never color alone. */
export const STATUS_SHAPE: Record<CameraStatus, string> = { calibrated: '●', uncalibrated: '◌', no_image: '■' };

export function counts(cameras: readonly CameraProps[]): CameraCounts {
	const c: CameraCounts = { calibrated: 0, uncalibrated: 0, no_image: 0 };
	for (const p of cameras) c[p.status]++;
	return c;
}

/**
 * The layers, each with its slot (docs/14 §14.8 "Layer order"): cones in
 * `footprints` (draped), camera icons in `points`. All start hidden.
 */
export function cameraLayers(): SlottedLayer[] {
	const hidden = { visibility: 'none' as const };
	const radius = ['interpolate', ['linear'], ['zoom'], 10, 4, 14, 7, 18, 11] as unknown as number;
	return [
		{ slot: 'footprints', layer: { id: 'cones-fill', type: 'fill', source: CONES, layout: hidden,
			paint: { 'fill-color': '#2c8c99', 'fill-opacity': 0.14 } } },
		{ slot: 'footprints', layer: { id: 'cones-line', type: 'line', source: CONES, layout: hidden,
			paint: { 'line-color': '#2c8c99', 'line-width': 1.5, 'line-opacity': 0.8 } } },
		{ slot: 'points', layer: { id: 'cameras-no-image', type: 'circle', source: SOURCE, filter: ['==', ['get', 'status'], 'no_image'], layout: hidden,
			paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 18, 6], 'circle-color': '#9a958c',
				'circle-stroke-color': '#fffbf4', 'circle-stroke-width': 1 } } },
		{ slot: 'points', layer: { id: 'cameras-uncalibrated', type: 'circle', source: SOURCE, filter: ['==', ['get', 'status'], 'uncalibrated'], layout: hidden,
			paint: { 'circle-radius': radius, 'circle-color': 'rgba(255,251,244,0.85)', 'circle-stroke-color': '#f2a20c',
				'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 2, 16, 3.5] } } },
		{ slot: 'points', layer: { id: 'cameras-calibrated', type: 'circle', source: SOURCE, filter: ['==', ['get', 'status'], 'calibrated'], layout: hidden,
			paint: { 'circle-radius': radius, 'circle-color': '#2c8c99', 'circle-stroke-color': '#fffbf4', 'circle-stroke-width': 2 } } },
		{ slot: 'points', layer: { id: 'cameras-calibrated-check', type: 'symbol', source: SOURCE, filter: ['==', ['get', 'status'], 'calibrated'],
			minzoom: 12,
			layout: { ...hidden, 'text-field': '✓', 'text-size': 11, 'text-font': ['Noto Sans Medium'], 'text-allow-overlap': true },
			paint: { 'text-color': '#fffbf4' } } }
	];
}
