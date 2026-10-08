import type { GeoJSONSource, MapGeoJSONFeature, MapMouseEvent } from 'maplibre-gl';
import { untrack } from 'svelte';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { addSlotted } from '#lib/map/order.js';
import { discSprite, type OverlayInstance } from '#lib/overlay/index.js';
import { historyOf } from '#lib/state/history.svelte.js';
import { Poller } from '#lib/state/poll.svelte.js';
import { windowsOf, type Point, type WindowSpec } from '#lib/state/windows.svelte.js';
import { take } from '../prefetch.js';
import { PRIORITY, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import { badgeImage } from './badges.js';
import Card from './Card.svelte';
import def, { DATA_URL } from './def.js';
import { ALL_LAYERS, BADGE_LAYER, CREAM, HOLLOW_IMAGE, INK, roadWeatherLayers, SOLID_IMAGE, SOURCE, stationFeatures } from './layers.js';
import Legend from './Legend.svelte';
import { creditOf, inBounds, stationFact, type Bounds, type RoadWeather, type RoadWeatherStation } from './model.js';
import StationWindow from './StationWindow.svelte';

/** Ages and "no live feed" are fetched again this often while the layer is shown (pictures change about every 15 min). */
export const REFRESH_MS = 5 * 60_000;
/** Window kind for pinned station windows (reopened on the next visit). */
export const WINDOW_KIND = 'roadweather';
/** The overlay group of window number badges on stations. */
export const BADGES = 'roadweather-windows';
/** 511's road-weather pictures are 800 × 486. */
export const ASPECT = 800 / 486;

export const stationKey = (id: number) => `roadweather:${id}`;
export function stationIdOf(key: string): number | null {
	const m = /^roadweather:(\d+)$/.exec(key);
	return m ? Number(m[1]) : null;
}
const badgeKey = (n: number) => `roadweather-window-${n}`;

async function getJson(res: Promise<Response>): Promise<RoadWeather> {
	const r = await res;
	if (!r.ok) throw new Error((await r.json().catch(() => null))?.message ?? `HTTP ${r.status}`);
	return r.json();
}

/**
 * The Road weather module (docs/14 §14.6 "Road weather"; WP16):
 *
 * - the stations from /api/roadweather, drawn as badges where they're inside
 *   the base map (hollow when every view shows 511's "no live feed"
 *   picture); the rest are loaded but not drawn until the study area grows;
 * - a click on a station opens its window beside it: one tab per view, each
 *   with the newest captured picture and its age, on the road-weather
 *   freshness thresholds (StationWindow.svelte, through the app's one live
 *   feed);
 * - each open window's number on its station (the overlay), pinned windows
 *   reopening on the next visit, and windows stepping aside during a mode;
 * - while shown, the list is fetched again every 5 minutes (paused while the
 *   tab is hidden); a toggle within that time makes no request.
 */
export class RoadWeatherModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	/** The last answer. */
	data = $state.raw<RoadWeather | null>(null);
	/** The stations drawn: those inside the base map. */
	drawn = $state.raw<RoadWeatherStation[]>([]);
	/** Server clock minus ours, ms. */
	skew = $state(0);
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{
			layerIds: [BADGE_LAYER],
			priority: PRIORITY.weather,
			pick: (f: MapGeoJSONFeature): Selection | null => {
				const s = this.#byId.get(Number(f.properties?.id));
				return s ? this.#selection(s) : null;
			}
		}
	];
	/** Requests made to /api/roadweather (tests and the console). */
	requests = 0;
	#ctx: AppCtx | null = null;
	#scope: MapScope | null = null;
	#byId = new Map<number, RoadWeatherStation>();
	#visible = false;
	#destroyed = false;
	#poller: Poller | null = null;
	#debug: object | null = null;

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		this.requests++;
		const first = getJson(take(DATA_URL, { cache: 'no-store' }));
		let data: RoadWeather;
		try {
			data = await first;
		} catch (e) {
			this.status = 'error';
			this.error = `Road weather unavailable: ${e instanceof Error ? e.message : e}`;
			throw new Error(this.error);
		}
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		const scope = (this.#scope = new MapScope(map));
		for (const [id, hollow] of [[SOLID_IMAGE, false], [HOLLOW_IMAGE, true]] as const) {
			const img = badgeImage(hollow, 2);
			if (img) scope.addImage(id, img, { pixelRatio: 2 });
		}
		scope.addSource(SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] }, attribution: def.source });
		addSlotted(map, roadWeatherLayers(), def.order, (l, before) => scope.addLayer(l, before));
		this.#set(data);

		scope.on('click', this.#onClick);
		const windows = windowsOf(ctx);
		for (let n = 1; n <= 4; n++) ctx.overlay.sprite(discSprite({ key: badgeKey(n), text: String(n), color: INK, textColor: CREAM, size: 22 }));
		scope.defer(windows.registerKind(WINDOW_KIND, (d) => this.#reopen(d)));
		scope.defer(windows.listen(() => this.#syncBadges()));
		// A mode (calibrate, look-through) owns the screen: station windows step aside; the mode's
		// view snapshot brings them back when it ends (§14.3).
		scope.defer(
			$effect.root(() => {
				$effect(() => {
					if (ctx.modes.current !== 'explore') untrack(() => this.#closeWindows());
				});
			})
		);
		scope.defer(() => ctx.overlay.remove(BADGES));
		scope.defer(() => this.#stopPoll());
		this.#installDebug();
		scope.defer(() => this.#uninstallDebug());

		this.status = 'ready';
		this.setVisible(this.#visible);
	}

	/** The base map's bounds: stations outside are loaded but not drawn. */
	get bounds(): Bounds | null {
		return (this.#ctx?.manifest?.bounds as Bounds | undefined) ?? null;
	}

	#set(data: RoadWeather) {
		this.data = data;
		this.updatedAt = Date.now();
		this.skew = data.now * 1000 - Date.now();
		this.#byId = new Map(data.stations.map((s) => [s.id, s]));
		const b = this.bounds;
		this.drawn = data.stations.filter((s) => inBounds(s, b));
		(this.#scope?.map.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(stationFeatures(data.stations, b));
		// The open card follows the station's new state.
		const sel = this.#ctx?.selection.current;
		if (sel?.layer === def.id) {
			const s = this.#byId.get(Number(sel.id));
			if (s) this.#ctx?.selection.select(this.#selection(s));
		}
		this.#syncBadges();
	}

	/** Fetch the list again (the poll, or a test). */
	async refresh(signal?: AbortSignal): Promise<void> {
		this.requests++;
		const data = await getJson(fetch(DATA_URL, { cache: 'no-store', signal }));
		if (this.#destroyed || signal?.aborted) return;
		this.#set(data);
		if (this.status === 'error' || this.status === 'stale') this.status = 'ready';
	}

	station(id: number): RoadWeatherStation | undefined {
		return this.#byId.get(id);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		const map = this.#scope?.map;
		if (!map) return;
		for (const id of ALL_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		if (on) this.#startPoll();
		else this.#stopPoll();
		this.#syncBadges();
	}

	#startPoll() {
		if (this.#poller?.running) return;
		// Fresh data needs no request now: a toggle soon after loading costs nothing.
		const due = this.updatedAt === null || Date.now() - this.updatedAt >= REFRESH_MS;
		this.#poller = new Poller(
			async (signal) => {
				try {
					await this.refresh(signal);
				} catch (e) {
					// Shown, but old: ▲ on the button until a refresh works (the poller backs off meanwhile).
					if (!signal.aborted && !this.#destroyed) this.status = 'stale';
					throw e;
				}
			},
			{ interval: REFRESH_MS, immediate: due }
		);
		this.#poller.start();
	}

	#stopPoll() {
		this.#poller?.stop();
		this.#poller = null;
	}

	// --- selection, windows -------------------------------------------------------------

	#selection(s: RoadWeatherStation): Selection {
		return {
			kind: 'weather',
			id: String(s.id),
			layer: def.id,
			title: s.name,
			fact: stationFact(s),
			source: creditOf(s.provider),
			at: [s.lon, s.lat],
			data: s
		};
	}

	#spec(s: RoadWeatherStation, anchor?: Point): WindowSpec {
		return {
			key: stationKey(s.id),
			title: s.name,
			component: StationWindow,
			props: { stationId: s.id, name: s.name },
			aspect: ASPECT,
			anchor,
			status: s.hollow
				? { shape: '■', word: 'no live feed', color: 'var(--ink-soft)', detail: "Every view shows 511's “no live feed” picture" }
				: { shape: '◌', word: 'waiting', color: 'var(--ink-soft)', detail: 'Asking for the newest pictures…' },
			restore: { kind: WINDOW_KIND, data: { id: s.id } }
		};
	}

	#reopen(data: unknown): WindowSpec | null {
		const id = (data as { id?: unknown } | null)?.id;
		const s = typeof id === 'number' ? this.#byId.get(id) : undefined;
		return s ? this.#spec(s) : null;
	}

	#closeWindows() {
		const ctx = this.#ctx;
		if (!ctx) return;
		const windows = windowsOf(ctx);
		for (const w of [...windows.list]) if (stationIdOf(w.key) !== null) windows.close(w.key, { returnFocus: false, forget: false });
	}

	/** Open a station's window beside it (or focus it when open). Returns whether one is open now. */
	open(id: number, o: { focus?: boolean } = {}): boolean {
		const ctx = this.#ctx;
		const s = this.#byId.get(id);
		if (!ctx || !s) return false;
		const map = this.#scope?.map ?? null;
		let anchor: Point | undefined;
		if (map) {
			const box = map.getContainer().getBoundingClientRect();
			const p = map.project([s.lon, s.lat]);
			if (p.x >= 0 && p.y >= 0 && p.x <= box.width && p.y <= box.height) anchor = { x: box.left + p.x, y: box.top + p.y };
		}
		return windowsOf(ctx).open(this.#spec(s, anchor), { focus: o.focus ?? true }) !== null;
	}

	/** The station's window number, or null when none is open. */
	windowOf(id: number): number | null {
		return this.#ctx ? windowsOf(this.#ctx).numberOf(stationKey(id)) : null;
	}

	/** Fly the map to a station (a programmatic fly: the view history keeps where it was; a jump under reduced motion). */
	flyTo(id: number): void {
		const map = this.#scope?.map;
		const s = this.#byId.get(id);
		if (!map || !s || !this.#ctx) return;
		const to = { center: [s.lon, s.lat] as [number, number], zoom: Math.max(map.getZoom(), 13) };
		const h = historyOf(this.#ctx);
		if (h.attached) h.fly(to);
		else map.flyTo(to);
	}

	#onClick = (e: MapMouseEvent) => {
		const ctx = this.#ctx;
		if (!ctx || !this.#visible || ctx.modes.current !== 'explore') return;
		const touch = (e.originalEvent as PointerEvent | undefined)?.pointerType === 'touch';
		const top = ctx.picker.pickAt(e.point, touch).top;
		if (top?.kind === 'weather' && top.layer === def.id) this.open(Number(top.id));
	};

	/** Each open station window's number on its station (through the overlay). */
	#syncBadges() {
		const ctx = this.#ctx;
		if (!ctx || this.#destroyed) return;
		const instances: OverlayInstance[] = [];
		if (this.#visible) {
			for (const w of windowsOf(ctx).list) {
				const id = stationIdOf(w.key);
				const s = id === null ? undefined : this.#byId.get(id);
				if (!s || !inBounds(s, this.bounds) || w.number < 1 || w.number > 4) continue;
				instances.push({ id: w.key, lng: s.lon, lat: s.lat, sprite: badgeKey(w.number), offset: [14, -14], pick: this.#selection(s), radius: 12 });
			}
		}
		ctx.overlay.set(BADGES, instances, { z: 55, priority: PRIORITY.weather });
	}

	// --- chrome ---------------------------------------------------------------------------

	summary(): string | null {
		const n = this.data?.stations.length ?? 0;
		return n ? `${n} road-weather station${n === 1 ? '' : 's'}` : null;
	}

	destroy(): void {
		this.#destroyed = true;
		this.#stopPoll();
		this.#scope?.dispose();
		this.#scope = null;
	}

	// --- debug ------------------------------------------------------------------------------

	/** A read-only handle for tests and the console: `__tvtRoadWeather`. */
	#installDebug() {
		const ctx = this.#ctx!;
		const handle = Object.freeze({
			/** The stations drawn, with where the map puts them now (CSS px in the map). */
			stations: () =>
				this.drawn.map((s) => {
					const p = this.#scope?.map.project([s.lon, s.lat]);
					return { id: s.id, name: s.name, provider: s.provider, hollow: s.hollow, views: s.views.length, x: p?.x ?? null, y: p?.y ?? null };
				}),
			/** Every station loaded, drawn or not. */
			loaded: () => this.data?.stations.map((s) => ({ id: s.id, name: s.name, drawn: inBounds(s, this.bounds) })) ?? [],
			open: (id: number) => this.open(id),
			refresh: () => this.refresh(),
			requests: () => this.requests,
			polling: () => this.#poller?.running ?? false,
			windows: () =>
				windowsOf(ctx)
					.list.filter((w) => stationIdOf(w.key) !== null)
					.map((w) => ({ key: w.key, stationId: stationIdOf(w.key), number: w.number, status: w.status ? `${w.status.shape} ${w.status.word}` : null }))
		});
		Object.defineProperty(globalThis, '__tvtRoadWeather', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#debug = handle;
	}

	#uninstallDebug() {
		if ((globalThis as { __tvtRoadWeather?: unknown }).__tvtRoadWeather === this.#debug) Reflect.deleteProperty(globalThis, '__tvtRoadWeather');
		this.#debug = null;
	}
}

export function create(): LayerModule {
	return new RoadWeatherModule();
}
