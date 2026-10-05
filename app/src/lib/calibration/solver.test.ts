import { describe, expect, it } from 'vitest';
import { footprint, pixelToGround, project, solve, type Pair, type Pose } from './solver';

// A camera like Eagle & Fairview's: 511 frame size, on a corner pole.
const SIZE = { width: 768, height: 466 };
const POLE: [number, number] = [-116.3545, 43.6198];
const TRUE: Pose = { lon: -116.35444, lat: 43.61977, alt: 801.5 + 12, heading: 37, tilt: 18, roll: 1.2, vfov: 42 };

/** Deterministic pseudo-random numbers so the test is repeatable. */
function rng(seed: number) {
	return () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
}

function syntheticPairs(n: number, noisePx: number, seed = 7): Pair[] {
	const rand = rng(seed);
	const pairs: Pair[] = [];
	while (pairs.length < n) {
		// Pick a pixel in the lower two thirds of the frame (where the road is),
		// find the ground point it sees on gently uneven ground, then add click noise.
		const px: [number, number] = [20 + rand() * (SIZE.width - 40), SIZE.height * 0.35 + rand() * SIZE.height * 0.6];
		const g = pixelToGround(TRUE, SIZE, px, 801.5 + (rand() - 0.5) * 0.6);
		if (!g) continue;
		const back = project(TRUE, SIZE, g)!;
		pairs.push({ pixel: [back[0] + (rand() - 0.5) * 2 * noisePx, back[1] + (rand() - 0.5) * 2 * noisePx], ground: g });
	}
	return pairs;
}

const metersBetween = (a: Pose, b: Pose) =>
	Math.hypot((a.lon - b.lon) * 111320 * Math.cos((a.lat * Math.PI) / 180), (a.lat - b.lat) * 111320);

describe('pose solver', () => {
	it('round-trips project and pixelToGround', () => {
		const g = pixelToGround(TRUE, SIZE, [400, 380], 801.5)!;
		const px = project(TRUE, SIZE, g)!;
		expect(px[0]).toBeCloseTo(400, 6);
		expect(px[1]).toBeCloseTo(380, 6);
	});

	it('recovers a known camera from 8 pairs with click noise', () => {
		const s = solve(syntheticPairs(8, 1.0), SIZE, POLE)!;
		expect(s.rms).toBeLessThan(1.5);
		expect(Math.abs(s.pose.heading - TRUE.heading)).toBeLessThan(1.5);
		expect(Math.abs(s.pose.tilt - TRUE.tilt)).toBeLessThan(1.5);
		expect(Math.abs(s.pose.vfov - TRUE.vfov)).toBeLessThan(2.5);
		expect(Math.abs(s.pose.alt - TRUE.alt)).toBeLessThan(2);
		expect(metersBetween(s.pose, TRUE)).toBeLessThan(3);
	});

	it('is near-exact with noise-free pairs', () => {
		const s = solve(syntheticPairs(6, 0), SIZE, POLE)!;
		expect(s.rms).toBeLessThan(0.05);
		expect(Math.abs(s.pose.heading - TRUE.heading)).toBeLessThan(0.1);
		expect(Math.abs(s.pose.vfov - TRUE.vfov)).toBeLessThan(0.2);
	});

	it('builds a closed view footprint within the cut-off distance, ahead of the camera', () => {
		const ring = footprint(TRUE, SIZE, 801.5, 250);
		expect(ring[0]).toEqual(ring.at(-1));
		expect(ring[0]).toEqual([TRUE.lon, TRUE.lat]);
		const k = 111320 * Math.cos((TRUE.lat * Math.PI) / 180);
		for (const [lon, lat] of ring.slice(1, -1)) {
			const e = (lon - TRUE.lon) * k, n = (lat - TRUE.lat) * 111320;
			expect(Math.hypot(e, n)).toBeLessThanOrEqual(250.5);
			// Every edge point lies within the camera's horizontal field of view of its heading.
			const bearing = ((Math.atan2(e, n) * 180) / Math.PI + 360) % 360;
			const off = Math.abs(((bearing - TRUE.heading + 540) % 360) - 180);
			expect(off).toBeLessThan(40);
		}
	});

	it('needs at least four pairs', () => {
		expect(solve(syntheticPairs(3, 0), SIZE, POLE)).toBeNull();
	});
});
