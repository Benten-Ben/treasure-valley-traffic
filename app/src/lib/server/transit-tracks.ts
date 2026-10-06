import type postgres from 'postgres';
import {
	TRACKS_CONTRACT,
	type RouteSource,
	type StepKind,
	type TrackStep,
	type TrackVehicle,
	type Tracks
} from '#lib/contracts/tracks.js';

/**
 * Playback steps for GET /api/transit/tracks (docs/14 §14.4 "Playback";
 * contract in #lib/contracts/tracks).
 *
 * One query joins the bus fixes with their progress rows (migration 0007,
 * written by ingest/transit_progress.py) and each fix's next fix (`lead()`).
 * "Along" steps carry their path, a `ST_LineSubstring` of the matched shape
 * between the two measures (two pieces across a loop seam). Fixes with no
 * progress row yet still come through, classified here from time and
 * distance alone (gap, still or straight), so playback never goes blank,
 * not even before migration 0007 or the first backfill.
 *
 * - The window ends at T: now, or a past `at` pinned for replay and tests,
 *   in which case nothing after `at` is visible and `now` is `at`.
 * - A bus's newest fix up to T is a step with `t1 = null`. Buses whose newest
 *   fix is more than 15 min old are left out (the client hides them then).
 * - `routeRuns`: per route, spans of fixes over the 75 min before T, split
 *   where consecutive fixes are more than 15 min apart.
 * - A 5 s in-process micro-cache means N viewers cost one query.
 */

export const DEFAULT_WINDOW_S = 120;
export const MAX_WINDOW_S = 900;
/** A bus's newest fix is shown (waiting, then stale) for this long, then hidden. */
export const STALE_S = 900;
export const RUNS_S = 75 * 60;
export const RUN_SPLIT_S = 900;
/** The step rules from ingest/transit_progress.py, for fixes not matched yet. */
export const GAP_S = 150;
export const STILL_M = 12;
const CACHE_MS = 5_000;
const CACHE_MAX = 32;
/** Path simplification, metres (UTM 11N): drops collinear vertices, keeps the turns. */
const SIMPLIFY_M = 1;

export const INK = '#2b2a33';
export const WHITE = '#ffffff';
/** Buses whose route isn't known (§14.4). */
export const UNKNOWN_ROUTE = '#8a857c';
const BADGE_MIN = 4.5;

// -- parameters -----------------------------------------------------------------------------------

/** `window` in seconds: default 120, at most 900; null when it isn't a positive whole number. */
export function parseWindow(value: string | null): number | null {
	if (value === null || value === '') return DEFAULT_WINDOW_S;
	if (!/^\d{1,6}$/.test(value)) return null;
	const n = Number(value);
	return n >= 1 ? Math.min(n, MAX_WINDOW_S) : null;
}

/**
 * `at` as epoch seconds: null for live (absent, or not in the past);
 * undefined when it can't be read as a time.
 */
export function parseAt(value: string | null, nowS: number): number | null | undefined {
	if (value === null || value === '') return null;
	const ms = Date.parse(value);
	if (!Number.isFinite(ms)) return undefined;
	const at = Math.floor(ms / 1000);
	return at < nowS ? at : null;
}

// -- the badge rule (§14.3), as in ingest/route_colors.py -------------------------------------------

function luminance(hex: string): number {
	const n = parseInt(hex.slice(1), 16);
	const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
		const c = v / 255;
		return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
	});
	return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
	const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
	return (hi + 0.05) / (lo + 0.05);
}

const isHex = (c: string | null | undefined): c is string => !!c && /^#[0-9a-f]{6}$/i.test(c);

/** Plate color, numeral color and halo for a route color (unknown routes are gray, with a halo). */
export function badge(color: string | null, textColor: string | null): { color: string; textColor: string; halo: boolean } {
	const plate = isHex(color) ? color.toLowerCase() : UNKNOWN_ROUTE;
	const given = textColor?.toLowerCase();
	const text = given === WHITE || given === INK ? given : contrast(plate, WHITE) >= contrast(plate, INK) ? WHITE : INK;
	return { color: plate, textColor: text, halo: contrast(plate, text) < BADGE_MIN };
}

// -- steps -------------------------------------------------------------------------------------------

/** A step between two fixes that the matcher hasn't reached: time and distance only. */
export function fallbackStep(dt: number, chord: number): [StepKind, number | null] {
	if (dt > GAP_S) return ['gap', null];
	if (chord < STILL_M) return ['still', 0];
	return ['straight', dt > 0 ? chord / dt : null];
}

/** One row of the steps query: a fix, its next fix (if any, up to T) and, on a bus's newest fix, the bus. */
export interface StepRow {
	vid: string;
	t0: number;
	t1: number | null;
	lon: number;
	lat: number;
	bearing: number | null;
	/** The matcher's step, when both this fix and the next have progress rows. */
	step: StepKind | null;
	speed: number | null;
	/** Metres to the next fix. */
	chord: number | null;
	/** GeoJSON LineString of an along step's path. */
	path: string | null;
	// The vehicle (newest fix only):
	label?: string | null;
	route_id?: string | null;
	route_source?: RouteSource | null;
	short_name?: string | null;
	color?: string | null;
	text_color?: string | null;
	headsign?: string | null;
}

const r6 = (v: number) => Math.round(v * 1e6) / 1e6;
const r1 = (v: number | null) => (v === null || v === undefined ? null : Math.round(v * 10) / 10);

/** A GeoJSON line as flat lon,lat,…; null for anything else (a zero-length substring is a Point). */
export function flatPath(geojson: string | null): number[] | null {
	if (!geojson) return null;
	const g = JSON.parse(geojson) as { type?: string; coordinates?: unknown };
	const lines =
		g.type === 'LineString' ? [g.coordinates as number[][]] : g.type === 'MultiLineString' ? (g.coordinates as number[][][]) : [];
	const out: number[] = [];
	for (const line of lines) {
		for (const [lon, lat] of line) {
			const x = r6(lon);
			const y = r6(lat);
			if (out.length && out[out.length - 2] === x && out[out.length - 1] === y) continue;
			out.push(x, y);
		}
	}
	return out.length >= 4 ? out : null;
}

/** A query row as a contract step. */
export function toStep(row: StepRow): TrackStep {
	const base = [row.vid, row.t0, row.t1] as const;
	const at = [r6(row.lon), r6(row.lat), row.bearing === null ? null : Math.round(row.bearing)] as const;
	if (row.t1 === null) return [...base, null, ...at, null, null];
	const dt = row.t1 - row.t0;
	let kind: StepKind | null = row.step;
	let speed: number | null = row.speed;
	let path: number[] | null = null;
	if (kind === 'along') {
		path = flatPath(row.path);
		// A matched step whose path can't be drawn (its shape is gone) still plays, straight.
		if (!path) [kind, speed] = ['straight', row.chord !== null && dt > 0 ? row.chord / dt : null];
	} else if (kind === null) {
		[kind, speed] = fallbackStep(dt, row.chord ?? 0);
	} else if (kind === 'still') speed = 0;
	else if (kind === 'gap') speed = null;
	return [...base, kind, ...at, r1(speed), path];
}

/** The vehicle record from a bus's newest fix. */
export function toVehicle(row: StepRow): TrackVehicle {
	const known = row.route_id ?? null;
	const b = badge(known ? (row.color ?? null) : null, known ? (row.text_color ?? null) : null);
	return {
		label: row.label ?? null,
		routeId: known,
		routeSource: known ? (row.route_source ?? null) : null,
		shortName: known ? (row.short_name ?? known) : null,
		color: b.color,
		textColor: b.textColor,
		halo: b.halo,
		headsign: row.headsign ?? null
	};
}

// -- running routes ----------------------------------------------------------------------------------

/**
 * Spans of fixes per route: rows (route, epoch s) in any order; a new span starts
 * wherever consecutive fixes of the route are more than RUN_SPLIT_S apart.
 */
export function routeRuns(rows: { route: string; t: number }[]): Record<string, [number, number][]> {
	const by = new Map<string, number[]>();
	for (const { route, t } of rows) {
		let ts = by.get(route);
		if (!ts) by.set(route, (ts = []));
		ts.push(t);
	}
	const out: Record<string, [number, number][]> = {};
	for (const route of [...by.keys()].sort()) {
		const ts = by.get(route)!.sort((a, b) => a - b);
		const spans: [number, number][] = [];
		for (const t of ts) {
			const last = spans[spans.length - 1];
			if (last && t - last[1] <= RUN_SPLIT_S) last[1] = t;
			else spans.push([t, t]);
		}
		out[route] = spans;
	}
	return out;
}

/** §14.4 "Running": a route is running at T iff some span starts at or before T and ends at or after T − 900 s. */
export function runningAt(runs: Record<string, [number, number][]>, T: number): Set<string> {
	const out = new Set<string>();
	for (const [route, spans] of Object.entries(runs)) {
		if (spans.some(([start, end]) => start <= T && end >= T - RUN_SPLIT_S)) out.add(route);
	}
	return out;
}

// -- assembling the answer (pure) ---------------------------------------------------------------------

export type TracksBody = Omit<Tracks, 'now'>;

export function assemble(rows: StepRow[], runRows: { route: string; t: number }[], lastFix: number | null): TracksBody {
	const vehicles: Record<string, TrackVehicle> = {};
	const steps: TrackStep[] = [];
	for (const row of rows) {
		steps.push(toStep(row));
		if (row.t1 === null) vehicles[row.vid] = toVehicle(row);
	}
	return { contract: TRACKS_CONTRACT, vehicles, steps, routeRuns: routeRuns(runRows), lastFix };
}

// -- queries ------------------------------------------------------------------------------------------

/** obs.vehicle_progress, or an empty stand-in with its columns before migration 0007. */
function progressTable(sql: postgres.Sql, exists: boolean) {
	return exists
		? sql`obs.vehicle_progress`
		: sql`(select null::text as vehicle_id, null::timestamptz as ts, null::text as shape_id, null::real as m,
		              null::text as route_id, null::text as route_source, null::text as step,
		              null::real as step_speed_ms, null::text as method)`;
}

/** The steps whose time span meets [T − window, T], plus each bus's newest fix up to 15 min old. */
function stepsQuery(sql: postgres.Sql, T: number, windowS: number, hasProgress: boolean) {
	const lo = T - windowS - STALE_S;
	const g = progressTable(sql, hasProgress);
	return sql<StepRow[]>`
		with fx as (
			select p.vehicle_id, p.ts, p.geom, p.bearing, p.vehicle_label, p.trip_id, p.route_id,
			       (p.ts at time zone 'America/Boise')::date as d,
			       g.shape_id, g.m, g.route_id as g_route, g.route_source as g_source, g.step, g.step_speed_ms,
			       g.vehicle_id is not null as matched
			from obs.vehicle_position p
			left join ${g} g on g.vehicle_id = p.vehicle_id and g.ts = p.ts
			where p.ts > to_timestamp(${lo}::float8) and p.ts <= to_timestamp(${T}::float8)
			  and g.method is distinct from 'late'
		),
		seq as (
			select fx.*, lead(ts) over w as ts1, lead(geom) over w as geom1, lead(m) over w as m1,
			       lead(shape_id) over w as shape1, lead(matched) over w as matched1
			from fx window w as (partition by vehicle_id order by ts)
		),
		st as (
			select * from seq
			where (ts1 is null and ts >= to_timestamp(${T - STALE_S}::float8))
			   or ts1 >= to_timestamp(${T - windowS}::float8)
		),
		tm as (
			select t.trip_id, t.d,
			       (select x.route_id from obs.trip_route_match x
			        where x.trip_id = t.trip_id and x.service_date between t.d - 1 and t.d
			        order by x.service_date desc limit 1) as route_id
			from (select distinct trip_id, d from st where ts1 is null and route_id is null and trip_id is not null) t
		),
		sh as materialized (
			select s.shape_id, s.route_id, ST_Transform(s.geom, 26911) as g, ST_Length(ST_Transform(s.geom, 26911)) as len
			from core.transit_shape s
			where s.shape_id in (select shape_id from st where shape_id is not null)
		),
		hs as (
			select distinct on (shape_id) shape_id, headsign
			from core.transit_trip
			where headsign is not null and shape_id in (select shape_id from sh)
			group by shape_id, headsign
			order by shape_id, count(*) desc, headsign
		),
		v as (
			select st.vehicle_id, st.ts,
			       coalesce(st.route_id, tm.route_id, case when st.g_source = 'path' then st.g_route end) as route_id,
			       case when st.route_id is not null then
			                 case when st.g_source in ('feed', 'trip') then st.g_source
			                      when coalesce(st.trip_id, '') <> '' then 'trip' else 'feed' end
			            when tm.route_id is not null then 'matched'
			            when st.g_source = 'path' then 'path' end as route_source
			from st left join tm on tm.trip_id = st.trip_id and tm.d = st.d
			where st.ts1 is null
		)
		select st.vehicle_id as vid,
		       extract(epoch from st.ts)::float8 as t0,
		       extract(epoch from st.ts1)::float8 as t1,
		       ST_X(st.geom) as lon, ST_Y(st.geom) as lat, st.bearing,
		       case when st.matched and st.matched1 then st.step end as step,
		       st.step_speed_ms as speed,
		       case when st.ts1 is not null then ST_Distance(st.geom::geography, st.geom1::geography) end as chord,
		       case when st.step = 'along' and st.matched and st.matched1 and st.shape1 = st.shape_id and sh.len > 0
		                 and st.m1 <> st.m then
		         ST_AsGeoJSON(ST_Transform(ST_Simplify(
		           case when st.m1 >= st.m
		             then ST_LineSubstring(sh.g, greatest(least(st.m / sh.len, 1), 0), greatest(least(st.m1 / sh.len, 1), 0))
		             -- across a loop's seam: to the end, then from the start
		             else ST_MakeLine(ST_LineSubstring(sh.g, greatest(least(st.m / sh.len, 1), 0), 1),
		                              ST_LineSubstring(sh.g, 0, greatest(least(st.m1 / sh.len, 1), 0)))
		           end, ${SIMPLIFY_M}::float8, true), 4326), 6)
		       end as path,
		       case when st.ts1 is null then st.vehicle_label end as label,
		       v.route_id, v.route_source, r.short_name, r.color, r.text_color,
		       case when st.ts1 is null then
		         coalesce(tt.headsign, case when sh.route_id = v.route_id then hs.headsign end) end as headsign
		from st
		left join sh on sh.shape_id = st.shape_id
		left join v on v.vehicle_id = st.vehicle_id and v.ts = st.ts
		left join core.transit_route r on r.route_id = v.route_id
		left join core.transit_trip tt on st.ts1 is null and tt.trip_id = st.trip_id
		left join hs on st.ts1 is null and hs.shape_id = st.shape_id
		order by st.vehicle_id, st.ts`;
}

/** Every route-attributed fix in the 75 min before T (feed, trip ID, trip_route_match or path), deduplicated. */
function runsQuery(sql: postgres.Sql, T: number, hasProgress: boolean) {
	const g = progressTable(sql, hasProgress);
	return sql<{ route: string; t: number }[]>`
		with fx as (
			select p.vehicle_id, p.ts, p.trip_id, p.route_id, (p.ts at time zone 'America/Boise')::date as d
			from obs.vehicle_position p
			where p.ts > to_timestamp(${T - RUNS_S}::float8) and p.ts <= to_timestamp(${T}::float8)
		),
		tm as (
			select t.trip_id, t.d,
			       (select x.route_id from obs.trip_route_match x
			        where x.trip_id = t.trip_id and x.service_date between t.d - 1 and t.d
			        order by x.service_date desc limit 1) as route_id
			from (select distinct trip_id, d from fx where route_id is null and trip_id is not null) t
		),
		a as (
			select coalesce(fx.route_id, tm.route_id, case when g.route_source = 'path' then g.route_id end) as route,
			       extract(epoch from fx.ts)::float8 as t
			from fx
			left join tm on tm.trip_id = fx.trip_id and tm.d = fx.d
			left join ${g} g on g.vehicle_id = fx.vehicle_id and g.ts = fx.ts
		)
		select distinct route, t from a where route is not null`;
}

let progressKnown: { at: number; exists: boolean } | undefined;

/** Whether migration 0007 is applied; rechecked every minute until it is. */
async function hasProgressTable(sql: postgres.Sql, nowMs: number): Promise<boolean> {
	if (progressKnown && (progressKnown.exists || nowMs - progressKnown.at < 60_000)) return progressKnown.exists;
	const [row] = await sql`select to_regclass('obs.vehicle_progress') is not null as exists`;
	progressKnown = { at: nowMs, exists: Boolean(row.exists) };
	return progressKnown.exists;
}

/** Read the tracks for the window ending at T (epoch s) from the database. */
export async function readTracks(sql: postgres.Sql, T: number, windowS: number, nowMs = Date.now()): Promise<TracksBody> {
	const hasProgress = await hasProgressTable(sql, nowMs);
	const [rows, runs, [last]] = await Promise.all([
		stepsQuery(sql, T, windowS, hasProgress),
		runsQuery(sql, T, hasProgress),
		sql<{ t: number | null }[]>`
			select extract(epoch from max(ts))::float8 as t from obs.vehicle_position where ts <= to_timestamp(${T}::float8)`
	]);
	return assemble(rows, runs, last?.t ?? null);
}

// -- the micro-cache ----------------------------------------------------------------------------------

type Loader = (T: number, windowS: number) => Promise<TracksBody>;
const cache = new Map<string, { at: number; value: Promise<TracksBody> }>();

/**
 * The answer for a window (s) and an optional pinned `at` (epoch s). Requests
 * for the same window and `at` within 5 s share one query; `now` is filled in
 * per response, so the client's clock offset stays exact.
 */
export async function tracks(
	load: Loader,
	windowS: number,
	at: number | null,
	nowMs = Date.now()
): Promise<{ body: Tracks; hit: boolean }> {
	const key = `${windowS}|${at ?? 'live'}`;
	let entry = cache.get(key);
	const hit = Boolean(entry && nowMs - entry.at < CACHE_MS);
	if (!hit) {
		const T = at ?? Math.floor(nowMs / 1000);
		entry = { at: nowMs, value: load(T, windowS) };
		cache.delete(key);
		cache.set(key, entry);
		while (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value!);
		// A failure isn't cached: the next request tries again.
		const failed = entry;
		entry.value.catch(() => {
			if (cache.get(key) === failed) cache.delete(key);
		});
	}
	const body = await entry!.value;
	return { body: { ...body, now: at ?? nowMs / 1000 }, hit };
}

/** For tests: forget cached answers and what's known about the schema. */
export function resetTracksCache() {
	cache.clear();
	progressKnown = undefined;
}
