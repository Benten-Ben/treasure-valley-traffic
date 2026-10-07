import { describe, expect, it } from 'vitest';
import { axes, project } from '#lib/calibration/solver.js';
import { toLocal } from '#lib/calibration/solver.js';
import type { Selection } from '../types.js';
import { cardPhoto, PHOTO_PX } from './card3d.js';
import type { Calibration, CameraProps } from './cameras.js';
import { progress, shownBox, MIN_STEPS } from './lookthrough.js';
import { build3d, modelFade, poleGirth, type Cam3D } from './scene.js';

const KEY: CameraProps = { id: 59, name: 'Eagle & Fairview', achdCamId: 1, views: 1, status: 'calibrated' };
const OPEN: CameraProps = { id: 7, name: 'Somewhere', achdCamId: 2, views: 1, status: 'uncalibrated' };
const DARK: CameraProps = { id: 8, name: 'Nowhere', achdCamId: 3, views: 0, status: 'no_image' };
const CAMS: Cam3D[] = [
	{ props: KEY, at: [-116.35486, 43.61969] },
	{ props: OPEN, at: [-116.3, 43.6] },
	{ props: DARK, at: [-116.31, 43.61] }
];
const CAL: Calibration = {
	calibrationId: 501,
	viewId: 26,
	cameraId: 59,
	pose: { lon: -116.35476, lat: 43.61964, alt: 811.1, heading: 355, tilt: 20, roll: 0, vfov: 42 },
	size: { width: 768, height: 466 },
	groundZ: 801.1,
	frame: 'view-26/seed.jpg'
};
const selection = (p: CameraProps): Selection => ({ kind: 'camera', id: String(p.id), layer: 'cameras', title: p.name });
const base = { zoom: 17, lat: 43.6, ground: () => 801.1, selection };

describe('3D cameras (build3d)', () => {
	it('draws a calibrated camera as a pole, a head and a cone with four frustum edges; one that isn’t as a pin', () => {
		const b = build3d(CAMS, [CAL], base);
		expect(b.instances.map((i) => i.mesh)).toEqual(['pole', 'head', 'pin']);
		expect(b.cones).toHaveLength(1);
		expect(b.cones[0].ends).toHaveLength(32);
		expect(b.lines).toHaveLength(4);
		// Nothing for the camera with no image.
		expect(b.instances.some((i) => i.id.endsWith(`-${DARK.id}`))).toBe(false);
		// Every model selects its camera.
		for (const i of b.instances) expect(i.pick?.id).toBe(i.mesh === 'pin' ? String(OPEN.id) : String(KEY.id));
	});

	it("the pole stands on the ground up to the head; the head's axes are the solver's", () => {
		const b = build3d(CAMS, [CAL], { ...base, ground: () => 800.6 });
		const pole = b.instances.find((i) => i.mesh === 'pole')!;
		const head = b.instances.find((i) => i.mesh === 'head')!;
		expect(pole.alt).toBeUndefined();
		expect((pole.scale as number[])[2]).toBeCloseTo(811.1 - 800.6 - 0.15, 9);
		expect(head.alt).toBe(811.1);
		expect(head.minPx).toBe(12);
		expect(head.basis).toEqual(axes(355, 20, 0));
		// Without terrain data, the calibration's ground height.
		const flat = build3d(CAMS, [CAL], { ...base, ground: () => null });
		expect((flat.instances.find((i) => i.mesh === 'pole')!.scale as number[])[2]).toBeCloseTo(811.1 - 801.1 - 0.15, 9);
	});

	it("the cone's corner edges run from the head through the image corners", () => {
		const b = build3d(CAMS, [CAL], base);
		const corners = b.lines.map((l) => l.points[1] as [number, number, number]);
		const px = corners.map((c) => project(CAL.pose, CAL.size, c)!);
		const want = [
			[0, 0],
			[768, 0],
			[768, 466],
			[0, 466]
		];
		px.forEach((p, i) => expect(Math.hypot(p[0] - want[i][0], p[1] - want[i][1])).toBeLessThan(0.01));
	});

	it('leaves out the camera looked through, and cameras away from the view', () => {
		expect(build3d(CAMS, [CAL], { ...base, exclude: new Set([59]) }).instances.map((i) => i.mesh)).toEqual(['pin']);
		const near = (lng: number) => lng < -116.33;
		expect(build3d(CAMS, [CAL], { ...base, near }).instances.map((i) => i.mesh)).toEqual(['pole', 'head']);
	});

	it('dithers in over 14.7–15 and widens the pole to 3 px until it’s that wide', () => {
		expect(modelFade(14.6)).toBe(0);
		expect(modelFade(14.85)).toBeCloseTo(0.5, 9);
		expect(modelFade(15)).toBe(1);
		expect(build3d(CAMS, [CAL], { ...base, zoom: 14.85 }).instances.every((i) => Math.abs((i.opacity ?? 1) - 0.5) < 1e-9)).toBe(true);
		expect(poleGirth(15, 43.6)).toBeGreaterThan(5);
		expect(poleGirth(23, 43.6)).toBe(1);
	});
});

describe('the photo in the cone', () => {
	it('hangs the picture without the 511 bar, centred on the axis, about 140 px wide, its back named', () => {
		const p = cardPhoto(CAL, 'Eagle & Fairview', 'card:26:abc', 0.5);
		expect(p.apex).toEqual([CAL.pose.lon, CAL.pose.lat, CAL.pose.alt]);
		expect(p.widthPx).toBe(PHOTO_PX);
		expect(p.label).toBe('Eagle & Fairview');
		expect(p.opacity).toBe(0.5);
		const t = Math.tan((21 * Math.PI) / 180);
		expect(p.tx).toBeCloseTo((t * 768) / 466, 9);
		// 34 px of bar off the bottom, and as much off the top.
		expect(p.ty).toBeCloseTo((t * (466 - 68)) / 466, 9);
		// Its corners at any distance are on the frustum: at 10 m, the bottom-right lands on the crop's corner.
		const d = 10;
		const v = [0, 1, 2].map((i) => d * (p.forward[i] + p.tx * p.right[i] + p.ty * p.down[i]));
		const local = toLocal([CAL.pose.lon, CAL.pose.lat], [CAL.pose.lon, CAL.pose.lat, CAL.pose.alt]);
		expect(local[0]).toBeCloseTo(0, 9);
		const k = 1 / (111_320 * Math.cos((CAL.pose.lat * Math.PI) / 180));
		const corner: [number, number, number] = [CAL.pose.lon + v[0] * k, CAL.pose.lat + v[1] / 111_320, CAL.pose.alt + v[2]];
		const px = project(CAL.pose, CAL.size, corner)!;
		expect(px[0]).toBeCloseTo(768, 0);
		expect(px[1]).toBeCloseTo(466 - 34, 0);
	});
});

describe('look-through helpers', () => {
	it('animations go by time, but never more than 1/8 a frame', () => {
		expect(progress(100, 400, 1)).toBeCloseTo(1 / MIN_STEPS, 9);
		expect(progress(50, 400, 3)).toBeCloseTo(0.125, 9);
		expect(progress(5000, 400, 2)).toBeCloseTo(2 / MIN_STEPS, 9);
		expect(progress(5000, 400, MIN_STEPS)).toBe(1);
	});

	it('maps a crop of the picture onto its letterbox', () => {
		const box = { x: 10, y: 20, width: 768 * 2, height: 466 * 2 };
		expect(shownBox(box, { width: 768, height: 466 }, { x: 0, y: 0, width: 768, height: 432 })).toEqual({ x: 10, y: 20, width: 1536, height: 864 });
	});
});
