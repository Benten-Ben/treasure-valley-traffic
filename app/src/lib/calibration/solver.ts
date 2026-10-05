/**
 * Camera pose from point pairs (camera calibration).
 *
 * Camera model (docs/11, db/migrations/0002): a pinhole camera with square
 * pixels and the principal point at the image center.
 *  - heading: compass bearing the camera looks along (0 = north, clockwise), degrees
 *  - tilt: degrees below the horizon
 *  - roll: degrees, turning the image about the view axis
 *  - vfov: vertical field of view, degrees
 *
 * Coordinates are worked in a local east/north/up frame (meters) centered on
 * the camera's pole; within a few hundred meters the flat-earth error is
 * negligible. The fit is Levenberg-Marquardt on pixel reprojection error, with
 * a gentle prior that keeps the camera near its pole when points are few.
 */

export type LngLatZ = [number, number, number];
export type Pixel = [number, number];
export interface Pair {
	pixel: Pixel;
	ground: LngLatZ;
}
export interface ImageSize {
	width: number;
	height: number;
}
export interface Pose {
	lon: number;
	lat: number;
	alt: number; // meters above sea level
	heading: number;
	tilt: number;
	roll: number;
	vfov: number;
}
export interface Solution {
	pose: Pose;
	rms: number; // pixels, over the pairs only
	residuals: number[]; // pixels, per pair
	heightAboveGround: number; // meters above the median ground point
	hfov: number;
	iterations: number;
}

const R = 6378137;
const D2R = Math.PI / 180;
export const MIN_PAIRS = 4;
/** Prior: the camera sits within ~25 m of its pole (one pixel of cost per 25 m). */
const POLE_PRIOR_PX_PER_M = 1 / 25;

type Vec = [number, number, number];
const dot = (a: Vec, b: Vec) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: Vec, b: Vec): Vec => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

export function toLocal(origin: [number, number], p: LngLatZ): Vec {
	const [lon0, lat0] = origin;
	return [R * (p[0] - lon0) * D2R * Math.cos(lat0 * D2R), R * (p[1] - lat0) * D2R, p[2]];
}

export function fromLocal(origin: [number, number], v: Vec): LngLatZ {
	const [lon0, lat0] = origin;
	return [lon0 + v[0] / (R * D2R * Math.cos(lat0 * D2R)), lat0 + v[1] / (R * D2R), v[2]];
}

/** Camera axes in east/north/up: right, down (image y), forward. */
function axes(heading: number, tilt: number, roll: number): [Vec, Vec, Vec] {
	const h = heading * D2R, t = tilt * D2R, r = roll * D2R;
	const fwd: Vec = [Math.sin(h) * Math.cos(t), Math.cos(h) * Math.cos(t), -Math.sin(t)];
	const right0: Vec = [Math.cos(h), -Math.sin(h), 0];
	const down0 = cross(fwd, right0);
	const right: Vec = [0, 1, 2].map((i) => right0[i] * Math.cos(r) + down0[i] * Math.sin(r)) as Vec;
	const down: Vec = [0, 1, 2].map((i) => -right0[i] * Math.sin(r) + down0[i] * Math.cos(r)) as Vec;
	return [right, down, fwd];
}

/** params: [east, north, up, heading, tilt, roll, vfov] in the local frame. */
function projectLocal(params: number[], size: ImageSize, p: Vec): Pixel | null {
	const [e, n, u, heading, tilt, roll, vfov] = params;
	const [right, down, fwd] = axes(heading, tilt, roll);
	const v: Vec = [p[0] - e, p[1] - n, p[2] - u];
	const z = dot(v, fwd);
	if (z <= 0.01) return null;
	const f = size.height / 2 / Math.tan((vfov * D2R) / 2);
	return [size.width / 2 + (f * dot(v, right)) / z, size.height / 2 + (f * dot(v, down)) / z];
}

/** Where a ground point lands in the image for a pose, or null if behind the camera. */
export function project(pose: Pose, size: ImageSize, ground: LngLatZ): Pixel | null {
	const origin: [number, number] = [pose.lon, pose.lat];
	return projectLocal([0, 0, pose.alt, pose.heading, pose.tilt, pose.roll, pose.vfov], size,
		toLocal(origin, ground));
}

/** Where an image pixel's ray meets the horizontal plane at height groundZ, or null if it doesn't. */
export function pixelToGround(pose: Pose, size: ImageSize, px: Pixel, groundZ: number): LngLatZ | null {
	const [right, down, fwd] = axes(pose.heading, pose.tilt, pose.roll);
	const f = size.height / 2 / Math.tan((pose.vfov * D2R) / 2);
	const x = (px[0] - size.width / 2) / f, y = (px[1] - size.height / 2) / f;
	const ray: Vec = [0, 1, 2].map((i) => fwd[i] + x * right[i] + y * down[i]) as Vec;
	if (ray[2] >= -1e-6) return null;
	const s = (groundZ - pose.alt) / ray[2];
	return fromLocal([pose.lon, pose.lat], [s * ray[0], s * ray[1], groundZ]);
}

/**
 * The ground area a calibrated view sees: a polygon from the camera through
 * the image's left, bottom and right edges onto the plane at groundZ, cut
 * off at maxDistance meters (the far field is too coarse to be useful).
 */
export function footprint(pose: Pose, size: ImageSize, groundZ: number, maxDistance = 250): [number, number][] {
	const edge: Pixel[] = [];
	const steps = 12;
	for (let i = 0; i <= steps; i++) edge.push([0, (size.height * i) / steps]);
	for (let i = 1; i <= steps; i++) edge.push([(size.width * i) / steps, size.height]);
	for (let i = steps - 1; i >= 0; i--) edge.push([size.width, (size.height * i) / steps]);
	const origin: [number, number] = [pose.lon, pose.lat];
	const ring: [number, number][] = [[pose.lon, pose.lat]];
	for (const px of edge) {
		const g = pixelToGround(pose, size, px, groundZ);
		let v: Vec;
		if (g) {
			v = toLocal(origin, g);
		} else {
			// Above the horizon: run the ray's direction out to the cut-off distance.
			const [right, down, fwd] = axes(pose.heading, pose.tilt, pose.roll);
			const f = size.height / 2 / Math.tan((pose.vfov * D2R) / 2);
			const x = (px[0] - size.width / 2) / f;
			const y = (px[1] - size.height / 2) / f;
			v = [0, 1, 2].map((i) => fwd[i] + x * right[i] + y * down[i]) as Vec;
			v = [v[0] * 1e6, v[1] * 1e6, 0];
		}
		const d = Math.hypot(v[0], v[1]);
		const k = d > maxDistance ? maxDistance / d : 1;
		const p = fromLocal(origin, [v[0] * k, v[1] * k, groundZ]);
		ring.push([p[0], p[1]]);
	}
	ring.push([pose.lon, pose.lat]);
	return ring;
}

/** Median ground height of a calibration's pairs: the plane used for cones and draping. */
export function groundHeight(pairs: Pair[]): number {
	const zs = pairs.map((p) => p.ground[2]).sort((a, b) => a - b);
	return zs[Math.floor(zs.length / 2)];
}

function residualVector(params: number[], size: ImageSize, pts: Vec[], pixels: Pixel[]): number[] {
	const out: number[] = [];
	for (let i = 0; i < pts.length; i++) {
		const q = projectLocal(params, size, pts[i]);
		if (!q) out.push(1e4, 1e4);
		else out.push(q[0] - pixels[i][0], q[1] - pixels[i][1]);
	}
	out.push(params[0] * POLE_PRIOR_PX_PER_M, params[1] * POLE_PRIOR_PX_PER_M);
	return out;
}

const sumSq = (r: number[]) => r.reduce((s, v) => s + v * v, 0);

function solveLinear(a: number[][], b: number[]): number[] | null {
	const n = b.length;
	const m = a.map((row, i) => [...row, b[i]]);
	for (let c = 0; c < n; c++) {
		let p = c;
		for (let r = c + 1; r < n; r++) if (Math.abs(m[r][c]) > Math.abs(m[p][c])) p = r;
		if (Math.abs(m[p][c]) < 1e-12) return null;
		[m[c], m[p]] = [m[p], m[c]];
		for (let r = 0; r < n; r++) {
			if (r === c) continue;
			const k = m[r][c] / m[c][c];
			for (let k2 = c; k2 <= n; k2++) m[r][k2] -= k * m[c][k2];
		}
	}
	return m.map((row, i) => row[n] / row[i]);
}

const STEP = [0.01, 0.01, 0.01, 1e-3, 1e-3, 1e-3, 1e-3];
const LIMITS: [number, number][] = [[-500, 500], [-500, 500], [-1e4, 1e4], [-1e9, 1e9], [-89, 89], [-45, 45], [3, 120]];

function levenbergMarquardt(start: number[], size: ImageSize, pts: Vec[], pixels: Pixel[]) {
	let p = [...start];
	let r = residualVector(p, size, pts, pixels);
	let cost = sumSq(r);
	let lambda = 1e-3;
	let it = 0;
	for (; it < 300; it++) {
		const J = p.map((_, j) => {
			const hi = [...p], lo = [...p];
			hi[j] += STEP[j];
			lo[j] -= STEP[j];
			const rh = residualVector(hi, size, pts, pixels), rl = residualVector(lo, size, pts, pixels);
			return rh.map((v, i) => (v - rl[i]) / (2 * STEP[j]));
		});
		const JtJ = p.map((_, a) => p.map((__, b) => J[a].reduce((s, v, i) => s + v * J[b][i], 0)));
		const Jtr = p.map((_, a) => J[a].reduce((s, v, i) => s + v * r[i], 0));
		let improved = false;
		for (let tries = 0; tries < 10 && !improved; tries++) {
			const A = JtJ.map((row, a) => row.map((v, b) => (a === b ? v * (1 + lambda) + 1e-9 : v)));
			const delta = solveLinear(A, Jtr.map((v) => -v));
			if (!delta) {
				lambda *= 10;
				continue;
			}
			const next = p.map((v, j) => Math.min(LIMITS[j][1], Math.max(LIMITS[j][0], v + delta[j])));
			const rn = residualVector(next, size, pts, pixels);
			const cn = sumSq(rn);
			if (cn < cost) {
				const gain = cost - cn;
				p = next;
				r = rn;
				cost = cn;
				lambda = Math.max(lambda / 3, 1e-9);
				improved = true;
				if (gain < 1e-10 * (1 + cost)) return { params: p, cost, iterations: it + 1 };
			} else {
				lambda *= 4;
			}
		}
		if (!improved) break;
	}
	return { params: p, cost, iterations: it };
}

/**
 * Fit a pose to the pairs. pole: the camera's approximate [lon, lat] (from the
 * camera list). Returns null with fewer than MIN_PAIRS pairs.
 */
export function solve(pairs: Pair[], size: ImageSize, pole: [number, number]): Solution | null {
	if (pairs.length < MIN_PAIRS) return null;
	const pts = pairs.map((p) => toLocal(pole, p.ground));
	const pixels = pairs.map((p) => p.pixel);
	const zs = pts.map((p) => p[2]).sort((a, b) => a - b);
	const groundZ = zs[Math.floor(zs.length / 2)];
	const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
	const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
	const dist = Math.max(5, Math.hypot(cx, cy));
	const bearing = (Math.atan2(cx, cy) / D2R + 360) % 360;

	let best: { params: number[]; cost: number; iterations: number } | null = null;
	for (const height of [8, 15]) {
		for (const vfov of [25, 45, 70]) {
			for (const dh of [-30, 0, 30]) {
				const tilt = Math.atan2(height, dist) / D2R;
				const fit = levenbergMarquardt([0, 0, groundZ + height, bearing + dh, tilt, 0, vfov], size, pts, pixels);
				if (!best || fit.cost < best.cost) best = fit;
			}
		}
	}
	const p = best!.params;
	const residuals = pts.map((pt, i) => {
		const q = projectLocal(p, size, pt);
		return q ? Math.hypot(q[0] - pixels[i][0], q[1] - pixels[i][1]) : Infinity;
	});
	const rms = Math.sqrt(residuals.reduce((s, v) => s + v * v, 0) / residuals.length);
	const [lon, lat, alt] = fromLocal(pole, [p[0], p[1], p[2]]);
	const vfov = p[6];
	const hfov = (2 * Math.atan(Math.tan((vfov * D2R) / 2) * (size.width / size.height))) / D2R;
	return {
		pose: { lon, lat, alt, heading: ((p[3] % 360) + 360) % 360, tilt: p[4], roll: p[5], vfov },
		rms,
		residuals,
		heightAboveGround: alt - groundZ,
		hfov,
		iterations: best!.iterations
	};
}
