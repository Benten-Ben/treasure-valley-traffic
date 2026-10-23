import type { MapGeoJSONFeature, VectorTileSource } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { layerSource } from '#lib/contracts/layer-tiles.js';
import { parseHex } from '#lib/map/color.js';
import { addSlotted } from '#lib/map/order.js';
import { take } from '../prefetch.js';
import { PRIORITY, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import { YEAR_URL } from './def.js';
import { ALL_IDS, cropLayers, DEFAULT_GROWTH, ID, PICK_LAYERS, restyle, selectedFilter, SOURCE_FIELDS, SOURCE_YEAR, type CropState } from './layers.js';
import Legend from './Legend.svelte';
import { fieldSelection, groupInYear, yearsOf, type FieldCard, type FieldProps, type YearInfo } from './model.js';
import { PATTERN_INK } from './palette.js';
import { imageId, PATTERN_KEYS, PATTERNS, PIXEL_RATIO, PIXELS, rasterize, type GrowthKey } from './patterns.js';
import { FIELDS_LAYER, hasCut, MAX_ZOOM, MIN_ZOOM, PLUGIN, YEAR_MAX_ZOOM, yearUrl, CUT_YEARS } from './tiles.js';

/** Where a deep link flies to, and how close. */
const LINK_ZOOM = 14.2;
const DETAILS_KEPT = 40;
/** The hash parameter that names a field: `#...&field=<id>`. */
export const FIELD_PARAM = 'field';

/**
 * The Crop fields module (landscape sprint plan §3.4 K1-K2, P3-app):
 *
 * - two vector sources from the farm tiles (`./tiles.ts`): the fields (z8-14: dissolves, then one feature per
 *   field) and an earlier year's z8-10 dissolves, whose tile URL is swapped when the year changes;
 * - the style layers of `./layers.ts` (fills in Clay, copies over Aerial, patterns, hatches, linework,
 *   labels), their pattern images made here from `./patterns.ts`;
 * - the year switcher (`setYear`) and the growth toggles (`setGrowth`), which re-style the layers in place;
 * - a click on a field (z11 and in) selects it through the central picker and opens the card
 *   (`Card.svelte`, which reads `GET /api/farm/fields/<id>`); `#field=<id>` in the URL opens the same card
 *   and flies there, and is kept in step with the selection.
 */
export class CropsModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	info = $state.raw<YearInfo | null>(null);
	/** The year shown. */
	year = $state(0);
	growth = $state<Record<GrowthKey, boolean>>({ ...DEFAULT_GROWTH });
	/** The credit the build recorded, for the legend. */
	credit = $state<string | null>(null);
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{
			layerIds: PICK_LAYERS,
			priority: PRIORITY.crop,
			pick: (f: MapGeoJSONFeature): Selection | null => {
				const id = f.id ?? f.properties?.id;
				if (id === undefined || id === null || id === '') return null;
				return fieldSelection(f.properties as FieldProps, id, this.current);
			}
		}
	];
	#ctx: AppCtx | null = null;
	#scope: MapScope | null = null;
	#visible = false;
	#destroyed = false;
	#details = new globalThis.Map<string, Promise<FieldCard | null>>();
	#pendingLink = false;
	#debug: object | null = null;

	/** The newest crop year (the fields layer's own dissolves). */
	get current(): number {
		return this.info?.year ?? 0;
	}
	get first(): number {
		return this.info?.first_year ?? 0;
	}
	get years(): number[] {
		return this.info ? yearsOf(this.info) : [];
	}

	#state(): CropState {
		return { year: this.year, current: this.current, first: this.first, growth: this.growth };
	}

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		let info: YearInfo;
		try {
			const res = await take(YEAR_URL);
			if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
			info = (await res.json()) as YearInfo;
		} catch (e) {
			this.status = 'error';
			this.error = `Crop fields unavailable: ${e instanceof Error ? e.message : e}`;
			throw new Error(this.error);
		}
		if (!info.built || info.year === null || info.first_year === null) {
			this.status = 'error';
			this.error = 'Crop fields are not built yet';
			throw new Error(this.error);
		}
		this.info = info;
		this.year = info.year;
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		const scope = (this.#scope = new MapScope(map));
		const origin = location.origin;
		scope.addSource(SOURCE_FIELDS, layerSource(origin, ctx.meta, PLUGIN, FIELDS_LAYER, { minzoom: MIN_ZOOM, maxzoom: MAX_ZOOM }));
		// The year source starts on the oldest year; its layers stay out of every zoom until an earlier year is chosen.
		const placeholder = layerSource(origin, ctx.meta, PLUGIN, FIELDS_LAYER, { minzoom: MIN_ZOOM, maxzoom: YEAR_MAX_ZOOM });
		scope.addSource(SOURCE_YEAR, { ...placeholder, tiles: [yearUrl(origin, ctx.meta, CUT_YEARS[0])] });
		this.credit = (placeholder.attribution as string | undefined) ?? null;
		const ink = parseHex(PATTERN_INK);
		for (const k of PATTERN_KEYS) scope.addImage(imageId(k), { width: PIXELS, height: PIXELS, data: rasterize(PATTERNS[k], ink) }, { pixelRatio: PIXEL_RATIO });
		const layers = cropLayers(this.#state());
		const add = (l: Parameters<MapScope['addLayer']>[0], before?: string) => scope.addLayer(l, before);
		// Fills at rank 10 in areas; their Aerial copies at rank 5 in land; patterns and linework at 20; labels at 25.
		addSlotted(map, layers.areas, 10, add, 'crops');
		addSlotted(map, layers.copies, 5, add, 'crops');
		addSlotted(map, layers.land, 20, add, 'crops');
		addSlotted(map, layers.labels, 25, add, 'crops');
		this.#installDebug();
		scope.defer(() => this.#uninstallDebug());
		this.status = 'ready';
		this.updatedAt = Date.now();
		this.setVisible(this.#visible);
		const link = ctx.view.getParam(FIELD_PARAM);
		if (link) void this.#openLink(link);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		const map = this.#scope?.map;
		if (!map) return;
		for (const id of ALL_IDS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		if (!on) this.#mark(null);
	}

	// --- the year and the toggles ---------------------------------------------------------------------

	/** Show another year of USDA's maps: the dissolves from its own tiles (z8-10), the fields recoloured by letter (z11 on). */
	setYear(year: number): void {
		if (!this.years.includes(year) || year === this.year) return;
		this.year = year;
		const map = this.#scope?.map;
		if (map && this.#ctx && hasCut(year) && year !== this.current) {
			(map.getSource(SOURCE_YEAR) as VectorTileSource | undefined)?.setTiles([yearUrl(location.origin, this.#ctx.meta, year)]);
		}
		this.#restyle();
	}

	setGrowth(key: GrowthKey, on: boolean): void {
		if (this.growth[key] === on) return;
		this.growth = { ...this.growth, [key]: on };
		this.#restyle();
	}

	/** Whether the year has a map at z8-10 (the newest year, and the earlier ones with a cut). */
	hasLowZoom(year: number): boolean {
		return year === this.current || hasCut(year);
	}

	#restyle() {
		const map = this.#scope?.map;
		if (!map) return;
		for (const op of restyle(this.#state())) {
			if (!map.getLayer(op.id)) continue;
			if (op.zoom) map.setLayerZoomRange(op.id, op.zoom[0], op.zoom[1]);
			if (op.filter) map.setFilter(op.id, op.filter as never);
			for (const [k, v] of op.paint ?? []) map.setPaintProperty(op.id, k as never, v as never);
			for (const [k, v] of op.layout ?? []) map.setLayoutProperty(op.id, k as never, v as never);
		}
		this.updatedAt = Date.now();
	}

	// --- the card and the deep link -------------------------------------------------------------------

	/** One field's card data (kept for a while). */
	detail(id: string): Promise<FieldCard | null> {
		let p = this.#details.get(id);
		if (!p) {
			p = fetch(`/api/farm/fields/${encodeURIComponent(id)}`).then(async (res) => {
				if (res.status === 404) return null;
				if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
				return (await res.json()) as FieldCard;
			});
			p.catch(() => this.#details.delete(id));
			this.#details.set(id, p);
			if (this.#details.size > DETAILS_KEPT) this.#details.delete(this.#details.keys().next().value!);
		}
		return p;
	}

	/** `#field=<id>`: select that field, fly there and open the same card. */
	async #openLink(id: string): Promise<void> {
		const ctx = this.#ctx;
		if (!ctx || !/^\d{1,9}$/.test(id)) return;
		this.#pendingLink = true;
		try {
			const card = await this.detail(id);
			if (!card || this.#destroyed) {
				if (card === null && ctx.view.getParam(FIELD_PARAM) === id) ctx.view.setParam(FIELD_PARAM, null);
				return;
			}
			const last = card.years.at(-1);
			const props: FieldProps = { id: card.id, a: card.acres ?? undefined, g: last?.group, n: last?.name ?? undefined };
			ctx.selection.select(fieldSelection(props, card.id, this.current, card.centre));
			this.#scope?.map.flyTo({ center: card.centre, zoom: Math.max(this.#scope.map.getZoom(), LINK_ZOOM), duration: 1200 });
		} catch {
			// The card shows the problem when asked again; the link just does nothing.
		} finally {
			this.#pendingLink = false;
		}
	}

	selected(s: Selection | null): void {
		const ctx = this.#ctx;
		const mine = s?.layer === 'crops' && s.kind === 'crop';
		this.#mark(mine ? s!.id : null);
		if (!ctx) return;
		if (mine) {
			if (ctx.view.getParam(FIELD_PARAM) !== s!.id) ctx.view.setParam(FIELD_PARAM, s!.id);
		} else if (!this.#pendingLink && ctx.view.getParam(FIELD_PARAM) !== null) {
			ctx.view.setParam(FIELD_PARAM, null);
		}
	}

	/** Outline the selected field. */
	#mark(id: string | null) {
		const map = this.#scope?.map;
		if (map?.getLayer(ID.selected)) map.setFilter(ID.selected, selectedFilter(id) as never);
	}

	summary(): string | null {
		return this.info?.label ? `${this.year === this.current ? this.info.label : this.year}` : null;
	}

	destroy(): void {
		this.#destroyed = true;
		this.#scope?.dispose();
		this.#scope = null;
	}

	// --- debug ---------------------------------------------------------------------------------------

	/** A read-only handle for tests and the console: `__tvtCrops`. */
	#installDebug() {
		const self = this;
		const handle = Object.freeze({
			info: () => ({ visible: self.#visible, year: self.year, current: self.current, first: self.first, growth: { ...self.growth }, years: self.years }),
			/** A style layer's visibility, filter and zoom range as the map holds them now. */
			layer: (id: string) => {
				const map = self.#scope?.map;
				if (!map?.getLayer(id)) return null;
				const l = map.getLayer(id)!;
				return { visibility: map.getLayoutProperty(id, 'visibility') ?? 'visible', minzoom: l.minzoom, maxzoom: l.maxzoom, filter: map.getFilter(id) ?? null };
			},
			/** The fields drawn now: id, group of the year and screen point (from the fill layer). */
			fields: () => {
				const map = self.#scope?.map;
				if (!map) return [];
				return map.queryRenderedFeatures({ layers: PICK_LAYERS.filter((id) => map.getLayer(id)) }).map((f) => {
					const p = f.properties as FieldProps;
					const g = groupInYear(p, self.year, self.first, self.current) ?? null;
					const c = (f.geometry as GeoJSON.Polygon).coordinates?.[0]?.[0];
					return { id: f.id, group: g, n: p.n ?? null, y: p.y ?? null, lngLat: c ?? null };
				});
			},
			setYear: (y: number) => self.setYear(y),
			setGrowth: (k: GrowthKey, on: boolean) => self.setGrowth(k, on)
		});
		Object.defineProperty(globalThis, '__tvtCrops', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#debug = handle;
	}

	#uninstallDebug() {
		if ((globalThis as { __tvtCrops?: unknown }).__tvtCrops === this.#debug) Reflect.deleteProperty(globalThis, '__tvtCrops');
		this.#debug = null;
	}
}

export function create(): LayerModule {
	return new CropsModule();
}

