import { describe, expect, it } from 'vitest';
import { circumferenceAt, makeFrame, mercatorX, mercatorY, multiply, offset, projectLocal, projectLocal32, projectMercator32 } from './rtc.js';

/**
 * Rendering relative to centre (docs/14 §14.8, "Projection and precision"),
 * against a matrix built the way MapLibre 6.12's Mercator transform builds the
 * custom layer's mainMatrix (perspective · flip · camera distance · roll ·
 * pitch · bearing · centre · metres scale · centre elevation · Mercator scale).
 */
type M = Float64Array;
const mul = (a: M, b: M) => multiply(new Float64Array(16), a, b);
const scale = (x: number, y: number, z: number) => new Float64Array([x, 0, 0, 0, 0, y, 0, 0, 0, 0, z, 0, 0, 0, 0, 1]);
const translate = (x: number, y: number, z: number) => new Float64Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]);
const rotX = (r: number) => new Float64Array([1, 0, 0, 0, 0, Math.cos(r), Math.sin(r), 0, 0, -Math.sin(r), Math.cos(r), 0, 0, 0, 0, 1]);
const rotZ = (r: number) => new Float64Array([Math.cos(r), Math.sin(r), 0, 0, -Math.sin(r), Math.cos(r), 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
function perspective(fovy: number, aspect: number, near: number, far: number): M {
	const f = 1 / Math.tan(fovy / 2);
	const nf = 1 / (near - far);
	return new Float64Array([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0]);
}

interface Cam {
	lng: number;
	lat: number;
	zoom: number;
	pitch: number;
	bearing: number;
	roll: number;
	fov: number;
	elevation: number;
}
const W = 1280;
const H = 800;

function mainMatrix(c: Cam): M {
	const ws = 512 * 2 ** c.zoom;
	const ppm = ws / circumferenceAt(c.lat);
	const fov = (c.fov * Math.PI) / 180;
	const d = (0.5 / Math.tan(fov / 2)) * H;
	let m = perspective(fov, W / H, H / 50, d * 200);
	m = mul(m, scale(1, -1, 1));
	m = mul(m, translate(0, 0, -d));
	m = mul(m, rotZ((-c.roll * Math.PI) / 180));
	m = mul(m, rotX((c.pitch * Math.PI) / 180));
	m = mul(m, rotZ((-c.bearing * Math.PI) / 180));
	m = mul(m, translate(-mercatorX(c.lng) * ws, -mercatorY(c.lat) * ws, 0));
	m = mul(m, scale(1, 1, ppm));
	m = mul(m, translate(0, 0, -c.elevation));
	return mul(m, scale(ws, ws, ws / ppm));
}

/** Float64 projection of a lng/lat/elevation through mainMatrix (the reference). */
function reference(main: M, c: Cam, lng: number, lat: number, z: number) {
	const v = [mercatorX(lng), mercatorY(lat), z / circumferenceAt(c.lat), 1];
	const o = [0, 0, 0, 0];
	for (let r = 0; r < 4; r++) o[r] = main[r] * v[0] + main[4 + r] * v[1] + main[8 + r] * v[2] + main[12 + r] * v[3];
	return { x: ((o[0] / o[3] + 1) / 2) * W, y: ((1 - o[1] / o[3]) / 2) * H, w: o[3] };
}

const BOISE = { lng: -116.2023, lat: 43.615, elevation: 830 };
const metres = (c: Cam, east: number, north: number): [number, number] => [
	c.lng + (east / circumferenceAt(c.lat)) * 360,
	// Inverse Mercator for a north offset at the centre's scale.
	(Math.atan(Math.sinh(Math.PI * (1 - 2 * (mercatorY(c.lat) - north / circumferenceAt(c.lat))))) * 180) / Math.PI
];

describe('rtc', () => {
	it('offsets are true metres east and north at the centre, and up from the origin', () => {
		const c = { ...BOISE, zoom: 15, pitch: 0, bearing: 0, roll: 0, fov: 36.87 };
		const f = makeFrame(mainMatrix(c), c.lng, c.lat, 830, W, H, (c.fov * Math.PI) / 180, c.zoom);
		const [lng, lat] = metres(c, 120, -45);
		const o: [number, number, number] = [0, 0, 0];
		offset(f, mercatorX(lng), mercatorY(lat), 842, o);
		expect(o[0]).toBeCloseTo(120, 6);
		expect(o[1]).toBeCloseTo(-45, 6);
		expect(o[2]).toBeCloseTo(12, 9);
	});

	it('in float64 it is the same projection as mainMatrix itself', () => {
		for (const pitch of [0, 45, 85])
			for (const roll of [-5, 0, 5]) {
				const c = { ...BOISE, zoom: 17, pitch, bearing: 30, roll, fov: 36.87 };
				const main = mainMatrix(c);
				const f = makeFrame(main, c.lng, c.lat, 830, W, H, (c.fov * Math.PI) / 180, c.zoom);
				for (const [e, n] of [
					[0, 0],
					[40, 70],
					[-90, 15]
				]) {
					const [lng, lat] = metres(c, e, n);
					const ref = reference(main, c, lng, lat, 833);
					const o: [number, number, number] = [0, 0, 0];
					offset(f, mercatorX(lng), mercatorY(lat), 833, o);
					const pt = { x: 0, y: 0, w: 0 };
					if (!projectLocal(f, o[0], o[1], o[2], pt)) continue;
					expect(Math.hypot(pt.x - ref.x, pt.y - ref.y)).toBeLessThan(1e-6);
				}
			}
	});

	it('in float32 (as the GPU) it stays within 0.05 px at z22.5 for pitch 0–85, fov 20–60 and roll ±5', () => {
		let worst = 0;
		for (const pitch of [0, 30, 60, 85])
			for (const fov of [20, 36.87, 60])
				for (const roll of [-5, 5]) {
					// The camera ~1 m up a 12 m pole looking across a street: z22.5.
					const c = { ...BOISE, lng: BOISE.lng + 0.0123456, lat: BOISE.lat + 0.0065432, zoom: 22.5, pitch, bearing: 17, roll, fov };
					const main = mainMatrix(c);
					const f = makeFrame(main, c.lng, c.lat, 830, W, H, (fov * Math.PI) / 180, c.zoom);
					for (let k = 0; k < 40; k++) {
						const [lng, lat] = metres(c, Math.sin(k) * 1.5, Math.cos(k * 1.3) * 1.5 + 0.5);
						const ref = reference(main, c, lng, lat, 830.4);
						if (!(ref.w > 0) || ref.x < 0 || ref.y < 0 || ref.x > W || ref.y > H) continue;
						const o: [number, number, number] = [0, 0, 0];
						offset(f, mercatorX(lng), mercatorY(lat), 830.4, o);
						const pt = { x: 0, y: 0 };
						expect(projectLocal32(f, o[0], o[1], o[2], pt)).toBe(true);
						worst = Math.max(worst, Math.hypot(pt.x - ref.x, pt.y - ref.y));
					}
				}
		expect(worst).toBeLessThan(0.05);
	});

	it('plain float32 Mercator is many pixels off at z22 (what RTC avoids)', () => {
		const c = { ...BOISE, lng: BOISE.lng + 0.0123456, lat: BOISE.lat + 0.0065432, zoom: 22, pitch: 60, bearing: 17, roll: 0, fov: 36.87 };
		const main = mainMatrix(c);
		let worst = 0;
		for (let k = 0; k < 40; k++) {
			const [lng, lat] = metres(c, Math.sin(k) * 2, Math.cos(k * 1.3) * 2 + 1);
			const ref = reference(main, c, lng, lat, 830);
			if (!(ref.w > 0) || ref.x < 0 || ref.y < 0 || ref.x > W || ref.y > H) continue;
			const pt = { x: 0, y: 0 };
			if (projectMercator32(main, mercatorX(lng), mercatorY(lat), 830, c.lat, W, H, pt)) worst = Math.max(worst, Math.hypot(pt.x - ref.x, pt.y - ref.y));
		}
		expect(worst).toBeGreaterThan(5);
	});

	it('pxPerMetreW gives the screen size of a metre at a clip depth', () => {
		const c = { ...BOISE, zoom: 18, pitch: 0, bearing: 0, roll: 0, fov: 36.87 };
		const main = mainMatrix(c);
		const f = makeFrame(main, c.lng, c.lat, 830, W, H, (c.fov * Math.PI) / 180, c.zoom);
		const a = { x: 0, y: 0, w: 0 };
		const b = { x: 0, y: 0, w: 0 };
		projectLocal(f, 0, 0, 0, a);
		projectLocal(f, 1, 0, 0, b);
		expect(Math.hypot(b.x - a.x, b.y - a.y)).toBeCloseTo(f.pxPerMetreW / a.w, 6);
		// Looking straight down, a metre at the centre is the ground resolution: 0.216 m/px at z18 (§14.4's table, 512 px tiles).
		expect(f.pxPerMetreW / a.w).toBeCloseTo((512 * 2 ** 18) / circumferenceAt(c.lat), 6);
		expect(1 / (f.pxPerMetreW / a.w)).toBeCloseTo(0.216, 3);
	});

	it('the matrix it hands the shaders is mainMatrix · T(origin) · S(k, −k, k), cast to float32', () => {
		const c = { ...BOISE, zoom: 14, pitch: 45, bearing: -12, roll: 0, fov: 36.87 };
		const main = mainMatrix(c);
		const f = makeFrame(main, c.lng, c.lat, 812, W, H, (c.fov * Math.PI) / 180, c.zoom);
		const k = 1 / circumferenceAt(c.lat);
		const expected = mul(main, mul(translate(mercatorX(c.lng), mercatorY(c.lat), 812 * k), scale(k, -k, k)));
		for (let i = 0; i < 16; i++) {
			expect(Math.abs(f.m64[i] - expected[i])).toBeLessThanOrEqual(1e-12 * Math.max(1, Math.abs(expected[i])));
			expect(f.m32[i]).toBe(Math.fround(f.m64[i]));
		}
	});
});
