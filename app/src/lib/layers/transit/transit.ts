import type { ExpressionSpecification } from 'maplibre-gl';
import type { Feature, LineString } from 'geojson';
import type { SlottedLayer } from '#lib/map/order.js';

/**
 * The Transit layer's pure parts (docs/13 §13.5, ported from the Transit lens
 * to the layer registry by WP2): Valley Regional Transit's routes in our
 * route colors, stops, and live buses that glide to each new position with
 * fading trails. Color never carries identity alone: every bus wears its
 * route number, and route numbers repeat along the lines.
 *
 * Positions arrive 35–50 s old (the feed refreshes every ~30 s), so a bus is
 * drawn where it last reported, never extrapolated, and a bus that goes quiet
 * for two minutes turns hollow. WP8 replaces this with the ribbons and the
 * delayed playback of §14.4.
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

export interface Stop {
	stopId: string;
	name: string;
	routeIds: string[];
}

/** Buses the feed doesn't place on a route. */
export const UNKNOWN_COLOR = '#8a857c';
export const INK = '#2b2a33';
export const CREAM = '#fffbf4';
export const STALE_AFTER_S = 120;
export const TRAIL_S = 300;
export const GLIDE_MS = 2500;
export const POLL_MS = 15_000;
export const CREDIT = 'Valley Regional Transit (CC BY 3.0)';

export const L = {
	casing: 'transit-routes-casing',
	routes: 'transit-routes',
	labels: 'transit-route-labels',
	stops: 'transit-stops',
	trails: 'transit-trails'
} as const;
/** The fallback bus layers, used only when the overlay can't start. */
export const FALLBACK = {
	heading: 'transit-bus-heading',
	buses: 'transit-buses',
	numbers: 'transit-bus-numbers'
} as const;
export const TRANSIT_LAYERS: string[] = Object.values(L);
export const FALLBACK_LAYERS: string[] = Object.values(FALLBACK);
export const SOURCES = { shapes: 'transit-shapes', stops: 'transit-stops', trails: 'transit-trails', buses: 'transit-buses' } as const;
export const ARROW = 'transit-arrow';

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

/** Metres between two lon/lat points (equirectangular; fine at bus scale). */
export function metres(a: [number, number], b: [number, number]): number {
	const k = Math.cos((((a[1] + b[1]) / 2) * Math.PI) / 180);
	const dx = (b[0] - a[0]) * k * 111_320;
	const dy = (b[1] - a[1]) * 110_574;
	return Math.hypot(dx, dy);
}

/** Routes with at least one live (not stale) bus, and how many each has. */
export function liveByRoute(vehicles: readonly Vehicle[], now: number): Record<string, number> {
	const out: Record<string, number> = {};
	for (const v of vehicles) {
		if (isStale(v, now)) continue;
		const k = v.routeId ?? '?';
		out[k] = (out[k] ?? 0) + 1;
	}
	return out;
}

const zoomWidth = (base: number): ExpressionSpecification => ['interpolate', ['linear'], ['zoom'], 10, base * 0.6, 13, base, 16, base * 1.8];

/**
 * The layers, each with its slot (docs/14 §14.8 "Layer order"): route lines
 * and trails in `routes` (draped), stops in `points`, route numbers in
 * `labels`. All start hidden. Buses are drawn by the overlay.
 */
export function transitLayers(): SlottedLayer[] {
	const hidden = { visibility: 'none' as const };
	return [
		{ slot: 'routes', layer: { id: L.casing, type: 'line', source: SOURCES.shapes,
			layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' },
			paint: { 'line-color': INK, 'line-opacity': 0.55, 'line-width': zoomWidth(5.5) } } },
		{ slot: 'routes', layer: { id: L.routes, type: 'line', source: SOURCES.shapes,
			layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' },
			paint: { 'line-color': ['get', 'color'], 'line-width': zoomWidth(3.5) } } },
		{ slot: 'routes', layer: { id: L.trails, type: 'line', source: SOURCES.trails, layout: { ...hidden, 'line-cap': 'round' },
			paint: { 'line-color': ['get', 'color'], 'line-opacity': ['get', 'opacity'], 'line-width': zoomWidth(4) } } },
		{ slot: 'points', layer: { id: L.stops, type: 'circle', source: SOURCES.stops, minzoom: 14.5, layout: hidden,
			paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 14.5, 2.5, 18, 5], 'circle-color': CREAM,
				'circle-stroke-color': INK, 'circle-stroke-width': 1.2 } } },
		{ slot: 'labels', layer: { id: L.labels, type: 'symbol', source: SOURCES.shapes, minzoom: 12,
			layout: { ...hidden, 'symbol-placement': 'line', 'symbol-spacing': 320, 'text-field': ['get', 'shortName'],
				'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-rotation-alignment': 'viewport' },
			paint: { 'text-color': INK, 'text-halo-color': CREAM, 'text-halo-width': 2 } } }
	];
}

/** The fallback bus layers (circle and number), only when the overlay can't start; on top of the labels. */
export function fallbackBusLayers(): SlottedLayer[] {
	const hidden = { visibility: 'none' as const };
	return [
		{ slot: 'overlay', layer: { id: FALLBACK.heading, type: 'symbol', source: SOURCES.buses, filter: ['has', 'bearing'],
			layout: { ...hidden, 'icon-image': ARROW, 'icon-rotate': ['get', 'bearing'], 'icon-rotation-alignment': 'map',
				'icon-offset': [0, -15], 'icon-allow-overlap': true, 'icon-ignore-placement': true },
			paint: { 'icon-opacity': ['case', ['get', 'stale'], 0.35, 1] } } },
		{ slot: 'overlay', layer: { id: FALLBACK.buses, type: 'circle', source: SOURCES.buses, layout: hidden,
			paint: {
				'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 7, 13, 11, 17, 14],
				'circle-color': ['case', ['get', 'stale'], CREAM, ['get', 'color']],
				'circle-stroke-color': ['case', ['get', 'stale'], ['get', 'color'], CREAM],
				'circle-stroke-width': ['case', ['get', 'stale'], 2.5, 2]
			} } },
		{ slot: 'overlay', layer: { id: FALLBACK.numbers, type: 'symbol', source: SOURCES.buses,
			layout: { ...hidden, 'text-field': ['get', 'number'], 'text-font': ['Noto Sans Medium'],
				'text-size': ['interpolate', ['linear'], ['zoom'], 10, 8, 13, 11, 17, 13],
				'text-allow-overlap': true, 'text-ignore-placement': true },
			paint: { 'text-color': ['case', ['get', 'stale'], INK, ['get', 'textColor']] } } }
	];
}

/** A small heading arrow for the fallback layers: ink with a cream outline, pointing up (north) before rotation. */
export function arrowImage(): ImageData {
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
