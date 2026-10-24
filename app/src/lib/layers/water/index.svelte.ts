import type { Map as GlMap, MapGeoJSONFeature } from 'maplibre-gl';
import type { GeoJSONSource } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import contribution, { BODIES_LAYER, ID as CONTRIBUTION_ID, PICKABLE_LAYERS } from '#lib/base/water/water.base.js';
import { WETLAND_LAYER_IDS } from '#lib/base/water/wetlands.base.js';
import type { FlavorName } from '#lib/map/flavors.js';
import { addSlotted } from '#lib/map/order.js';
import { flavorKit } from '#lib/map/style.js';
import { take } from '../prefetch.js';
import { PRIORITY, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import def, { NOTICES_URL, POINTS_URL } from './def.js';
import Legend from './Legend.svelte';
import {
	BAKED_LAYERS,
	bakedLayers,
	flavorPaints,
	GAUGE_LAYER,
	IMAGE,
	LABELS_OWNER,
	LANDSCAPE_SOURCE,
	NOTICE_LAYER,
	noticeFeatures,
	NOTICES_SOURCE,
	pointFeatures,
	pointId,
	pointLayers,
	POINT_LAYERS,
	POINTS_SOURCE,
	SELECTED_BODY_LAYER,
	SELECTED_REACH_LAYER,
	STRUCTURE_LAYER
} from './layers.js';
import { markerImage, MARKERS } from './markers.js';
import {
	BODY_WORD,
	bodyTitle,
	ecoliResultText,
	FLOOD_WORD,
	HAZARD_STATUS_WORD,
	HAZARD_WORD,
	NOTICES_ATTRIBUTION,
	POINTS_ATTRIBUTION,
	reachFact,
	reachTitle,
	sourceLine,
	STRUCTURE_WORD,
	type BodyDetail,
	type BodyKind,
	type EcoliSample,
	type GaugeDetail,
	type Hazard,
	type Notices,
	type ReachDetail,
	type ReachKind,
	type StructureDetail,
	type StructureKind,
	type WaterPoints,
	type WaterThing
} from './water.js';

/** Details kept for the card. */
const DETAILS_KEPT = 60;

/** What a water selection's `data` carries. */
export type WaterSelectionData =
	| { type: 'reach'; id: number; kind: ReachKind; name: string | null; width_m: number; intermittent: boolean; piped: boolean; nhd_only: boolean; canal: number }
	| { type: 'body'; id: number; kind: BodyKind; name: string | null; intermittent: boolean; nhd_only: boolean }
	| { type: 'gauge'; lid: string }
	| { type: 'structure'; id: number }
	| { type: 'hazard'; id: string }
	| { type: 'ecoli'; id: string };

/** The detail each kind of selection fetches. */
export interface Details {
	reach: ReachDetail;
	body: BodyDetail;
	gauge: GaugeDetail;
	structure: StructureDetail;
}

const ROUTES: Record<keyof Details, string> = { reach: 'reach', body: 'body', gauge: 'gauge', structure: 'structure' };

const bool = (v: unknown) => v === true || v === 1 || v === 'true' || v === '1';

/**
 * The Water module (landscape sprint plan v3 §4.2 P4-app):
 *
 * - the water points from /api/water/points (gauges, structures) and the river notices from
 *   /api/water/notices (hazards, E. coli sites), as badges in the `points` slot;
 * - while it is on, the baked reaches and areas of the base map are clickable (PRIORITY.water, 25; the points
 *   one above), each opening a card that fetches /api/water/<reach|body|structure|gauge>/<id>;
 * - when the water network is baked, the italic names of reaches and areas draw in `labels` and the base's own
 *   water labels step aside, and the picked line or area is drawn a little wider and darker. When it isn't
 *   baked, none of that is added and the basemap's water and labels stay (the legend says so).
 */
export class WaterModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	points = $state.raw<WaterPoints | null>(null);
	notices = $state.raw<Notices | null>(null);
	/** Why the notices aren't here (the rest of the layer still works). */
	noticesProblem = $state<string | null>(null);
	/** The water network is baked and on the map: its labels and picked shape draw. */
	baked = $state(false);
	/** The credit lines of the baked water layers, from the manifest (HydroShare appears when its names are used). */
	bakedCredit = $state.raw<string[]>([]);
	Legend = Legend;
	Card = Card;
	/** The look the map draws in now (the legend's samples follow it). Reactive. */
	get flavor(): FlavorName {
		return this.#ctx?.layers?.flavor ?? 'valley';
	}
	interactive: Interactive[] = [
		{
			layerIds: [...PICKABLE_LAYERS, ...WETLAND_LAYER_IDS],
			priority: PRIORITY.water,
			pick: (f) => (this.#visible ? this.#pickBaked(f) : null)
		},
		{
			layerIds: [...POINT_LAYERS],
			priority: PRIORITY.water + 1,
			pick: (f) => (this.#visible ? this.#pickPoint(f) : null)
		}
	];
	#scope: MapScope | null = null;
	#ctx: AppCtx | null = null;
	#visible = false;
	#destroyed = false;
	#details = new globalThis.Map<string, Promise<unknown>>();
	#debug: object | null = null;

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		try {
			const res = await take(POINTS_URL);
			if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
			this.points = (await res.json()) as WaterPoints;
		} catch (e) {
			this.status = 'error';
			this.error = `Water unavailable: ${e instanceof Error ? e.message : e}`;
			throw new Error(this.error);
		}
		try {
			const res = await take(NOTICES_URL);
			if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
			this.notices = (await res.json()) as Notices;
		} catch (e) {
			// The gauges, structures and the baked network don't need them.
			this.noticesProblem = `Couldn't load the river notices: ${e instanceof Error ? e.message : e}`;
		}
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		const scope = (this.#scope = new MapScope(map));
		const kit = flavorKit();
		// The attribution card credits the data these badges draw while the layer is on (docs/14 §14.11).
		scope.addSource(POINTS_SOURCE, { type: 'geojson', data: pointFeatures(this.points), promoteId: 'id', attribution: POINTS_ATTRIBUTION });
		scope.addSource(NOTICES_SOURCE, {
			type: 'geojson',
			data: noticeFeatures(this.notices ?? { hazards: [], ecoli: [] }),
			promoteId: 'id',
			attribution: NOTICES_ATTRIBUTION
		});
		for (const m of MARKERS) {
			const img = markerImage(m.image);
			if (img) scope.addImage(m.image, img, { pixelRatio: 2 });
		}
		const owner = def.id;
		addSlotted(map, pointLayers(), def.order, (l, before) => scope.addLayer(l, before), owner);
		// The baked network: labels and the picked shape draw from the landscape file, once it is baked.
		const manifest = ctx.manifest;
		if (manifest && kit.contributionStatus(contribution, manifest, ctx.meta).built && map.getSource(LANDSCAPE_SOURCE)) {
			addSlotted(map, bakedLayers(), def.order, (l, before) => scope.addLayer(l, before), owner);
			for (const [id, paint] of Object.entries(flavorPaints())) scope.defer(kit.registerFlavorPaint(map, id, paint));
			this.baked = true;
			const info = manifest.landscape?.status === 'baked' ? manifest.landscape.layers : {};
			this.bakedCredit = [...new Set(['water.reaches', 'water.bodies'].flatMap((k) => info[k]?.credit ?? []))];
		}
		scope.defer(() => kit.releaseGroups(map, LABELS_OWNER));
		this.#installDebug();
		scope.defer(() => this.#uninstallDebug());
		this.status = 'ready';
		this.updatedAt = Date.now();
		this.setVisible(this.#visible);
		this.selected(ctx.selection.current);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		const map = this.#scope?.map;
		if (!map) return;
		const show = (id: string, want: boolean) => {
			if (map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== (want ? 'visible' : 'none')) map.setLayoutProperty(id, 'visibility', want ? 'visible' : 'none');
		};
		for (const id of POINT_LAYERS) show(id, on);
		for (const id of BAKED_LAYERS) show(id, on && !id.startsWith('water-selected'));
		// The basemap's water names give way to the italic ones, only while those draw.
		const kit = flavorKit();
		if (on && this.baked) kit.suppressGroups(map, LABELS_OWNER, ['water-labels']);
		else kit.releaseGroups(map, LABELS_OWNER);
		if (on) this.selected(this.#ctx?.selection.current ?? null);
		else this.#highlight(null);
	}

	// --- picking ----------------------------------------------------------------------------------------------

	#pickBaked(f: MapGeoJSONFeature): Selection | null {
		const p = f.properties ?? {};
		const id = Number(p.id);
		if (!Number.isFinite(id)) return null;
		const nhdOnly = bool(p.nhd_only);
		// A wetland is its own tuft layer (a fill pattern, hit across its whole polygon), not the bodies' fill.
		if (f.layer.id === BODIES_LAYER || (WETLAND_LAYER_IDS as readonly string[]).includes(f.layer.id)) {
			const kind = String(p.kind) as BodyKind;
			if (!(kind in BODY_WORD)) return null;
			const name = String(p.name ?? '') || null;
			return {
				kind: 'water',
				id: `body:${id}`,
				layer: 'water',
				title: bodyTitle(kind, name),
				fact: [BODY_WORD[kind], bool(p.intermittent) ? 'dries up part of the year' : null].filter(Boolean).join(', '),
				source: sourceLine(nhdOnly),
				data: { type: 'body', id, kind, name, intermittent: bool(p.intermittent), nhd_only: nhdOnly } satisfies WaterSelectionData
			};
		}
		const kind = String(p.kind) as ReachKind;
		const name = String(p.name ?? '') || null;
		const width = Number(p.width_m);
		const piped = bool(p.piped);
		const intermittent = bool(p.intermittent);
		return {
			kind: 'water',
			id: `reach:${id}`,
			layer: 'water',
			title: reachTitle(kind, name, piped),
			fact: reachFact(kind, width, { intermittent, piped, nhdOnly }),
			source: sourceLine(nhdOnly),
			data: { type: 'reach', id, kind, name, width_m: width, intermittent, piped, nhd_only: nhdOnly, canal: Number(p.canal) || 0 } satisfies WaterSelectionData
		};
	}

	#pickPoint(f: MapGeoJSONFeature): Selection | null {
		const p = f.properties ?? {};
		const at = f.geometry.type === 'Point' ? (f.geometry.coordinates as [number, number]) : undefined;
		switch (p.kind) {
			case 'gauge': {
				const lid = String(p.lid);
				const flood = p.flood ? FLOOD_WORD[p.flood as keyof typeof FLOOD_WORD] : null;
				return {
					kind: 'water',
					id: pointId.gauge(lid),
					layer: 'water',
					title: String(p.name),
					fact: flood ? `Gauge · ${flood}` : 'Gauge',
					source: 'NOAA National Water Prediction Service',
					at,
					data: { type: 'gauge', lid } satisfies WaterSelectionData
				};
			}
			case 'hazard': {
				const h = this.#hazard(String(p.hid));
				if (!h) return null;
				return {
					kind: 'water',
					id: pointId.hazard(h.id),
					layer: 'water',
					title: h.name ?? 'River hazard',
					fact: `${HAZARD_WORD[h.kind]} · ${HAZARD_STATUS_WORD[h.status].toLowerCase()}`,
					source: 'City of Boise (Float the Boise)',
					at,
					data: { type: 'hazard', id: h.id } satisfies WaterSelectionData
				};
			}
			case 'ecoli': {
				const s = this.#sample(String(p.eid));
				if (!s) return null;
				return {
					kind: 'water',
					id: pointId.ecoli(s.id),
					layer: 'water',
					title: s.site ?? s.id,
					fact: `E. coli ${ecoliResultText(s)} · ${s.sampled}`,
					source: 'City of Boise Parks and Recreation',
					at,
					data: { type: 'ecoli', id: s.id } satisfies WaterSelectionData
				};
			}
			default: {
				const sid = Number(p.sid);
				const kind = String(p.kind) as StructureKind;
				if (!Number.isFinite(sid) || !(kind in STRUCTURE_WORD)) return null;
				return {
					kind: 'water',
					id: pointId.structure(sid),
					layer: 'water',
					title: String(p.name),
					fact: STRUCTURE_WORD[kind],
					source: 'OpenStreetMap · USGS NHD',
					at,
					data: { type: 'structure', id: sid } satisfies WaterSelectionData
				};
			}
		}
	}

	#hazard(id: string): Hazard | undefined {
		return this.notices?.hazards.find((h) => h.id === id);
	}

	#sample(id: string): EcoliSample | undefined {
		return this.notices?.ecoli.find((s) => s.id === id);
	}

	/** The hazard or E. coli site a card shows (from the notices already here). */
	hazard = (id: string) => this.#hazard(id);
	sample = (id: string) => this.#sample(id);

	/** The picked reach or area is drawn wider and darker; anything else clears it. */
	selected(s: Selection | null): void {
		const d = s && s.layer === 'water' ? (s.data as WaterSelectionData | undefined) : undefined;
		this.#highlight(this.#visible && d && (d.type === 'reach' || d.type === 'body') ? d : null);
	}

	#highlight(d: Extract<WaterSelectionData, { type: 'reach' | 'body' }> | null) {
		const map = this.#scope?.map;
		if (!map || !this.baked) return;
		const set = (layer: string, id: number | null) => {
			if (!map.getLayer(layer)) return;
			map.setFilter(layer, ['==', ['get', 'id'], id ?? -1]);
			map.setLayoutProperty(layer, 'visibility', id === null ? 'none' : 'visible');
		};
		set(SELECTED_REACH_LAYER, d?.type === 'reach' ? d.id : null);
		set(SELECTED_BODY_LAYER, d?.type === 'body' ? d.id : null);
	}

	// --- details ----------------------------------------------------------------------------------------------

	/** One thing's details for the card (kept for a while); null when the build no longer has it. */
	detail<K extends keyof Details>(type: K, id: string | number): Promise<Details[K] | null> {
		const key = `${type}:${id}`;
		let p = this.#details.get(key) as Promise<Details[K] | null> | undefined;
		if (!p) {
			p = fetch(`/api/water/${ROUTES[type]}/${encodeURIComponent(String(id))}`).then(async (res) => {
				if (res.status === 404) return null;
				if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
				return (await res.json()) as Details[K];
			});
			p.catch(() => this.#details.delete(key));
			this.#details.set(key, p);
			if (this.#details.size > DETAILS_KEPT) this.#details.delete(this.#details.keys().next().value!);
		}
		return p;
	}

	summary(): string | null {
		const g = this.points?.gauges.length ?? 0;
		return g ? `${g} gauge${g === 1 ? '' : 's'}` : null;
	}

	destroy(): void {
		this.#destroyed = true;
		this.#scope?.dispose();
		this.#scope = null;
	}

	// --- debug --------------------------------------------------------------------------------------------------

	/** A read-only handle for tests and the console: `__tvtWater`. */
	#installDebug() {
		const self = this;
		const map = (): GlMap | undefined => self.#scope?.map;
		const handle = Object.freeze({
			info: () => ({
				visible: self.#visible,
				baked: self.baked,
				contribution: CONTRIBUTION_ID,
				gauges: self.points?.gauges.length ?? 0,
				structures: self.points?.structures.length ?? 0,
				hazards: self.notices?.hazards.length ?? 0,
				ecoli: self.notices?.ecoli.length ?? 0,
				images: Object.values(IMAGE).filter((i) => map()?.hasImage(i))
			}),
			/** Source data counts, as the map holds them. */
			sources: () => ({
				points: (map()?.getSource(POINTS_SOURCE) as GeoJSONSource | undefined) ? 1 : 0,
				notices: (map()?.getSource(NOTICES_SOURCE) as GeoJSONSource | undefined) ? 1 : 0
			}),
			layers: () => [...POINT_LAYERS, ...BAKED_LAYERS].filter((id) => map()?.getLayer(id)),
			label: (id: string) => map()?.getLayoutProperty(id, 'visibility') ?? null
		});
		Object.defineProperty(globalThis, '__tvtWater', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#debug = handle;
	}

	#uninstallDebug() {
		if ((globalThis as { __tvtWater?: unknown }).__tvtWater === this.#debug) Reflect.deleteProperty(globalThis, '__tvtWater');
		this.#debug = null;
	}
}

export type { WaterThing };
export { GAUGE_LAYER, NOTICE_LAYER, STRUCTURE_LAYER };

export function create(): LayerModule {
	return new WaterModule();
}
