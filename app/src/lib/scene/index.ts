import type { CustomRenderMethodInput, Map } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import { SpriteAtlas } from '#lib/gl/atlas.js';
import type { Selection } from '#lib/layers/types.js';
import type { Loop } from '#lib/map/loop.js';
import type { Hit, HitSource, Hover } from '#lib/map/picker.js';
import { pxPerSecond } from '#lib/overlay/project.js';
import { CONE_FLOATS, Floats, LINE_FLOATS } from './batches/cone.js';
import { INSTANCE_FLOATS, InstanceData } from './batches/mesh.js';
import { PHOTO_FLOATS } from './batches/photo.js';
import { ShadowData } from './batches/shadow.js';
import { GroundTracker, renderedZ } from './ground.js';
import { addSceneLayer, createGpu, destroyGpu, SCENE_LAYER, sceneLayer, type Gpu } from './layer.js';
import { allMeshes, rgb, type Mesh, type MeshKind } from './meshes.js';
import { PickIndex, priorityOf, selectionKey } from './pick.js';
import { makeFrame, mercatorX, mercatorY, offset, projectLocal, projectMercator32, type Frame } from './rtc.js';
import { PhotoTextures } from './textures.js';

/**
 * The 3D mesh engine (docs/14 §14.8, "The 3D engine (instead of deck.gl)"):
 * our own WebGL2 custom layer, a lazy chunk loaded through `app.scene()`.
 *
 * Owners (3D buses and stops, 3D cameras) hand it groups of instances, much
 * like the overlay: `set(group, instances)`, and `update(group, fn)` for
 * things that move, run once per rendered frame. The engine:
 *
 * - places each instance relative to the centre (rtc.ts), on the drawn ground
 *   or at a true height (ground.ts), so it lands where `map.project` says;
 * - draws one instanced call per mesh type, then blob shadows, cones and
 *   lines, then photo planes: 12 draw calls or fewer in all;
 * - picks on the CPU through the central picker, and shows hover (a cream
 *   tint) and selection (lifted 2 m, 1.2×, an ink-and-cream ground ring and
 *   one 1.2 s pulse) for whatever the picker and the selection say;
 * - asks the render loop for frames only while something moves or eases;
 * - survives a lost WebGL context.
 *
 * Usage (3D buses, WP10; 3D cameras, WP13):
 *
 * ```ts
 * const scene = await app.scene();             // never before the first idle
 * scene.set('transit-buses-3d', buses);         // { id, mesh: 'bus', lng, lat, heading, pitch, color, opacity, shadow, pick }
 * scene.update('transit-buses-3d', (now, list) => { ...move them...; return fastestMps; });
 * scene.set('cameras-3d', [pole, head]);        // head: { mesh: 'head', alt, basis: axes(), minPx: 12, pick }
 * scene.setCones('cameras-3d', [cone]);         // apex and ray ends in true metres
 * scene.setLines('cameras-3d', edges);
 * await scene.textures.load(viewKey, frameUrl, { x: 0, y: 0, width, height: height - bar });
 * scene.setPhotos('cameras-3d', [{ apex, right, down, forward, tx, ty, texture: viewKey, label: name }]);
 * scene.show('transit-buses-3d', false);        // the owner's layer was turned off
 * ```
 */
export type { MeshKind } from './meshes.js';
export { renderedZ, slopePitch } from './ground.js';
export { allMeshes } from './meshes.js';
export { SCENE_LAYER } from './layer.js';

export type Vec3 = [number, number, number];
export type LngLatAlt = [number, number, number];

export interface SceneInstance {
	id: string;
	/** Default 'bus'. */
	mesh?: MeshKind;
	lng: number;
	lat: number;
	/** True height of the model's origin, metres (absolute). Unset: on the drawn ground. */
	alt?: number;
	/** The true ground under it when known (used when terrain is off). */
	groundAlt?: number;
	/** Metres above that (the selection adds 2). */
	lift?: number;
	/** Compass degrees (the model's +y), nose-up pitch and roll, degrees. */
	heading?: number;
	pitch?: number;
	roll?: number;
	/** Explicit model axes in east/north/up (x, y, z columns): overrides heading, pitch and roll. */
	basis?: [Vec3, Vec3, Vec3];
	scale?: number | Vec3;
	/** Grow so the model is at least this many px across on screen. */
	minPx?: number;
	/** The color of tinted faces (#rrggbb). */
	color?: string;
	/** Up to four slot colors (the stop post's route flags); null leaves a slot out. */
	slots?: (string | null)[];
	/** 0–1 (below 1 dithers: the disc-to-model crossfade). */
	opacity?: number;
	/** A blob shadow under it. */
	shadow?: boolean;
	/** What a click on it selects (null: not pickable). */
	pick?: Selection | null;
	/** Least hit radius, px (the picker adds its own minimum: 14 px, 22 for touch). */
	radius?: number;
}

/** A view cone: the apex and its ray ends, true metres (absolute). */
export interface SceneCone {
	id: string;
	apex: LngLatAlt;
	ends: LngLatAlt[];
	groundAlt?: number;
	color: string;
	/** Default 0.18. */
	opacity?: number;
}

/** A polyline of a fixed screen width; a point without a height sits on the drawn ground. */
export interface SceneLine {
	id: string;
	points: ([number, number] | LngLatAlt)[];
	groundAlt?: number;
	color: string;
	/** px, default 1.5. */
	width?: number;
	opacity?: number;
}

/**
 * A photo plane (§14.6, "The photo in the cone"): corners at
 * `apex + d·(forward ± tx·right ± ty·down)`; the front faces the apex.
 */
export interface ScenePhoto {
	id: string;
	apex: LngLatAlt;
	groundAlt?: number;
	/** Unit vectors, east/north/up (the solver's axes()). */
	right: Vec3;
	down: Vec3;
	forward: Vec3;
	/** tan(vfov/2)·W/H and tan(vfov/2). */
	tx: number;
	ty: number;
	/** Distance from the apex, metres; unset: sized to `widthPx` on screen. */
	d?: number;
	/** Default 140. */
	widthPx?: number;
	/** The longest d allowed when sizing by width (metres; default 80). */
	maxD?: number;
	/** A PhotoTextures key; a cream panel until it's uploaded. */
	texture?: string;
	/** The back panel's text (the camera's name). */
	label?: string;
	opacity?: number;
	/** False in look-through: nothing in front can cut it. */
	depthTest?: boolean;
}

/** Runs once per rendered frame; mutate in place; return m/s of the fastest, true for full rate, or false. */
export type SceneUpdate = (now: number, instances: SceneInstance[]) => number | boolean | void;

export interface GroupOptions {
	/** Picking priority for its instances (default: by each pick's kind). */
	priority?: number;
}

interface Group {
	instances: SceneInstance[];
	cones: SceneCone[];
	lines: SceneLine[];
	photos: ScenePhoto[];
	opts: GroupOptions;
	update: SceneUpdate | null;
	visible: boolean;
}

export interface SceneStats {
	frames: number;
	drawCalls: number;
	instances: number;
	/** JS time of the last frame (update, placement, upload and draw calls), ms. */
	lastFrameMs: number;
	/** p95 of the last 120 frames' JS time, ms. */
	p95Ms: number;
	/** Terrain queries in the last frame (things that moved, or everything after the camera moved). */
	groundQueries: number;
}

/** One probed instance: where the GPU put its anchor, and where `map.project` says. */
export interface ProbeRow {
	id: string;
	lng: number;
	lat: number;
	/** The GPU's result (transform feedback of the same placement the mesh shader uses), CSS px. */
	x: number;
	y: number;
	/** `map.project` (float64, with terrain), CSS px. */
	rx: number;
	ry: number;
	/** The drawn base height used, and `queryTerrainElevation` there, metres. */
	z: number;
	ground: number | null;
	/** Plain float32 Mercator (no RTC), for comparison, CSS px. */
	mx: number;
	my: number;
}

export interface SceneDeps {
	loop: Loop;
	picker?: { addSource(s: HitSource): () => void; onHover(fn: (h: Hover | null) => void): () => void } | null;
	selection?: { current: Selection | null; listen(fn: (s: Selection | null) => void): () => void } | null;
	/** The live terrain exaggeration (app.exaggeration()). */
	exaggeration: () => number;
	reducedMotion?: () => boolean;
}

const SELECT_LIFT = 2;
const SELECT_SCALE = 1.2;
const PULSE_MS = 1200;
const DEG = Math.PI / 180;
const CREAM = '#fffbf4';

const reduced = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

const ONES: Vec3 = [1, 1, 1];

/** Model axes (x right, y forward, z up) for a compass heading, nose-up pitch and roll (right side down), in east/north/up, written into `out`. */
export function hprInto(out: [Vec3, Vec3, Vec3], heading = 0, pitch = 0, roll = 0): [Vec3, Vec3, Vec3] {
	const sh = Math.sin(heading * DEG);
	const ch = Math.cos(heading * DEG);
	const sp = Math.sin(pitch * DEG);
	const cp = Math.cos(pitch * DEG);
	const sr = Math.sin(roll * DEG);
	const cr = Math.cos(roll * DEG);
	// Forward pitched up; up tilted back by the pitch; right and up turned about forward by the roll.
	const [right, f, up] = out;
	f[0] = sh * cp;
	f[1] = ch * cp;
	f[2] = sp;
	const u0 = -sh * sp;
	const u1 = -ch * sp;
	const u2 = cp;
	right[0] = ch * cr - u0 * sr;
	right[1] = -sh * cr - u1 * sr;
	right[2] = -u2 * sr;
	up[0] = ch * sr + u0 * cr;
	up[1] = -sh * sr + u1 * cr;
	up[2] = u2 * cr;
	return out;
}

/** Model axes for a compass heading, nose-up pitch and roll (right side down), in east/north/up. */
export function hprBasis(heading = 0, pitch = 0, roll = 0): [Vec3, Vec3, Vec3] {
	return hprInto(
		[
			[0, 0, 0],
			[0, 0, 0],
			[0, 0, 0]
		],
		heading,
		pitch,
		roll
	);
}

/** Pack #rrggbb (and alpha 0–255) into one uint for the slot colors. */
export function packColor(hex: string | null | undefined): number {
	if (!hex) return 0;
	const n = parseInt(hex.replace('#', ''), 16);
	return ((n << 8) | 255) >>> 0;
}

const p95 = (xs: number[]) => {
	if (!xs.length) return 0;
	const s = [...xs].sort((a, b) => a - b);
	return s[Math.min(s.length - 1, Math.floor(s.length * 0.95))];
};

export class Scene implements HitSource {
	/** The layer is running (WebGL2). */
	ok = false;
	/** Why it isn't, in words. */
	error: string | null = null;
	readonly layerId = SCENE_LAYER;
	readonly textures = new PhotoTextures();

	#deps: SceneDeps;
	#map: Map | null = null;
	#gpu: Gpu | null = null;
	#labels: SpriteAtlas;
	#groups = new globalThis.Map<string, Group>();
	#meshes: Record<MeshKind, Mesh> = allMeshes();
	#data = new globalThis.Map<MeshKind, InstanceData>();
	#shadows = new ShadowData();
	#cones = new Floats(CONE_FLOATS);
	#lines = new Floats(LINE_FLOATS);
	#photos = new Floats(PHOTO_FLOATS);
	#ground = new GroundTracker();
	#pick = new PickIndex();
	#frame: Frame | undefined;
	#size = { w: 0, h: 0 };
	#hoverKey = '';
	#selectedKey = '';
	/** Bumped when the drawn ground may have changed (camera moved, terrain tiles or settings changed). */
	#epoch = 0;
	/** Bumped only when terrain data changed (DEM tiles arrived, terrain set, context restored): heights queried before aren't trusted for culling. */
	#dataEpoch = 0;
	#selectedAt = 0;
	#cleanup: (() => void)[] = [];
	#times: number[] = [];
	#probe: { kind: MeshKind; local: Vec3; resolve: (rows: ProbeRow[]) => void; reject: (e: Error) => void } | null = null;
	/** Ids per mesh kind in the order they were written this frame (for the probe). */
	#order = new globalThis.Map<MeshKind, { id: string; lng: number; lat: number; z: number }[]>();
	#stats: SceneStats = { frames: 0, drawCalls: 0, instances: 0, lastFrameMs: 0, p95Ms: 0, groundQueries: 0 };
	#layer = sceneLayer({
		onAdd: (gl) => this.#setup(gl),
		onRemove: () => this.#teardown(),
		prerender: (gl) => this.#prerender(gl),
		render: (gl, args) => this.#render(gl, args)
	});

	constructor(deps: SceneDeps) {
		this.#deps = deps;
		this.#labels = new SpriteAtlas(Math.min(globalThis.devicePixelRatio || 1, 2), 512, 256);
		for (const k of Object.keys(this.#meshes) as MeshKind[]) this.#data.set(k, new InstanceData());
		this.textures.onReady = () => this.#repaint();
	}

	/** Add the custom layer to the map (before `anchor:scene`) and register with the picker. */
	attach(map: Map): boolean {
		this.#map = map;
		try {
			addSceneLayer(map, this.#layer);
		} catch (e) {
			this.#fail(e);
		}
		const onResize = () => {
			const c = map.getCanvas();
			this.#size = { w: c.clientWidth, h: c.clientHeight };
		};
		onResize();
		const onLost = () => this.#lose();
		// MapLibre rebuilds its style after a restore and drops custom layers: add ours again once it's back.
		const onRestored = () => {
			this.#epoch++;
			this.#dataEpoch++;
			const readd = () => {
				try {
					addSceneLayer(map, this.#layer);
				} catch (e) {
					this.#fail(e);
				}
			};
			if (map.isStyleLoaded()) readd();
			else map.once('style.load', readd);
		};
		// The drawn ground changes only when the camera moves, terrain tiles arrive or terrain is set.
		const bump = () => void this.#epoch++;
		const bumpData = () => {
			this.#epoch++;
			this.#dataEpoch++;
		};
		const onSource = (e: { sourceId?: string }) => {
			if (e.sourceId && e.sourceId === map.getTerrain()?.source) bumpData();
		};
		map.on('resize', onResize);
		map.on('webglcontextlost', onLost);
		map.on('webglcontextrestored', onRestored);
		map.on('move', bump);
		map.on('terrain', bumpData);
		map.on('sourcedata', onSource);
		this.#cleanup.push(() => {
			map.off('resize', onResize);
			map.off('webglcontextlost', onLost);
			map.off('webglcontextrestored', onRestored);
			map.off('move', bump);
			map.off('terrain', bumpData);
			map.off('sourcedata', onSource);
		});
		const d = this.#deps;
		if (d.picker) {
			this.#cleanup.push(d.picker.addSource(this));
			this.#cleanup.push(
				d.picker.onHover((h) => {
					const k = selectionKey(h?.selection);
					if (k !== this.#hoverKey) {
						this.#hoverKey = k;
						this.#repaint();
					}
				})
			);
		}
		if (d.selection) {
			this.#selectedKey = selectionKey(d.selection.current);
			this.#cleanup.push(
				d.selection.listen((s) => {
					this.#selectedKey = selectionKey(s);
					this.#selectedAt = performance.now();
					if (this.#selectedKey && !(d.reducedMotion ?? reduced)()) d.loop.tween('scene:pulse', PULSE_MS);
					this.#repaint();
				})
			);
		}
		for (const [key, g] of this.#groups) if (g.update) d.loop.want(`scene:${key}`, 60);
		return this.ok;
	}

	/** Remove the layer and every registration (the scene can't be used afterwards). */
	destroy(): void {
		for (const f of this.#cleanup.splice(0)) f();
		const map = this.#map;
		try {
			if (map?.getLayer(SCENE_LAYER)) map.removeLayer(SCENE_LAYER);
		} catch {
			/* the map is going away */
		}
		for (const key of this.#groups.keys()) this.#deps.loop.want(`scene:${key}`, null);
		this.#deps.loop.want('scene:ease', null);
		this.#groups.clear();
		this.textures.destroy();
		this.#map = null;
	}

	// Groups ------------------------------------------------------------------

	#group(name: string): Group {
		let g = this.#groups.get(name);
		if (!g) this.#groups.set(name, (g = { instances: [], cones: [], lines: [], photos: [], opts: {}, update: null, visible: true }));
		return g;
	}

	/** Replace a group's instances (kept by reference, so `update` may move them). */
	set(group: string, instances: SceneInstance[], opts: GroupOptions = {}): void {
		const g = this.#group(group);
		g.instances = instances;
		g.opts = { ...g.opts, ...opts };
		this.#repaint();
	}

	setCones(group: string, cones: SceneCone[]): void {
		this.#group(group).cones = cones;
		this.#repaint();
	}

	setLines(group: string, lines: SceneLine[]): void {
		this.#group(group).lines = lines;
		this.#repaint();
	}

	setPhotos(group: string, photos: ScenePhoto[]): void {
		this.#group(group).photos = photos;
		this.#repaint();
	}

	/** Run `fn` once per rendered frame for this group (null stops it). */
	update(group: string, fn: SceneUpdate | null): void {
		this.#group(group).update = fn;
		this.#deps.loop.want(`scene:${group}`, fn ? 60 : null);
		this.#repaint();
	}

	/** Show or hide a group (its owner's layer was toggled); hidden groups aren't drawn or picked. */
	show(group: string, on: boolean): void {
		const g = this.#group(group);
		if (g.visible === on) return;
		g.visible = on;
		if (!on) this.#deps.loop.want(`scene:${group}`, null);
		else if (g.update) this.#deps.loop.want(`scene:${group}`, 60);
		this.#repaint();
	}

	remove(group: string): void {
		this.#groups.delete(group);
		this.#deps.loop.want(`scene:${group}`, null);
		this.#repaint();
	}

	groups(): string[] {
		return [...this.#groups.keys()];
	}

	stats(): SceneStats {
		return { ...this.#stats };
	}

	/** The picker's hit test (HitSource). */
	hits(x: number, y: number, minRadius: number): Hit[] {
		return this.#pick.hits(x, y, minRadius);
	}

	/** Where each pickable instance was drawn in the last frame (screen centre and radius, px). */
	placed(): { id: string; x: number; y: number; r: number }[] {
		return this.#pick.placed().map((p) => ({ id: p.pick.id, x: p.x, y: p.y, r: p.r }));
	}

	/**
	 * Tests and the spike gate: on the next frame, project every `kind`
	 * instance's model point `local` on the GPU (the mesh shader's own
	 * placement, read back by transform feedback), next to `map.project`.
	 */
	probe(kind: MeshKind = 'bus', local: Vec3 = [0, 0, 0]): Promise<ProbeRow[]> {
		return new Promise((resolve, reject) => {
			this.#probe = { kind, local, resolve, reject };
			this.#repaint();
		});
	}

	// Lifecycle -----------------------------------------------------------------

	#repaint() {
		this.#map?.triggerRepaint();
	}

	#fail(e: unknown) {
		this.ok = false;
		this.error = `The 3D scene couldn't start: ${e instanceof Error ? e.message : e}`;
		console.warn(this.error);
	}

	#setup(gl: WebGL2RenderingContext) {
		if (this.#gpu && this.#gpu.gl === gl && !gl.isContextLost()) return;
		try {
			this.#gpu = createGpu(gl, this.#labels);
			this.ok = true;
			this.error = null;
		} catch (e) {
			this.#gpu = null;
			this.#fail(e);
		}
	}

	#teardown() {
		destroyGpu(this.#gpu);
		this.#gpu = null;
		this.#labels.destroy();
		this.#pick.clear();
		this.ok = false;
	}

	/** The context is gone: forget GPU objects (not deletable now); they're rebuilt on the next render. */
	#lose() {
		this.#gpu = null;
		this.#labels.lose();
		this.textures.lose();
		this.#pick.clear();
		this.ok = false;
	}

	#prerender(gl: WebGL2RenderingContext) {
		if (gl.isContextLost()) return;
		this.textures.prerender(gl);
	}

	// The frame -----------------------------------------------------------------

	#render(gl: WebGL2RenderingContext, args: CustomRenderMethodInput) {
		const map = this.#map;
		if (!map || gl.isContextLost()) return;
		if (!this.#gpu) {
			this.#setup(gl);
			if (!this.#gpu) return;
		}
		const gpu = this.#gpu;
		const t0 = performance.now();
		const deps = this.#deps;
		const wall = Date.now();
		const zoom = map.getZoom();
		const centre = map.getCenter();
		this.#stats.frames++;

		// Moving groups first: their update decides how many frames come next.
		for (const [key, g] of this.#groups) {
			if (!g.update || !g.visible) continue;
			const r = g.update(wall, g.instances);
			const fps = r === true ? 60 : typeof r === 'number' && r > 0 ? 2 * pxPerSecond(r, zoom, centre.lat) : null;
			deps.loop.want(`scene:${key}`, fps);
		}

		if (!this.#size.w) {
			const c = map.getCanvas();
			this.#size = { w: c.clientWidth, h: c.clientHeight };
		}
		const terrain = Boolean(map.getTerrain());
		const exag = terrain ? deps.exaggeration() : 0;
		const oz = terrain ? (map.queryTerrainElevation([centre.lng, centre.lat]) ?? 0) : 0;
		const f = (this.#frame = makeFrame(args.defaultProjectionData.mainMatrix, centre.lng, centre.lat, oz, this.#size.w, this.#size.h, args.fov, zoom, this.#frame));
		const now = performance.now();
		const still = (deps.reducedMotion ?? reduced)();
		this.#ground.begin();
		this.#pick.begin();
		for (const d of this.#data.values()) d.reset();
		for (const o of this.#order.values()) o.length = 0;
		this.#shadows.reset();
		this.#cones.reset();
		this.#lines.reset();
		this.#photos.reset();
		const cosC = Math.cos(centre.lat * DEG);
		const pulse = this.#pulse(now, still);
		let total = 0;

		/** True ground under a point (eased), and the drawn base height for a true height (or the ground). */
		const epoch = this.#epoch;
		const data = this.#dataEpoch;
		const groundAt = (id: string, lng: number, lat: number, groundAlt: number | undefined, fallback: number) => {
			if (!terrain) return groundAlt ?? fallback;
			return this.#ground.sample(id, lng, lat, () => map.queryTerrainElevation([lng, lat]) ?? 0, exag, now, still, epoch, data);
		};
		const zAt = (id: string, lng: number, lat: number, alt: number | undefined, groundAlt: number | undefined) => {
			const g = groundAt(id, lng, lat, groundAlt, alt ?? 0);
			return alt === undefined ? exag * g : renderedZ(alt, g, exag);
		};
		const pt = { x: 0, y: 0, w: 0 };
		const local: Vec3 = [0, 0, 0];
		const tested: ScenePhoto[] = [];
		const over: ScenePhoto[] = [];
		this.#lastMain = args.defaultProjectionData.mainMatrix;

		for (const [, g] of this.#groups) {
			if (!g.visible) continue;
			for (const inst of g.instances) {
				const kind = inst.mesh ?? 'bus';
				const mesh = this.#meshes[kind];
				if (!mesh) continue;
				const key = inst.pick && (this.#selectedKey || this.#hoverKey) ? selectionKey(inst.pick) : '';
				const selected = Boolean(key) && key === this.#selectedKey;
				const hover = Boolean(key) && key === this.#hoverKey;
				const mx = mercatorX(inst.lng);
				const my = mercatorY(inst.lat);
				const sv = typeof inst.scale === 'number' ? this.#sv.fill(inst.scale) : (inst.scale ?? ONES);
				let s = selected ? SELECT_SCALE * (1 + 0.08 * pulse) : 1;
				const lift = (inst.lift ?? 0) + (selected ? SELECT_LIFT : 0);
				// Off screen (judged on the ground last read under it): neither drawn, picked nor queried for its ground.
				// That reading counts only from the current terrain data: one taken before its DEM tile arrived
				// (0) could place it off screen for good, since a culled model isn't read again.
				const prev = terrain ? this.#ground.peek(inst.id, data) : undefined;
				if (prev !== undefined || !terrain) {
					const approx = terrain ? (inst.alt === undefined ? exag * prev! : renderedZ(inst.alt, prev!, exag)) : zAt(inst.id, inst.lng, inst.lat, inst.alt, inst.groundAlt);
					offset(f, mx, my, approx + lift, local);
					const rM = mesh.radius * 2 * Math.max(sv[0], sv[1], sv[2]) * s;
					if (projectLocal(f, local[0], local[1], local[2], pt)) {
						const m = Math.max((rM * f.pxPerMetreW) / pt.w, (inst.minPx ?? 0) / 2) + 64;
						if (pt.x < -m || pt.y < -m || pt.x > f.width + m || pt.y > f.height + m) continue;
					} else if (pt.w < -rM * f.worldPerMetre) continue;
				}
				const base = zAt(inst.id, inst.lng, inst.lat, inst.alt, inst.groundAlt);
				const z = base + lift;
				offset(f, mx, my, z, local);
				// Axes, with the instance's scale; east and north grow by the Mercator scale here over the centre's.
				const axes = inst.basis ?? hprInto(this.#axes, inst.heading, inst.pitch, inst.roll);
				const c = cosC / Math.cos(inst.lat * DEG);
				// Screen size: the bounding sphere's centre and radius.
				const ctr = mesh.center;
				const cx = local[0] + (axes[0][0] * ctr[0] * sv[0] + axes[1][0] * ctr[1] * sv[1] + axes[2][0] * ctr[2] * sv[2]) * s * c;
				const cy = local[1] + (axes[0][1] * ctr[0] * sv[0] + axes[1][1] * ctr[1] * sv[1] + axes[2][1] * ctr[2] * sv[2]) * s * c;
				const cz = local[2] + (axes[0][2] * ctr[0] * sv[0] + axes[1][2] * ctr[1] * sv[1] + axes[2][2] * ctr[2] * sv[2]) * s;
				const visible = projectLocal(f, cx, cy, cz, pt);
				const rMetres = mesh.radius * Math.max(sv[0], sv[1], sv[2]) * s;
				let rPx = visible ? (rMetres * f.pxPerMetreW) / pt.w : 0;
				if (visible && inst.minPx && 2 * rPx < inst.minPx && rPx > 0) {
					const grow = inst.minPx / (2 * rPx);
					s *= grow;
					rPx *= grow;
				}
				const d = this.#data.get(kind)!;
				const o = d.push();
				const a = d.f32;
				a[o] = local[0];
				a[o + 1] = local[1];
				a[o + 2] = local[2];
				for (let col = 0; col < 3; col++) {
					const k = sv[col] * s;
					a[o + 3 + col * 3] = axes[col][0] * k * c;
					a[o + 4 + col * 3] = axes[col][1] * k * c;
					a[o + 5 + col * 3] = axes[col][2] * k;
				}
				const color = this.#rgb(inst.color ?? CREAM);
				a[o + 12] = color[0];
				a[o + 13] = color[1];
				a[o + 14] = color[2];
				a[o + 15] = inst.opacity ?? 1;
				const u = d.u32;
				for (let k = 0; k < 4; k++) u[o + 16 + k] = packColor(inst.slots?.[k]);
				a[o + 20] = hover ? 1 : 0;
				let order = this.#order.get(kind);
				if (!order) this.#order.set(kind, (order = []));
				order.push({ id: inst.id, lng: inst.lng, lat: inst.lat, z });
				total++;

				if (inst.shadow || selected) {
					const gz = base - f.oz;
					const [e0, n0] = [local[0], local[1]];
					const halfLen = ((mesh.max[1] - mesh.min[1]) / 2) * sv[1] * s * c;
					const halfWid = ((mesh.max[0] - mesh.min[0]) / 2) * sv[0] * s * c;
					const fx = axes[1][0];
					const fy = axes[1][1];
					const fl = Math.hypot(fx, fy) || 1;
					if (inst.shadow) {
						const so = this.#shadows.push();
						const sh = this.#shadows.f32;
						sh[so] = e0;
						sh[so + 1] = n0;
						sh[so + 2] = gz + 0.08;
						sh[so + 3] = (fx / fl) * (halfLen + 0.5);
						sh[so + 4] = (fy / fl) * (halfLen + 0.5);
						sh[so + 5] = (fy / fl) * (halfWid + 0.5);
						sh[so + 6] = (-fx / fl) * (halfWid + 0.5);
						sh[so + 7] = inst.opacity ?? 1;
					}
					if (selected) {
						// The ground ring: wide enough to circle the footprint, with one pulse.
						const ring = this.#data.get('ring')!;
						const ro = ring.push();
						const rr = Math.max(Math.hypot(halfLen, halfWid) * 1.15, 1.5 * c) * (1 + 0.25 * pulse);
						const ra = ring.f32;
						ra[ro] = e0;
						ra[ro + 1] = n0;
						ra[ro + 2] = gz;
						ra.set([rr, 0, 0, 0, rr, 0, 0, 0, 1], ro + 3);
						ra.set([1, 1, 1, 1], ro + 12);
						for (let k = 0; k < 4; k++) ring.u32[ro + 16 + k] = 0;
						ra[ro + 20] = 0;
					}
				}
				if (inst.pick && visible) this.#pick.add({ x: pt.x, y: pt.y, r: Math.max(rPx, inst.radius ?? 0), w: pt.w, pick: inst.pick, priority: priorityOf(inst.pick, g.opts.priority) });
			}
			for (const cone of g.cones) this.#cone(cone, f, zAt);
			for (const line of g.lines) this.#line(line, f, zAt);
			for (const photo of g.photos) (photo.depthTest === false ? over : tested).push(photo);
		}
		// Depth-tested photo planes first, then those drawn over everything (look-through).
		for (const p of tested) this.#writePhoto(p, f, zAt, cosC);
		const split = this.#photos.n;
		for (const p of over) this.#writePhoto(p, f, zAt, cosC);

		// Draw: opaque models → blob shadows → cones and lines → photo planes.
		let calls = 0;
		const light = this.#light(map);
		gl.enable(gl.DEPTH_TEST);
		gl.depthFunc(gl.LEQUAL);
		gl.depthMask(true);
		gl.disable(gl.BLEND);
		gl.disable(gl.STENCIL_TEST);
		gl.enable(gl.CULL_FACE);
		gl.cullFace(gl.BACK);
		gl.frontFace(gl.CCW);
		calls += gpu.meshes.draw(this.#data, f.m32, light);
		// The probe (tests only) stalls until the GPU is done; keep it out of the frame's JS time.
		let probeMs = 0;
		if (this.#probe) {
			const p0 = performance.now();
			this.#runProbe(map, gpu);
			probeMs = performance.now() - p0;
		}
		gl.disable(gl.CULL_FACE);
		gl.enable(gl.BLEND);
		gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
		gl.depthMask(false);
		calls += gpu.shadows.draw(this.#shadows, f.m32);
		calls += gpu.cones.drawCones(this.#cones, f.m32);
		calls += gpu.cones.drawLines(this.#lines, f.m32, f.width, f.height, args.nearZ * 0.5);
		if (this.#photos.n) {
			// Depth-tested planes first, then those drawn over everything (look-through).
			gpu.photos.upload(this.#photos);
			calls += gpu.photos.draw(0, split, f.m32, this.textures);
			gl.disable(gl.DEPTH_TEST);
			calls += gpu.photos.draw(split, this.#photos.n - split, f.m32, this.textures);
			gl.enable(gl.DEPTH_TEST);
		}
		gl.depthMask(true);
		gl.disable(gl.BLEND);
		gl.bindVertexArray(null);
		this.#pick.commit();

		const ms = performance.now() - t0 - probeMs;
		this.#times.push(ms);
		if (this.#times.length > 120) this.#times.shift();
		this.#stats.drawCalls = calls;
		this.#stats.instances = total;
		this.#stats.lastFrameMs = ms;
		this.#stats.p95Ms = p95(this.#times);
		this.#stats.groundQueries = this.#ground.queries;
		// Keep frames coming while heights ease or the selection pulses.
		deps.loop.want('scene:ease', this.#ground.tweening ? 60 : null);
	}

	#axes: [Vec3, Vec3, Vec3] = [
		[1, 0, 0],
		[0, 1, 0],
		[0, 0, 1]
	];
	#sv: Vec3 = [1, 1, 1];
	#colors = new globalThis.Map<string, [number, number, number]>();

	/** #rrggbb → 0–1, parsed once per color. */
	#rgb(hex: string): [number, number, number] {
		let c = this.#colors.get(hex);
		if (!c) {
			if (this.#colors.size > 512) this.#colors.clear();
			this.#colors.set(hex, (c = rgb(hex)));
		}
		return c;
	}

	/** 0 → 1 → 0 over the pulse after a selection; 0 under reduced motion. */
	#pulse(now: number, still: boolean): number {
		if (still || !this.#selectedKey) return 0;
		const k = (now - this.#selectedAt) / PULSE_MS;
		return k >= 0 && k < 1 ? Math.sin(k * Math.PI) : 0;
	}

	/** The style's light, as a unit vector toward it in east/north/up. */
	#light(map: Map): [number, number, number] {
		const l = map.getLight?.() ?? {};
		const pos = Array.isArray(l.position) ? (l.position as number[]) : [1.15, 210, 30];
		const a = ((pos[1] + (l.anchor === 'map' ? 0 : map.getBearing())) * Math.PI) / 180;
		const p = (pos[2] * Math.PI) / 180;
		return [Math.sin(p) * Math.sin(a), Math.sin(p) * Math.cos(a), Math.cos(p)];
	}

	#cone(cone: SceneCone, f: Frame, zAt: (id: string, lng: number, lat: number, alt: number | undefined, g: number | undefined) => number) {
		if (cone.ends.length < 2) return;
		const [r, g, b] = rgb(cone.color);
		const a = cone.opacity ?? 0.18;
		const place = (p: LngLatAlt, id: string, out: Vec3) => {
			offset(f, mercatorX(p[0]), mercatorY(p[1]), zAt(id, p[0], p[1], p[2], cone.groundAlt), out);
		};
		const apex: Vec3 = [0, 0, 0];
		place(cone.apex, `${cone.id}#a`, apex);
		const ends = cone.ends.map((p, i) => {
			const v: Vec3 = [0, 0, 0];
			place(p, `${cone.id}#${i}`, v);
			return v;
		});
		const d = this.#cones;
		const put = (v: Vec3) => {
			const o = d.push();
			d.f32.set([v[0], v[1], v[2], r * a, g * a, b * a, a], o);
		};
		for (let i = 0; i < ends.length; i++) {
			put(apex);
			put(ends[i]);
			put(ends[(i + 1) % ends.length]);
		}
	}

	#line(line: SceneLine, f: Frame, zAt: (id: string, lng: number, lat: number, alt: number | undefined, g: number | undefined) => number) {
		const pts = line.points.map((p, i) => {
			const v: Vec3 = [0, 0, 0];
			offset(f, mercatorX(p[0]), mercatorY(p[1]), zAt(`${line.id}#${i}`, p[0], p[1], p[2], line.groundAlt) + (p[2] === undefined ? 0.3 : 0), v);
			return v;
		});
		const [r, g, b] = rgb(line.color);
		const op = line.opacity ?? 1;
		const width = line.width ?? 1.5;
		const d = this.#lines;
		for (let i = 0; i + 1 < pts.length; i++) {
			const A = pts[i];
			const B = pts[i + 1];
			// Two triangles: (a,+) (a,−) (b,+) and (b,+) (a,−) (b,−).
			for (const [t, side] of [
				[0, 1],
				[0, -1],
				[1, 1],
				[1, 1],
				[0, -1],
				[1, -1]
			]) {
				const o = d.push();
				d.f32.set([A[0], A[1], A[2], B[0], B[1], B[2], t, side, r * op, g * op, b * op, op, width], o);
			}
		}
	}

	#writePhoto(photo: ScenePhoto, f: Frame, zAt: (id: string, lng: number, lat: number, alt: number | undefined, g: number | undefined) => number, cosC: number) {
		const apex: Vec3 = [0, 0, 0];
		offset(f, mercatorX(photo.apex[0]), mercatorY(photo.apex[1]), zAt(`${photo.id}#a`, photo.apex[0], photo.apex[1], photo.apex[2], photo.groundAlt), apex);
		const c = cosC / Math.cos(photo.apex[1] * DEG);
		const sc = (v: Vec3): Vec3 => [v[0] * c, v[1] * c, v[2]];
		const R = sc(photo.right);
		const D = sc(photo.down);
		const F = sc(photo.forward);
		let d = photo.d;
		if (d === undefined) {
			// Size to about widthPx on screen: clip w is linear along the axis, w(d) = w0 + d·wf.
			const m = f.m64;
			const w0 = m[3] * apex[0] + m[7] * apex[1] + m[11] * apex[2] + m[15];
			const wf = m[3] * F[0] + m[7] * F[1] + m[11] * F[2];
			const target = photo.widthPx ?? 140;
			const den = 2 * photo.tx * f.pxPerMetreW - target * wf;
			const maxD = photo.maxD ?? 80;
			d = den > 0 && w0 > 0 ? Math.min(maxD, (target * w0) / den) : maxD;
			d = Math.max(0.5, d);
		}
		const corner = (sx: number, sy: number): Vec3 => [0, 1, 2].map((i) => apex[i] + d! * (F[i] + sx * photo.tx * R[i] + sy * photo.ty * D[i])) as Vec3;
		const tl = corner(-1, -1);
		const tr = corner(1, -1);
		const br = corner(1, 1);
		const bl = corner(-1, 1);
		const layer = this.textures.layer(photo.texture);
		const back = photo.label ? this.#gpu!.photos.label(photo.label) : [0, 0, 0, 0];
		const op = photo.opacity ?? 1;
		const out = this.#photos;
		// Counter-clockwise seen from the apex: (tl, bl, br) and (tl, br, tr).
		for (const [v, u, w] of [
			[tl, 0, 0],
			[bl, 0, 1],
			[br, 1, 1],
			[tl, 0, 0],
			[br, 1, 1],
			[tr, 1, 0]
		] as [Vec3, number, number][]) {
			const o = out.push();
			out.f32.set([v[0], v[1], v[2], u, w, layer, back[0], back[1], back[2], back[3], op], o);
		}
	}

	#runProbe(map: Map, gpu: Gpu) {
		const req = this.#probe!;
		this.#probe = null;
		try {
			const f = this.#frame!;
			const d = this.#data.get(req.kind)!;
			const clip = gpu.meshes.probe(req.kind, d.n, f.m32, req.local);
			const ids = this.#order.get(req.kind) ?? [];
			const rows: ProbeRow[] = [];
			const merc = { x: 0, y: 0 };
			const main = (this.#lastMain ?? f.m64) as ArrayLike<number>;
			for (let i = 0; i < d.n; i++) {
				const w = clip[i * 4 + 3];
				const meta = ids[i];
				if (!meta || !(w > 0)) continue;
				const ref = map.project([meta.lng, meta.lat]);
				projectMercator32(main, mercatorX(meta.lng), mercatorY(meta.lat), meta.z, f.lat, f.width, f.height, merc);
				rows.push({
					id: meta.id,
					lng: meta.lng,
					lat: meta.lat,
					x: ((clip[i * 4] / w + 1) / 2) * f.width,
					y: ((1 - clip[i * 4 + 1] / w) / 2) * f.height,
					rx: ref.x,
					ry: ref.y,
					z: meta.z,
					ground: map.queryTerrainElevation([meta.lng, meta.lat]),
					mx: merc.x,
					my: merc.y
				});
			}
			req.resolve(rows);
		} catch (e) {
			req.reject(e instanceof Error ? e : new Error(String(e)));
		}
	}

	#lastMain: ArrayLike<number> | null = null;
}

/** The scene for this map (the lazy chunk's entry; `app.scene()` calls it once). */
export async function createScene(app: AppCtx): Promise<Scene> {
	const map = await app.styleReady;
	const scene = new Scene({ loop: app.loop, picker: app.picker, selection: app.selection, exaggeration: () => app.exaggeration() });
	scene.attach(map);
	return scene;
}
