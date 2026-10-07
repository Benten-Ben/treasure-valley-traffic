import { describe, expect, it } from 'vitest';
import {
	along,
	bodyColor,
	BUS_HEIGHT_M,
	BUS_LENGTH_M,
	busModel,
	FADE_ZOOMS,
	ghostOf,
	lodAt,
	MAX_MODEL_SCALE,
	MIN_MODEL_PX,
	metresPerPx,
	modelFade,
	modelScale,
	modelZoom,
	placeModel,
	plateAltitude,
	SELECT_LIFT_M,
	slopeAt,
	turn,
	UNKNOWN_GHOST,
	type GroundAt,
	type ModelFrame
} from './bus3d.js';
import { UNKNOWN_COLOR } from './transit.js';

const LAT = 43.6;
const lengthPx = (zoom: number) => (BUS_LENGTH_M * modelScale(zoom, LAT)) / metresPerPx(zoom, LAT);

describe('bus level of detail (§14.4 "Buses and stops")', () => {
	it('uses §14.4 ground resolutions: 12.2 m is 3.5, 7, 14 and 28 px at z14–17', () => {
		expect(BUS_LENGTH_M / metresPerPx(14, LAT)).toBeCloseTo(3.5, 0);
		expect(BUS_LENGTH_M / metresPerPx(15, LAT)).toBeCloseTo(7, 0);
		expect(BUS_LENGTH_M / metresPerPx(16, LAT)).toBeCloseTo(14, 0);
		expect(BUS_LENGTH_M / metresPerPx(17, LAT)).toBeCloseTo(28, 0);
	});

	it('models start about z15, where 4× real size reaches 28 px', () => {
		const zm = modelZoom(LAT);
		expect(zm).toBeGreaterThan(14.9);
		expect(zm).toBeLessThan(15.1);
		expect(modelScale(zm, LAT)).toBeCloseTo(MAX_MODEL_SCALE, 6);
		expect(lengthPx(zm)).toBeCloseTo(MIN_MODEL_PX, 6);
	});

	it('a drawn model is at least 28 px long, at up to 4× real size, true scale from about z17', () => {
		for (let z = modelZoom(LAT); z <= 19; z += 0.05) {
			expect(lengthPx(z), `z${z.toFixed(2)}`).toBeGreaterThanOrEqual(MIN_MODEL_PX - 1e-9);
			expect(modelScale(z, LAT)).toBeLessThanOrEqual(MAX_MODEL_SCALE);
			expect(modelScale(z, LAT)).toBeGreaterThanOrEqual(1);
		}
		expect(modelScale(16, LAT)).toBeCloseTo(2, 0);
		expect(modelScale(17.1, LAT)).toBe(1);
		expect(modelScale(18, LAT)).toBe(1);
	});

	it('disc and model crossfade over 0.3 zoom', () => {
		const zm = modelZoom(LAT);
		expect(modelFade(zm - 0.01, LAT)).toBe(0);
		expect(modelFade(zm + FADE_ZOOMS / 2, LAT)).toBeCloseTo(0.5, 6);
		expect(modelFade(zm + FADE_ZOOMS, LAT)).toBe(1);
		let last = -1;
		for (let z = 14; z < 16; z += 0.02) {
			const f = modelFade(z, LAT);
			expect(f).toBeGreaterThanOrEqual(last);
			last = f;
			const lod = lodAt(z, LAT, 0, true);
			expect(lod.fade + lod.disc).toBeCloseTo(1, 9);
		}
	});

	it('without the scene, buses stay discs at every zoom', () => {
		for (const z of [10, 15, 16, 17, 20]) {
			const lod = lodAt(z, LAT, 45, false);
			expect(lod.fade).toBe(0);
			expect(lod.disc).toBe(1);
		}
	});

	it('puts the plate above the roof, lifted with the selected model', () => {
		const lod = lodAt(16, LAT, 0, true);
		expect(lod.plateAlt).toBeGreaterThan(BUS_HEIGHT_M * lod.scale);
		expect(plateAltitude(lod, true) - plateAltitude(lod, false)).toBeGreaterThanOrEqual(SELECT_LIFT_M);
		// Seen from above, the plate clears the model's half-length; tilted, less (its height lifts it).
		expect(lodAt(16, LAT, 0, true).clearance).toBeCloseTo(MIN_MODEL_PX / 2, 1);
		expect(lodAt(16, LAT, 60, true).clearance).toBeCloseTo(MIN_MODEL_PX / 4, 1);
	});
});

describe('bus looks', () => {
	it('route color; ghost when stale or another route is spotlit; gray for unknown routes', () => {
		const base = { routeId: '9', color: '#2a78d6', ghost: '#b1c6e2', stale: false, dimmed: false };
		expect(bodyColor(base)).toBe('#2a78d6');
		expect(bodyColor({ ...base, stale: true })).toBe('#b1c6e2');
		expect(bodyColor({ ...base, dimmed: true })).toBe('#b1c6e2');
		expect(bodyColor({ ...base, ghost: null, stale: true })).toBe(ghostOf('#2a78d6'));
		expect(bodyColor({ ...base, routeId: null })).toBe(UNKNOWN_COLOR);
		expect(bodyColor({ ...base, routeId: null, stale: true })).toBe(UNKNOWN_GHOST);
	});

	it('a made-up ghost moves toward the clay surface', () => {
		expect(ghostOf('#000000')).toBe('#928e88');
		expect(ghostOf('#f3ede2')).toBe('#f3ede2');
	});
});

describe('heading and slope', () => {
	it('turns toward the path heading across north, and keeps its own without one', () => {
		expect(turn(null, 90, 16)).toBe(90);
		expect(turn(90, null, 16)).toBe(90);
		const h = turn(350, 10, 120)!;
		expect(h === 0 || h > 350 || h < 10).toBe(true);
		// After 5 time constants it's within 1% of the turn.
		expect(turn(0, 90, 600)!).toBeCloseTo(90 * (1 - Math.exp(-5)), 6);
		// A model not drawn for a while snaps.
		expect(turn(0, 90, 5000)).toBe(90);
	});

	it('a turning model stays within a few degrees of a path turning 45°/s', () => {
		let model: number | null = 0;
		let path = 0;
		let worst = 0;
		for (let t = 0; t < 2000; t += 16) {
			path += 45 * 0.016;
			model = turn(model, path, 16);
			worst = Math.max(worst, Math.abs(path - model!));
		}
		expect(worst).toBeLessThan(10);
	});

	/** A plane rising 10 m per 100 m northward. */
	const plane: GroundAt = ([, lat]) => (lat - 43.6) * 111_195 * 0.1;

	it('pitches with the slope 6 m ahead and behind', () => {
		expect(slopeAt(plane, -116.2, 43.6, 0)).toBeCloseTo(Math.atan(0.1) * (180 / Math.PI), 1);
		expect(slopeAt(plane, -116.2, 43.6, 180)).toBeCloseTo(-Math.atan(0.1) * (180 / Math.PI), 1);
		expect(slopeAt(plane, -116.2, 43.6, 90)).toBeCloseTo(0, 6);
		expect(slopeAt(() => null, -116.2, 43.6, 0)).toBe(0);
		// A cliff is clamped.
		expect(slopeAt(([, lat]) => (lat - 43.6) * 1e7, -116.2, 43.6, 0)).toBe(15);
		const [lng, lat] = along(-116.2, 43.6, 90, 100);
		expect(lat).toBeCloseTo(43.6, 6);
		expect((lng + 116.2) * 111_195 * Math.cos(43.6 * (Math.PI / 180))).toBeCloseTo(100, 0);
	});

	it('reads the slope again only when the bus moved, turned or the terrain changed', () => {
		let reads = 0;
		const ground: GroundAt = (p) => {
			reads++;
			return plane(p);
		};
		const m = busModel('7', null);
		const frame = (over: Partial<ModelFrame> = {}): ModelFrame => ({ lng: -116.2, lat: 43.6, heading: 0, color: '#2a78d6', opacity: 1, scale: 1, now: 1000, epoch: 1, ground, ...over });
		placeModel(m, frame());
		expect(reads).toBe(2);
		expect(m.inst.pitch).toBeCloseTo(5.7, 1);
		placeModel(m, frame({ now: 1016 }));
		expect(reads).toBe(2);
		placeModel(m, frame({ now: 1032, lat: 43.6 + 1 / 111_000 }));
		expect(reads).toBe(4);
		placeModel(m, frame({ now: 1048, lat: 43.6 + 1 / 111_000, epoch: 2 }));
		expect(reads).toBe(6);
		// Hidden: nothing read.
		placeModel(m, frame({ now: 1064, opacity: 0, epoch: 3 }));
		expect(reads).toBe(6);
		expect(m.inst).toMatchObject({ mesh: 'bus', shadow: true, color: '#2a78d6', opacity: 0 });
	});
});
