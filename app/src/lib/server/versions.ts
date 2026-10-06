import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import type postgres from 'postgres';
import { DATABASE_URL } from '$app/env/private';
import { db } from './db.js';
import { META_CONTRACT, type DataMeta } from '#lib/contracts/meta.js';

/**
 * Data versions for GET /api/meta (docs/14 §14.8, "Boot"). Each layer's data
 * URL carries its version as `?v=`, so it can be cached until the data
 * actually changes. Tables that don't exist yet (migrations 0006 and 0007)
 * are checked with to_regclass and read as "none", so this works before and
 * after them.
 */

const TTL_MS = 15_000;

/** A short, opaque version string from anything JSON-serializable. */
export function shortHash(...parts: unknown[]): string {
	return createHash('sha1').update(JSON.stringify(parts)).digest('hex').slice(0, 12);
}

/** What the database contributes: the public fields, plus the inputs each version is hashed from. */
export type DbPart = Pick<DataMeta, 'gtfs' | 'ribbons' | 'progress' | 'roads' | 'cameras' | 'calibrations'> & {
	inputs: { roads: unknown[] | null; cameras: string | null; calibrations: unknown[] | null };
};

const num = (v: unknown) => (v === null || v === undefined ? null : Number(v));

/** Everything /api/meta reads from the database, with any postgres.js client. */
export async function readDatabase(sql: postgres.Sql): Promise<DbPart> {
	const [has] = await sql`
		select to_regclass('core.transit_route') is not null as routes,
		       to_regclass('core.transit_ribbon') is not null as ribbons,
		       to_regclass('obs.vehicle_progress') is not null as progress,
		       to_regclass('core.road_segment') is not null as roads,
		       to_regclass('core.camera') is not null as cameras,
		       to_regclass('core.camera_view') is not null as views,
		       to_regclass('core.camera_calibration') is not null as calibrations`;
	const none = Promise.resolve([] as postgres.Row[]);
	const [gtfs, ribbons, roads, cameras, views, calibrations] = await Promise.all([
		has.routes
			? sql`select (select feed_version from core.transit_route where active
			              order by updated_at desc limit 1) as feed_version,
			             count(*) filter (where active)::int as routes,
			             extract(epoch from max(updated_at))::float8 as updated_at
			      from core.transit_route`
			: none,
		has.ribbons
			? sql`select string_agg(distinct build, ',') as build, count(*)::int as segments from core.transit_ribbon`
			: none,
		has.roads
			? sql`select count(*) filter (where active)::int as segments, count(*)::int as total,
			             max(id)::text as max_id, extract(epoch from max(last_seen))::float8 as last_seen
			      from core.road_segment`
			: none,
		has.cameras
			? sql`select count(*) filter (where active)::int as cameras,
			             md5(string_agg(concat_ws(':', id, name, achd_cam_id, active,
			                 round(ST_X(pole_geom)::numeric, 7), round(ST_Y(pole_geom)::numeric, 7)), ',' order by id)) as content
			      from core.camera`
			: none,
		has.views
			? sql`select count(*)::int as views, count(image_id)::int as with_image,
			             md5(string_agg(concat_ws(':', id, camera_id, image_id, status, direction, sort_order), ',' order by id)) as content
			      from core.camera_view`
			: none,
		has.calibrations
			? sql`select count(*) filter (where upper_inf(valid))::int as current, max(id)::int as latest_id,
			             extract(epoch from max(created_at))::float8 as latest_at,
			             extract(epoch from max(upper(valid)))::float8 as closed_at
			      from core.camera_calibration`
			: none
	]);
	const g = gtfs[0];
	const r = ribbons[0];
	const rd = roads[0];
	const c = cameras[0];
	const v = views[0];
	const cal = calibrations[0];
	return {
		gtfs: g && g.routes > 0 ? { feedVersion: String(g.feed_version), routes: g.routes, updatedAt: Number(g.updated_at) } : null,
		ribbons: r && r.segments > 0 ? { build: String(r.build), segments: r.segments } : null,
		progress: { available: Boolean(has.progress) },
		roads: rd && rd.total > 0 ? { segments: rd.segments, lastSeen: num(rd.last_seen) } : null,
		cameras: c && v ? { cameras: c.cameras, views: v.views, withImage: v.with_image } : null,
		calibrations: cal ? { current: cal.current, latestId: num(cal.latest_id), latestAt: num(cal.latest_at) } : null,
		inputs: {
			roads: rd && rd.total > 0 ? [rd.segments, rd.total, rd.max_id, num(rd.last_seen)] : null,
			cameras: c && v ? `${c.content}/${v.content}` : null,
			calibrations: cal ? [cal.current, num(cal.latest_id), num(cal.closed_at)] : null
		}
	};
}

interface ManifestDates {
	basemap: string | null;
	terrain: string | null;
	imagery: string | null;
	buildings: string | null;
}

let manifestCache: { mtimeMs: number; dates: ManifestDates } | undefined;

/**
 * Build dates from the basemap manifest, when this server can see it: the dev
 * and preview servers use TILES_DIR (like vite.config.ts); in production the
 * app container doesn't mount the tiles, so this is null there and the
 * client reads the manifest itself.
 */
export async function readTiles(dir = process.env.TILES_DIR ?? '../data/tiles'): Promise<ManifestDates | null> {
	const file = join(resolve(dir), 'manifest.json');
	try {
		const s = await stat(file);
		if (manifestCache?.mtimeMs === s.mtimeMs) return manifestCache.dates;
		const m = JSON.parse(await readFile(file, 'utf8'));
		const dates: ManifestDates = {
			basemap: m.basemap?.built ?? null,
			terrain: m.terrain?.built ?? null,
			imagery: m.imagery?.built ?? null,
			buildings: m.buildings?.built ?? null
		};
		manifestCache = { mtimeMs: s.mtimeMs, dates };
		return dates;
	} catch {
		return null;
	}
}

/** Assemble the answer from its parts (pure; tested). */
export function assembleMeta(
	now: number,
	database: DataMeta['database'],
	part: DbPart | null,
	tiles: ManifestDates | null
): DataMeta {
	const calVersion = part?.inputs.calibrations ? shortHash('cal', part.inputs.calibrations) : null;
	return {
		contract: META_CONTRACT,
		generatedAt: now,
		database,
		versions: {
			gtfs: part?.gtfs ? part.gtfs.feedVersion : null,
			ribbons: part?.ribbons ? part.ribbons.build : 'none',
			roads: part?.inputs.roads ? shortHash('roads', part.inputs.roads) : null,
			// /api/cameras reports each camera's calibration status, so its version follows calibrations too.
			cameras: part?.inputs.cameras ? shortHash('cameras', part.inputs.cameras, calVersion) : null,
			calibrations: calVersion,
			tiles: tiles ? shortHash('tiles', tiles) : null
		},
		gtfs: part?.gtfs ?? null,
		ribbons: part?.ribbons ?? null,
		progress: part?.progress ?? { available: false },
		roads: part?.roads ?? null,
		cameras: part?.cameras ?? null,
		calibrations: part?.calibrations ?? null,
		tiles
	};
}

async function compute(): Promise<DataMeta> {
	const now = Date.now() / 1000;
	const tiles = await readTiles();
	if (!DATABASE_URL) return assembleMeta(now, 'unconfigured', null, tiles);
	try {
		return assembleMeta(now, 'ok', await readDatabase(db()), tiles);
	} catch (e) {
		console.error('/api/meta: the database query failed:', e);
		return assembleMeta(now, 'error', null, tiles);
	}
}

let memo: { at: number; value: Promise<DataMeta> } | undefined;

/** The current data versions, memoized for 15 s; concurrent callers share one computation. */
export function dataMeta(nowMs = Date.now()): Promise<DataMeta> {
	if (memo && nowMs - memo.at < TTL_MS) return memo.value;
	memo = { at: nowMs, value: compute() };
	return memo.value;
}

/** For tests: forget the memoized answer. */
export function resetMetaCache() {
	memo = undefined;
	manifestCache = undefined;
}
