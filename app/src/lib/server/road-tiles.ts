import { promisify } from 'node:util';
import { constants, gunzip as gunzipCb, gzip as gzipCb } from 'node:zlib';
import type postgres from 'postgres';
import { versionedCacheControl } from './cache-headers.js';

/**
 * Road segments as Mapbox vector tiles (GET /api/tiles/roads/z/x/y?v=;
 * docs/14 §14.8 "APIs", §14.9 fix 5).
 *
 * - PostGIS cuts each tile once per roads version; it's gzipped once and kept
 *   in an LRU of about 40 MB, so revisits and other viewers leave the database
 *   idle. Concurrent requests for the same tile share one cut.
 * - It's sent gzipped (Caddy's `encode` doesn't list the MVT type, so before
 *   this road tiles went out uncompressed), plain only to a client that
 *   doesn't accept gzip.
 * - Caching: immutable when `?v=` is the current roads version from
 *   /api/meta, else `max-age=60`; a strong ETag per version and encoding.
 */

export const MIN_ZOOM = 8;
export const MAX_ZOOM = 16;

/** Smallest zoom at which each functional class appears: zoomed out, only the bigger roads, so tiles stay small. */
export const CLASS_MIN_ZOOM: Record<string, number> = {
	Interstate: 8,
	'Principal Arterial': 8,
	Ramp: 11,
	'Minor Arterial': 10,
	Collector: 11,
	Local: 13,
	Alley: 15,
	Driveway: 15,
	Parks: 14
};

export const CONTENT_TYPE = 'application/vnd.mapbox-vector-tile';
/** For a client that asks with an old version (or none): current data, rechecked within a minute. */
export const SHORT_CACHE = 'public, max-age=60';
/** The LRU's budget, in compressed bytes (plus a small allowance per entry). */
export const CACHE_BYTES = 40e6;
const ENTRY_OVERHEAD = 128;

const gzip = promisify(gzipCb);
const gunzip = promisify(gunzipCb);

export interface TileId {
	z: number;
	x: number;
	y: number;
}

/** The tile in a route's params, or null when it isn't one we serve (a 404). */
export function parseTile(params: { z?: string; x?: string; y?: string }): TileId | null {
	const [z, x, y] = [params.z, params.x, params.y].map((s) => (s !== undefined && /^\d+$/.test(s) ? Number(s) : NaN));
	if (![z, x, y].every(Number.isInteger) || z < MIN_ZOOM || z > MAX_ZOOM || x >= 2 ** z || y >= 2 ** z) return null;
	return { z, x, y };
}

/** The functional classes drawn at zoom z. */
export function classesAt(z: number): string[] {
	return Object.entries(CLASS_MIN_ZOOM)
		.filter(([, minz]) => z >= minz)
		.map(([c]) => c);
}

/** Cut one tile with PostGIS (layer "roads"): raw MVT bytes, empty when no road crosses it. */
export async function cutRoadTile(sql: postgres.Sql, { z, x, y }: TileId): Promise<Uint8Array> {
	const [row] = await sql`
		with bounds as (select ST_TileEnvelope(${z}, ${x}, ${y}) as env),
		tile as (
			select s.id, s.name, s.functional_class as class, s.posted_speed_mph as speed, s.one_way,
			       s.private, (s.from_level = 20 or s.to_level = 20) as elevated, s.community,
			       ST_AsMVTGeom(ST_Transform(s.geom, 3857), b.env, 4096, 64, true) as geom
			from core.road_segment s, bounds b
			where s.active and s.functional_class = any(${classesAt(z)})
			  and s.geom && ST_Transform(b.env, 4326))
		select ST_AsMVT(tile, 'roads', 4096, 'geom', 'id') as mvt from tile where geom is not null`;
	return row?.mvt ? new Uint8Array(row.mvt) : new Uint8Array();
}

/** A least-recently-used map with a byte budget. */
export class ByteLru<V> {
	#map = new Map<string, { value: V; bytes: number }>();
	#bytes = 0;
	constructor(readonly maxBytes: number) {}

	get(key: string): V | undefined {
		const e = this.#map.get(key);
		if (!e) return undefined;
		// Most recently used last.
		this.#map.delete(key);
		this.#map.set(key, e);
		return e.value;
	}

	set(key: string, value: V, bytes: number): void {
		const old = this.#map.get(key);
		if (old) {
			this.#bytes -= old.bytes;
			this.#map.delete(key);
		}
		if (bytes > this.maxBytes) return;
		this.#map.set(key, { value, bytes });
		this.#bytes += bytes;
		for (const [k, e] of this.#map) {
			if (this.#bytes <= this.maxBytes) break;
			this.#map.delete(k);
			this.#bytes -= e.bytes;
		}
	}

	get size(): number {
		return this.#map.size;
	}

	get bytes(): number {
		return this.#bytes;
	}
}

export interface RoadTileDeps {
	/** The current roads version (/api/meta's `versions.roads`), null when there is none. */
	version(): Promise<string | null>;
	/** Raw MVT bytes for one tile. */
	cut(t: TileId): Promise<Uint8Array>;
	maxBytes?: number;
}

export interface RoadTileServer {
	respond(t: TileId, requestedVersion: string | null, acceptEncoding: string | null, ifNoneMatch?: string | null): Promise<Response>;
	readonly cache: ByteLru<Uint8Array>;
	/** How many tiles were cut (for tests and the HUD-minded). */
	readonly cuts: number;
}

const acceptsGzip = (h: string | null) =>
	!!h &&
	h.split(',').some((part) => {
		const [name, ...params] = part.trim().toLowerCase().split(';');
		if (name !== 'gzip' && name !== '*') return false;
		const q = params.map((p) => p.trim()).find((p) => p.startsWith('q='));
		return !q || Number(q.slice(2)) > 0;
	});

export function roadTileServer(deps: RoadTileDeps): RoadTileServer {
	const cache = new ByteLru<Uint8Array>(deps.maxBytes ?? CACHE_BYTES);
	const inflight = new Map<string, Promise<Uint8Array>>();
	let cuts = 0;

	/** The tile gzipped (empty stays empty), from the cache or cut once. */
	function compressed(key: string, t: TileId): Promise<Uint8Array> {
		const hit = cache.get(key);
		if (hit) return Promise.resolve(hit);
		let p = inflight.get(key);
		if (!p) {
			p = (async () => {
				cuts++;
				const raw = await deps.cut(t);
				const gz = raw.length ? new Uint8Array(await gzip(raw, { level: constants.Z_BEST_COMPRESSION })) : raw;
				cache.set(key, gz, gz.length + ENTRY_OVERHEAD);
				return gz;
			})().finally(() => inflight.delete(key));
			inflight.set(key, p);
		}
		return p;
	}

	return {
		cache,
		get cuts() {
			return cuts;
		},
		async respond(t, requestedVersion, acceptEncoding, ifNoneMatch) {
			const current = await deps.version();
			const key = `${current ?? '-'}/${t.z}/${t.x}/${t.y}`;
			const gz = await compressed(key, t);
			const encode = gz.length > 0 && acceptsGzip(acceptEncoding);
			const headers = new Headers({
				'content-type': CONTENT_TYPE,
				'cache-control': versionedCacheControl(requestedVersion, current, SHORT_CACHE),
				vary: 'Accept-Encoding'
			});
			if (current) headers.set('etag', `"roads-${current}${encode ? '-gz' : ''}"`);
			if (current && ifNoneMatch && ifNoneMatch.split(',').some((v) => v.trim().replace(/^W\//, '') === headers.get('etag')))
				return new Response(null, { status: 304, headers });
			if (encode) {
				headers.set('content-encoding', 'gzip');
				return new Response(gz as Uint8Array<ArrayBuffer>, { headers });
			}
			const body = gz.length ? new Uint8Array(await gunzip(gz)) : gz;
			return new Response(body as Uint8Array<ArrayBuffer>, { headers });
		}
	};
}
