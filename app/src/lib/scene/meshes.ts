/**
 * Meshes built in code (docs/14 §14.8, "Models"): pure functions returning
 * typed arrays, so there are no binary files, no loader and no license
 * question.
 *
 * Vertex layout (FLOATS_PER_VERTEX floats): position (metres), flat normal,
 * color (linear 0–1 sRGB values), and a tint index:
 *
 * - 0: the vertex color as built;
 * - 1: the instance's color (route-colored faces: the bus body, the pin);
 * - 2–5: the instance's slot colors 0–3 (the stop post's route flags; a slot
 *   left empty isn't drawn).
 *
 * Axes: buses, stop posts, poles and pins use x right, y forward, z up, with
 * the origin on the ground at the footprint's centre. The camera head uses
 * x right, y down (image y) and z forward along the view axis, with the
 * origin at the optical centre, so the solver's axes() map onto it directly.
 *
 * Triangles wind counter-clockwise seen from their normal's side, so back
 * faces can be culled.
 */
export const FLOATS_PER_VERTEX = 10;

export type MeshKind = 'bus' | 'stop' | 'pole' | 'head' | 'pin' | 'ring';

/** Triangle budgets (§14.8, "Models"); `ring` is the selection ground ring. */
export const BUDGETS: Record<MeshKind, number> = { bus: 300, stop: 60, pole: 80, head: 120, pin: 80, ring: 80 };

export interface Mesh {
	kind: MeshKind;
	vertices: Float32Array;
	indices: Uint16Array;
	/** Bounding box, metres. */
	min: [number, number, number];
	max: [number, number, number];
	/** Bounding sphere around the box centre (for picking and screen size). */
	center: [number, number, number];
	radius: number;
}

type V3 = [number, number, number];
type Rgb = [number, number, number];

export const TINT = { none: 0, instance: 1, slot0: 2 } as const;

/** #rrggbb → [0–1] ×3. */
export function rgb(hex: string): Rgb {
	const n = parseInt(hex.replace('#', ''), 16);
	return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

const INK = rgb('#2b2a33');
const CREAM = rgb('#fffbf4');
const ROOF = rgb('#f3ede2');
const TYRE = rgb('#35343b');
const STEEL = rgb('#8d8a86');
const GLASS = rgb('#3b4250');

const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a: V3): V3 => {
	const l = Math.hypot(a[0], a[1], a[2]) || 1;
	return [a[0] / l, a[1] / l, a[2] / l];
};

class Builder {
	v: number[] = [];
	i: number[] = [];
	#n = 0;

	/** A flat polygon (convex, in order) with one normal and color, fanned into triangles. */
	poly(pts: V3[], color: Rgb, tint = 0, normal?: V3): void {
		const n = normal ?? norm(cross(sub(pts[1], pts[0]), sub(pts[2], pts[0])));
		const base = this.#n;
		for (const p of pts) {
			this.v.push(p[0], p[1], p[2], n[0], n[1], n[2], color[0], color[1], color[2], tint);
			this.#n++;
		}
		for (let k = 1; k < pts.length - 1; k++) {
			// Wind counter-clockwise around the normal.
			const ccw = dot(cross(sub(pts[k], pts[0]), sub(pts[k + 1], pts[0])), n) >= 0;
			if (ccw) this.i.push(base, base + k, base + k + 1);
			else this.i.push(base, base + k + 1, base + k);
		}
	}

	/** Both faces of a flat polygon (flags, signs). */
	twoSided(pts: V3[], color: Rgb, tint = 0): void {
		const n = norm(cross(sub(pts[1], pts[0]), sub(pts[2], pts[0])));
		this.poly(pts, color, tint, n);
		this.poly([...pts].reverse(), color, tint, [-n[0], -n[1], -n[2]]);
	}

	/** An axis-aligned box; `skip` names faces left out ('-z' for a bottom nobody sees). */
	box(min: V3, max: V3, color: Rgb, tint = 0, skip: string[] = []): void {
		const [x0, y0, z0] = min;
		const [x1, y1, z1] = max;
		const faces: [string, V3[], V3][] = [
			['+x', [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]], [1, 0, 0]],
			['-x', [[x0, y1, z0], [x0, y0, z0], [x0, y0, z1], [x0, y1, z1]], [-1, 0, 0]],
			['+y', [[x1, y1, z0], [x0, y1, z0], [x0, y1, z1], [x1, y1, z1]], [0, 1, 0]],
			['-y', [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]], [0, -1, 0]],
			['+z', [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], [0, 0, 1]],
			['-z', [[x0, y1, z0], [x1, y1, z0], [x1, y0, z0], [x0, y0, z0]], [0, 0, -1]]
		];
		for (const [name, pts, n] of faces) if (!skip.includes(name)) this.poly(pts, color, tint, n);
	}

	/**
	 * A prism: a convex profile in the plane of axes (a, b), extruded along
	 * axis c from c0 to c1, with optional caps. `at(a, b, c)` builds the point.
	 */
	prism(profile: [number, number][], c0: number, c1: number, at: (a: number, b: number, c: number) => V3, color: Rgb | ((edge: number) => [Rgb, number]), caps: { start?: Rgb; end?: Rgb } = {}, tint = 0): void {
		const n = profile.length;
		const center: [number, number] = [profile.reduce((s, p) => s + p[0], 0) / n, profile.reduce((s, p) => s + p[1], 0) / n];
		const mid = at(center[0], center[1], (c0 + c1) / 2);
		for (let k = 0; k < n; k++) {
			const p = profile[k];
			const q = profile[(k + 1) % n];
			const quad: V3[] = [at(p[0], p[1], c0), at(q[0], q[1], c0), at(q[0], q[1], c1), at(p[0], p[1], c1)];
			let nrm = norm(cross(sub(quad[1], quad[0]), sub(quad[3], quad[0])));
			// Outward: away from the prism's axis.
			const facePt: V3 = [(quad[0][0] + quad[2][0]) / 2, (quad[0][1] + quad[2][1]) / 2, (quad[0][2] + quad[2][2]) / 2];
			if (dot(nrm, sub(facePt, mid)) < 0) nrm = [-nrm[0], -nrm[1], -nrm[2]];
			const [c, t] = typeof color === 'function' ? color(k) : [color, tint];
			this.poly(quad, c, t, nrm);
		}
		const capAt = (c: number, col: Rgb) => {
			const pts = profile.map((p) => at(p[0], p[1], c));
			let nrm = norm(sub(at(center[0], center[1], c), mid));
			this.poly(pts, col, 0, nrm);
		};
		if (caps.start) capAt(c0, caps.start);
		if (caps.end) capAt(c1, caps.end);
	}

	build(kind: MeshKind): Mesh {
		const vertices = new Float32Array(this.v);
		const min: V3 = [Infinity, Infinity, Infinity];
		const max: V3 = [-Infinity, -Infinity, -Infinity];
		for (let k = 0; k < vertices.length; k += FLOATS_PER_VERTEX)
			for (let a = 0; a < 3; a++) {
				min[a] = Math.min(min[a], vertices[k + a]);
				max[a] = Math.max(max[a], vertices[k + a]);
			}
		const center: V3 = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
		const radius = Math.hypot(max[0] - center[0], max[1] - center[1], max[2] - center[2]);
		return { kind, vertices, indices: new Uint16Array(this.i), min, max, center, radius };
	}
}

/** A regular polygon's points (radius r, `sides`), starting at angle a0. */
function circle(r: number, sides: number, a0 = 0): [number, number][] {
	return Array.from({ length: sides }, (_, k) => {
		const a = a0 + (k / sides) * Math.PI * 2;
		return [Math.cos(a) * r, Math.sin(a) * r] as [number, number];
	});
}

export const BUS = { length: 12.2, width: 2.6, height: 3.1 };

/**
 * The bus (§14.4 "Buses and stops"; ≤ 300 triangles): a bevelled 12.2 × 2.6 ×
 * 3.1 m body in the route color (tint 1) with a cream roof, an ink window
 * band, 8-sided wheels, a roof pod and a destination sign. Forward is +y.
 */
export function busMesh(): Mesh {
	const b = new Builder();
	const L = BUS.length / 2;
	const W = BUS.width / 2;
	const bottom = 0.42;
	const roof = 2.95;
	const bevel = 0.18;
	const winLow = 1.3;
	const winHigh = 2.5;
	// The body's cross-section (x, z), counter-clockwise from the bottom right.
	const profile: [number, number][] = [
		[W - bevel, bottom],
		[W, bottom + bevel],
		[W, winLow],
		[W, winHigh],
		[W, roof - bevel],
		[W - bevel, roof],
		[-W + bevel, roof],
		[-W, roof - bevel],
		[-W, winHigh],
		[-W, winLow],
		[-W, bottom + bevel],
		[-W + bevel, bottom]
	];
	// Per edge: underside ink; sides tinted; window band ink; the roof cream.
	const edgeLook = (k: number): [Rgb, number] => {
		if (k === 11) return [INK, 0];
		if (k === 2 || k === 8) return [GLASS, 0];
		if (k === 5) return [ROOF, 0];
		return [CREAM, 1];
	};
	b.prism(profile, -L + 0.02, L - 0.02, (x, z, y) => [x, y, z], edgeLook);
	// Front and back faces in the body color, then the glass and the sign just in front of them.
	const cap = (y: number) => profile.map(([x, z]) => [x, y, z] as V3);
	b.poly(cap(L - 0.02), CREAM, 1, [0, 1, 0]);
	b.poly(cap(-L + 0.02), CREAM, 1, [0, -1, 0]);
	const decal = (y: number, x0: number, x1: number, z0: number, z1: number, color: Rgb, n: V3) =>
		b.poly(
			[
				[x0, y, z0],
				[x1, y, z0],
				[x1, y, z1],
				[x0, y, z1]
			],
			color,
			0,
			n
		);
	decal(L - 0.01, -W + 0.12, W - 0.12, winLow - 0.25, winHigh, GLASS, [0, 1, 0]);
	decal(L, -W + 0.4, W - 0.4, winHigh + 0.07, roof - 0.06, CREAM, [0, 1, 0]);
	decal(-L, -W + 0.2, W - 0.2, winLow + 0.1, winHigh, GLASS, [0, -1, 0]);
	// The roof pod.
	b.box([-0.8, -2.6, roof], [0.8, 0.4, BUS.height], ROOF, 0, ['-z']);
	// Wheels: 8-sided, axis along x, the outer face just inside the body's width.
	const wheel = (x: number, y: number) => {
		const outer = x > 0 ? W - 0.02 : -W + 0.02;
		const inner = x > 0 ? W - 0.32 : -W + 0.32;
		b.prism(circle(0.5, 8), Math.min(inner, outer), Math.max(inner, outer), (yy, zz, xx) => [xx, y + yy, 0.5 + zz], TYRE, x > 0 ? { end: INK } : { start: INK });
	};
	for (const y of [L - 2.6, -L + 3.1]) for (const x of [1, -1]) wheel(x, y);
	return b.build('bus');
}

/**
 * The stop post (≤ 60 triangles): a sign post with a cream sign and four flag
 * slots below it, one per route (tint 2–5: the instance's slot colors).
 */
export function stopMesh(): Mesh {
	const b = new Builder();
	b.prism(circle(0.05, 6), 0, 2.4, (x, y, z) => [x, y, z], STEEL, { end: STEEL });
	// The sign: a thin box facing ±y.
	b.box([-0.25, -0.03, 2.4], [0.25, 0.03, 2.9], CREAM, 0);
	// Flag slots: small two-sided plates, stacked down the post.
	for (let s = 0; s < 4; s++) {
		const z1 = 2.32 - s * 0.24;
		const z0 = z1 - 0.18;
		b.twoSided(
			[
				[0.05, 0, z0],
				[0.4, 0, z0],
				[0.4, 0, z1],
				[0.05, 0, z1]
			],
			CREAM,
			TINT.slot0 + s
		);
	}
	return b.build('stop');
}

/** The camera pole (≤ 80 triangles): radius 0.15 m and 1 m tall; instances scale z to the height. */
export function poleMesh(): Mesh {
	const b = new Builder();
	b.prism(circle(0.15, 12), 0, 1, (x, y, z) => [x, y, z], STEEL, { end: STEEL });
	return b.build('pole');
}

/**
 * The camera head (≤ 120 triangles): x right, y down, z forward, with the
 * origin at the optical centre, so a basis of the solver's axes() (right,
 * down, forward) turns it to its heading, tilt and roll.
 */
export function headMesh(): Mesh {
	const b = new Builder();
	// Housing behind the lens.
	b.box([-0.13, -0.11, -0.46], [0.13, 0.11, -0.02], CREAM, 0);
	// Lens: an 8-sided barrel along z, glass in front.
	b.prism(circle(0.07, 8, Math.PI / 8), -0.02, 0, (x, y, z) => [x, y, z], INK, { end: GLASS });
	// Sun hood above (−y is up in the head's frame), and the mount below.
	b.box([-0.16, -0.15, -0.5], [0.16, -0.11, 0.08], ROOF, 0);
	b.box([-0.04, 0.11, -0.3], [0.04, 0.3, -0.18], STEEL, 0, ['+y']);
	return b.build('head');
}

/**
 * Pin and ring (≤ 80 triangles) for uncalibrated cameras: a pin standing at
 * ACHD's point and a dashed ring of about 25 m (the location's uncertainty),
 * both in the instance's color (tint 1).
 */
export function pinMesh(ringRadius = 25): Mesh {
	const b = new Builder();
	// An 8-sided cone, point down on the ground, and its flat top.
	const top = circle(0.45, 8);
	for (let k = 0; k < 8; k++) {
		const p = top[k];
		const q = top[(k + 1) % 8];
		const tri: V3[] = [
			[0, 0, 0.05],
			[q[0], q[1], 1.6],
			[p[0], p[1], 1.6]
		];
		const mid: V3 = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2, 0.4];
		let n = norm(cross(sub(tri[1], tri[0]), sub(tri[2], tri[0])));
		if (dot(n, mid) < 0) n = [-n[0], -n[1], -n[2]];
		b.poly(tri, CREAM, 1, n);
	}
	b.poly(
		top.map(([x, y]) => [x, y, 1.6] as V3),
		CREAM,
		1,
		[0, 0, 1]
	);
	// The dashed ring: 16 dashes on the ground, facing up.
	const dashes = 16;
	const w = 0.35;
	for (let k = 0; k < dashes; k++) {
		const a0 = (k / dashes) * Math.PI * 2;
		const a1 = a0 + (0.55 / dashes) * Math.PI * 2;
		const pt = (r: number, a: number): V3 => [Math.cos(a) * r, Math.sin(a) * r, 0.15];
		b.poly([pt(ringRadius - w, a0), pt(ringRadius + w, a0), pt(ringRadius + w, a1), pt(ringRadius - w, a1)], CREAM, 1, [0, 0, 1]);
	}
	return b.build('pin');
}

/**
 * The selection ground ring (§14.3: "an ink-and-cream ground ring"), radius
 * 1 m (instances scale it): an ink band outside a cream one, facing up.
 */
export function ringMesh(segments = 16): Mesh {
	const b = new Builder();
	const band = (r0: number, r1: number, color: Rgb) => {
		for (let k = 0; k < segments; k++) {
			const a0 = (k / segments) * Math.PI * 2;
			const a1 = ((k + 1) / segments) * Math.PI * 2;
			const pt = (r: number, a: number): V3 => [Math.cos(a) * r, Math.sin(a) * r, 0.05];
			b.poly([pt(r0, a0), pt(r1, a0), pt(r1, a1), pt(r0, a1)], color, 0, [0, 0, 1]);
		}
	};
	band(0.72, 0.86, CREAM);
	band(0.86, 1, INK);
	return b.build('ring');
}

export const MESHES: Record<MeshKind, () => Mesh> = { bus: busMesh, stop: stopMesh, pole: poleMesh, head: headMesh, pin: () => pinMesh(), ring: () => ringMesh() };

/** Every mesh, once (they're pure, so the result can be shared). */
let built: Record<MeshKind, Mesh> | null = null;
export function allMeshes(): Record<MeshKind, Mesh> {
	built ??= Object.fromEntries(Object.entries(MESHES).map(([k, f]) => [k, f()])) as Record<MeshKind, Mesh>;
	return built;
}

export const triangles = (m: Mesh) => m.indices.length / 3;
