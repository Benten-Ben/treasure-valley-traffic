import type { GeoJSONSource, MapGeoJSONFeature } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { addSlotted } from '#lib/map/order.js';
import type { Scene } from '#lib/scene/index.js';
import { take } from '../prefetch.js';
import { PRIORITY, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import { buildSegments, creditOf, fenceLayers, fenceSelection, GROUP, LAYER_IDS, LINE_LAYER, linesUrl, ORDER, propsOf, RADIUS_M, SCENE_FROM_ZOOM, SOURCE, WALLS_FROM_ZOOM, SEGMENT_CAP, M_PER_DEG, type FenceCollection, type FenceFeature } from './fences.js';
import Legend from './Legend.svelte';

/** Wait this long after the map stops before building the batch for the new view, ms. */
export const REBUILD_DEBOUNCE_MS = 250;
/** The batch is built again when the view's centre has moved this far from where it was built, metres. */
export const REBUILD_MOVE_M = RADIUS_M / 4;

const EMPTY: FenceCollection = { type: 'FeatureCollection', features: [] };

/** What the legend shows. */
export interface FencesView {
	/** Fences in the data. */
	fences: number;
	/** Segments in the 3D batch now. */
	segments: number;
	/** 3D walls are off on this device (a phone). */
	phone: boolean;
	/** The map is in 3D range (z15.5 and in). */
	walls: boolean;
}

const isPhone = () => typeof matchMedia === 'function' && matchMedia('(max-width: 599px)').matches;

/**
 * The Fences module (plan §4.2 P10):
 *
 * - **one GeoJSON** from /api/fences/lines (versioned, gzipped; about 1,500 lines), which feeds both the 2D line and the
 *   3D batch;
 * - **the 2D line** (a GeoJSON source and three line layers in `land`) from z14.5, at every zoom after;
 * - **low 3D walls** from z15.5, once the scene engine runs: the segments of the fences within 1.5 km of the view's
 *   centre (the nearest few thousand), built into one static batch and built again when the view has moved a good way.
 *   Off on a phone;
 * - a click on the line or on a wall selects the fence and opens its card.
 */
export class FencesModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	view = $state.raw<FencesView>({ fences: 0, segments: 0, phone: false, walls: false });
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{
			layerIds: [LINE_LAYER],
			priority: PRIORITY.fence,
			pick: (f: MapGeoJSONFeature): Selection | null => {
				const p = propsOf(f);
				return p ? this.#selection(this.#byId.get(p.id) ?? { type: 'Feature', geometry: f.geometry as GeoJSON.LineString, properties: p }) : null;
			}
		}
	];
	#ctx: AppCtx | null = null;
	#scope: MapScope | null = null;
	#visible = false;
	#destroyed = false;
	#features: FenceFeature[] = [];
	#byId = new globalThis.Map<string, FenceFeature>();
	#picks = new globalThis.Map<string, Selection>();
	#scene: Scene | null = null;
	#sceneState: 'none' | 'loading' | 'ready' | 'failed' = 'none';
	#builtAt: [number, number] | null = null;
	#timer: ReturnType<typeof setTimeout> | undefined;
	#phone = isPhone();
	#hovered: string | null = null;
	#debug: object | null = null;

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		let data: FenceCollection;
		try {
			const res = await take(linesUrl(ctx.meta));
			if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
			data = (await res.json()) as FenceCollection;
		} catch (e) {
			this.status = 'error';
			this.error = `Fences unavailable: ${e instanceof Error ? e.message : e}`;
			throw new Error(this.error);
		}
		this.#features = data.features ?? [];
		this.#byId = new globalThis.Map(this.#features.map((f) => [f.properties.id, f]));
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		const scope = (this.#scope = new MapScope(map));
		scope.addSource(SOURCE, { type: 'geojson', data: data ?? EMPTY, promoteId: 'id', attribution: creditOf(ctx.meta) });
		addSlotted(map, fenceLayers(), ORDER, (l, before) => scope.addLayer(l, before), 'fences');
		scope.on('moveend', () => this.#schedule());
		scope.on('zoom', () => this.#onZoom());
		scope.defer(ctx.picker.onHover((h) => this.#hover(h?.selection ?? null)));
		scope.defer(() => clearTimeout(this.#timer));
		scope.defer(() => this.#dropScene());
		this.#installDebug();
		scope.defer(() => this.#uninstallDebug());
		this.status = 'ready';
		this.updatedAt = Date.now();
		this.view = { ...this.view, fences: this.#features.length, phone: this.#phone };
		this.setVisible(this.#visible);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		const map = this.#scope?.map;
		if (!map) return;
		for (const id of LAYER_IDS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		if (on) {
			this.#onZoom();
			// Walls built before it was switched off may be for another place; #rebuild skips when the view is still there.
			if (this.#view3d()) this.#rebuild();
		} else {
			clearTimeout(this.#timer);
			this.#showWalls(false);
			this.#setHover(null);
		}
	}

	summary(): string | null {
		return this.#features.length ? `${this.#features.length.toLocaleString('en-US')} mapped fences and walls` : null;
	}

	// --- selections ---------------------------------------------------------------------------------

	#selection(f: FenceFeature): Selection {
		let s = this.#picks.get(f.properties.id);
		if (!s) {
			const c = f.geometry.coordinates;
			const mid = c[Math.floor(c.length / 2)];
			this.#picks.set(f.properties.id, (s = fenceSelection(f.properties, [mid[0], mid[1]])));
		}
		return s;
	}

	// --- the 3D walls --------------------------------------------------------------------------------

	#schedule() {
		if (!this.#visible || this.#sceneState !== 'ready') return;
		clearTimeout(this.#timer);
		this.#timer = setTimeout(() => this.#rebuild(), REBUILD_DEBOUNCE_MS);
	}

	#onZoom() {
		const map = this.#scope?.map;
		if (!map || !this.#visible) return;
		const zoom = map.getZoom();
		if (this.#sceneState === 'none' && !this.#phone && this.#features.length && zoom >= SCENE_FROM_ZOOM) this.#wantScene();
		const walls = this.#sceneState === 'ready' && zoom >= WALLS_FROM_ZOOM;
		this.#showWalls(walls);
		if (walls && !this.#builtAt) this.#rebuild();
		if (walls !== this.view.walls) this.view = { ...this.view, walls };
	}

	#view3d(): boolean {
		const map = this.#scope?.map;
		return !!map && this.#sceneState === 'ready' && map.getZoom() >= WALLS_FROM_ZOOM;
	}

	#showWalls(on: boolean) {
		const scene = this.#scene;
		if (!scene) return;
		const want = on && this.#visible;
		scene.show(GROUP, want);
		scene.showStatic(GROUP, want);
	}

	/** Build the batch for the view's centre, unless it is still where it was built. */
	#rebuild(force = false) {
		const scene = this.#scene;
		const map = this.#scope?.map;
		if (!scene || !map || this.#destroyed) return;
		const c = map.getCenter();
		const at = this.#builtAt;
		if (!force && at) {
			const dx = (c.lng - at[0]) * M_PER_DEG * Math.cos((c.lat * Math.PI) / 180);
			const dy = (c.lat - at[1]) * M_PER_DEG;
			if (Math.hypot(dx, dy) < REBUILD_MOVE_M) return;
		}
		if (map.getZoom() < WALLS_FROM_ZOOM - 0.5 && at) return;
		const segments = buildSegments(this.#features, [c.lng, c.lat], (f) => this.#selection(f), RADIUS_M, this.#phone ? 0 : SEGMENT_CAP);
		this.#builtAt = [c.lng, c.lat];
		scene.setStatic(GROUP, segments);
		scene.set(GROUP, [], { priority: PRIORITY.fence });
		this.#showWalls(map.getZoom() >= WALLS_FROM_ZOOM);
		this.view = { ...this.view, segments: segments.length };
	}

	/** Load the scene (never before the map's first idle: app.scene() waits for it). Walls stay off if it can't start. */
	#wantScene() {
		const ctx = this.#ctx;
		if (!ctx || this.#sceneState !== 'none') return;
		this.#sceneState = 'loading';
		ctx.scene().then(
			(scene) => this.#sceneReady(scene),
			(e) => {
				if (this.#destroyed) return;
				this.#sceneState = 'failed';
				console.warn(`Fences: 3D walls are off: ${e instanceof Error ? e.message : e}`);
			}
		);
	}

	#sceneReady(scene: Scene) {
		if (this.#destroyed || !this.#scope) return;
		if (!scene.ok) {
			this.#sceneState = 'failed';
			return;
		}
		this.#scene = scene;
		this.#sceneState = 'ready';
		this.#builtAt = null;
		this.#onZoom();
	}

	#dropScene() {
		const scene = this.#scene;
		this.#scene = null;
		if (this.#sceneState === 'ready') this.#sceneState = 'none';
		this.#builtAt = null;
		scene?.remove(GROUP);
	}

	// --- hover ---------------------------------------------------------------------------------------

	#hover(sel: Selection | null) {
		this.#setHover(sel?.kind === 'fence' && sel.layer === 'fences' ? sel.id : null);
	}

	/** A hovered line turns ink (feature-state; the walls get the scene's cream tint). */
	#setHover(id: string | null) {
		const map = this.#scope?.map;
		if (id === this.#hovered || !map?.getSource(SOURCE)) return;
		if (this.#hovered) map.setFeatureState({ source: SOURCE, id: this.#hovered }, { hover: false });
		this.#hovered = id;
		if (id && this.#byId.has(id)) map.setFeatureState({ source: SOURCE, id }, { hover: true });
	}

	destroy(): void {
		this.#destroyed = true;
		this.#scope?.dispose();
		this.#scope = null;
	}

	// --- debug ---------------------------------------------------------------------------------------

	/** A read-only handle for tests and the console: `__tvtFences`. */
	#installDebug() {
		const self = this;
		const handle = Object.freeze({
			info: () => ({
				visible: self.#visible,
				fences: self.#features.length,
				scene: self.#sceneState,
				segments: self.view.segments,
				walls: self.view.walls,
				phone: self.#phone,
				source: ((self.#scope?.map.getSource(SOURCE) as GeoJSONSource | undefined) ? 'ready' : 'none')
			}),
			/** A fence's middle on screen: id and px. */
			points: () => {
				const map = self.#scope?.map;
				if (!map) return [];
				return self.#features.map((f) => {
					const c = f.geometry.coordinates;
					const a = c[0];
					const b = c[c.length - 1];
					const p = map.project([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
					return { id: f.properties.id, x: p.x, y: p.y };
				});
			},
			/** The scene's counters (static segments drawn, draw calls). */
			sceneStats: () => self.#scene?.stats() ?? null,
			/** Build the 3D batch for the view now. */
			rebuild: () => self.#rebuild(true),
			/** Load the scene now (it loads by itself near z15). */
			load3d: () => {
				self.#wantScene();
				return self.#ctx ? self.#ctx.scene().then(() => self.#sceneState === 'ready') : Promise.resolve(false);
			}
		});
		Object.defineProperty(globalThis, '__tvtFences', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#debug = handle;
	}

	#uninstallDebug() {
		if ((globalThis as { __tvtFences?: unknown }).__tvtFences === this.#debug) Reflect.deleteProperty(globalThis, '__tvtFences');
		this.#debug = null;
	}
}

export function create(): LayerModule {
	return new FencesModule();
}
