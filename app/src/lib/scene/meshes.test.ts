import { describe, expect, it } from 'vitest';
import { allMeshes, BUDGETS, BUS, FLOATS_PER_VERTEX, triangles, type Mesh, type MeshKind } from './meshes.js';

/** Mesh budgets (docs/14 §14.8, "Models"): triangle budgets, bounding boxes, index ranges and the tint flag. */
const meshes = allMeshes();
const kinds = Object.keys(meshes) as MeshKind[];

const tints = (m: Mesh) => {
	const out = new Set<number>();
	for (let i = 9; i < m.vertices.length; i += FLOATS_PER_VERTEX) out.add(m.vertices[i]);
	return out;
};

describe('meshes', () => {
	it.each(kinds)('%s stays within its triangle budget', (kind) => {
		const m = meshes[kind];
		expect(m.indices.length % 3).toBe(0);
		expect(triangles(m)).toBeGreaterThan(0);
		expect(triangles(m)).toBeLessThanOrEqual(BUDGETS[kind]);
	});

	it('meets the plan’s budgets: bus 300, stop 60, pole 80, head 120, pin and ring 80', () => {
		expect(BUDGETS).toMatchObject({ bus: 300, stop: 60, pole: 80, head: 120, pin: 80 });
	});

	it.each(kinds)('%s indexes only its own vertices, with finite positions and unit normals', (kind) => {
		const m = meshes[kind];
		const n = m.vertices.length / FLOATS_PER_VERTEX;
		expect(Number.isInteger(n)).toBe(true);
		expect(n).toBeLessThan(65536);
		for (const i of m.indices) expect(i).toBeLessThan(n);
		for (let v = 0; v < n; v++) {
			const o = v * FLOATS_PER_VERTEX;
			for (let k = 0; k < 9; k++) expect(Number.isFinite(m.vertices[o + k])).toBe(true);
			expect(Math.hypot(m.vertices[o + 3], m.vertices[o + 4], m.vertices[o + 5])).toBeCloseTo(1, 5);
			for (let k = 6; k < 9; k++) expect(m.vertices[o + k]).toBeGreaterThanOrEqual(0);
		}
	});

	it.each(kinds)('%s winds every triangle counter-clockwise around its normal (back faces can be culled)', (kind) => {
		const m = meshes[kind];
		const p = (i: number) => [m.vertices[i * FLOATS_PER_VERTEX], m.vertices[i * FLOATS_PER_VERTEX + 1], m.vertices[i * FLOATS_PER_VERTEX + 2]];
		for (let t = 0; t < m.indices.length; t += 3) {
			const [a, b, c] = [p(m.indices[t]), p(m.indices[t + 1]), p(m.indices[t + 2])];
			const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
			const w = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
			const x = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]];
			const o = m.indices[t] * FLOATS_PER_VERTEX;
			const dot = x[0] * m.vertices[o + 3] + x[1] * m.vertices[o + 4] + x[2] * m.vertices[o + 5];
			expect(dot).toBeGreaterThan(0);
		}
	});

	it('the bus is a 12.2 × 2.6 × 3.1 m box standing on its origin, forward along +y', () => {
		const m = meshes.bus;
		expect(m.max[0] - m.min[0]).toBeCloseTo(BUS.width, 6);
		expect(m.max[1] - m.min[1]).toBeCloseTo(BUS.length, 6);
		expect(m.max[2] - m.min[2]).toBeCloseTo(BUS.height, 6);
		expect(m.min[2]).toBeCloseTo(0, 6);
		expect(m.min[0]).toBeCloseTo(-m.max[0], 6);
		expect(m.min[1]).toBeCloseTo(-m.max[1], 6);
	});

	it('the bus marks its body faces for the route color (tint 1), and its roof, glass and wheels not', () => {
		const t = tints(meshes.bus);
		expect(t.has(1)).toBe(true);
		expect(t.has(0)).toBe(true);
		const m = meshes.bus;
		let tinted = 0;
		let roofTinted = 0;
		for (let o = 0; o < m.vertices.length; o += FLOATS_PER_VERTEX) {
			if (m.vertices[o + 9] !== 1) continue;
			tinted++;
			// No upward-facing roof face takes the route color.
			if (m.vertices[o + 5] > 0.99) roofTinted++;
		}
		expect(tinted).toBeGreaterThan(20);
		expect(roofTinted).toBe(0);
	});

	it('the stop post has four flag slots (tints 2–5) on a post about 2.9 m tall', () => {
		const t = tints(meshes.stop);
		for (const s of [2, 3, 4, 5]) expect(t.has(s)).toBe(true);
		expect(meshes.stop.max[2]).toBeCloseTo(2.9, 6);
		expect(meshes.stop.min[2]).toBeCloseTo(0, 6);
	});

	it('the camera pole has a 0.15 m radius and a 1 m unit height (instances scale z)', () => {
		const m = meshes.pole;
		expect(m.max[0]).toBeCloseTo(0.15, 6);
		expect(m.min[2]).toBeCloseTo(0, 6);
		expect(m.max[2]).toBeCloseTo(1, 6);
	});

	it('the camera head has its origin at the optical centre and +z along the view axis', () => {
		const m = meshes.head;
		// The lens front sits at z = 0; the housing is behind it (−z), the hood above (−y in the head's frame).
		expect(m.max[2]).toBeGreaterThan(0);
		expect(m.max[2]).toBeLessThan(0.1);
		expect(m.min[2]).toBeLessThan(-0.4);
		const m0 = meshes.head.vertices;
		let glassFront = false;
		for (let o = 0; o < m0.length; o += FLOATS_PER_VERTEX) if (m0[o + 2] === 0 && m0[o + 5] > 0.99) glassFront = true;
		expect(glassFront).toBe(true);
		expect(m.min[1]).toBeLessThan(-0.11);
	});

	it('the pin stands on the ground with a dashed ring of about 25 m, all in the instance color', () => {
		const m = meshes.pin;
		expect(m.min[2]).toBeGreaterThanOrEqual(0);
		expect(m.max[0]).toBeGreaterThan(24.5);
		expect(m.max[0]).toBeLessThan(25.5);
		expect([...tints(m)]).toEqual([1]);
	});

	it('the selection ring is a flat ink-and-cream ring of radius 1', () => {
		const m = meshes.ring;
		expect(m.max[0]).toBeCloseTo(1, 6);
		expect(m.max[2] - m.min[2]).toBeCloseTo(0, 6);
		expect([...tints(m)]).toEqual([0]);
	});

	it('is pure: building twice gives identical arrays', async () => {
		const { busMesh } = await import('./meshes.js');
		expect(busMesh().vertices).toEqual(busMesh().vertices);
		expect(busMesh().indices).toEqual(busMesh().indices);
	});
});
