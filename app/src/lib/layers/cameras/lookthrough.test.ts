import type { Map } from 'maplibre-gl';
import { describe, expect, it } from 'vitest';
import { eyeOf, eyePose, metresBetween, nearMetres, pxPerMetre, type EyePose } from '#lib/calibration/frustum.js';
import type { Pose } from '#lib/calibration/solver.js';
import { ANCHOR_BELOW_M, GROUND_JUMP_M, offGround, placeEye, usableGround } from './lookthrough.js';

/**
 * Look-through's placement (docs/14 §14.6 "Look through", step 5), on a
 * stand-in for MapLibre 6.12's camera that places the centre the way its
 * `calculateCenterFromCameraLngLatAlt` does: along the view axis down to the
 * height the centre has now, or 10 km out (and that far down the axis) when
 * the axis can't reach it. That second case is what entering from a
 * zoomed-out view hit: the centre kilometres away and underground, zoom about
 * 12 and a near plane of 140–200 m.
 */
const D2R = Math.PI / 180;
const H = 800;
/** MapLibre's `maxMercatorHorizonAngle`. */
const HORIZON = 89.25;
const circumference = (lat: number) => 2 * Math.PI * 6371008.8 * Math.cos(lat * D2R);

interface Sim {
	map: Map;
	state: { lng: number; lat: number; elevation: number; zoom: number; pitch: number; bearing: number; roll: number; fov: number };
	jumps: number;
}

/** A map camera with MapLibre's centre rule, and terrain from `ground` (null: no terrain). */
function simMap(ground: ((lng: number, lat: number) => number) | null, elevation = 0): Sim {
	const state = { lng: -116.3, lat: 43.6, elevation, zoom: 14, pitch: 0, bearing: 0, roll: 0, fov: 36.87 };
	const sim: Sim = { map: null as unknown as Map, state, jumps: 0 };
	const zoomFor = (dist: number, lat: number) => Math.log2(((H / 2 / Math.tan((state.fov * D2R) / 2) / dist) * circumference(lat)) / 512);
	const map = {
		getVerticalFieldOfView: () => state.fov,
		setVerticalFieldOfView: (f: number) => void (state.fov = f),
		calculateCameraOptionsFromCameraLngLatAltRotation(ll: [number, number], alt: number, bearing: number, pitch: number, roll: number) {
			const dz = -Math.cos(pitch * D2R);
			const agl = alt - state.elevation;
			let dist: number;
			let elev = state.elevation;
			if (dz * agl >= 0 || Math.abs(dz) < Math.cos(HORIZON * D2R)) {
				dist = 10000;
				elev = alt + dist * dz;
			} else dist = -agl / dz;
			const h = Math.sin(pitch * D2R) * dist;
			const lat = ll[1] + ((h * Math.cos(bearing * D2R)) / circumference(0)) * 360;
			const lng = ll[0] + ((h * Math.sin(bearing * D2R)) / circumference(lat)) * 360;
			return { center: [lng, lat], elevation: elev, zoom: zoomFor(dist, lat), bearing, pitch, roll };
		},
		jumpTo(o: { center?: [number, number]; elevation?: number; zoom?: number; bearing?: number; pitch?: number; roll?: number }) {
			sim.jumps++;
			if (o.center) [state.lng, state.lat] = o.center;
			if (o.elevation !== undefined) state.elevation = o.elevation;
			if (o.zoom !== undefined) state.zoom = o.zoom;
			if (o.bearing !== undefined) state.bearing = o.bearing;
			if (o.pitch !== undefined) state.pitch = o.pitch;
			if (o.roll !== undefined) state.roll = o.roll;
		},
		getCenter: () => ({ lng: state.lng, lat: state.lat }),
		getCenterElevation: () => state.elevation,
		getZoom: () => state.zoom,
		getTerrain: () => (ground ? { source: 'terrain' } : null),
		queryTerrainElevation: (ll: { lng: number; lat: number } | [number, number]) => {
			if (!ground) return null;
			const [lng, lat] = Array.isArray(ll) ? ll : [ll.lng, ll.lat];
			return ground(lng, lat);
		}
	};
	sim.map = map as unknown as Map;
	return sim;
}

/** Where the simulated map's eye is (frustum.ts's eyeOf, as the readback check reads it). */
const eyeNow = (s: Sim) => eyeOf({ center: [s.state.lng, s.state.lat], elevation: s.state.elevation, zoom: s.state.zoom, pitch: s.state.pitch, bearing: s.state.bearing, fov: s.state.fov, height: H });
/** How far the centre is from the eye, m. */
const centreDistance = (s: Sim) => (0.5 / Math.tan((s.state.fov * D2R) / 2)) * H / pxPerMetre(s.state.zoom, s.state.lat);

// The key seed: a 10 m pole looking 20° down, with its ground at 801.1 m.
const POSE: Pose = { lon: -116.35476, lat: 43.61964, alt: 811.1, heading: 355, tilt: 20, roll: 0, vfov: 42 };
const GROUND_Z = 801.1;
const EYE: EyePose = eyePose(POSE, 45);
const flat = (h: number) => () => h;

describe('placing the map camera at a pose (step 5)', () => {
	it('MapLibre’s rule alone, from a centre above the eye, puts the centre 10 km out and underground (the bug)', () => {
		// Entering from a zoomed-out view whose centre is on higher ground than the camera.
		const s = simMap(flat(915), 915);
		placeEye(s.map, EYE);
		expect(s.state.elevation).toBeLessThan(-1000);
		expect(s.state.zoom).toBeLessThan(13);
		expect(nearMetres(H, s.state.zoom, s.state.lat)).toBeGreaterThan(100);
	});

	it('anchored on the calibration’s ground height, the centre is on the ground along the axis, from any start', () => {
		for (const start of [915, 2000, 811.1, 0, -3397]) {
			const s = simMap(flat(801), start);
			placeEye(s.map, EYE, undefined, { anchor: GROUND_Z, terrain: true });
			const label = `from a centre at ${start} m`;
			expect(s.state.elevation, label).toBeCloseTo(801, 6);
			// (alt − ground)/cos(pitch) along the axis, so tens of metres, not kilometres.
			expect(centreDistance(s), label).toBeCloseTo((811.1 - 801) / Math.cos(70 * D2R), 3);
			expect(s.state.zoom, label).toBeGreaterThan(19);
			expect(nearMetres(H, s.state.zoom, s.state.lat), label).toBeLessThanOrEqual(2);
			expect(metresBetween([POSE.lon, POSE.lat, POSE.alt], eyeNow(s)), `${label}: the eye`).toBeLessThan(1e-3);
		}
	});

	it('takes the terrain under the axis only when it’s believable: loaded, below the eye and within a few metres', () => {
		const cases: [string, (lng: number, lat: number) => number, number][] = [
			['terrain 3 m below the ground height: taken', flat(798.1), 798.1],
			['a tile not loaded yet (0): kept on the ground height', flat(0), GROUND_Z],
			['a far parent tile 200 m off: kept', flat(1001.1), GROUND_Z],
			['terrain at the eye: kept', flat(811.1), GROUND_Z],
			[`more than ${GROUND_JUMP_M} m away: kept`, flat(GROUND_Z + GROUND_JUMP_M + 1), GROUND_Z]
		];
		for (const [label, ground, want] of cases) {
			const s = simMap(ground, 915);
			placeEye(s.map, EYE, undefined, { anchor: GROUND_Z, terrain: true });
			expect(s.state.elevation, label).toBeCloseTo(want, 6);
			expect(metresBetween([POSE.lon, POSE.lat, POSE.alt], eyeNow(s)), `${label}: the eye`).toBeLessThan(1e-3);
		}
	});

	it('follows a gentle slope along the axis in two passes, the eye kept', () => {
		// Ground falling 5 cm per metre northward, 801 m under the pole.
		const slope = (_lng: number, lat: number) => 801 - (lat - POSE.lat) * 111_320 * 0.05;
		const s = simMap(slope, 915);
		placeEye(s.map, EYE, undefined, { anchor: GROUND_Z, terrain: true });
		expect(Math.abs(s.state.elevation - slope(s.state.lng, s.state.lat))).toBeLessThan(0.2);
		expect(offGround(s.map, POSE.alt)).toBeLessThan(0.2);
		expect(metresBetween([POSE.lon, POSE.lat, POSE.alt], eyeNow(s))).toBeLessThan(1e-3);
	});

	it('keeps the anchor below the eye, so the axis always meets it', () => {
		// A ground height at or above the eye (a bad calibration): the anchor goes 1 m under the eye.
		const s = simMap(null, 915);
		placeEye(s.map, EYE, undefined, { anchor: 900 });
		expect(s.state.elevation).toBeCloseTo(POSE.alt - ANCHOR_BELOW_M, 9);
		expect(centreDistance(s)).toBeCloseTo(ANCHOR_BELOW_M / Math.cos(70 * D2R), 3);
	});

	it('usableGround: known, below the eye, and not a jump', () => {
		expect(usableGround(null, 800, 811)).toBe(false);
		expect(usableGround(Number.NaN, 800, 811)).toBe(false);
		expect(usableGround(803, 800, 811)).toBe(true);
		expect(usableGround(810.6, 806, 811)).toBe(false);
		expect(usableGround(812, 810, 811)).toBe(false);
		expect(usableGround(800 + GROUND_JUMP_M + 0.1, 800, 900)).toBe(false);
		expect(usableGround(1000, 800, 2000, Infinity)).toBe(true);
	});
});
