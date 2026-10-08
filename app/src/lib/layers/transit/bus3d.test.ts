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
	scaleAt,
	SELECT_LIFT_M,
	slopeAt,
	streetBearing,
	STREET_MAX_M,
	turn,
	UNKNOWN_GHOST,
	type GroundAt,
	LENGTH_MARGIN,
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

	it('draws models at least 42 px long, at up to 6× real size: 1.5× the first 28 px and 4× (Oct 8)', () => {
		expect(MIN_MODEL_PX).toBe(42);
		expect(MAX_MODEL_SCALE).toBe(6);
	});

	it('models start about z15, where 6× real size reaches 42 px', () => {
		const zm = modelZoom(LAT);
		expect(zm).toBeGreaterThan(14.9);
		expect(zm).toBeLessThan(15.1);
		expect(modelScale(zm, LAT)).toBeCloseTo(MAX_MODEL_SCALE, 6);
		expect(lengthPx(zm)).toBeCloseTo(MIN_MODEL_PX * LENGTH_MARGIN, 6);
	});

	it('a drawn model is at least 42 px long, at up to 6× real size, true scale from about z17.6', () => {
		for (let z = modelZoom(LAT); z <= 19; z += 0.05) {
			expect(lengthPx(z), `z${z.toFixed(2)}`).toBeGreaterThanOrEqual(MIN_MODEL_PX - 1e-9);
			expect(modelScale(z, LAT)).toBeLessThanOrEqual(MAX_MODEL_SCALE);
			expect(modelScale(z, LAT)).toBeGreaterThanOrEqual(1);
		}
		expect(modelScale(16, LAT)).toBeCloseTo(3, 0);
		expect(modelScale(17, LAT)).toBeCloseTo(1.5, 1);
		expect(modelScale(17.6, LAT)).toBe(1);
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

	it('corrects a model for its ground height: lower ground is farther from the camera', () => {
		const lod = lodAt(15.5, LAT, 0, true);
		// At z15.5 the camera is about 1.47 km from the centre (a 36.87° field of view, 800 px tall).
		const depthC = (400 / Math.tan((36.87 * Math.PI) / 360)) * metresPerPx(15.5, LAT);
		expect(depthC).toBeGreaterThan(1400);
		expect(depthC).toBeLessThan(1550);
		expect(scaleAt(lod, 800, 800, depthC)).toBeCloseTo(lod.scale0, 9);
		// 20 m lower: 20/1466 farther, drawn that much larger to stay 42 px long.
		expect(scaleAt(lod, 780, 800, depthC) / lod.scale0).toBeCloseTo(1 + 20 / depthC, 9);
		expect(scaleAt(lod, 820, 800, depthC) / lod.scale0).toBeCloseTo(1 - 20 / depthC, 9);
		// Tilted, a height difference is only partly a depth difference.
		const tilted = lodAt(15.5, LAT, 60, true);
		expect(scaleAt(tilted, 780, 800, depthC) / tilted.scale0).toBeCloseTo(1 + (20 * 0.5) / depthC, 9);
		// Never past 6× or below true size; no ground, no correction.
		expect(scaleAt(lodAt(14, LAT, 0, true), 0, 800, 3000)).toBe(MAX_MODEL_SCALE);
		expect(scaleAt(lodAt(19, LAT, 0, true), 900, 800, 100)).toBe(1);
		expect(scaleAt(lod, null, 800, depthC)).toBeCloseTo(lod.scale, 9);
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
		expect(lodAt(16, LAT, 0, true).clearance).toBeCloseTo((MIN_MODEL_PX * LENGTH_MARGIN) / 2, 6);
		expect(lodAt(16, LAT, 60, true).clearance).toBeCloseTo((MIN_MODEL_PX * LENGTH_MARGIN) / 4, 6);
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

	/** Two streets: one running east from (-116.2, 43.6), one running north-east from 50 m east of it. */
	const lines = {
		byRoute: new Map([
			['9', [[-116.2, 43.6, -116.19, 43.6]]],
			['3', [[-116.1993, 43.6, -116.1893, 43.61]]]
		]),
		all: [
			[-116.2, 43.6, -116.19, 43.6],
			[-116.1993, 43.6, -116.1893, 43.61]
		]
	};
	const north = (m: number) => 43.6 + m / 111_195;

	it('finds the bearing of the street a bus is on: its own route first, any route when it has none', () => {
		// 10 m north of the east-running street, on route 9: east.
		expect(streetBearing(lines, '9', -116.199, north(10))).toBeCloseTo(90, 1);
		// A bus 5 m off route 3's line lies along it (north-east, about 36° at this latitude).
		const ne = streetBearing(lines, '3', -116.1983 + 5 / 80_500, 43.601)!;
		expect(ne).toBeGreaterThan(30);
		expect(ne).toBeLessThan(45);
		// No route (or one with no lines): the nearest line of any.
		expect(streetBearing(lines, null, -116.199, north(5))).toBeCloseTo(90, 1);
		expect(streetBearing(lines, 'nope', -116.199, north(5))).toBeCloseTo(90, 1);
		// Nothing within STREET_MAX_M.
		expect(streetBearing(lines, '9', -116.199, north(STREET_MAX_M + 5))).toBeNull();
	});

	it('lays a bus with no heading yet along its street, until it has one of its own', () => {
		let looks = 0;
		const street = (lng: number, lat: number, routeId: string | null) => {
			looks++;
			return streetBearing(lines, routeId, lng, lat);
		};
		const m = busModel('7', null);
		const frame = (over: Partial<ModelFrame> = {}): ModelFrame => ({ lng: -116.199, lat: north(3), heading: null, color: '#2a78d6', opacity: 1, scale: 1, now: 1000, epoch: 1, ground: null, routeId: '9', street, ...over });
		placeModel(m, frame());
		expect(m.inst.heading).toBeCloseTo(90, 1);
		expect(looks).toBe(1);
		// Still there: not looked for again.
		placeModel(m, frame({ now: 1016 }));
		expect(looks).toBe(1);
		// A jump of more than 5 m (a gap): looked for again.
		placeModel(m, frame({ now: 1032, lng: -116.1985 }));
		expect(looks).toBe(2);
		// Its own heading arrives: it turns to that, and the street is forgotten.
		placeModel(m, frame({ now: 5000, heading: 270 }));
		expect(m.inst.heading).toBe(270);
		expect(m.street).toBeNull();
		// Without one again later, it keeps its own.
		placeModel(m, frame({ now: 5016 }));
		expect(m.inst.heading).toBe(270);
		expect(looks).toBe(2);
		// Off every street and with no heading: north, the last resort.
		const lost = busModel('8', null);
		placeModel(lost, frame({ lat: north(500) }));
		expect(lost.inst.heading).toBe(0);
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
		// A metre on: the slope it has is still good.
		placeModel(m, frame({ now: 1032, lat: 43.6 + 1 / 111_000 }));
		expect(reads).toBe(2);
		placeModel(m, frame({ now: 1048, lat: 43.6 + 3 / 111_000 }));
		expect(reads).toBe(4);
		placeModel(m, frame({ now: 1064, lat: 43.6 + 3 / 111_000, epoch: 2 }));
		expect(reads).toBe(6);
		// Turned: read again.
		placeModel(m, frame({ now: 1080, lat: 43.6 + 3 / 111_000, epoch: 2, heading: 90 }));
		expect(reads).toBe(8);
		// Hidden: nothing read.
		placeModel(m, frame({ now: 1096, opacity: 0, epoch: 3 }));
		expect(reads).toBe(8);
		expect(m.inst).toMatchObject({ mesh: 'bus', shadow: true, color: '#2a78d6', opacity: 0 });
		// Off screen: it keeps the slope it has.
		const pitch = m.inst.pitch;
		placeModel(m, frame({ now: 1112, lat: 43.7, epoch: 4, slope: false }));
		expect(reads).toBe(8);
		expect(m.inst.pitch).toBe(pitch);
		// …unless it never had one.
		const fresh = busModel('8', null);
		placeModel(fresh, frame({ slope: false }));
		expect(reads).toBe(10);
		// With a size, the scale follows the ground it read (the plane is 0 m at 43.6); a bigger model reaches
		// farther for its slope, so it reads again.
		const lod = lodAt(15.5, 43.6, 0, true);
		placeModel(fresh, frame({ now: 1016, scale: lod.scale, size: { lod, elevC: 20, depthC: 1466 } }));
		expect(reads).toBe(12);
		expect(fresh.inst.scale).toBeCloseTo(lod.scale0 * (1 + 20 / 1466), 6);
	});
});
