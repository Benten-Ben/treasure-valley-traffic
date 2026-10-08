import type { Feature, LineString } from 'geojson';
import type { SlottedLayer } from '#lib/map/order.js';

/**
 * Small shared parts of the Transit layer (docs/14 §14.4): the credit and
 * colors, age and stop wording, and the fallback bus layers, which draw buses
 * as a symbol layer only when the overlay can't start (§14.8). The routes,
 * stops and playback are in network.ts and playback.ts (WP8), which replaced
 * the Transit lens's own route layers and gliding buses. The trail and glide
 * helpers below are what's left of that lens, kept with their tests.
 */

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
export const CREDIT = 'Valley Regional Transit (CC BY 3.0)';

/** The fallback bus layers, used only when the overlay can't start. */
export const FALLBACK = {
	heading: 'transit-bus-heading',
	buses: 'transit-buses',
	numbers: 'transit-bus-numbers'
} as const;
export const FALLBACK_LAYERS: string[] = Object.values(FALLBACK);
/** The fallback bus layers' source (the same id as network.ts's SOURCES.buses). */
export const SOURCES = { buses: 'transit-buses' } as const;
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
