import { GrowableBuffer } from '#lib/gl/buffer.js';
import { createProgram, type Program } from '#lib/gl/program.js';
import type { Selection } from '#lib/layers/types.js';
import type { Hit } from '#lib/map/picker.js';
import { rgb, unitBoxMesh } from '../meshes.js';
import { priorityOf, segmentDistance, selectionKey } from '../pick.js';
import { circumferenceAt, mercatorX, mercatorY, originMatrix } from '../rtc.js';
import { INSTANCE_FLOATS, MESH_FRAGMENT, MESH_VERTEX, setInstanceAttribs, uploadMesh } from './mesh.js';

/**
 * The static batch (docs/19, fences; plan §4.2 S7): things that never move, drawn from one buffer in one call.
 *
 * A segment is a wall or a fence between two points. It is built into instances of one unit box
 * (the mesh shader's own instance layout), expressed in metres from the batch's own origin, so
 * float32 is exact at any zoom: the batch has its own matrix, `mainMatrix · T(origin) · S` (rtc.ts),
 * where the instanced meshes use the map centre's. Built and uploaded once per `setStatic`; its
 * heights are worked out again only when the terrain data changed (DEM tiles arrived), from the ground
 * read at each segment's ends.
 *
 * - solid: one box `thickness` wide (0.15 m for fences, 0.3 m for walls), `height` tall;
 * - open: a post every 2.5 m or less (`thickness` square), a top rail 0.08 m tall and, under it, a
 *   panel a quarter of the height tall and half as thick.
 *
 * A box follows the ground between a segment's ends: its along-axis carries the rise and its up-axis
 * stays vertical, so posts stand upright and rails slope.
 *
 * Picking is lazy: nothing is projected until a pointer event asks (`hits`).
 */
export interface StaticSegment {
	id: string;
	/** [lng, lat] of each end. */
	from: [number, number];
	to: [number, number];
	/** Metres above the ground. */
	height: number;
	/** Metres across (fences 0.15, walls 0.3). */
	thickness: number;
	look: 'solid' | 'open';
	/** #rrggbb. */
	color: string;
	/** What a click on it selects (null: not pickable). */
	pick: Selection | null;
}

export const POST_SPACING_M = 2.5;
export const RAIL_M = 0.08;
export const PANEL_SHARE = 0.25;
const DEG = Math.PI / 180;

/** How many boxes a segment takes. */
export function boxesFor(s: StaticSegment): number {
	if (s.look === 'solid') return 1;
	const len = lengthM(s);
	return Math.max(1, Math.ceil(len / POST_SPACING_M - 1e-6)) + 1 + 2;
}

function lengthM(s: StaticSegment): number {
	const cosLat = Math.cos(((s.from[1] + s.to[1]) / 2) * DEG);
	const dx = (s.to[0] - s.from[0]) * DEG * cosLat * 6371008.8;
	const dy = (s.to[1] - s.from[1]) * DEG * 6371008.8;
	return Math.hypot(dx, dy);
}

/** Maps a Mercator point and an absolute drawn height to CSS px; false when it is behind the camera. */
export type Projector = (mx: number, my: number, z: number, out: { x: number; y: number; w: number }) => boolean;

export class StaticData {
	readonly segments: StaticSegment[];
	/** The batch's origin: the middle of its bounding box (lng, lat), Mercator and 1 / circumference there. */
	readonly origin = { lng: 0, lat: 0, mx: 0, my: 0, k: 1 };
	/** True ground at each segment's ends (metres), from the last `ground`. */
	readonly groundTrue: Float32Array;
	/** The true ground at the origin, the zero of the batch's heights. */
	gOrigin = 0;
	/** The terrain epoch it was last grounded in (-1: not yet) and the exaggeration it is built for. */
	groundedEpoch = -1;
	exag = 0;
	/** performance.now() of the last grounding (the scene throttles on it). */
	groundedAt = -Infinity;
	/** Bumped whenever `f32` changes: the GPU copy is stale until it has uploaded this version. */
	version = 0;
	/** Counters for tests: how often the boxes were built, and the ground read. */
	builds = 0;
	grounds = 0;
	boxes = 0;
	buf: ArrayBuffer;
	f32: Float32Array;
	u32: Uint32Array;
	/** The first box and the box count of each segment. */
	readonly first: Uint32Array;
	readonly count: Uint32Array;
	readonly #colors: [number, number, number][];
	#keys: string[] | null = null;
	#hover = -1;

	constructor(segments: StaticSegment[]) {
		this.segments = segments;
		const n = segments.length;
		this.first = new Uint32Array(n);
		this.count = new Uint32Array(n);
		this.groundTrue = new Float32Array(2 * n);
		let total = 0;
		let [w, s, e, nn] = [Infinity, Infinity, -Infinity, -Infinity];
		for (let i = 0; i < n; i++) {
			const g = segments[i];
			this.first[i] = total;
			this.count[i] = boxesFor(g);
			total += this.count[i];
			for (const p of [g.from, g.to]) {
				w = Math.min(w, p[0]);
				e = Math.max(e, p[0]);
				s = Math.min(s, p[1]);
				nn = Math.max(nn, p[1]);
			}
		}
		this.boxes = total;
		this.buf = new ArrayBuffer(Math.max(1, total) * INSTANCE_FLOATS * 4);
		this.f32 = new Float32Array(this.buf);
		this.u32 = new Uint32Array(this.buf);
		if (n) {
			const lng = (w + e) / 2;
			const lat = (s + nn) / 2;
			this.origin = { lng, lat, mx: mercatorX(lng), my: mercatorY(lat), k: 1 / circumferenceAt(lat) };
		}
		this.#colors = segments.map((g) => rgb(g.color));
		this.rebuild(0);
	}

	/** Read the ground at every segment end (`query` gives the true ground in metres at a point) and build again. */
	ground(query: (lng: number, lat: number) => number, exag: number, epoch: number, now = 0): void {
		let sum = 0;
		for (let i = 0; i < this.segments.length; i++) {
			const g = this.segments[i];
			this.groundTrue[2 * i] = query(g.from[0], g.from[1]);
			this.groundTrue[2 * i + 1] = query(g.to[0], g.to[1]);
			sum += this.groundTrue[2 * i] + this.groundTrue[2 * i + 1];
		}
		this.gOrigin = this.segments.length ? sum / (2 * this.segments.length) : 0;
		this.grounds++;
		this.groundedEpoch = epoch;
		this.groundedAt = now;
		this.rebuild(exag);
	}

	/** Write every box again for this terrain exaggeration (0: flat ground), from the ground last read. */
	rebuild(exag: number): void {
		this.builds++;
		this.exag = exag;
		const { mx: ox, my: oy, k } = this.origin;
		const a = this.f32;
		const u = this.u32;
		const hoverIdx = this.#hover;
		for (let i = 0; i < this.segments.length; i++) {
			const g = this.segments[i];
			const [r, gr, b] = this.#colors[i];
			const e0 = (mercatorX(g.from[0]) - ox) / k;
			const n0 = -(mercatorY(g.from[1]) - oy) / k;
			const e1 = (mercatorX(g.to[0]) - ox) / k;
			const n1 = -(mercatorY(g.to[1]) - oy) / k;
			const z0 = exag * (this.groundTrue[2 * i] - this.gOrigin);
			const z1 = exag * (this.groundTrue[2 * i + 1] - this.gOrigin);
			const de = e1 - e0;
			const dn = n1 - n0;
			const len = Math.hypot(de, dn);
			// Unit along the segment and its right-hand side (any direction for a point).
			const ue = len > 1e-6 ? de / len : 1;
			const un = len > 1e-6 ? dn / len : 0;
			const th = g.thickness;
			const hover = i === hoverIdx ? 1 : 0;
			let o = this.first[i] * INSTANCE_FLOATS;
			const put = (cx: number, cy: number, cz: number, bx: [number, number, number], by: [number, number, number], bz: number) => {
				a[o] = cx;
				a[o + 1] = cy;
				a[o + 2] = cz;
				a[o + 3] = bx[0];
				a[o + 4] = bx[1];
				a[o + 5] = bx[2];
				a[o + 6] = by[0];
				a[o + 7] = by[1];
				a[o + 8] = by[2];
				a[o + 9] = 0;
				a[o + 10] = 0;
				a[o + 11] = bz;
				a[o + 12] = r;
				a[o + 13] = gr;
				a[o + 14] = b;
				a[o + 15] = 1;
				u[o + 16] = u[o + 17] = u[o + 18] = u[o + 19] = 0;
				a[o + 20] = hover;
				o += INSTANCE_FLOATS;
			};
			const across = (w: number): [number, number, number] => [un * w, -ue * w, 0];
			const whole: [number, number, number] = [de, dn, z1 - z0];
			if (g.look === 'solid') {
				put((e0 + e1) / 2, (n0 + n1) / 2, (z0 + z1) / 2, across(th), len > 1e-6 ? whole : [th * ue, th * un, 0], g.height);
				continue;
			}
			const posts = this.count[i] - 3;
			for (let j = 0; j <= posts; j++) {
				const t = j / posts;
				put(e0 + de * t, n0 + dn * t, z0 + (z1 - z0) * t, across(th), [ue * th, un * th, 0], g.height);
			}
			const rail = Math.min(RAIL_M, g.height / 2);
			const panel = Math.min(PANEL_SHARE * g.height, g.height - rail);
			const mid = (z0 + z1) / 2;
			put((e0 + e1) / 2, (n0 + n1) / 2, mid + g.height - rail, across(Math.min(th, 0.1)), whole, rail);
			put((e0 + e1) / 2, (n0 + n1) / 2, mid + g.height - rail - panel, across(th * 0.5), whole, panel);
		}
		this.version++;
	}

	/** The batch's matrix: metres from its origin → clip space, for the map's `mainMatrix` and the exaggeration it was built for. */
	matrix(main: ArrayLike<number>, out64: Float64Array, out32: Float32Array): void {
		originMatrix(main, this.origin.mx, this.origin.my, this.exag * this.gOrigin, this.origin.k, out64);
		out32.set(out64);
	}

	/** Tint the segment whose selection has this key (the picker's hover); '' clears it. True when the buffer changed. */
	setHover(key: string): boolean {
		let idx = -1;
		if (key) {
			this.#keys ??= this.segments.map((s) => (s.pick ? selectionKey(s.pick) : ''));
			idx = this.#keys.indexOf(key);
		}
		if (idx === this.#hover) return false;
		const set = (i: number, v: number) => {
			if (i < 0) return;
			for (let b = 0; b < this.count[i]; b++) this.f32[(this.first[i] + b) * INSTANCE_FLOATS + 20] = v;
		};
		set(this.#hover, 0);
		set(idx, 1);
		this.#hover = idx;
		this.version++;
		return true;
	}

	/**
	 * Lazy picking: the segments within max(minRadius, half their drawn height) of (x, y), by their
	 * mid-height line on screen. `project` maps Mercator x and y and an absolute drawn height to px.
	 */
	hits(project: Projector, x: number, y: number, minRadius: number, priority?: number): Hit[] {
		const out: Hit[] = [];
		const a = { x: 0, y: 0, w: 0 };
		const b = { x: 0, y: 0, w: 0 };
		const top = { x: 0, y: 0, w: 0 };
		const base = { x: 0, y: 0, w: 0 };
		const exag = this.exag;
		for (let i = 0; i < this.segments.length; i++) {
			const g = this.segments[i];
			if (!g.pick) continue;
			const g0 = exag * this.groundTrue[2 * i];
			const g1 = exag * this.groundTrue[2 * i + 1];
			const mx0 = mercatorX(g.from[0]);
			const my0 = mercatorY(g.from[1]);
			const mx1 = mercatorX(g.to[0]);
			const my1 = mercatorY(g.to[1]);
			const half = g.height / 2;
			if (!project(mx0, my0, g0 + half, a) || !project(mx1, my1, g1 + half, b)) continue;
			// Half the height on screen at the middle: a tall wall seen close is hit across its face.
			const mxm = (mx0 + mx1) / 2;
			const mym = (my0 + my1) / 2;
			const gm = (g0 + g1) / 2;
			let r = minRadius;
			if (project(mxm, mym, gm + g.height, top) && project(mxm, mym, gm, base)) r = Math.max(r, Math.abs(top.y - base.y) / 2);
			const d = segmentDistance(x, y, [a.x, a.y, b.x, b.y]);
			if (d <= r) out.push({ selection: g.pick, priority: priorityOf(g.pick, priority), distance: d });
		}
		return out;
	}
}

interface Gpu1 {
	buffer: GrowableBuffer;
	version: number;
}

/** Draws StaticData: one instanced call each, with the unit box and the mesh shader. */
export class StaticBatch {
	#gl: WebGL2RenderingContext;
	#program: Program;
	#vao: WebGLVertexArrayObject;
	#vbo: WebGLBuffer;
	#ibo: WebGLBuffer;
	#indexCount: number;
	#data = new Map<StaticData, Gpu1>();

	constructor(gl: WebGL2RenderingContext) {
		this.#gl = gl;
		this.#program = createProgram(gl, MESH_VERTEX, MESH_FRAGMENT, [], ['u_m', 'u_light']);
		const box = unitBoxMesh();
		const { vao, vbo, ibo } = uploadMesh(gl, box);
		gl.bindVertexArray(null);
		this.#vao = vao;
		this.#vbo = vbo;
		this.#ibo = ibo;
		this.#indexCount = box.indices.length;
	}

	/** Draw one batch (opaque pass: depth test and write on, back faces culled). Returns the draw calls made (0 or 1). */
	draw(d: StaticData, m32: Float32Array, light: [number, number, number]): number {
		if (!d.boxes) return 0;
		const gl = this.#gl;
		let g = this.#data.get(d);
		if (!g) this.#data.set(d, (g = { buffer: new GrowableBuffer(gl), version: -1 }));
		if (g.version !== d.version) {
			g.buffer.upload(d.f32, d.boxes * INSTANCE_FLOATS);
			g.version = d.version;
		}
		const p = this.#program;
		gl.useProgram(p.program);
		gl.uniformMatrix4fv(p.uniforms.u_m, false, m32);
		gl.uniform3f(p.uniforms.u_light, light[0], light[1], light[2]);
		gl.bindVertexArray(this.#vao);
		setInstanceAttribs(gl, g.buffer.buffer);
		gl.drawElementsInstanced(gl.TRIANGLES, this.#indexCount, gl.UNSIGNED_SHORT, 0, d.boxes);
		gl.bindVertexArray(null);
		return 1;
	}

	/** Free a batch's buffer (it was replaced or removed). */
	forget(d: StaticData): void {
		const g = this.#data.get(d);
		if (!g) return;
		if (!this.#gl.isContextLost()) g.buffer.destroy();
		this.#data.delete(d);
	}

	destroy(): void {
		const gl = this.#gl;
		if (gl.isContextLost()) return;
		for (const g of this.#data.values()) g.buffer.destroy();
		this.#data.clear();
		gl.deleteProgram(this.#program.program);
		gl.deleteVertexArray(this.#vao);
		gl.deleteBuffer(this.#vbo);
		gl.deleteBuffer(this.#ibo);
	}
}
