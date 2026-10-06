import type { ExpressionSpecification, GeoJSONSource, MapGeoJSONFeature } from 'maplibre-gl';
import type { Feature, FeatureCollection, Point } from 'geojson';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { addSlotted } from '#lib/map/order.js';
import { discSprite, needsHalo, ringSprite, type OverlayInstance, type SpriteDef } from '#lib/overlay/index.js';
import { Poller } from '#lib/state/poll.svelte.js';
import { take } from '../prefetch.js';
import { PRIORITY, type Badge, type Chip, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import def from './def.js';
import Legend from './Legend.svelte';
import {
	ageText,
	ARROW,
	arrowImage,
	CREAM,
	CREDIT,
	ease,
	fallbackBusLayers,
	FALLBACK_LAYERS,
	GLIDE_MS,
	INK,
	isStale,
	L,
	lerp,
	liveByRoute,
	metres,
	POLL_MS,
	SOURCES,
	STALE_AFTER_S,
	TRANSIT_LAYERS,
	trailSegments,
	transitLayers,
	UNKNOWN_COLOR,
	type Stop,
	type TransitRoute,
	type Vehicle
} from './transit.js';

const BUS_GROUP = 'transit-buses';
const HEADING_GROUP = 'transit-heading';
const RING_GROUP = 'transit-selected';
const HEADING = 'transit-heading';
const RING = 'transit-ring';

/** The heading arrow as an overlay sprite: drawn at the top of a square centred on the bus, so turning it puts the arrow ahead. */
function headingSprite(): SpriteDef {
	const s = 44;
	return {
		key: HEADING,
		width: s,
		height: s,
		draw(g) {
			const c = s / 2;
			g.beginPath();
			g.moveTo(c, 1.5);
			g.lineTo(c + 6, 11);
			g.lineTo(c, 8.5);
			g.lineTo(c - 6, 11);
			g.closePath();
			g.lineJoin = 'round';
			g.lineWidth = 2.5;
			g.strokeStyle = CREAM;
			g.stroke();
			g.fillStyle = INK;
			g.fill();
		}
	};
}

export function badgeFor(v: { shortName: string | null; color: string | null; textColor: string | null }): Badge {
	const color = v.color ?? UNKNOWN_COLOR;
	const textColor = v.textColor ?? (v.color ? CREAM : INK);
	return { text: v.shortName ?? '?', color, textColor, halo: needsHalo(color, textColor) };
}

export function routeBadge(r: TransitRoute): Badge {
	return { text: r.short_name, color: r.color, textColor: r.text_color, halo: needsHalo(r.color, r.text_color) };
}

const parseIds = (v: unknown): string[] => {
	if (Array.isArray(v)) return v.map(String);
	if (typeof v === 'string') {
		try {
			const x = JSON.parse(v);
			return Array.isArray(x) ? x.map(String) : [];
		} catch {
			return [];
		}
	}
	return [];
};

/**
 * The Transit module: routes and stops from /api/transit/routes (versioned
 * by the GTFS feed), live buses from /api/transit/vehicles polled every 15 s
 * while shown and the tab is visible. Buses are discs with their route
 * number in the overlay, gliding to each new fix with no `setData`; trails
 * change once per poll. If the overlay can't start, the lens-era circle
 * layers draw the buses instead.
 */
export class TransitModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	routes = $state.raw<TransitRoute[]>([]);
	vehicles = $state.raw<Vehicle[]>([]);
	/** The server's clock at the last poll (epoch s). */
	feedNow = $state(0);
	/** The spotlit route: every other one dims. */
	spot = $state<string | null>(null);
	pollError = $state<string | null>(null);
	Legend = Legend;
	Card = Card;
	readonly poller = new Poller((signal) => this.#poll(signal), { interval: POLL_MS });
	interactive: Interactive[] = [
		{
			layerIds: [L.routes],
			priority: PRIORITY.route,
			pick: (f: MapGeoJSONFeature) => {
				const r = this.routes.find((x) => x.route_id === f.properties?.routeId);
				return r ? this.routeSelection(r) : null;
			}
		},
		{
			layerIds: [L.stops],
			priority: PRIORITY.stop,
			pick: (f: MapGeoJSONFeature) => {
				const p = f.properties ?? {};
				const stop: Stop = { stopId: String(p.stopId), name: String(p.name ?? 'Stop'), routeIds: parseIds(p.routeIds) };
				return {
					kind: 'stop',
					id: stop.stopId,
					layer: 'transit',
					title: stop.name,
					fact: `${stop.routeIds.length} route${stop.routeIds.length === 1 ? '' : 's'} stop here`,
					source: CREDIT,
					at: f.geometry.type === 'Point' ? (f.geometry.coordinates.slice(0, 2) as [number, number]) : undefined,
					data: stop
				};
			}
		},
		{
			// The fallback bus layer, when the overlay can't start.
			layerIds: [FALLBACK_LAYERS[1]],
			priority: PRIORITY.bus,
			pick: (f: MapGeoJSONFeature) => {
				const v = this.vehicles.find((x) => x.vehicleId === f.properties?.vehicleId);
				return v ? this.busSelection(v) : null;
			}
		}
	];

	#ctx: AppCtx | null = null;
	#scope: MapScope | null = null;
	#visible = false;
	#destroyed = false;
	#useOverlay = false;
	#shown: Record<string, [number, number]> = {};
	#glides: Record<string, { from: [number, number]; to: [number, number] }> = {};
	#glideStart = 0;
	#fastest = 0;
	#frame = 0;
	#buses: OverlayInstance[] = [];
	#headings: OverlayInstance[] = [];
	#ring: OverlayInstance[] = [];
	#selectedBus: string | null = null;

	routeSelection(r: TransitRoute): Selection {
		const n = liveByRoute(this.vehicles, this.feedNow)[r.route_id] ?? 0;
		return {
			kind: 'route',
			id: r.route_id,
			layer: 'transit',
			title: r.long_name ?? `Route ${r.short_name}`,
			fact: n ? `${n} bus${n === 1 ? '' : 'es'} live` : 'No live buses',
			source: CREDIT,
			badge: routeBadge(r)
		};
	}

	busSelection(v: Vehicle): Selection {
		return {
			kind: 'bus',
			id: v.vehicleId,
			layer: 'transit',
			title: `${v.longName ?? 'Route not reported'} · bus ${v.label ?? v.vehicleId}`,
			fact: `updated ${ageText(this.feedNow - v.ts)}`,
			source: CREDIT,
			badge: badgeFor(v),
			data: v.vehicleId
		};
	}

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		let data: { routes: TransitRoute[]; shapes: FeatureCollection; stops: FeatureCollection };
		try {
			const res = await take(await ctx.dataUrl('/api/transit/routes', 'gtfs'));
			if (!res.ok) {
				const msg = (await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`;
				throw new Error(msg);
			}
			data = await res.json();
		} catch (e) {
			this.status = 'error';
			this.error = `Transit unavailable: ${e instanceof Error ? e.message : e}`;
			throw new Error(this.error);
		}
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		this.routes = data.routes;
		const scope = (this.#scope = new MapScope(map));
		const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
		scope.addSource(SOURCES.shapes, { type: 'geojson', data: data.shapes, attribution: CREDIT });
		scope.addSource(SOURCES.stops, { type: 'geojson', data: data.stops });
		scope.addSource(SOURCES.trails, { type: 'geojson', data: empty });
		addSlotted(map, transitLayers(), def.order, (l, before) => scope.addLayer(l, before));
		this.#useOverlay = ctx.overlay.ok;
		if (this.#useOverlay) {
			const o = ctx.overlay;
			o.sprite(headingSprite());
			o.sprite(ringSprite(RING, 44));
			o.set(HEADING_GROUP, [], { z: 9 });
			o.set(BUS_GROUP, [], { z: 10, priority: PRIORITY.bus });
			o.set(RING_GROUP, [], { z: 11 });
			scope.defer(() => {
				for (const g of [HEADING_GROUP, BUS_GROUP, RING_GROUP]) o.remove(g);
			});
		} else {
			scope.addSource(SOURCES.buses, { type: 'geojson', data: empty });
			scope.addImage(ARROW, arrowImage(), { pixelRatio: 2 });
			addSlotted(map, fallbackBusLayers(), def.order, (l, before) => scope.addLayer(l, before));
		}
		this.status = 'ready';
		this.updatedAt = Date.now();
		this.setVisible(this.#visible);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		const map = this.#scope?.map;
		if (!map) return;
		const layers = this.#useOverlay ? TRANSIT_LAYERS : [...TRANSIT_LAYERS, ...FALLBACK_LAYERS];
		for (const id of layers) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		if (this.#useOverlay) this.#drawBuses();
		if (on) this.poller.start();
		else this.poller.stop();
	}

	/** Spotlight one route (others dim), or none. */
	spotlight(routeId: string | null): void {
		this.spot = routeId;
		const map = this.#scope?.map;
		if (!map) return;
		const dim = (bright: number, faint: number): ExpressionSpecification | number =>
			routeId === null ? bright : ['case', ['==', ['get', 'routeId'], routeId], bright, faint];
		map.setPaintProperty(L.routes, 'line-opacity', dim(1, 0.15));
		map.setPaintProperty(L.casing, 'line-opacity', dim(0.55, 0.08));
		map.setPaintProperty(L.labels, 'text-opacity', dim(1, 0.15));
		map.setPaintProperty(
			L.trails,
			'line-opacity',
			routeId === null ? ['get', 'opacity'] : ['case', ['==', ['get', 'routeId'], routeId], ['get', 'opacity'], 0.04]
		);
		if (this.#useOverlay) this.#drawBuses();
	}

	/** Select a route (spotlighting it) from the legend, or clear it. */
	selectRoute(routeId: string | null): void {
		const ctx = this.#ctx;
		if (!ctx) return;
		const r = routeId ? this.routes.find((x) => x.route_id === routeId) : null;
		if (r) ctx.selection.select(this.routeSelection(r));
		else if (ctx.selection.current?.layer === 'transit') ctx.selection.clear();
	}

	selected(s: Selection | null): void {
		this.spotlight(s?.layer === 'transit' && s.kind === 'route' ? s.id : null);
		this.#selectedBus = s?.layer === 'transit' && s.kind === 'bus' ? s.id : null;
		if (this.#useOverlay) this.#drawBuses();
	}

	chips(): Chip[] {
		if (this.status !== 'ready' && this.status !== 'stale') return [];
		const now = this.feedNow || Date.now() / 1000;
		const live = this.vehicles.filter((v) => !isStale(v, now));
		const running = Object.keys(liveByRoute(this.vehicles, now)).filter((k) => k !== '?').length;
		const newest = this.vehicles.length ? Math.max(...this.vehicles.map((v) => v.ts)) : null;
		const age = newest === null ? null : now - newest;
		const stale = Boolean(this.pollError) || age === null || age >= STALE_AFTER_S;
		const title = `${CREDIT} · ${this.pollError ?? (age === null ? 'no bus has reported in the last 15 minutes' : `newest position ${ageText(age)}`)}`;
		return [
			{ id: 'buses', text: `${live.length} bus${live.length === 1 ? '' : 'es'}`, title, stale },
			{ id: 'routes', text: `${running}/${this.routes.length} routes running`, title, stale }
		];
	}

	summary(): string | null {
		return this.routes.length ? `${this.routes.length} routes` : null;
	}

	destroy(): void {
		this.#destroyed = true;
		this.poller.stop();
		cancelAnimationFrame(this.#frame);
		this.#scope?.dispose();
		this.#scope = null;
	}

	async #poll(signal: AbortSignal) {
		try {
			const res = await fetch('/api/transit/vehicles', { signal });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			if (signal.aborted || this.#destroyed) return;
			this.pollError = null;
			if (this.status === 'stale') this.status = 'ready';
			this.#update(data.vehicles, data.now);
		} catch (err) {
			if (signal.aborted) return;
			this.pollError = `Live buses unavailable: ${err instanceof Error ? err.message : err}`;
			this.status = 'stale';
			throw err;
		}
	}

	#update(vehicles: Vehicle[], now: number) {
		this.vehicles = vehicles;
		this.feedNow = now;
		this.updatedAt = Date.now();
		this.#fastest = 0;
		for (const v of vehicles) {
			const to: [number, number] = [v.lon, v.lat];
			const from = this.#shown[v.vehicleId] ?? to;
			this.#glides[v.vehicleId] = { from, to };
			this.#fastest = Math.max(this.#fastest, metres(from, to));
		}
		for (const id of Object.keys(this.#glides)) if (!vehicles.some((v) => v.vehicleId === id)) delete this.#glides[id];
		(this.#scope?.map.getSource(SOURCES.trails) as GeoJSONSource | undefined)?.setData({
			type: 'FeatureCollection',
			features: vehicles.flatMap((v) => trailSegments(v, now))
		});
		this.#glideStart = performance.now();
		if (this.#useOverlay) {
			this.#drawBuses();
			this.#ctx?.overlay.update(BUS_GROUP, this.#glide);
		} else {
			cancelAnimationFrame(this.#frame);
			this.#animateFallback();
		}
	}

	/** Rebuild the overlay instances (on a poll, a spotlight or a selection; never per frame). */
	#drawBuses() {
		const o = this.#ctx?.overlay;
		if (!o) return;
		if (!this.#visible) {
			this.#buses = [];
			this.#headings = [];
			this.#ring = [];
		} else {
			const now = this.feedNow;
			const buses: OverlayInstance[] = [];
			const headings: OverlayInstance[] = [];
			for (const v of this.vehicles) {
				const stale = isStale(v, now);
				const b = badgeFor(v);
				const key = `bus:${b.color}:${b.textColor}:${b.text}:${stale ? 'h' : 's'}`;
				if (!o.hasSprite(key)) o.sprite(discSprite({ key, text: b.text, color: b.color, textColor: b.textColor, hollow: stale, halo: stale ? false : b.halo }));
				const at = this.#shown[v.vehicleId] ?? [v.lon, v.lat];
				const dim = this.spot !== null && v.routeId !== this.spot;
				buses.push({ id: v.vehicleId, lng: at[0], lat: at[1], sprite: key, opacity: dim ? 0.3 : 1, pick: this.busSelection(v), radius: 14 });
				if (v.bearing !== null)
					headings.push({ id: v.vehicleId, lng: at[0], lat: at[1], sprite: HEADING, rotate: v.bearing, rotateWithMap: true, opacity: stale ? 0.35 : dim ? 0.3 : 1 });
			}
			this.#buses = buses;
			this.#headings = headings;
			const sel = buses.find((b) => b.id === this.#selectedBus);
			this.#ring = sel ? [{ id: sel.id, lng: sel.lng, lat: sel.lat, sprite: RING }] : [];
		}
		o.set(BUS_GROUP, this.#buses);
		o.set(HEADING_GROUP, this.#headings);
		o.set(RING_GROUP, this.#ring);
	}

	/** Per rendered frame while buses glide: move the instances (no setData). Returns the fastest speed, m/s. */
	#glide = () => {
		const t = Math.min(1, (performance.now() - this.#glideStart) / GLIDE_MS);
		const k = ease(t);
		const heads = new Map(this.#headings.map((h) => [h.id, h]));
		for (const inst of this.#buses) {
			const g = this.#glides[inst.id];
			if (!g) continue;
			const at = lerp(g.from, g.to, k);
			this.#shown[inst.id] = at;
			inst.lng = at[0];
			inst.lat = at[1];
			const h = heads.get(inst.id);
			if (h) {
				h.lng = at[0];
				h.lat = at[1];
			}
			for (const r of this.#ring) if (r.id === inst.id) [r.lng, r.lat] = at;
		}
		// The ease peaks at twice the average speed.
		return t < 1 ? (2 * this.#fastest) / (GLIDE_MS / 1000) : false;
	};

	/** The lens-era glide on the fallback layers (setData per frame; only when the overlay can't start). */
	#animateFallback = () => {
		const t = Math.min(1, (performance.now() - this.#glideStart) / GLIDE_MS);
		const k = ease(t);
		const features: Feature<Point>[] = [];
		for (const v of this.vehicles) {
			const g = this.#glides[v.vehicleId];
			if (!g) continue;
			const at = lerp(g.from, g.to, k);
			this.#shown[v.vehicleId] = at;
			const props: Record<string, unknown> = {
				vehicleId: v.vehicleId,
				routeId: v.routeId ?? '',
				number: v.shortName ?? '?',
				color: v.color ?? UNKNOWN_COLOR,
				textColor: v.textColor ?? CREAM,
				stale: isStale(v, this.feedNow)
			};
			if (v.bearing !== null) props.bearing = v.bearing;
			features.push({ type: 'Feature', geometry: { type: 'Point', coordinates: at }, properties: props });
		}
		(this.#scope?.map.getSource(SOURCES.buses) as GeoJSONSource | undefined)?.setData({ type: 'FeatureCollection', features });
		if (t < 1 && this.#visible && !this.#destroyed) this.#frame = requestAnimationFrame(this.#animateFallback);
	};
}

export function create(): LayerModule {
	return new TransitModule();
}
