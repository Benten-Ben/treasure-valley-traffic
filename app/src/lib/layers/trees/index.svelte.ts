import type { GeoJSONSource, MapGeoJSONFeature } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { addSlotted } from '#lib/map/order.js';
import type { Scene, SceneInstance } from '#lib/scene/index.js';
import { historyOf } from '#lib/state/history.svelte.js';
import { take } from '../prefetch.js';
import { PRIORITY, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import def, { AREAS_URL } from './def.js';
import Legend from './Legend.svelte';
import {
	discCollection,
	discOpacity,
	DISCS,
	DISCS_ZOOM,
	inBox,
	intersects,
	KIND_OPACITY,
	KINDS,
	LIMIT_3D,
	LIMIT_DISCS,
	modelFade,
	MODELS_FADE,
	MODELS_ZOOM,
	SCENE_CAP,
	SCENE_FROM_ZOOM,
	SOURCE,
	stillServes,
	TREE_PREFIX,
	treeInstance,
	treeLayers,
	TREES_3D,
	treeSelection,
	treesUrl,
	wantedBox,
	type Box,
	type TreeArea,
	type TreeDetail,
	type TreeKind,
	type TreeRow,
	type TreesInView
} from './trees.js';

/** Wait this long after the map stops before asking for the view's trees, ms. */
export const FETCH_DEBOUNCE_MS = 250;
/** Tree details kept for the panel. */
const DETAILS_KEPT = 40;
const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };

/** What the legend shows about the view (written when it changes, never per frame). */
export interface TreesView {
	/** far: zoomed out past the discs; discs; models: 3D trees. */
	mode: 'far' | 'discs' | 'models';
	/** Trees fetched for the view, by kind. */
	kinds: Record<TreeKind, number>;
	shown: number;
	/** The API cut the view's trees to the tallest. */
	truncated: boolean;
	/** The scene got only the tallest `cap` of them. */
	capped: boolean;
	cap: number;
	/** Some built area is in or near the view. */
	here: boolean;
	/** The fetch failed: why. */
	problem: string | null;
}

const metresPerPx = (zoom: number, lat: number) => (40_075_016.686 * Math.cos((lat * Math.PI) / 180)) / (512 * 2 ** zoom);

/**
 * The Trees module (docs/19 §19.6):
 *
 * - where trees are built, from /api/trees/areas (the legend says so, and
 *   nothing is asked for where nothing is built);
 * - the view's trees from /api/trees, asked for when the map stops (250 ms
 *   later; a box that still serves the view isn't asked for again), the
 *   tallest first;
 * - **close up** (z15 and in, once the scene engine runs): one scene
 *   instance per tree, up to the tallest SCENE_CAP in view, dithering in over
 *   14.7–15 as the discs fade out;
 * - **farther out**, or when the scene can't start: crown discs (a circle
 *   layer from z13, sized in metres), with the same opacity by kind;
 * - a click on a tree (model or disc) selects it through the central picker
 *   and opens the tree panel (Card.svelte), which fetches /api/trees/<id>.
 */
export class TreesModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	areas = $state.raw<TreeArea[]>([]);
	view = $state.raw<TreesView>({ mode: 'far', kinds: { catalogued: 0, placed: 0, estimated: 0 }, shown: 0, truncated: false, capped: false, cap: SCENE_CAP, here: true, problem: null });
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{
			layerIds: [DISCS],
			priority: PRIORITY.tree,
			pick: (f: MapGeoJSONFeature): Selection | null => {
				const id = String(f.properties?.id ?? '');
				const row = this.#byId.get(id);
				return row ? treeSelection(row) : null;
			}
		}
	];
	/** Requests made to /api/trees (tests and the console). */
	requests = 0;
	#ctx: AppCtx | null = null;
	#scope: MapScope | null = null;
	#visible = false;
	#destroyed = false;
	#rows: TreeRow[] = [];
	#byId = new globalThis.Map<string, TreeRow>();
	#fetched: { box: Box; limit: number; truncated: boolean } | null = null;
	#abort: AbortController | null = null;
	#timer: ReturnType<typeof setTimeout> | undefined;
	#lastUrl: string | null = null;
	#scene: Scene | null = null;
	#sceneState: 'none' | 'loading' | 'ready' | 'failed' = 'none';
	/** The scene's group array (mutated in place). */
	#instances: SceneInstance[] = [];
	#instById = new globalThis.Map<string, SceneInstance>();
	#fade = -1;
	#modelsOn = false;
	#cap = SCENE_CAP;
	/** Trees asked for close up (LIMIT_3D; the measurement raises it). */
	#limit3d = LIMIT_3D;
	#hovered: string | null = null;
	#details = new globalThis.Map<string, Promise<TreeDetail | null>>();
	#debug: object | null = null;

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		let areas: TreeArea[];
		try {
			const res = await take(AREAS_URL);
			if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
			areas = ((await res.json()) as { areas: TreeArea[] }).areas ?? [];
		} catch (e) {
			this.status = 'error';
			this.error = `Trees unavailable: ${e instanceof Error ? e.message : e}`;
			throw new Error(this.error);
		}
		this.areas = areas;
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		const scope = (this.#scope = new MapScope(map));
		scope.addSource(SOURCE, { type: 'geojson', data: EMPTY, promoteId: 'id', attribution: 'Trees: USGS 3DEP lidar, City of Boise, US Forest Service' });
		addSlotted(map, treeLayers(), def.order, (l, before) => scope.addLayer(l, before));
		scope.on('moveend', () => this.#schedule());
		scope.on('resize', () => this.#schedule());
		scope.on('zoom', () => this.#onZoom());
		scope.defer(ctx.picker.onHover((h) => this.#hover(h?.selection ?? null)));
		scope.defer(() => {
			clearTimeout(this.#timer);
			this.#abort?.abort();
		});
		scope.defer(() => this.#dropScene());
		this.#installDebug();
		scope.defer(() => this.#uninstallDebug());
		this.status = 'ready';
		this.updatedAt = Date.now();
		this.setVisible(this.#visible);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		const map = this.#scope?.map;
		if (!map) return;
		if (map.getLayer(DISCS)) map.setLayoutProperty(DISCS, 'visibility', on ? 'visible' : 'none');
		if (on) {
			this.#onZoom();
			void this.#refresh();
		} else {
			clearTimeout(this.#timer);
			this.#abort?.abort();
			this.#showModels(false);
			this.#setHover(null);
		}
	}

	// --- the view's trees ----------------------------------------------------------------------------

	#schedule() {
		if (!this.#visible) return;
		clearTimeout(this.#timer);
		this.#timer = setTimeout(() => void this.#refresh(), FETCH_DEBOUNCE_MS);
	}

	/** Ask for the view's trees, unless what's here still serves it. */
	async #refresh(force = false): Promise<void> {
		const map = this.#scope?.map;
		if (!map || !this.#visible || this.#destroyed) return;
		const zoom = map.getZoom();
		const c = map.getCenter();
		const b = map.getBounds();
		const canvas = map.getCanvas();
		const radius = Math.hypot(canvas.clientWidth || 1024, canvas.clientHeight || 768) * metresPerPx(zoom, c.lat);
		const want = wantedBox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], [c.lng, c.lat], radius);
		const here = this.areas.some((a) => intersects(a.bounds, want));
		this.#setMode(zoom, here);
		if (zoom < DISCS_ZOOM) return;
		const limit = zoom >= SCENE_FROM_ZOOM ? this.#limit3d : LIMIT_DISCS;
		if (!here) {
			if (this.#rows.length) this.#setTrees({ trees: [], truncated: false }, want, limit);
			return;
		}
		if (!force && stillServes(this.#fetched, want, limit)) {
			this.#syncScene();
			return;
		}
		this.#abort?.abort();
		const ctl = (this.#abort = new AbortController());
		const url = treesUrl(want, limit);
		this.#lastUrl = url;
		this.requests++;
		try {
			const res = await fetch(url, { signal: ctl.signal });
			if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
			const data = (await res.json()) as TreesInView;
			if (ctl.signal.aborted || this.#destroyed) return;
			this.#setTrees(data, want, limit);
			if (this.view.problem) this.view = { ...this.view, problem: null };
		} catch (e) {
			if (ctl.signal.aborted || this.#destroyed) return;
			this.view = { ...this.view, problem: `Couldn't load the trees here: ${e instanceof Error ? e.message : e}` };
		}
	}

	#setTrees(data: TreesInView, box: Box, limit: number) {
		this.#rows = data.trees;
		this.#byId = new globalThis.Map(data.trees.map((t) => [t.id, t]));
		this.#fetched = { box, limit, truncated: data.truncated };
		// Models for trees no longer here are let go.
		for (const id of this.#instById.keys()) if (!this.#byId.has(id)) this.#instById.delete(id);
		const map = this.#scope?.map;
		(map?.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(discCollection(data.trees));
		this.#syncScene();
		const kinds: Record<TreeKind, number> = { catalogued: 0, placed: 0, estimated: 0 };
		for (const t of data.trees) kinds[t.kind]++;
		this.updatedAt = Date.now();
		this.view = { ...this.view, kinds, shown: data.trees.length, truncated: data.truncated, capped: this.#capped };
	}

	#setMode(zoom: number, here: boolean) {
		const models = this.#sceneState === 'ready' && zoom >= MODELS_ZOOM - MODELS_FADE;
		const mode: TreesView['mode'] = zoom < DISCS_ZOOM ? 'far' : models ? 'models' : 'discs';
		if (mode !== this.view.mode || here !== this.view.here) this.view = { ...this.view, mode, here };
	}

	// --- the 3D trees ----------------------------------------------------------------------------------

	#capped = false;

	/** Hand the scene the tallest trees in the view (up to the cap), as models. */
	#syncScene() {
		const scene = this.#scene;
		const map = this.#scope?.map;
		if (!scene || !map) return;
		const b = map.getBounds();
		const dx = (b.getEast() - b.getWest()) / 4;
		const dy = (b.getNorth() - b.getSouth()) / 4;
		const view: Box = [b.getWest() - dx, b.getSouth() - dy, b.getEast() + dx, b.getNorth() + dy];
		const fade = modelFade(map.getZoom());
		const list = this.#instances;
		list.length = 0;
		let inView = 0;
		for (const t of this.#rows) {
			if (!inBox(view, t.lng, t.lat)) continue;
			inView++;
			if (list.length >= this.#cap) continue;
			let inst = this.#instById.get(t.id);
			if (!inst) this.#instById.set(t.id, (inst = treeInstance(t, fade)));
			list.push(inst);
		}
		this.#capped = inView > list.length;
		this.#fade = -1;
		this.#applyFade(fade);
		scene.set(TREES_3D, list, { priority: PRIORITY.tree });
		if (this.view.capped !== this.#capped || this.view.cap !== this.#cap) this.view = { ...this.view, capped: this.#capped, cap: this.#cap };
	}

	#applyFade(fade: number) {
		if (fade === this.#fade) return;
		this.#fade = fade;
		for (const inst of this.#instances) {
			const row = this.#byId.get(inst.id.slice(TREE_PREFIX.length));
			if (row) inst.opacity = KIND_OPACITY[row.kind] * fade;
		}
		this.#scope?.map.triggerRepaint();
	}

	/** Zooming: ask for the scene near z15; models dither in as the discs fade out. */
	#onZoom() {
		const map = this.#scope?.map;
		if (!map || !this.#visible) return;
		const zoom = map.getZoom();
		if (this.#sceneState === 'none' && zoom >= SCENE_FROM_ZOOM) this.#wantScene();
		if (this.#sceneState === 'ready') {
			const fade = modelFade(zoom);
			this.#applyFade(fade);
			this.#showModels(fade > 0);
		}
		this.#setMode(zoom, this.view.here);
	}

	#showModels(on: boolean) {
		const scene = this.#scene;
		const want = on && this.#visible && this.#sceneState === 'ready';
		if (!scene || want === this.#modelsOn) return;
		this.#modelsOn = want;
		scene.show(TREES_3D, want);
	}

	/** Load the scene (never before the map's first idle: app.scene() waits for it). */
	#wantScene() {
		const ctx = this.#ctx;
		if (!ctx || this.#sceneState !== 'none') return;
		this.#sceneState = 'loading';
		ctx.scene().then(
			(scene) => this.#sceneReady(scene),
			(e) => {
				if (this.#destroyed) return;
				// Trees simply stay crown discs at every zoom.
				this.#sceneState = 'failed';
				console.warn(`Trees: 3D trees are off: ${e instanceof Error ? e.message : e}`);
			}
		);
	}

	#sceneReady(scene: Scene) {
		const map = this.#scope?.map;
		if (this.#destroyed || !map) return;
		if (!scene.ok) {
			this.#sceneState = 'failed';
			return;
		}
		this.#scene = scene;
		this.#sceneState = 'ready';
		// The discs give way to the models at z15, fading out as they dither in.
		if (map.getLayer(DISCS)) {
			map.setLayerZoomRange(DISCS, DISCS_ZOOM, MODELS_ZOOM);
			map.setPaintProperty(DISCS, 'circle-opacity', discOpacity(true) as never);
			map.setPaintProperty(DISCS, 'circle-stroke-opacity', discOpacity(true) as never);
		}
		scene.set(TREES_3D, this.#instances, { priority: PRIORITY.tree });
		scene.show(TREES_3D, false);
		this.#modelsOn = false;
		this.#syncScene();
		this.#onZoom();
		// The view may need the 3D limit now.
		void this.#refresh();
	}

	#dropScene() {
		const scene = this.#scene;
		this.#scene = null;
		if (this.#sceneState === 'ready') this.#sceneState = 'none';
		this.#modelsOn = false;
		scene?.remove(TREES_3D);
	}

	// --- hover, the panel, the legend's actions --------------------------------------------------------

	#hover(sel: Selection | null) {
		this.#setHover(sel?.kind === 'tree' && sel.layer === 'trees' ? sel.id : null);
	}

	/** A hovered disc gets an ink edge (feature-state; the models get the scene's cream tint). */
	#setHover(id: string | null) {
		const map = this.#scope?.map;
		if (id === this.#hovered || !map?.getSource(SOURCE)) return;
		if (this.#hovered) map.setFeatureState({ source: SOURCE, id: this.#hovered }, { hover: false });
		this.#hovered = id;
		if (id && this.#byId.has(id)) map.setFeatureState({ source: SOURCE, id }, { hover: true });
	}

	/** One tree's details for the panel (kept for a while). */
	detail(id: string): Promise<TreeDetail | null> {
		let p = this.#details.get(id);
		if (!p) {
			p = fetch(`/api/trees/${encodeURIComponent(id)}`).then(async (res) => {
				if (res.status === 404) return null;
				if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
				return (await res.json()) as TreeDetail;
			});
			p.catch(() => this.#details.delete(id));
			this.#details.set(id, p);
			if (this.#details.size > DETAILS_KEPT) this.#details.delete(this.#details.keys().next().value!);
		}
		return p;
	}

	/** Fly to a built area (the legend's "Go there"). */
	goTo(area: TreeArea): void {
		const ctx = this.#ctx;
		const map = this.#scope?.map;
		if (!ctx || !map) return;
		const [w, s, e, n] = area.bounds;
		const cam = map.cameraForBounds(
			[
				[w, s],
				[e, n]
			],
			{ padding: 60 }
		);
		const zoom = Math.min(17, Math.max(MODELS_ZOOM + 0.5, cam?.zoom ?? 16));
		const center = cam?.center ?? [(w + e) / 2, (s + n) / 2];
		const h = historyOf(ctx);
		if (h.attached) h.fly({ center, zoom, duration: 1200 });
		else map.flyTo({ center, zoom, duration: 1200 });
	}

	summary(): string | null {
		const n = this.areas.reduce((s, a) => s + a.trees, 0);
		return n ? `${n.toLocaleString('en-US')} trees` : null;
	}

	destroy(): void {
		this.#destroyed = true;
		this.#scope?.dispose();
		this.#scope = null;
	}

	// --- debug ---------------------------------------------------------------------------------------

	/** A read-only handle for tests and the console: `__tvtTrees`. */
	#installDebug() {
		const self = this;
		const handle = Object.freeze({
			info: () => ({
				visible: self.#visible,
				mode: self.view.mode,
				scene: self.#sceneState,
				modelsOn: self.#modelsOn,
				fetched: self.#rows.length,
				truncated: self.#fetched?.truncated ?? false,
				inScene: self.#instances.length,
				capped: self.#capped,
				cap: self.#cap,
				requests: self.requests,
				url: self.#lastUrl,
				areas: self.areas,
				kinds: Object.fromEntries(KINDS.map((k) => [k, self.view.kinds[k]]))
			}),
			/** The trees the scene drew in its last frame: id, screen centre and hit radius (px). */
			placed: () => {
				const ids = new Set(self.#instances.map((i) => i.id.slice(TREE_PREFIX.length)));
				return (self.#scene?.placed() ?? []).filter((p) => ids.has(p.id));
			},
			/** Crown discs drawn now: id and screen point. */
			discs: () => {
				const map = self.#scope?.map;
				if (!map?.getLayer(DISCS)) return [];
				return map.queryRenderedFeatures({ layers: [DISCS] }).map((f) => {
					const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates;
					const p = map.project([lng, lat]);
					return { id: String(f.properties?.id), x: p.x, y: p.y, r: Number(f.properties?.r) };
				});
			},
			sceneStats: () => self.#scene?.stats() ?? null,
			/** The models' cap and, optionally, the close-up limit asked of the API (the measurement). */
			setCap: (n: number, limit?: number) => {
				self.#cap = Math.max(0, Math.floor(n));
				if (limit) self.#limit3d = Math.min(LIMIT_DISCS, Math.max(1, Math.floor(limit)));
				self.#syncScene();
				void self.#refresh();
			},
			/** Ask for the view's trees now. */
			refresh: () => void self.#refresh(true),
			/** Load the scene now (it loads by itself near z15). */
			load3d: () => {
				self.#wantScene();
				return self.#ctx ? self.#ctx.scene().then(() => self.#sceneState === 'ready') : Promise.resolve(false);
			}
		});
		Object.defineProperty(globalThis, '__tvtTrees', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#debug = handle;
	}

	#uninstallDebug() {
		if ((globalThis as { __tvtTrees?: unknown }).__tvtTrees === this.#debug) Reflect.deleteProperty(globalThis, '__tvtTrees');
		this.#debug = null;
	}
}

export function create(): LayerModule {
	return new TreesModule();
}

