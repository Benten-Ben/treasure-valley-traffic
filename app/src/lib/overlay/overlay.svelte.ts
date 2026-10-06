import type { CustomLayerInterface, CustomRenderMethodInput, Map } from 'maplibre-gl';
import { SpriteAtlas, type SpriteDef } from '#lib/gl/atlas.js';
import { GrowableBuffer, staticBuffer } from '#lib/gl/buffer.js';
import { createProgram, type Program } from '#lib/gl/program.js';
import type { Selection } from '#lib/layers/types.js';
import { PRIORITY } from '#lib/layers/types.js';
import type { Loop } from '#lib/map/loop.js';
import { ANCHORS } from '#lib/map/order.js';
import type { Hit, HitSource } from '#lib/map/picker.js';
import { circumferenceAt, mercatorX, mercatorY, projectTo, pxPerSecond } from './project.js';

/**
 * The always-loaded 2D overlay (docs/14 §14.8, "The overlay"): one custom
 * layer, `overlay` (slot 13, the top of the map), that draws screen-aligned
 * sprites from one instance buffer: bus discs and their number plates,
 * selection rings, window number badges. It is part of the initial bundle, so
 * buses draw at the default view without the 3D chunk and without `setData`.
 *
 * - Sprites come from one atlas texture, drawn on a canvas once each.
 * - Each anchor (lon, lat, and its ground elevation from
 *   `queryTerrainElevation`) is projected on the CPU in float64 with the
 *   frame's `mainMatrix`, so sprites sit exactly where `map.project` says.
 * - `set(group, instances)` replaces a group; `update(group, fn)` runs `fn`
 *   once per rendered frame for things that move, and asks the loop for
 *   frames only while something does.
 * - Every group with a `pick` on its instances is hit-tested by the picker.
 * - If the custom layer can't start (no WebGL2), `ok` is false and `error`
 *   says why; owners fall back to MapLibre layers.
 */

export interface OverlayInstance {
	id: string;
	lng: number;
	lat: number;
	/** A sprite key registered with `sprite()`. */
	sprite: string;
	opacity?: number;
	/** Degrees clockwise on screen, or a compass bearing with `rotateWithMap`. */
	rotate?: number;
	rotateWithMap?: boolean;
	/** Screen offset, px. */
	offset?: [number, number];
	scale?: number;
	/** Metres above the drawn ground. */
	altitude?: number;
	/** What a click on it selects (null: not pickable). */
	pick?: Selection | null;
	/** Hit radius, px (default: half the sprite's larger side). */
	radius?: number;
}

export interface GroupOptions {
	/** Draw order between groups (higher on top). */
	z?: number;
	/** Picking priority for its instances (default: by each pick's kind). */
	priority?: number;
}

/**
 * Runs once per rendered frame for a moving group. Mutate the instances in
 * place; return the fastest speed in m/s (the loop gives 2 × its screen
 * speed in fps), true for full rate, or false/0 when nothing moves.
 */
export type UpdateFn = (now: number, instances: OverlayInstance[]) => number | boolean | void;

interface Group {
	instances: OverlayInstance[];
	opts: GroupOptions;
	update: UpdateFn | null;
}

interface Placed {
	x: number;
	y: number;
	r: number;
	inst: OverlayInstance;
	priority: number;
}

const FLOATS = 12; // x, y, w, h, u0, v0, u1, v1, ax, ay, opacity, rotation

const VERTEX = `#version 300 es
in vec2 a_corner;
in vec2 a_pos;
in vec2 a_size;
in vec4 a_uv;
in vec2 a_anchor;
in float a_opacity;
in float a_rot;
uniform vec2 u_viewport;
out vec2 v_uv;
out float v_opacity;
void main() {
	vec2 local = (a_corner - a_anchor) * a_size;
	float c = cos(a_rot);
	float s = sin(a_rot);
	vec2 p = a_pos + vec2(local.x * c - local.y * s, local.x * s + local.y * c);
	gl_Position = vec4(p.x / u_viewport.x * 2.0 - 1.0, 1.0 - p.y / u_viewport.y * 2.0, 0.0, 1.0);
	v_uv = mix(a_uv.xy, a_uv.zw, a_corner);
	v_opacity = a_opacity;
}`;

const FRAGMENT = `#version 300 es
precision mediump float;
in vec2 v_uv;
in float v_opacity;
uniform sampler2D u_tex;
out vec4 color;
void main() {
	color = texture(u_tex, v_uv) * v_opacity;
}`;

export class Overlay implements HitSource {
	/** The custom layer is running (WebGL2). */
	ok = $state(false);
	/** Why it isn't, in words. */
	error = $state<string | null>(null);

	readonly layerId = 'overlay';
	#map: Map | null = null;
	#loop: Loop | null = null;
	#groups = new globalThis.Map<string, Group>();
	#defs = new globalThis.Map<string, SpriteDef>();
	#atlas: SpriteAtlas | null = null;
	#gl: WebGL2RenderingContext | null = null;
	#program: Program | null = null;
	#vao: WebGLVertexArrayObject | null = null;
	#corners: WebGLBuffer | null = null;
	#instances: GrowableBuffer | null = null;
	#data = new Float32Array(FLOATS * 256);
	#placed: Placed[] = [];
	#positions = new globalThis.Map<string, { id: string; x: number; y: number; lng: number; lat: number }[]>();
	#size = { w: 0, h: 0 };
	#pt = { x: 0, y: 0 };
	/** Frames this layer drew (for tests and the ?perf HUD). */
	frames = 0;
	/** JS time of the last frame's update + projection + upload, ms. */
	lastFrameMs = 0;

	/** Register a sprite (drawn into the atlas the first time an instance uses it). */
	sprite(def: SpriteDef): void {
		this.#defs.set(def.key, def);
	}

	hasSprite(key: string): boolean {
		return this.#defs.has(key);
	}

	/** Replace a group's instances (they're kept by reference: `update` may move them). */
	set(group: string, instances: OverlayInstance[], opts: GroupOptions = {}): void {
		const g = this.#groups.get(group);
		if (g) {
			g.instances = instances;
			g.opts = { ...g.opts, ...opts };
		} else this.#groups.set(group, { instances, opts, update: null });
		this.#repaint();
	}

	/** Run `fn` once per rendered frame for this group (null stops it). */
	update(group: string, fn: UpdateFn | null): void {
		let g = this.#groups.get(group);
		if (!g) this.#groups.set(group, (g = { instances: [], opts: {}, update: null }));
		g.update = fn;
		// Frames until the first one measures how fast things move.
		this.#loop?.want(`overlay:${group}`, fn ? 60 : null);
		this.#repaint();
	}

	remove(group: string): void {
		this.#groups.delete(group);
		this.#positions.delete(group);
		this.#loop?.want(`overlay:${group}`, null);
		this.#repaint();
	}

	groups(): string[] {
		return [...this.#groups.keys()];
	}

	/** Where each of a group's instances was drawn in the last frame (anchor, CSS px). */
	positions(group: string): { id: string; x: number; y: number; lng: number; lat: number }[] {
		return this.#positions.get(group) ?? [];
	}

	/** The picker's hit test (HitSource). */
	hits(x: number, y: number, minRadius: number): Hit[] {
		const out: Hit[] = [];
		for (const p of this.#placed) {
			const sel = p.inst.pick;
			if (!sel) continue;
			const d = Math.hypot(p.x - x, p.y - y);
			if (d <= Math.max(p.r, minRadius)) out.push({ selection: sel, priority: p.priority, distance: d });
		}
		return out;
	}

	/** Add the custom layer (before `anchor:overlay`). Returns whether it's running. */
	attach(map: Map, loop: Loop): boolean {
		this.#map = map;
		this.#loop = loop;
		const pr = Math.min(globalThis.devicePixelRatio || 1, 2);
		this.#atlas = new SpriteAtlas(pr);
		const layer: CustomLayerInterface = {
			id: this.layerId,
			type: 'custom',
			renderingMode: '2d',
			onAdd: (_m, gl) => this.#setup(gl as WebGL2RenderingContext),
			onRemove: () => this.#teardown(),
			render: (gl, args) => this.#render(gl as WebGL2RenderingContext, args)
		};
		try {
			map.addLayer(layer, map.getLayer(ANCHORS.overlay) ? ANCHORS.overlay : undefined);
		} catch (e) {
			this.#fail(e);
		}
		map.on('resize', this.#onResize);
		map.on('webglcontextlost', this.#onLost);
		this.#onResize();
		for (const [key, g] of this.#groups) if (g.update) loop.want(`overlay:${key}`, 60);
		return this.ok;
	}

	detach(): void {
		const map = this.#map;
		if (!map) return;
		map.off('resize', this.#onResize);
		map.off('webglcontextlost', this.#onLost);
		try {
			if (map.getLayer(this.layerId)) map.removeLayer(this.layerId);
		} catch {
			/* the map is going away */
		}
		for (const key of this.#groups.keys()) this.#loop?.want(`overlay:${key}`, null);
		this.#map = null;
	}

	#fail(e: unknown) {
		this.ok = false;
		this.error = `The overlay couldn't start: ${e instanceof Error ? e.message : e}`;
		console.warn(this.error);
	}

	#repaint() {
		this.#map?.triggerRepaint();
	}

	#onResize = () => {
		const c = this.#map?.getCanvas();
		if (c) this.#size = { w: c.clientWidth, h: c.clientHeight };
	};

	#onLost = () => {
		// Everything GPU-side is gone; the next render after the restore rebuilds it.
		this.#gl = null;
		this.#program = null;
		this.#vao = null;
		this.#corners = null;
		this.#instances = null;
		this.#atlas?.lose();
	};

	#setup(gl: WebGL2RenderingContext) {
		try {
			if (typeof WebGL2RenderingContext === 'undefined' || !(gl instanceof WebGL2RenderingContext)) throw new Error('WebGL2 is not available');
			const p = createProgram(gl, VERTEX, FRAGMENT, ['a_corner', 'a_pos', 'a_size', 'a_uv', 'a_anchor', 'a_opacity', 'a_rot'], ['u_viewport', 'u_tex']);
			const vao = gl.createVertexArray();
			if (!vao) throw new Error('no vertex array');
			const corners = staticBuffer(gl, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]));
			const instances = new GrowableBuffer(gl);
			gl.bindVertexArray(vao);
			gl.bindBuffer(gl.ARRAY_BUFFER, corners);
			gl.enableVertexAttribArray(p.attribs.a_corner);
			gl.vertexAttribPointer(p.attribs.a_corner, 2, gl.FLOAT, false, 0, 0);
			gl.bindBuffer(gl.ARRAY_BUFFER, instances.buffer);
			const stride = FLOATS * 4;
			const attr = (name: string, size: number, offset: number) => {
				const loc = p.attribs[name];
				if (loc < 0) return;
				gl.enableVertexAttribArray(loc);
				gl.vertexAttribPointer(loc, size, gl.FLOAT, false, stride, offset * 4);
				gl.vertexAttribDivisor(loc, 1);
			};
			attr('a_pos', 2, 0);
			attr('a_size', 2, 2);
			attr('a_uv', 4, 4);
			attr('a_anchor', 2, 8);
			attr('a_opacity', 1, 10);
			attr('a_rot', 1, 11);
			gl.bindVertexArray(null);
			this.#gl = gl;
			this.#program = p;
			this.#vao = vao;
			this.#corners = corners;
			this.#instances = instances;
			this.ok = true;
			this.error = null;
		} catch (e) {
			this.#fail(e);
		}
	}

	#teardown() {
		const gl = this.#gl;
		if (gl && !gl.isContextLost()) {
			if (this.#program) gl.deleteProgram(this.#program.program);
			if (this.#vao) gl.deleteVertexArray(this.#vao);
			if (this.#corners) gl.deleteBuffer(this.#corners);
			this.#instances?.destroy();
			this.#atlas?.destroy();
		}
		this.#onLost();
		this.ok = false;
	}

	#render(gl: WebGL2RenderingContext, args: CustomRenderMethodInput) {
		const map = this.#map;
		if (!map || gl.isContextLost()) return;
		if (this.#gl !== gl || !this.#program) {
			this.#setup(gl);
			if (!this.#program) return;
		}
		const t0 = performance.now();
		this.frames++;
		const now = Date.now();
		const zoom = map.getZoom();
		const centerLat = map.getCenter().lat;
		const bearing = map.getBearing();

		// Moving groups first: their update decides how many frames come next.
		for (const [key, g] of this.#groups) {
			if (!g.update) continue;
			const r = g.update(now, g.instances);
			const fps = r === true ? 60 : typeof r === 'number' && r > 0 ? 2 * pxPerSecond(r, zoom, centerLat) : null;
			this.#loop?.want(`overlay:${key}`, fps);
		}

		if (!this.#size.w) this.#onResize();
		const { w: W, h: H } = this.#size;
		const m = args.defaultProjectionData.mainMatrix;
		const zScale = 1 / circumferenceAt(centerLat);
		const atlas = this.#atlas!;
		const pt = this.#pt;
		const order = [...this.#groups.entries()].sort((a, b) => (a[1].opts.z ?? 0) - (b[1].opts.z ?? 0));
		let total = 0;
		// Draw any new sprites first: the atlas may grow, which moves every UV.
		for (const [, g] of order) {
			total += g.instances.length;
			for (const inst of g.instances) {
				if (atlas.has(inst.sprite)) continue;
				const def = this.#defs.get(inst.sprite);
				if (def) atlas.ensure(def);
			}
		}
		const aw = atlas.width;
		const ah = atlas.height;
		if (this.#data.length < total * FLOATS) this.#data = new Float32Array(Math.max(total, this.#data.length / FLOATS * 2) * FLOATS);
		const data = this.#data;
		const placed: Placed[] = [];
		let n = 0;
		for (const [key, g] of order) {
			const positions: { id: string; x: number; y: number; lng: number; lat: number }[] = [];
			for (const inst of g.instances) {
				const def = this.#defs.get(inst.sprite);
				const rect = def && atlas.rect(inst.sprite);
				if (!def || !rect) continue;
				const elevation = (map.queryTerrainElevation([inst.lng, inst.lat]) ?? 0) + (inst.altitude ?? 0);
				if (!projectTo(pt, m, mercatorX(inst.lng), mercatorY(inst.lat), elevation, zScale, W, H)) continue;
				positions.push({ id: inst.id, x: pt.x, y: pt.y, lng: inst.lng, lat: inst.lat });
				const scale = inst.scale ?? 1;
				const w = def.width * scale;
				const h = def.height * scale;
				const x = pt.x + (inst.offset?.[0] ?? 0);
				const y = pt.y + (inst.offset?.[1] ?? 0);
				const reach = Math.max(w, h);
				if (x < -reach || y < -reach || x > W + reach || y > H + reach) continue;
				const opacity = inst.opacity ?? 1;
				if (opacity <= 0) continue;
				const rot = (((inst.rotate ?? 0) - (inst.rotateWithMap ? bearing : 0)) * Math.PI) / 180;
				const o = n * FLOATS;
				data[o] = x;
				data[o + 1] = y;
				data[o + 2] = w;
				data[o + 3] = h;
				data[o + 4] = rect.x / aw;
				data[o + 5] = rect.y / ah;
				data[o + 6] = (rect.x + rect.w) / aw;
				data[o + 7] = (rect.y + rect.h) / ah;
				data[o + 8] = 0.5;
				data[o + 9] = 0.5;
				data[o + 10] = opacity;
				data[o + 11] = rot;
				n++;
				if (inst.pick)
					placed.push({ x, y, r: inst.radius ?? reach / 2, inst, priority: g.opts.priority ?? PRIORITY[inst.pick.kind as keyof typeof PRIORITY] ?? PRIORITY.sprite });
			}
			this.#positions.set(key, positions);
		}
		this.#placed = placed;
		this.lastFrameMs = performance.now() - t0;
		if (!n) return;

		const p = this.#program;
		gl.useProgram(p.program);
		gl.bindVertexArray(this.#vao);
		this.#instances!.upload(data, n * FLOATS);
		gl.activeTexture(gl.TEXTURE0);
		atlas.bind(gl);
		gl.uniform1i(p.uniforms.u_tex, 0);
		gl.uniform2f(p.uniforms.u_viewport, W, H);
		gl.disable(gl.DEPTH_TEST);
		gl.disable(gl.STENCIL_TEST);
		gl.disable(gl.CULL_FACE);
		gl.enable(gl.BLEND);
		gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
		gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, n);
		gl.bindVertexArray(null);
	}
}
