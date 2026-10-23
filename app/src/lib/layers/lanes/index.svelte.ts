import type { Map as GlMap, MapGeoJSONFeature } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { addSlotted } from '#lib/map/order.js';
import type { PavingCard } from '#lib/server/roads/paving.js';
import { PRIORITY, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import def from './def.js';
import Legend from './Legend.svelte';
import { CardError, newerMapReady as isNewerMap, pavingSelection, roadSelection, type LanesSelectionData, type PieceAnswer } from './lanes.js';
import { ARROW_LAYER, CONFLICT_LAYER, LANDSCAPE_SOURCE, ownLayers, OWN_LAYERS, pickablePavingLayers, pickableRoadLayers } from './layers.js';
import { allImages } from './markers.js';

/** Details kept for the card. */
const DETAILS_KEPT = 60;

/**
 * The Lanes module (landscape sprint plan v3 §4.2 P9):
 *
 * - once the landscape file holds the road lines and arrows, a ▲ at the middle of every flagged piece line and the
 *   turn arrows from z17.5 (the layer's own style layers; the roads themselves are the base contributions');
 * - while it is on, the contributions' surfaces, decks, edges, markings and piece lines are clickable
 *   (`PRIORITY.lane`) and open the piece card, asked from /api/roads/piece with the build the map's tiles are
 *   from (the manifest's landscape layer); paving (`PRIORITY.paving`) opens the paving card from
 *   /api/roads/paving. When the roads aren't baked, nothing is added and the legend says so.
 */
export class LanesModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	/** The landscape file has the road lines (▲ marks) and arrows. */
	marks = $state.raw({ lines: false, arrows: false });
	/** The landscape file has the road surfaces: clicks have something to open. */
	roads = $state(false);
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{ layerIds: pickableRoadLayers(), priority: PRIORITY.lane, pick: (f) => (this.#visible ? this.#pickRoad(f) : null) },
		{ layerIds: pickablePavingLayers(), priority: PRIORITY.paving, pick: (f) => (this.#visible ? pavingSelection(f.sourceLayer, f.properties) : null) }
	];
	#scope: MapScope | null = null;
	#ctx: AppCtx | null = null;
	#visible = false;
	#destroyed = false;
	#details = new globalThis.Map<string, Promise<unknown>>();
	#debug: object | null = null;

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		const scope = (this.#scope = new MapScope(map));
		const e = ctx.manifest?.landscape;
		const layers = e?.status === 'baked' ? e.layers : {};
		this.roads = 'roads.surfaces' in layers || 'roads.lines' in layers;
		this.marks = { lines: 'roads.lines' in layers, arrows: 'roads.arrows' in layers };
		if (map.getSource(LANDSCAPE_SOURCE) && (this.marks.lines || this.marks.arrows)) {
			for (const { id, image, ratio } of allImages()) scope.addImage(id, image, { pixelRatio: ratio });
			addSlotted(map, ownLayers(this.marks), def.order, (l, before) => scope.addLayer(l, before), def.id);
		}
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
		for (const id of OWN_LAYERS) {
			if (map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== (on ? 'visible' : 'none')) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		}
	}

	// --- picking ----------------------------------------------------------------------------------------------

	/** The build a source-layer's tiles are from, per the manifest (null when the file isn't baked). */
	#build(sourceLayer: string | undefined): string | null {
		const e = this.#ctx?.manifest?.landscape;
		return sourceLayer && e?.status === 'baked' ? (e.layers[sourceLayer]?.build ?? null) : null;
	}

	#pickRoad(f: MapGeoJSONFeature): Selection | null {
		return roadSelection(f.sourceLayer, f.properties, this.#build(f.sourceLayer));
	}

	// --- details ----------------------------------------------------------------------------------------------

	#kept<T>(key: string, load: () => Promise<T>): Promise<T> {
		let p = this.#details.get(key) as Promise<T> | undefined;
		if (!p) {
			p = load();
			p.catch(() => this.#details.delete(key));
			this.#details.set(key, p);
			if (this.#details.size > DETAILS_KEPT) this.#details.delete(this.#details.keys().next().value!);
		}
		return p;
	}

	/** One road piece's card (kept for a while). A build behind the map rejects with status 409; a missing one with 404. */
	piece(d: Extract<LanesSelectionData, { type: 'piece' }>): Promise<PieceAnswer> {
		return this.#kept(`piece:${d.build}:${d.ref}`, () => request<PieceAnswer>(`/api/roads/piece/${encodeURIComponent(d.ref)}?build=${encodeURIComponent(d.build)}`));
	}

	/** One parking lot's or paving way's card. */
	paving(d: Extract<LanesSelectionData, { type: 'paving' }>): Promise<PavingCard> {
		return this.#kept(`paving:${d.kind}:${d.id}`, () => request<PavingCard>(`/api/roads/paving/${d.kind}/${encodeURIComponent(d.id)}`));
	}

	/** Whether the server now holds a different landscape file than this page loaded (so a reload would bring newer roads). */
	async newerMapReady(): Promise<boolean> {
		try {
			const res = await fetch('/tiles/manifest.json', { cache: 'no-store' });
			return res.ok && isNewerMap(this.#ctx?.manifest, await res.json());
		} catch {
			return false;
		}
	}

	summary(): string | null {
		return this.roads ? null : 'roads not built yet';
	}

	destroy(): void {
		this.#destroyed = true;
		this.#scope?.dispose();
		this.#scope = null;
	}

	// --- debug --------------------------------------------------------------------------------------------------

	/** A read-only handle for tests and the console: `__tvtLanes`. */
	#installDebug() {
		const self = this;
		const map = (): GlMap | undefined => self.#scope?.map;
		const handle = Object.freeze({
			info: () => ({ visible: self.#visible, roads: self.roads, marks: self.marks }),
			layers: () => OWN_LAYERS.filter((id) => map()?.getLayer(id)),
			label: (id: string) => map()?.getLayoutProperty(id, 'visibility') ?? null,
			images: () => allImages().map((i) => i.id).filter((id) => map()?.hasImage(id))
		});
		Object.defineProperty(globalThis, '__tvtLanes', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#debug = handle;
	}

	#uninstallDebug() {
		if ((globalThis as { __tvtLanes?: unknown }).__tvtLanes === this.#debug) Reflect.deleteProperty(globalThis, '__tvtLanes');
		this.#debug = null;
	}
}

async function request<T>(url: string): Promise<T> {
	const res = await fetch(url);
	if (res.ok) return (await res.json()) as T;
	const message = (await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`;
	throw new CardError(message, res.status);
}

export { ARROW_LAYER, CardError, CONFLICT_LAYER };

export function create(): LayerModule {
	return new LanesModule();
}
