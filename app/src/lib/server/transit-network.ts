import { createHash } from 'node:crypto';
import type postgres from 'postgres';
import {
	NETWORK_CONTRACT,
	type DormantRoute,
	type NetworkHub,
	type NetworkRoute,
	type NetworkSegment,
	type NetworkStop,
	type TransitNetwork
} from '#lib/contracts/network.js';

/**
 * GET /api/transit/network (docs/14 §14.4, §14.8 "APIs"; contract in
 * #lib/contracts/network). Routes with their colors, the side-by-side corridor
 * segments that ingest/transit_ribbons.py builds, stops placed across their
 * bundle, hubs and dormant routes.
 *
 * - With a ribbon build (core.transit_ribbon has rows), segments are the
 *   build's: routes left to right, dormant routes in none of them.
 * - Without one (before migration 0006, a fresh deploy or a failed first
 *   build), each active route's plain shapes come as unbundled segments with
 *   one route each (`bundled: false`, build 'none'), so Transit never goes
 *   blank.
 *
 * The answer for a build never changes, so it's computed once per build and
 * kept; the plain-shapes answer is kept for a minute.
 *
 * The palette helpers (ghost, badge text and halo) mirror
 * ingest/route_colors.py, and tests pin both to the same table.
 */

export const CLAY = '#f3ede2';
export const INK = '#2b2a33';
export const WHITE = '#ffffff';
export const CREAM = '#fffbf4';
/** Buses whose route isn't known, and routes without a color yet. */
export const UNKNOWN_ROUTE = '#8a857c';
const BADGE_MIN = 4.5;

/** The 13 append-only route slots (docs/14 §14.4) with their ghosts on clay. Never edit a hex. */
export const ROUTE_PALETTE: readonly { name: string; color: string; ghost: string }[] = [
	{ name: 'blue', color: '#2a78d6', ghost: '#b1c6e2' },
	{ name: 'orange', color: '#eb6834', ghost: '#f5b59a' },
	{ name: 'aqua', color: '#1baf7a', ghost: '#a4d2b2' },
	{ name: 'yellow', color: '#eda100', ghost: '#f1c17b' },
	{ name: 'pink', color: '#e87ba4', ghost: '#f1b3c2' },
	{ name: 'green', color: '#008300', ghost: '#b3cda4' },
	{ name: 'violet', color: '#4a3aa7', ghost: '#bab8d4' },
	{ name: 'red', color: '#e34948', ghost: '#f4b3a7' },
	{ name: 'wine', color: '#99095c', ghost: '#deafb8' },
	{ name: 'lavender', color: '#a791fa', ghost: '#cbc0f1' },
	{ name: 'brown', color: '#7f4315', ghost: '#d1b8a4' },
	{ name: 'plum', color: '#9059af', ghost: '#d1bad3' },
	{ name: 'lime', color: '#8cc63f', ghost: '#b9d88e' }
];

// -- color helpers (ingest/route_colors.py) ------------------------------------------------------

const s2lin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const lin2s = (c: number) => {
	c = Math.max(0, Math.min(1, c));
	return c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
};

function linear(hex: string): [number, number, number] {
	const h = hex.replace('#', '');
	return [0, 2, 4].map((i) => s2lin(parseInt(h.slice(i, i + 2), 16) / 255)) as [number, number, number];
}

function oklab([r, g, b]: [number, number, number]): [number, number, number] {
	const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
	const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
	const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
	return [
		0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
		1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
		0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
	];
}

function fromOklab([L, a, b]: [number, number, number]): [number, number, number] {
	const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
	const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
	const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
	return [
		4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
		-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
		-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s
	];
}

// Python's round() rounds halves to even; match it so both sides make the same hex.
const roundHalfEven = (x: number) => {
	const f = Math.floor(x);
	const d = x - f;
	return d > 0.5 ? f + 1 : d < 0.5 ? f : f % 2 === 0 ? f : f + 1;
};
const toHex = (rgb: [number, number, number]) =>
	'#' + rgb.map((c) => roundHalfEven(lin2s(c) * 255).toString(16).padStart(2, '0')).join('');

/** OKLab distance x100 (normal vision). */
export function deltaE(a: string, b: string): number {
	const p = oklab(linear(a));
	const q = oklab(linear(b));
	return 100 * Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
}

/** WCAG contrast ratio. */
export function contrast(a: string, b: string): number {
	const lum = (h: string) => {
		const [r, g, b2] = linear(h);
		return 0.2126 * r + 0.7152 * g + 0.0722 * b2;
	};
	const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
	return (x + 0.05) / (y + 0.05);
}

const ghosts = new Map(ROUTE_PALETTE.map((p) => [p.color, p.ghost]));

/**
 * The pale color a route draws in when no bus is running on it: an OKLab mix
 * from clay toward the color, at the first 0.1% step from 30% whose hex sits
 * at least dE 14 from clay. The 13 slots are pinned; anything else is computed.
 */
export function ghostOf(color: string): string {
	const c = color.toLowerCase();
	return ghosts.get(c) ?? computeGhost(c);
}

/** The ghost formula itself (ghostOf looks the 13 slots up first). */
export function computeGhost(color: string): string {
	const c = color.toLowerCase();
	const s = oklab(linear(CLAY));
	const k = oklab(linear(c));
	for (let step = 0; ; step++) {
		const t = 0.3 + step * 0.001;
		if (t >= 1) return c;
		const g = toHex(fromOklab([0, 1, 2].map((i) => s[i] + t * (k[i] - s[i])) as [number, number, number]));
		if (deltaE(g, CLAY) >= 14) return g;
	}
}

/** Badge numerals: white or ink, whichever reads better on the color. */
export function badgeTextColor(color: string): string {
	return contrast(color, WHITE) >= contrast(color, INK) ? WHITE : INK;
}

/** The badge rule (docs/14 §14.3): under 4.5:1 on the plate, numerals get a 2 px halo in the opposite tone. */
export function badge(color: string, textColor?: string | null): { textColor: string; halo: boolean } {
	const text = textColor === WHITE || textColor === INK ? textColor : badgeTextColor(color);
	return { textColor: text, halo: contrast(color, text) < BADGE_MIN };
}

// -- assembling the answer (pure) ----------------------------------------------------------------

export interface RouteRow {
	route_id: string;
	short_name: string;
	long_name: string | null;
	color: string | null;
	text_color: string | null;
	sort_order: number | null;
}

/** Routes in display order with 1-based `rid` (the feature-state key; never 0, which MapLibre treats as no id). */
export function routesOf(rows: RouteRow[]): NetworkRoute[] {
	return rows.map((r, i) => {
		const color = (r.color ?? UNKNOWN_ROUTE).toLowerCase();
		const b = badge(color, r.color ? r.text_color : null);
		return {
			id: r.route_id,
			rid: i + 1,
			shortName: r.short_name,
			longName: r.long_name,
			color,
			ghost: ghostOf(color),
			textColor: b.textColor,
			halo: b.halo,
			sortOrder: r.sort_order
		};
	});
}

/** GeoJSON LineString coordinates to the contract's flat lon,lat,… list (6 decimals). */
export function flatCoords(coordinates: number[][]): number[] {
	const out: number[] = [];
	for (const [lon, lat] of coordinates) out.push(Math.round(lon * 1e6) / 1e6, Math.round(lat * 1e6) / 1e6);
	return out;
}

export interface HubStop {
	stop_id: string;
	name: string | null;
	lon: number;
	lat: number;
	route_ids: string[];
}

const HUB_JOIN_M = 300;

function metres(a: { lon: number; lat: number }, b: { lon: number; lat: number }) {
	const k = Math.cos(((a.lat + b.lat) / 2) * (Math.PI / 180));
	return Math.hypot((a.lon - b.lon) * k, a.lat - b.lat) * 111_320;
}

/**
 * Stations from stops served by 6 or more routes, stops within 300 m of each
 * other joined into one (the busiest names it, without a " - Lower Deck"
 * style suffix).
 */
export function hubsOf(stops: HubStop[]): NetworkHub[] {
	const sorted = [...stops].sort((a, b) => b.route_ids.length - a.route_ids.length || a.stop_id.localeCompare(b.stop_id));
	const groups: HubStop[][] = [];
	for (const s of sorted) {
		const g = groups.find((g) => metres(g[0], s) <= HUB_JOIN_M);
		if (g) g.push(s);
		else groups.push([s]);
	}
	return groups.map((g) => {
		const head = g[0];
		return {
			id: head.stop_id,
			name: (head.name ?? head.stop_id).split(' - ')[0].trim(),
			lon: Math.round((g.reduce((t, s) => t + s.lon, 0) / g.length) * 1e6) / 1e6,
			lat: Math.round((g.reduce((t, s) => t + s.lat, 0) / g.length) * 1e6) / 1e6,
			routes: [...new Set(g.flatMap((s) => s.route_ids))].sort()
		};
	});
}

/** Cache-Control for a request asking for version `v` (§14.8: immutable for the current build). */
export function cacheControl(net: Pick<TransitNetwork, 'build' | 'bundled'>, v: string | null): string {
	return net.bundled && net.build !== 'none' && v === net.build ? 'public, max-age=31536000, immutable' : 'no-cache';
}

// -- reading the database ------------------------------------------------------------------------

const STOP_ON_SEGMENT_M = 40;   // a stop farther than this from every segment carrying one of its routes lies on none
const HUB_ROUTES = 6;
const HUB_SEGMENT_M = 300;
const FALLBACK_SIMPLIFY_DEG = 0.000015;   // about 1.5 m, like the ribbon build

const num = (v: unknown) => (v === null || v === undefined ? null : Number(v));

export async function readNetwork(sql: postgres.Sql): Promise<TransitNetwork> {
	const [has] = await sql`select to_regclass('core.transit_ribbon') is not null as ribbons`;
	const [routeRows, hubRows, buildRows] = await Promise.all([
		sql<RouteRow[]>`
			select route_id, short_name, long_name, color, text_color, sort_order
			from core.transit_route where active
			order by sort_order nulls last,
			         case when short_name ~ '^[0-9]+$' then short_name::int end nulls last, short_name, route_id`,
		sql<HubStop[]>`
			select stop_id, name, ST_X(geom) as lon, ST_Y(geom) as lat, route_ids
			from core.transit_stop where active and cardinality(route_ids) >= ${HUB_ROUTES} order by stop_id`,
		has.ribbons
			? sql`select string_agg(distinct build, ',') as build, count(*)::int as n from core.transit_ribbon`
			: Promise.resolve([{ build: null, n: 0 }])
	]);
	const [feed] = await sql`select feed_version from core.transit_route where active order by updated_at desc limit 1`;
	const bundled = buildRows[0].n > 0;
	const build: string = bundled ? String(buildRows[0].build) : 'none';
	const routes = routesOf(routeRows);
	const active = new Set(routes.map((r) => r.id));

	let segments: NetworkSegment[];
	let stops: NetworkStop[];
	let dormant: DormantRoute[] = [];
	if (bundled) {
		const rows = await sql`
			select segment_id, routes, hub, length_m, ST_AsGeoJSON(geom, 6)::json as g
			from core.transit_ribbon order by segment_id`;
		// A build older than the feed (its rebuild failed) may name a retired route: leave it out.
		segments = rows
			.map((r) => ({
				id: r.segment_id,
				coords: flatCoords(r.g.coordinates),
				routes: (r.routes as string[]).filter((id) => active.has(id)),
				hub: r.hub,
				lengthM: Math.round(Number(r.length_m))
			}))
			.filter((s) => s.routes.length > 0);
		const kept = new Map(segments.map((s) => [s.id, s.routes.length]));
		stops = (await readStops(sql, 'ribbon')).map((s) =>
			s.segment === null || kept.get(s.segment) === s.n ? s
			: kept.has(s.segment) ? { ...s, n: kept.get(s.segment)! }
			: { ...s, segment: null, n: 1, bearing: null });
		const d = await sql`
			select r.route_id,
			       extract(epoch from greatest(
			         (select max(p.ts) from obs.vehicle_position p where p.route_id = r.route_id),
			         (select max(p.ts) from obs.trip_route_match m
			            join obs.vehicle_position p on p.trip_id = m.trip_id
			             and p.ts >= m.service_date - 1 and p.ts < m.service_date + 2
			          where m.route_id = r.route_id
			            and m.service_date = (select max(service_date) from obs.trip_route_match where route_id = r.route_id))
			       ))::float8 as last_fix
			from core.transit_route r
			where r.active
			  and exists (select 1 from core.transit_shape s where s.route_id = r.route_id and s.active)
			  and not exists (select 1 from core.transit_ribbon b where r.route_id = any(b.routes))`;
		const rank = new Map(routes.map((r, i) => [r.id, i]));
		dormant = d
			.map((x) => ({ routeId: String(x.route_id), lastFix: num(x.last_fix) }))
			.sort((a, b) => (rank.get(a.routeId) ?? 0) - (rank.get(b.routeId) ?? 0));
	} else {
		const rows = await sql`
			with hubs as (
			  select geom from core.transit_stop where active and cardinality(route_ids) >= ${HUB_ROUTES})
			select s.route_id, ST_AsGeoJSON(ST_SimplifyPreserveTopology(s.geom, ${FALLBACK_SIMPLIFY_DEG}), 6)::json as g,
			       ST_Length(s.geom::geography) as length_m,
			       exists (select 1 from hubs h
			               where ST_DWithin(ST_LineInterpolatePoint(s.geom, 0.5)::geography, h.geom::geography, ${HUB_SEGMENT_M})) as hub
			from core.transit_shape s join core.transit_route r on r.route_id = s.route_id and r.active
			where s.active order by s.shape_id`;
		segments = rows.map((r, i) => ({
			id: i + 1,
			coords: flatCoords(r.g.coordinates),
			routes: [String(r.route_id)],
			hub: r.hub,
			lengthM: Math.round(Number(r.length_m))
		}));
		stops = await readStops(sql, 'shapes');
	}
	return {
		contract: NETWORK_CONTRACT,
		build,
		bundled,
		feedVersion: feed?.feed_version ?? null,
		routes,
		segments,
		stops,
		hubs: hubsOf(hubRows.map((h) => ({ ...h, lon: Number(h.lon), lat: Number(h.lat) }))),
		dormant
	};
}

/**
 * Stops with the segment their capsule lies across: the nearest segment within
 * 40 m carrying one of the stop's routes, its bundle size and its bearing there.
 * Without a build the plain shapes stand in, numbered as in the answer.
 */
async function readStops(sql: postgres.Sql, from: 'ribbon' | 'shapes'): Promise<NetworkStop[]> {
	const lines =
		from === 'ribbon'
			? sql`select segment_id as id, routes, geom from core.transit_ribbon`
			: sql`select (row_number() over (order by s.shape_id))::int as id, array[s.route_id] as routes, s.geom
			      from core.transit_shape s join core.transit_route r on r.route_id = s.route_id and r.active
			      where s.active`;
	const rows = await sql`
		with seg as (${lines}),
		stop as (
		  select stop_id, name, geom, route_ids from core.transit_stop where active and cardinality(route_ids) > 0)
		select s.stop_id, s.name, ST_X(s.geom) as lon, ST_Y(s.geom) as lat, s.route_ids,
		       n.id as segment, coalesce(cardinality(n.routes), 1) as n,
		       case when n.id is null then null else degrees(ST_Azimuth(
		         ST_LineInterpolatePoint(n.geom, greatest(n.f - n.d, 0))::geography,
		         ST_LineInterpolatePoint(n.geom, least(n.f + n.d, 1))::geography)) end as bearing
		from stop s
		left join lateral (
		  select g.id, g.routes, g.geom, ST_LineLocatePoint(g.geom, s.geom) as f,
		         least(1, 10 / greatest(ST_Length(g.geom::geography), 1)) as d
		  from seg g
		  where g.routes && s.route_ids
		    and g.geom && ST_Expand(s.geom, 0.0006)
		    and ST_DWithin(g.geom::geography, s.geom::geography, ${STOP_ON_SEGMENT_M})
		  order by ST_Distance(g.geom::geography, s.geom::geography), g.id
		  limit 1) n on true
		order by s.stop_id`;
	return rows.map((r) => ({
		id: r.stop_id,
		name: r.name,
		lon: Math.round(Number(r.lon) * 1e6) / 1e6,
		lat: Math.round(Number(r.lat) * 1e6) / 1e6,
		routes: r.route_ids,
		segment: r.segment ?? null,
		n: Number(r.n),
		bearing: r.bearing === null ? null : Math.round(Number(r.bearing) * 10) / 10
	}));
}

// -- the cached answer ---------------------------------------------------------------------------

export interface NetworkAnswer {
	build: string;
	bundled: boolean;
	body: string;
	etag: string;
}

const FALLBACK_TTL_MS = 60_000;
let cached: { key: string; at: number; value: Promise<NetworkAnswer> } | undefined;

async function currentBuild(sql: postgres.Sql): Promise<string> {
	const [has] = await sql`select to_regclass('core.transit_ribbon') is not null as ribbons`;
	if (!has.ribbons) return 'none';
	const [b] = await sql`select string_agg(distinct build, ',') as build from core.transit_ribbon`;
	return b.build ?? 'none';
}

/** The serialized answer: computed once per build (the plain-shapes answer once a minute). */
export async function transitNetwork(sql: postgres.Sql, nowMs = Date.now()): Promise<NetworkAnswer> {
	const key = await currentBuild(sql);
	if (cached && cached.key === key && (key !== 'none' || nowMs - cached.at < FALLBACK_TTL_MS)) {
		try {
			return await cached.value;
		} catch {
			// a failed computation isn't kept: fall through and retry
		}
	}
	const value = readNetwork(sql).then((net) => {
		const body = JSON.stringify(net);
		return {
			build: net.build,
			bundled: net.bundled,
			body,
			etag: `"${createHash('sha1').update(body).digest('hex').slice(0, 20)}"`
		};
	});
	cached = { key, at: nowMs, value };
	value.catch(() => {
		if (cached?.value === value) cached = undefined;
	});
	return value;
}

/** For tests: forget the cached answer. */
export function resetNetworkCache() {
	cached = undefined;
}
