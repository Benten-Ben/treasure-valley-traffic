import type { ExpressionSpecification, FilterSpecification } from 'maplibre-gl';
import type { Feature, FeatureCollection, LineString, Point } from 'geojson';
import type { NetworkRoute, TransitNetwork } from '#lib/contracts/network.js';
import type { SlottedLayer } from '#lib/map/order.js';

/**
 * Side-by-side ribbons, shields, stop capsules and hub pills (docs/14 §14.4,
 * "Side-by-side ribbons" and "Buses and stops"; WP8). Pure: the features
 * and MapLibre layers for a /api/transit/network answer.
 *
 * - Each corridor segment expands into one feature per route, with `rid`
 *   (the route's number in this build, the source's promoteId), `slot` (its
 *   place left to right) and `n` (the bundle size). Offsets and widths come
 *   from the per-zoom table below, so a dense downtown corridor is a thin
 *   multi-colored cable that widens as you zoom in.
 * - Under the ribbons, every corridor has an opaque ink outline and a cream
 *   underlay (one feature per segment: the slot-0 one), whether or not its
 *   routes are running: ghosts are told from streets by form, not color.
 * - Running, spotlight and hover are feature-state on the route (`active`,
 *   `spot`, `dim`, `hover`), never `setData`.
 * - Shields: one label line per segment, an image of its route badges in slot
 *   order (ghost badges for routes not running), drawn on demand; that
 *   source changes only when the set of running routes does.
 * - Stops are cream capsules across the bundle, turned to the street, from
 *   z14; hubs are station pills from z14, drawn with the labels so a base
 *   POI label never covers one.
 */

/** Per-zoom ribbon width w, gap g and bundle cap B, px (§14.4): [zoom, w, g, B]. */
export const RIBBON_TABLE: readonly (readonly [number, number, number, number])[] = [
	[10, 1.5, 0, 6],
	[12, 2.25, 0.5, 10],
	[14, 3.5, 1, 18],
	[16, 5, 1.25, 30],
	[18, 7, 1.5, 48]
];

/** The outline and underlay: opaque ink at 55% pre-blended on clay, and cream. */
export const OUTLINE = '#86837f';
export const UNDERLAY = '#fffbf4';
export const INK = '#2b2a33';
export const CREAM = '#fffbf4';
/** Outline and underlay widths beyond the bundle, px. */
export const OUTLINE_EXTRA = 4.5;
export const UNDERLAY_EXTRA = 2.5;
/** The map's global state that names the spotlit route ('' for none): shields without it fade. */
export const SPOT_STATE = 'transit-spot';
/** Stops show from this zoom (capsules), hubs too. */
export const STOP_MINZOOM = 14;
export const SHIELD_MINZOOM = 13;
/** Stop capsules where no serving route is running. */
export const IDLE_STOP_OPACITY = 0.45;

export const L = {
	outline: 'transit-corridor-outline',
	underlay: 'transit-corridor-underlay',
	routes: 'transit-routes',
	trails: 'transit-trails',
	stops: 'transit-stops',
	hubs: 'transit-hubs',
	shields: 'transit-shields'
} as const;

export const SOURCES = {
	ribbons: 'transit-ribbons',
	shields: 'transit-shields',
	stops: 'transit-stops',
	hubs: 'transit-hubs',
	trails: 'transit-trails',
	buses: 'transit-buses'
} as const;

export const NETWORK_LAYERS: string[] = Object.values(L);

/** Image name prefixes (drawn on `styleimagemissing`). */
export const IMG = { shield: 'tvt-shield:', capsule: 'tvt-capsule:', pill: 'tvt-hub-pill' } as const;

// -- numbers (for tests and the capsules) -----------------------------------------------------------

/** Pitch (px between neighbouring ribbon centres) at a table row for a bundle of n. */
export const pitchAt = (w: number, g: number, B: number, n: number) => Math.min(w + g, B / n);

/** A value given per table row, at any zoom, interpolated linearly the way MapLibre interpolates stop outputs. */
export function atZoom(z: number, f: (w: number, g: number, B: number) => number): number {
	const T = RIBBON_TABLE;
	if (z <= T[0][0]) return f(T[0][1], T[0][2], T[0][3]);
	for (let i = 1; i < T.length; i++) {
		const [z1, w1, g1, B1] = T[i];
		if (z <= z1) {
			const [z0, w0, g0, B0] = T[i - 1];
			const k = (z - z0) / (z1 - z0);
			return f(w0, g0, B0) + (f(w1, g1, B1) - f(w0, g0, B0)) * k;
		}
	}
	const [, w, g, B] = T[T.length - 1];
	return f(w, g, B);
}

/** Line offset of a slot in a bundle of n, px, at a zoom. */
export const offsetPx = (z: number, slot: number, n: number) => atZoom(z, (w, g, B) => (slot - (n - 1) / 2) * pitchAt(w, g, B, n));
/** Ribbon width, px, at a zoom (running; × 0.6 when not). */
export const widthPx = (z: number, n: number, active = true) =>
	atZoom(z, (w, g, B) => Math.max(1, pitchAt(w, g, B, n) * (w / (w + g)) * (active ? 1 : 0.6)));
/** The whole bundle's width plus the outline's, px. */
export const bundlePx = (z: number, n: number, extra = OUTLINE_EXTRA) => atZoom(z, (w, g, B) => n * pitchAt(w, g, B, n) + extra);

// -- expressions -----------------------------------------------------------------------------------

const N: ExpressionSpecification = ['get', 'n'];
const pitch = (w: number, g: number, B: number): ExpressionSpecification => ['min', w + g, ['/', B, N]];
const state = (name: string): ExpressionSpecification => ['boolean', ['feature-state', name], false];

const byZoom = (f: (w: number, g: number, B: number) => ExpressionSpecification): ExpressionSpecification =>
	['interpolate', ['linear'], ['zoom'], ...RIBBON_TABLE.flatMap(([z, w, g, B]) => [z, f(w, g, B)])] as unknown as ExpressionSpecification;

export function ribbonOffset(): ExpressionSpecification {
	return byZoom((w, g, B) => ['*', ['-', ['get', 'slot'], ['/', ['-', N, 1], 2]], pitch(w, g, B)]);
}

/** Width: × 0.6 when not running, × 1.3 when selected (spotlit), + 2 px on hover. */
export function ribbonWidth(): ExpressionSpecification {
	return byZoom((w, g, B) => [
		'+',
		['max', 1, ['*', pitch(w, g, B), w / (w + g), ['case', state('spot'), 1.3, state('active'), 1, 0.6]]],
		['case', state('hover'), 2, 0]
	]);
}

/** The route color while running or spotlit; its ghost when not running or while another route is spotlit. */
export function ribbonColor(): ExpressionSpecification {
	return [
		'case',
		state('spot'),
		['get', 'color'],
		state('dim'),
		['get', 'ghost'],
		state('active'),
		['get', 'color'],
		['get', 'ghost']
	];
}

/** n · pitch + extra (the outline and underlay under a bundle). */
export function bundleWidth(extra: number): ExpressionSpecification {
	return byZoom((w, g, B) => ['+', ['*', N, pitch(w, g, B)], extra]);
}

/** While a route is spotlit, shields that don't carry it fade (global state, no setData). */
export function shieldOpacity(): ExpressionSpecification {
	const spot: ExpressionSpecification = ['to-string', ['coalesce', ['global-state', SPOT_STATE], '']];
	return ['case', ['==', spot, ''], 1, ['in', ['concat', ',', spot, ','], ['get', 'routes']], 1, 0.3];
}

/** One feature per segment carries the outline and underlay. */
const FIRST: FilterSpecification = ['==', ['get', 'slot'], 0];

// -- features --------------------------------------------------------------------------------------

export interface RibbonProps {
	rid: number;
	routeId: string;
	slot: number;
	n: number;
	color: string;
	ghost: string;
	seg: number;
}

function line(coords: number[]): LineString {
	const c: [number, number][] = [];
	for (let i = 0; i + 1 < coords.length; i += 2) c.push([coords[i], coords[i + 1]]);
	return { type: 'LineString', coordinates: c };
}

/** Each segment as one feature per route (left to right), with rid, slot and n. */
export function ribbonFeatures(net: Pick<TransitNetwork, 'routes' | 'segments'>): FeatureCollection<LineString, RibbonProps> {
	const byId = new Map(net.routes.map((r) => [r.id, r]));
	const features: Feature<LineString, RibbonProps>[] = [];
	for (const s of net.segments) {
		if (s.coords.length < 4) continue;
		const geometry = line(s.coords);
		const n = s.routes.length;
		s.routes.forEach((id, slot) => {
			const r = byId.get(id);
			if (!r) return;
			features.push({
				type: 'Feature',
				geometry,
				properties: { rid: r.rid, routeId: r.id, slot, n, color: r.color, ghost: r.ghost, seg: s.id }
			});
		});
	}
	return { type: 'FeatureCollection', features };
}

/** The shield image for a bundle: its routes' rids in slot order and which are running ('1'/'0'). */
export const shieldName = (rids: readonly number[], running: readonly boolean[]) =>
	`${IMG.shield}${rids.join('-')}:${running.map((r) => (r ? '1' : '0')).join('')}`;

/** Read a shield image name back: rids and running flags; null if it isn't one. */
export function parseShield(name: string): { rids: number[]; running: boolean[] } | null {
	if (!name.startsWith(IMG.shield)) return null;
	const [ids, mask] = name.slice(IMG.shield.length).split(':');
	const rids = ids ? ids.split('-').map(Number) : [];
	if (!rids.length || rids.some((x) => !Number.isInteger(x)) || !mask || mask.length !== rids.length) return null;
	return { rids, running: [...mask].map((c) => c === '1') };
}

/** One label line per segment: its badges in slot order, ghosts for routes not running. */
export function shieldFeatures(net: Pick<TransitNetwork, 'routes' | 'segments'>, running: ReadonlySet<string>): FeatureCollection<LineString> {
	const byId = new Map(net.routes.map((r) => [r.id, r]));
	const features: Feature<LineString>[] = [];
	for (const s of net.segments) {
		const routes = s.routes.map((id) => byId.get(id)).filter((r): r is NetworkRoute => Boolean(r));
		if (!routes.length || s.coords.length < 4) continue;
		features.push({
			type: 'Feature',
			geometry: line(s.coords),
			properties: {
				shield: shieldName(routes.map((r) => r.rid), routes.map((r) => running.has(r.id))),
				routes: `,${routes.map((r) => r.id).join(',')},`,
				seg: s.id
			}
		});
	}
	return { type: 'FeatureCollection', features };
}

export interface StopProps {
	/** 1-based index in network.stops: the promoteId. */
	sid: number;
	stopId: string;
	name: string;
	n: number;
	bearing: number;
	/** The capsule's length at z15 (px): icon-size scales it to the bundle at other zooms. */
	w15: number;
	capsule: string;
}

/** The capsule's length for a bundle of n at z15 (px): the bundle plus its outline. */
export const capsuleLength = (n: number) => Math.round(bundlePx(15, Math.max(1, n)) * 2) / 2;

/** Stops as points, each with its capsule image (by bundle size) and bearing. */
export function stopFeatures(net: Pick<TransitNetwork, 'stops'>): FeatureCollection<Point, StopProps> {
	return {
		type: 'FeatureCollection',
		features: net.stops.map((s, i) => {
			const n = Math.max(1, s.n || 1);
			return {
				type: 'Feature',
				geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
				properties: { sid: i + 1, stopId: s.id, name: s.name ?? 'Stop', n, bearing: s.bearing ?? 0, w15: capsuleLength(n), capsule: `${IMG.capsule}${n}` }
			};
		})
	};
}

export function hubFeatures(net: Pick<TransitNetwork, 'hubs'>): FeatureCollection<Point> {
	return {
		type: 'FeatureCollection',
		features: net.hubs.map((h, i) => ({
			type: 'Feature',
			geometry: { type: 'Point', coordinates: [h.lon, h.lat] },
			properties: { hid: i + 1, hubId: h.id, name: h.name }
		}))
	};
}

/** Which stops have no serving route running (for the 45% capsules). */
export function idleStops(net: Pick<TransitNetwork, 'stops'>, running: ReadonlySet<string>): boolean[] {
	return net.stops.map((s) => !s.routes.some((r) => running.has(r)));
}

// -- layers ----------------------------------------------------------------------------------------

/**
 * The network's layers, each in its slot (docs/14 §14.8 "Layer order"):
 * outline, underlay, ribbons and trails in `routes` (one draped block);
 * capsules and hub pills in `points`; shields in `labels`. All start hidden.
 */
export function networkLayers(): SlottedLayer[] {
	const hidden = { visibility: 'none' as const };
	const round = { 'line-cap': 'round' as const, 'line-join': 'round' as const };
	return [
		{ slot: 'routes', layer: { id: L.outline, type: 'line', source: SOURCES.ribbons, filter: FIRST,
			layout: { ...hidden, ...round }, paint: { 'line-color': OUTLINE, 'line-width': bundleWidth(OUTLINE_EXTRA) } } },
		{ slot: 'routes', layer: { id: L.underlay, type: 'line', source: SOURCES.ribbons, filter: FIRST,
			layout: { ...hidden, ...round }, paint: { 'line-color': UNDERLAY, 'line-width': bundleWidth(UNDERLAY_EXTRA) } } },
		{ slot: 'routes', layer: { id: L.routes, type: 'line', source: SOURCES.ribbons,
			layout: { ...hidden, ...round },
			paint: { 'line-color': ribbonColor(), 'line-width': ribbonWidth(), 'line-offset': ribbonOffset() } } },
		{ slot: 'routes', layer: { id: L.trails, type: 'line', source: SOURCES.trails,
			layout: { ...hidden, ...round }, paint: { 'line-color': INK, 'line-width': 1.5, 'line-opacity': 0.75 } } },
		{ slot: 'points', layer: { id: L.stops, type: 'symbol', source: SOURCES.stops, minzoom: STOP_MINZOOM,
			layout: { ...hidden, 'icon-image': ['get', 'capsule'], 'icon-rotate': ['get', 'bearing'],
				'icon-rotation-alignment': 'map', 'icon-pitch-alignment': 'map',
				'icon-size': ['interpolate', ['linear'], ['zoom'], ...RIBBON_TABLE.flatMap(([z, w, g, B]) =>
					[z, ['/', ['+', ['*', N, pitch(w, g, B)], OUTLINE_EXTRA], ['get', 'w15']]])] as unknown as ExpressionSpecification,
				'icon-allow-overlap': true, 'icon-ignore-placement': true },
			paint: { 'icon-opacity': ['case', state('idle'), IDLE_STOP_OPACITY, 1] } } },
		// Above the base labels, so a POI never covers the station's name.
		{ slot: 'labels', layer: { id: L.hubs, type: 'symbol', source: SOURCES.hubs, minzoom: STOP_MINZOOM,
			layout: { ...hidden, 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Medium'], 'text-size': 13,
				'icon-image': IMG.pill, 'icon-text-fit': 'both', 'icon-text-fit-padding': [3, 9, 3, 9],
				'text-allow-overlap': true, 'icon-allow-overlap': true, 'symbol-sort-key': 0 },
			paint: { 'text-color': INK } } },
		{ slot: 'labels', layer: { id: L.shields, type: 'symbol', source: SOURCES.shields, minzoom: SHIELD_MINZOOM,
			layout: { ...hidden, 'symbol-placement': 'line', 'symbol-spacing': 400, 'icon-image': ['get', 'shield'],
				'icon-rotation-alignment': 'viewport', 'icon-pitch-alignment': 'viewport', 'icon-padding': 4 },
			paint: { 'icon-opacity': shieldOpacity() } } }
	];
}
