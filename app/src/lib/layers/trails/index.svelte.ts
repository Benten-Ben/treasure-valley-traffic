import type { MapGeoJSONFeature } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { PAVED_LAYER } from '#lib/base/trails/paved.js';
import { layerSource } from '#lib/contracts/layer-tiles.js';
import { addSlotted } from '#lib/map/order.js';
import type { TrailStatus } from '#lib/server/trails/status.js';
import { take } from '../prefetch.js';
import { PRIORITY, type Chip, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import { STATUS_URL } from './def.js';
import { statusImages } from './images.js';
import Legend from './Legend.svelte';
import {
	CREDIT_CITY,
	CREDIT_OSM,
	HIT_AGENCY,
	HIT_WAYS,
	L,
	lineSelection,
	lineSev,
	pavedSelection,
	planStatus,
	RANK_LINES,
	RANK_MARKS,
	selectedFilter,
	selectedIds,
	SL,
	SRC,
	stateEntries,
	stateKey,
	TILE_LAYERS,
	TRAIL_LAYER_IDS,
	trailLayers,
	waySelection,
	ZOOMS,
	type Sev,
	type StateEntry,
	type Statuses,
	type TrailData
} from './trails.js';

/** Ask for the status again this often while the layer is on, ms (the pollers run every 30 and 60 minutes). */
export const POLL_MS = 5 * 60_000;
export { CREDIT_CITY };
const DETAILS_KEPT = 40;

const FALLBACK_CREDIT: Record<(typeof TILE_LAYERS)[number], string> = { paths: CREDIT_OSM, routes: CREDIT_OSM, agency: `${CREDIT_CITY} · ${CREDIT_OSM}` };

/** How long ago, in words ("12 min ago", "3 h ago"). */
export function agoText(ms: number, now = Date.now()): string {
	const min = Math.max(0, Math.round((now - ms) / 60_000));
	if (min < 1) return 'just now';
	if (min < 60) return `${min} min ago`;
	const h = Math.round(min / 60);
	return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

/**
 * The Trails module (plan §3.2; package P6-app):
 *
 * - three vector sources from the toggled-layer route (`/api/trails/tiles/<layer>`): the ways, the routes and the
 *   City's lines; their style layers (trails.ts) in `land`, `points` and `labels`;
 * - the status from /api/trails/status (taken at boot by the def's `prefetch`, again every few minutes while the
 *   layer is on), applied as feature-state: each painted way's and each agency line's `sev`, and `hide` on the informal
 *   ways near a closure. A status that doesn't load leaves the lines plain and the layer ▲ (stale), never blank;
 * - a click on a way, an agency line or (while Trails is on) a paved tread opens the card (Card.svelte), which
 *   fetches /api/trails/way/<id> or /api/trails/line/<id>.
 */
export class TrailsModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	/** The status API's last answer (the legend reads it). */
	trail = $state.raw<TrailStatus | null>(null);
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{ layerIds: HIT_WAYS, priority: PRIORITY.trail, pick: (f: MapGeoJSONFeature): Selection | null => this.#pick(() => waySelection(f, this.#statuses)) },
		{ layerIds: HIT_AGENCY, priority: PRIORITY.trail, pick: (f: MapGeoJSONFeature): Selection | null => this.#pick(() => lineSelection(f, this.#statuses)) },
		// The paved treads and areas are base layers (always drawn when built); they open a card only while Trails is on
		// (the picker keeps a mounted module's layers, on or off, so the module says no itself).
		{ layerIds: [PAVED_LAYER.treads], priority: PRIORITY.trail, pick: (f: MapGeoJSONFeature): Selection | null => this.#pick(() => pavedSelection(f, false, this.#statuses)) },
		{ layerIds: [PAVED_LAYER.areas], priority: PRIORITY.paving, pick: (f: MapGeoJSONFeature): Selection | null => this.#pick(() => pavedSelection(f, true, this.#statuses)) }
	];
	#ctx: AppCtx | null = null;
	#scope: MapScope | null = null;
	#visible = false;
	#destroyed = false;
	#timer: ReturnType<typeof setInterval> | undefined;
	#applied = new Map<string, StateEntry>();
	#byWay = new globalThis.Map<number, Sev>();
	#hiddenWays = new globalThis.Set<number>();
	#byLine = new globalThis.Map<number, { sev: Sev | null; label: string | null; state: string; name: string | null }>();
	#details = new globalThis.Map<string, Promise<unknown>>();
	/** When the newest poll of Ridge to Rivers or the Greenbelt landed (epoch ms), for the legend’s “as of”. */
	#polled = $state<number | null>(null);
	#loaded = false;
	#statusError: string | null = null;
	#tilesError: string | null = null;
	#debug: object | null = null;
	/** A pick, only while the layer is on. */
	#pick(make: () => Selection | null): Selection | null {
		return this.#visible ? make() : null;
	}
	/** Requests made for the status (tests and the console). */
	statusRequests = 0;
	readonly #statuses: Statuses = {
		way: (id) => this.#byWay.get(id) ?? null,
		line: (id) => this.#byLine.get(id) ?? null,
		hidden: (id) => this.#hiddenWays.has(id)
	};

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		// The status is on its way already (the def's prefetch); a failure is not the layer's: the lines draw plain.
		const first = this.#load(true);
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		const scope = (this.#scope = new MapScope(map));
		for (const layer of TILE_LAYERS) {
			const src = layerSource(location.origin, ctx.meta, 'trails', layer, ZOOMS);
			scope.addSource(SRC[layer], { ...src, attribution: src.attribution ?? FALLBACK_CREDIT[layer] });
		}
		for (const [id, img] of Object.entries(statusImages())) scope.addImage(id, img.data, img.options);
		const all = trailLayers();
		const add = (l: Parameters<MapScope['addLayer']>[0], before?: string) => scope.addLayer(l, before);
		addSlotted(map, all.filter((l) => l.slot === 'land'), RANK_LINES, add, 'trails');
		addSlotted(map, all.filter((l) => l.slot !== 'land'), RANK_MARKS, add, 'trails');
		// A tile that fails puts ▲ on the button until Retry (§14.3: map source errors go to their layer's status).
		scope.on('error', (e) => {
			const id = (e as { sourceId?: string }).sourceId;
			if (!id || !Object.values(SRC).includes(id as never)) return;
			this.#tilesError = `Some trail tiles failed to load: ${e.error?.message ?? 'unknown error'}`;
			this.#sync();
		});
		this.#installDebug();
		scope.defer(() => this.#uninstallDebug());
		await first;
		if (this.#destroyed) return;
		this.#loaded = true;
		this.updatedAt ??= Date.now();
		this.#sync();
		this.#applyStatus();
		this.setVisible(this.#visible);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		clearInterval(this.#timer);
		this.#timer = undefined;
		const map = this.#scope?.map;
		if (!map) return;
		for (const id of TRAIL_LAYER_IDS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		if (!on) return;
		this.#timer = setInterval(() => void this.#load(false), POLL_MS);
		// Back on after a while: the status may be old.
		if (this.updatedAt !== null && Date.now() - this.updatedAt > POLL_MS) void this.#load(false);
	}

	/** Ask for the status (the prefetched answer the first time), index it, and apply it. */
	async #load(first: boolean): Promise<void> {
		this.statusRequests++;
		try {
			const res = await (first ? take(STATUS_URL) : fetch(STATUS_URL, { cache: 'no-cache' }));
			if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
			const s = (await res.json()) as TrailStatus;
			if (this.#destroyed) return;
			this.#statusError = null;
			this.#take(s);
		} catch (e) {
			if (this.#destroyed) return;
			// Tiles and plain lines still draw; the status is what's missing.
			this.#statusError = `Trail status unavailable: ${e instanceof Error ? e.message : e}`;
		}
		this.#sync();
	}

	/** The layer's status from what's wrong: stale (▲) while the status or some tiles are missing, ready otherwise. */
	#sync() {
		if (!this.#loaded) return;
		const problem = this.#statusError ?? this.#tilesError;
		this.status = problem ? 'stale' : 'ready';
		this.error = problem;
	}

	#take(s: TrailStatus) {
		this.trail = s;
		// A card kept from before this poll may say what the map no longer does: ask again on the next open.
		this.#details.clear();
		this.#byWay = new globalThis.Map(Object.entries(s.ways).map(([id, sev]) => [Number(id), sev]));
		this.#hiddenWays = new globalThis.Set(s.hidden);
		this.#byLine = new globalThis.Map(
			s.agencies.filter((a) => a.line_id !== null).map((a) => [a.line_id!, { sev: lineSev(a), label: a.label, state: a.state, name: a.name }])
		);
		const polls = Object.values(s.polled).filter((x): x is string => Boolean(x)).map((x) => Date.parse(x));
		this.#polled = polls.length ? Math.max(...polls) : null;
		this.updatedAt = Date.now();
		this.#applyStatus();
	}

	/** Set the feature-state the status calls for, and take away what it dropped (a source not yet added is skipped). */
	#applyStatus() {
		const map = this.#scope?.map;
		const s = this.trail;
		if (!map || !s) return;
		const { set, remove } = planStatus(this.#applied, stateEntries(s));
		for (const e of remove) {
			if (map.getSource(e.source)) map.removeFeatureState({ source: e.source, sourceLayer: e.sourceLayer, id: e.id });
			this.#applied.delete(stateKey(e));
		}
		for (const e of set) {
			if (!map.getSource(e.source)) continue;
			// A key dropped from a feature's state (a way no longer hidden) needs the feature cleared before the new state is set.
			if (this.#applied.has(stateKey(e))) map.removeFeatureState({ source: e.source, sourceLayer: e.sourceLayer, id: e.id });
			map.setFeatureState({ source: e.source, sourceLayer: e.sourceLayer, id: e.id }, e.state);
			this.#applied.set(stateKey(e), e);
		}
	}

	/** Outline the selected trail (a filter change on its layers, not new data). */
	selected(s: Selection | null): void {
		const map = this.#scope?.map;
		if (!map) return;
		const { way, line } = selectedIds(s);
		for (const id of [L.selectedHalo, L.selected]) if (map.getLayer(id)) map.setFilter(id, selectedFilter(way));
		for (const id of [L.selectedHaloAgency, L.selectedAgency]) if (map.getLayer(id)) map.setFilter(id, selectedFilter(line));
	}

	/** One way's or line's card data (kept for a while). */
	detail<T>(kind: 'way' | 'line', id: number): Promise<T | null> {
		const k = `${kind}:${id}`;
		let p = this.#details.get(k);
		if (!p) {
			p = fetch(`/api/trails/${kind}/${id}`, { cache: 'no-cache' }).then(async (res) => {
				if (res.status === 404) return null;
				if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
				return (await res.json()) as T;
			});
			p.catch(() => this.#details.delete(k));
			this.#details.set(k, p);
			if (this.#details.size > DETAILS_KEPT) this.#details.delete(this.#details.keys().next().value!);
		}
		return p as Promise<T | null>;
	}

	chips(): Chip[] {
		const closed = this.trail?.counts.closed ?? 0;
		if (!this.#visible || !closed) return [];
		return [{ id: 'trails-closed', text: `${closed} trail${closed === 1 ? '' : 's'} closed`, title: "Ridge to Rivers' trails listed as closed (R2R's advice, from its map)", stale: this.status === 'stale' }];
	}

	age(): string | null {
		return this.#polled === null ? null : `Ridge to Rivers polled ${agoText(this.#polled)}`;
	}

	summary(): string | null {
		const n = Object.values(this.trail?.counts ?? {}).reduce((a, b) => a + b, 0);
		return n ? `${n} Ridge to Rivers trails` : null;
	}

	destroy(): void {
		this.#destroyed = true;
		clearInterval(this.#timer);
		this.#scope?.dispose();
		this.#scope = null;
		this.#applied.clear();
	}

	// --- debug ---------------------------------------------------------------------------------------

	/** A read-only handle for tests and the console: `__tvtTrails`. */
	#installDebug() {
		const self = this;
		const handle = Object.freeze({
			info: () => ({
				visible: self.#visible,
				status: self.status,
				error: self.error,
				statusRequests: self.statusRequests,
				applied: self.#applied.size,
				ways: self.#byWay.size,
				lines: self.#byLine.size
			}),
			/** The features a style layer draws now, with their feature-state and properties. */
			features: (layer: string) => {
				const map = self.#scope?.map;
				if (!map?.getLayer(layer)) return [];
				return map.queryRenderedFeatures({ layers: [layer] }).map((f) => ({ id: f.id as number, state: f.state as Record<string, unknown>, properties: f.properties }));
			},
			/** The status, as the module holds it. */
			trail: () => self.trail,
			refresh: () => self.#load(false)
		});
		Object.defineProperty(globalThis, '__tvtTrails', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#debug = handle;
	}

	#uninstallDebug() {
		if ((globalThis as { __tvtTrails?: unknown }).__tvtTrails === this.#debug) Reflect.deleteProperty(globalThis, '__tvtTrails');
		this.#debug = null;
	}
}

export type { TrailData };

export function create(): LayerModule {
	return new TrailsModule();
}
