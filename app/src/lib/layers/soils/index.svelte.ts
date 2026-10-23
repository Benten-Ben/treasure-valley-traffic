import type { MapGeoJSONFeature } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { layerSource } from '#lib/contracts/layer-tiles.js';
import type { SoilCard } from '#lib/server/soils/units.js';
import { parseHex } from '#lib/map/color.js';
import { addSlotted } from '#lib/map/order.js';
import { PRIORITY, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import Legend from './Legend.svelte';
import { ALL_IDS, ID, PICK_LAYERS, restyle, selectedFilter, soilLayers, SOURCE } from './layers.js';
import { DEFAULT_SHOW_BY, SHOW_BY, soilSelection, type ShowBy, type SoilProps } from './model.js';
import { PATTERN_INK } from './palette.js';
import { imageId, PATTERN_KEYS, PIXEL_RATIO, PIXELS, rasterize } from './patterns.js';
import { MAX_ZOOM, MIN_ZOOM, PLUGIN, LAYER } from './tiles.js';

const DETAILS_KEPT = 40;

/**
 * The Soils module (landscape sprint plan v3 §3.4 K6, P1-app):
 *
 * - one vector source from the soils tiles (`./tiles.ts`, z8-14: survey bounds, then map units, then
 *   polygons with their symbols), and the style layers of `./layers.ts` (the wash and its copy over Aerial,
 *   patterns, outlines, symbols and names), their pattern images made here from `./patterns.ts`;
 * - "Show by": which property the wash draws, re-styled in place (`setBy`);
 * - a click on a map unit selects it through the central picker (below every other layer) and opens the card
 *   (`Card.svelte`, which reads `GET /api/soils/mapunit/<mukey>`).
 */
export class SoilsModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	/** The property the wash draws. */
	by = $state<ShowBy>(DEFAULT_SHOW_BY);
	/** The credit the build recorded, for the legend. */
	credit = $state<string | null>(null);
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{
			layerIds: PICK_LAYERS,
			priority: PRIORITY.soil,
			pick: (f: MapGeoJSONFeature): Selection | null => soilSelection(f.properties as SoilProps)
		}
	];
	#scope: MapScope | null = null;
	#visible = false;
	#destroyed = false;
	#details = new globalThis.Map<string, Promise<SoilCard | null>>();
	#debug: object | null = null;

	async mount(ctx: AppCtx): Promise<void> {
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		const scope = (this.#scope = new MapScope(map));
		const source = layerSource(location.origin, ctx.meta, PLUGIN, LAYER, { minzoom: MIN_ZOOM, maxzoom: MAX_ZOOM });
		scope.addSource(SOURCE, source);
		this.credit = (source.attribution as string | undefined) ?? null;
		const ink = parseHex(PATTERN_INK);
		for (const k of PATTERN_KEYS) scope.addImage(imageId(k), { width: PIXELS, height: PIXELS, data: rasterize(k, ink) }, { pixelRatio: PIXEL_RATIO });
		const layers = soilLayers(this.by);
		const add = (l: Parameters<MapScope['addLayer']>[0], before?: string) => scope.addLayer(l, before);
		// The wash at rank 20 in areas; its Aerial copy at rank 5 in land; patterns and linework at 10; labels at 25.
		addSlotted(map, layers.areas, 20, add, 'soils');
		addSlotted(map, layers.copies, 5, add, 'soils');
		addSlotted(map, layers.land, 10, add, 'soils');
		addSlotted(map, layers.labels, 25, add, 'soils');
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
		for (const id of ALL_IDS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		if (!on) this.#mark(null);
	}

	/** Draw another property in the wash. */
	setBy(by: ShowBy): void {
		if (!SHOW_BY.includes(by) || by === this.by) return;
		this.by = by;
		const map = this.#scope?.map;
		if (!map) return;
		for (const op of restyle(by)) {
			if (!map.getLayer(op.id)) continue;
			if (op.filter) map.setFilter(op.id, op.filter as never);
			for (const [k, v] of op.paint ?? []) map.setPaintProperty(op.id, k as never, v as never);
		}
		this.updatedAt = Date.now();
	}

	/** One map unit's card data (kept for a while). */
	detail(mukey: string): Promise<SoilCard | null> {
		let p = this.#details.get(mukey);
		if (!p) {
			p = fetch(`/api/soils/mapunit/${encodeURIComponent(mukey)}`).then(async (res) => {
				if (res.status === 404) return null;
				if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
				return (await res.json()) as SoilCard;
			});
			p.catch(() => this.#details.delete(mukey));
			this.#details.set(mukey, p);
			if (this.#details.size > DETAILS_KEPT) this.#details.delete(this.#details.keys().next().value!);
		}
		return p;
	}

	selected(s: Selection | null): void {
		this.#mark(s?.layer === 'soils' && s.kind === 'soil' ? s.id : null);
	}

	/** Outline the selected map unit. */
	#mark(mukey: string | null) {
		const map = this.#scope?.map;
		if (map?.getLayer(ID.selected)) map.setFilter(ID.selected, selectedFilter(mukey) as never);
	}

	summary(): string | null {
		return null;
	}

	destroy(): void {
		this.#destroyed = true;
		this.#scope?.dispose();
		this.#scope = null;
	}

	/** A read-only handle for tests and the console: `__tvtSoils`. */
	#installDebug() {
		const self = this;
		const handle = Object.freeze({
			info: () => ({ visible: self.#visible, by: self.by }),
			/** A style layer's visibility, filter and zoom range as the map holds them now. */
			layer: (id: string) => {
				const map = self.#scope?.map;
				if (!map?.getLayer(id)) return null;
				const l = map.getLayer(id)!;
				return { visibility: map.getLayoutProperty(id, 'visibility') ?? 'visible', minzoom: l.minzoom, maxzoom: l.maxzoom, filter: map.getFilter(id) ?? null };
			},
			/** The map units drawn now (from the pick layer): key, symbol and screen point. */
			units: () => {
				const map = self.#scope?.map;
				if (!map) return [];
				return map.queryRenderedFeatures({ layers: PICK_LAYERS.filter((id) => map.getLayer(id)) }).map((f) => ({ ...(f.properties as SoilProps) }));
			},
			setBy: (by: ShowBy) => self.setBy(by)
		});
		Object.defineProperty(globalThis, '__tvtSoils', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#debug = handle;
	}

	#uninstallDebug() {
		if ((globalThis as { __tvtSoils?: unknown }).__tvtSoils === this.#debug) Reflect.deleteProperty(globalThis, '__tvtSoils');
		this.#debug = null;
	}
}

export function create(): LayerModule {
	return new SoilsModule();
}
