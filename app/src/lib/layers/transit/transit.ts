import type { ExpressionSpecification, GeoJSONSource, MapGeoJSONFeature, MapLayerMouseEvent } from 'maplibre-gl';
import type { Feature, FeatureCollection, LineString, Point } from 'geojson';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { firstBasemapLabel } from '#lib/map/style.js';
import { Poller } from '#lib/state/poll.svelte.js';

/**
 * The Transit lens (docs/13 §13.5): Valley Regional Transit's routes in our
 * route colors, stops, and live buses that glide to each new position with
 * fading trails. Color never carries identity alone: every bus wears its
 * route number, and route numbers repeat along the lines.
 *
 * Positions arrive 35–50 s old (the feed refreshes every ~30 s), so a bus is
 * drawn where it last reported, never extrapolated, and a bus that goes quiet
 * for two minutes turns hollow.
 *
 * Adapted to the app context (WP1): the routes fetch starts at boot, the
 * layers attach on `style.load`, vehicles are polled only while the lens is
 * shown and the tab is visible, clicks count only in Explore, and `destroy()`
 * removes everything it added. WP2 ports this to `#lib/layers/transit/`.
 */

export interface TransitRoute {
	route_id: string;
	short_name: string;
	long_name: string | null;
	color: string;
	text_color: string;
}

export interface Vehicle {
	vehicleId: string;
	label: string | null;
	routeId: string | null;
	/** The feed didn't name the route; it was matched from the bus's path. */
	routeMatched: boolean;
	shortName: string | null;
	longName: string | null;
	color: string | null;
	textColor: string | null;
	ts: number; // fix time, epoch seconds
	lon: number;
	lat: number;
	bearing: number | null;
	status: number | null; // GTFS-rt: 0 incoming at, 1 stopped at, 2 in transit to
	stopName: string | null;
	trail: [number, number, number][]; // lon, lat, epoch seconds; oldest first
}

/** Buses the feed doesn't place on a route. */
export const UNKNOWN_COLOR = '#8a857c';
const INK = '#2b2a33';
const CREAM = '#fffbf4';
export const STALE_AFTER_S = 120;
export const TRAIL_S = 300;
const GLIDE_MS = 2500;
const POLL_MS = 15_000;

const L = {
	wash: 'transit-wash',
	casing: 'transit-routes-casing',
	routes: 'transit-routes',
	labels: 'transit-route-labels',
	stops: 'transit-stops',
	trails: 'transit-trails',
	buses: 'transit-buses',
	numbers: 'transit-bus-numbers',
	heading: 'transit-bus-heading'
};
export const TRANSIT_LAYERS = Object.values(L);

export const isStale = (v: Pick<Vehicle, 'ts'>, now: number) => now - v.ts > STALE_AFTER_S;

/** "40 s ago", "3 min ago", "1 h 5 min ago". */
export function ageText(seconds: number): string {
	const s = Math.max(0, Math.round(seconds));
	if (s < 90) return `${s} s ago`;
	const m = Math.round(s / 60);
	return m < 60 ? `${m} min ago` : `${Math.floor(m / 60)} h ${m % 60} min ago`;
}

/** What the bus is doing relative to its stop, in words. */
export function stopText(v: Pick<Vehicle, 'status' | 'stopName'>): string | null {
	if (!v.stopName) return null;
	return v.status === 1 ? `At ${v.stopName}` : v.status === 0 ? `Arriving at ${v.stopName}` : `Next stop: ${v.stopName}`;
}

/**
 * A bus's trail as short segments that fade with age: newest nearly solid,
 * oldest almost gone. Points older than maxAge are dropped.
 */
export function trailSegments(v: Vehicle, now: number, maxAge = TRAIL_S): Feature<LineString>[] {
	const pts = v.trail.filter((p) => now - p[2] <= maxAge);
	const out: Feature<LineString>[] = [];
	for (let i = 1; i < pts.length; i++) {
		const a = pts[i - 1];
		const b = pts[i];
		if (a[0] === b[0] && a[1] === b[1]) continue;
		const age = now - (a[2] + b[2]) / 2;
		out.push({
			type: 'Feature',
			geometry: { type: 'LineString', coordinates: [[a[0], a[1]], [b[0], b[1]]] },
			properties: { color: v.color ?? UNKNOWN_COLOR, routeId: v.routeId ?? '', opacity: Math.max(0.06, 0.8 * (1 - age / maxAge)) }
		});
	}
	return out;
}

/** Ease in and out, so a glide starts and lands softly. */
export const ease = (t: number) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

export function lerp(a: [number, number], b: [number, number], t: number): [number, number] {
	return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/** A small heading arrow: ink with a cream outline, pointing up (north) before rotation. */
function arrowImage(): ImageData {
	const s = 32;
	const c = document.createElement('canvas');
	c.width = c.height = s;
	const g = c.getContext('2d')!;
	g.beginPath();
	g.moveTo(s / 2, 3);
	g.lineTo(s - 6, s - 7);
	g.lineTo(s / 2, s - 12);
	g.lineTo(6, s - 7);
	g.closePath();
	g.lineJoin = 'round';
	g.lineWidth = 5;
	g.strokeStyle = CREAM;
	g.stroke();
	g.fillStyle = INK;
	g.fill();
	return g.getImageData(0, 0, s, s);
}


type Handlers = {
	onSelect: (v: Vehicle | null) => void;
	onUpdate: (vehicles: Vehicle[], now: number) => void;
	onError: (message: string | null) => void;
};


export class TransitLayer {
	routes: TransitRoute[] = [];
	private vehicles: Vehicle[] = [];
	private now = Date.now() / 1000;
	private shown: Record<string, [number, number]> = {}; // where each bus is drawn right now
	private glides: Record<string, { from: [number, number]; to: [number, number] }> = {};
	private glideStart = 0;
	private frame = 0;
	private visible = false;
	private spot: string | null = null;
	private scope: MapScope | null = null;
	private destroyed = false;
	/** Vehicles are polled only while the lens is shown and the tab is visible. */
	readonly poller = new Poller((signal) => this.poll(signal), { interval: POLL_MS });

	constructor(
		private app: AppCtx,
		private on: Handlers
	) {}

	/**
	 * Fetch routes and stops (at once, versioned by /api/meta) and add the
	 * hidden layers when the style is ready. False if transit data isn't
	 * available or the map isn't.
	 */
	async load(): Promise<boolean> {
		let data: { routes: TransitRoute[]; shapes: FeatureCollection; stops: FeatureCollection };
		try {
			const res = await fetch(await this.app.dataUrl('/api/transit/routes', 'gtfs'));
			if (!res.ok) {
				const msg = (await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`;
				this.on.onError(`Transit unavailable: ${msg}`);
				return false;
			}
			data = await res.json();
		} catch (e) {
			this.on.onError(`Transit unavailable: ${e instanceof Error ? e.message : e}`);
			return false;
		}
		const map = await this.app.styleReady.catch(() => null);
		if (!map || this.destroyed) return false;
		this.routes = data.routes;
		const scope = (this.scope = new MapScope(map));
		const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
		const credit = 'Valley Regional Transit (CC BY 3.0)';
		scope.addSource('transit-wash', {
			type: 'geojson',
			data: { type: 'Polygon', coordinates: [[[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]]] }
		});
		scope.addSource('transit-shapes', { type: 'geojson', data: data.shapes, attribution: credit });
		scope.addSource('transit-stops', { type: 'geojson', data: data.stops });
		scope.addSource('transit-trails', { type: 'geojson', data: empty });
		scope.addSource('transit-buses', { type: 'geojson', data: empty });
		scope.addImage('transit-arrow', arrowImage(), { pixelRatio: 2 });

		// Route lines, stops and trails go under the basemap's labels; buses on top of everything.
		const firstLabel = firstBasemapLabel(map);
		const zoomWidth = (base: number): ExpressionSpecification =>
			['interpolate', ['linear'], ['zoom'], 10, base * 0.6, 13, base, 16, base * 1.8];
		const hidden = { visibility: 'none' as const };
		scope.addLayer({ id: L.wash, type: 'fill', source: 'transit-wash', layout: hidden,
			paint: { 'fill-color': '#f6f0e6', 'fill-opacity': 0.42 } }, firstLabel);
		scope.addLayer({ id: L.casing, type: 'line', source: 'transit-shapes',
			layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' },
			paint: { 'line-color': INK, 'line-opacity': 0.55, 'line-width': zoomWidth(5.5) } }, firstLabel);
		scope.addLayer({ id: L.routes, type: 'line', source: 'transit-shapes',
			layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' },
			paint: { 'line-color': ['get', 'color'], 'line-width': zoomWidth(3.5) } }, firstLabel);
		scope.addLayer({ id: L.trails, type: 'line', source: 'transit-trails', layout: { ...hidden, 'line-cap': 'round' },
			paint: { 'line-color': ['get', 'color'], 'line-opacity': ['get', 'opacity'], 'line-width': zoomWidth(4) } },
			firstLabel);
		scope.addLayer({ id: L.stops, type: 'circle', source: 'transit-stops', minzoom: 14.5, layout: hidden,
			paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 14.5, 2.5, 18, 5], 'circle-color': CREAM,
				'circle-stroke-color': INK, 'circle-stroke-width': 1.2 } }, firstLabel);
		scope.addLayer({ id: L.labels, type: 'symbol', source: 'transit-shapes', minzoom: 12,
			layout: { ...hidden, 'symbol-placement': 'line', 'symbol-spacing': 320, 'text-field': ['get', 'shortName'],
				'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-rotation-alignment': 'viewport' },
			paint: { 'text-color': INK, 'text-halo-color': CREAM, 'text-halo-width': 2 } });
		scope.addLayer({ id: L.heading, type: 'symbol', source: 'transit-buses', filter: ['has', 'bearing'],
			layout: { ...hidden, 'icon-image': 'transit-arrow', 'icon-rotate': ['get', 'bearing'],
				'icon-rotation-alignment': 'map', 'icon-offset': [0, -15], 'icon-allow-overlap': true,
				'icon-ignore-placement': true },
			paint: { 'icon-opacity': ['case', ['get', 'stale'], 0.35, 1] } });
		scope.addLayer({ id: L.buses, type: 'circle', source: 'transit-buses', layout: hidden,
			paint: {
				'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 7, 13, 11, 17, 14],
				'circle-color': ['case', ['get', 'stale'], CREAM, ['get', 'color']],
				'circle-stroke-color': ['case', ['get', 'stale'], ['get', 'color'], CREAM],
				'circle-stroke-width': ['case', ['get', 'stale'], 2.5, 2]
			} });
		scope.addLayer({ id: L.numbers, type: 'symbol', source: 'transit-buses',
			layout: { ...hidden, 'text-field': ['get', 'number'], 'text-font': ['Noto Sans Medium'],
				'text-size': ['interpolate', ['linear'], ['zoom'], 10, 8, 13, 11, 17, 13],
				'text-allow-overlap': true, 'text-ignore-placement': true },
			paint: { 'text-color': ['case', ['get', 'stale'], INK, ['get', 'textColor']] } });

		const exploring = () => this.app.modes.current === 'explore';
		scope.onLayer('click', L.buses, (e: MapLayerMouseEvent) => {
			if (!exploring()) return;
			const id = (e.features?.[0] as MapGeoJSONFeature | undefined)?.properties?.vehicleId;
			this.on.onSelect(this.vehicles.find((v) => v.vehicleId === id) ?? null);
		});
		for (const id of [L.buses, L.routes]) {
			scope.onLayer('mouseenter', id, () => {
				if (exploring()) map.getCanvas().style.cursor = 'pointer';
			});
			scope.onLayer('mouseleave', id, () => {
				if (exploring()) map.getCanvas().style.cursor = '';
			});
		}
		scope.onLayer('click', L.routes, (e: MapLayerMouseEvent) => {
			if (!exploring()) return;
			if (map.queryRenderedFeatures(e.point, { layers: [L.buses] }).length) return;
			const id = (e.features?.[0] as MapGeoJSONFeature | undefined)?.properties?.routeId ?? null;
			this.spotlight(this.spot === id ? null : id);
		});
		if (this.visible) this.setVisible(true);
		return true;
	}

	setVisible(on: boolean) {
		this.visible = on;
		const map = this.scope?.map;
		if (map) for (const id of TRANSIT_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		if (on && map) this.poller.start();
		else this.poller.stop();
	}

	/** Highlight one route (or none): the others dim. */
	spotlight(routeId: string | null) {
		this.spot = routeId;
		const map = this.scope?.map;
		if (!map) return;
		const dim = (bright: number, faint: number): ExpressionSpecification | number =>
			routeId === null ? bright : ['case', ['==', ['get', 'routeId'], routeId], bright, faint];
		map.setPaintProperty(L.routes, 'line-opacity', dim(1, 0.15));
		map.setPaintProperty(L.casing, 'line-opacity', dim(0.55, 0.08));
		map.setPaintProperty(L.labels, 'text-opacity', dim(1, 0.15));
		map.setPaintProperty(L.buses, 'circle-opacity', dim(1, 0.25));
		map.setPaintProperty(L.buses, 'circle-stroke-opacity', dim(1, 0.25));
		map.setPaintProperty(L.numbers, 'text-opacity', dim(1, 0.3));
		map.setPaintProperty(L.trails, 'line-opacity', routeId === null ? ['get', 'opacity']
			: ['case', ['==', ['get', 'routeId'], routeId], ['get', 'opacity'], 0.04]);
	}

	get spotlit() {
		return this.spot;
	}

	/** Stop polling and animating, and remove every source, layer, image and handler this added. */
	destroy() {
		this.destroyed = true;
		this.poller.stop();
		cancelAnimationFrame(this.frame);
		this.scope?.dispose();
		this.scope = null;
	}

	private async poll(signal: AbortSignal) {
		try {
			const res = await fetch('/api/transit/vehicles', { signal });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			if (signal.aborted || this.destroyed) return;
			this.on.onError(null);
			this.update(data.vehicles, data.now);
		} catch (err) {
			if (signal.aborted) return;
			this.on.onError(`Live buses unavailable: ${err instanceof Error ? err.message : err}`);
			throw err;
		}
	}

	private update(vehicles: Vehicle[], now: number) {
		this.vehicles = vehicles;
		this.now = now;
		for (const v of vehicles) {
			const to: [number, number] = [v.lon, v.lat];
			this.glides[v.vehicleId] = { from: this.shown[v.vehicleId] ?? to, to };
		}
		for (const id of Object.keys(this.glides))
			if (!vehicles.some((v) => v.vehicleId === id)) delete this.glides[id];
		(this.scope?.map.getSource('transit-trails') as GeoJSONSource | undefined)?.setData({
			type: 'FeatureCollection',
			features: vehicles.flatMap((v) => trailSegments(v, now))
		});
		this.on.onUpdate(vehicles, now);
		this.glideStart = performance.now();
		cancelAnimationFrame(this.frame);
		this.animate();
	}

	private animate = () => {
		const t = Math.min(1, (performance.now() - this.glideStart) / GLIDE_MS);
		const k = ease(t);
		const features: Feature<Point>[] = [];
		for (const v of this.vehicles) {
			const g = this.glides[v.vehicleId];
			if (!g) continue;
			const at = lerp(g.from, g.to, k);
			this.shown[v.vehicleId] = at;
			const props: Record<string, unknown> = {
				vehicleId: v.vehicleId,
				routeId: v.routeId ?? '',
				number: v.shortName ?? '?',
				color: v.color ?? UNKNOWN_COLOR,
				textColor: v.textColor ?? CREAM,
				stale: isStale(v, this.now)
			};
			if (v.bearing !== null) props.bearing = v.bearing;
			features.push({ type: 'Feature', geometry: { type: 'Point', coordinates: at }, properties: props });
		}
		(this.scope?.map.getSource('transit-buses') as GeoJSONSource | undefined)?.setData({ type: 'FeatureCollection', features });
		if (t < 1 && this.visible && !this.destroyed) this.frame = requestAnimationFrame(this.animate);
	};
}

