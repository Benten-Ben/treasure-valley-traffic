import { promisify } from 'node:util';
import { constants, gunzip as gunzipCb, gzip as gzipCb } from 'node:zlib';
import { error } from '@sveltejs/kit';
import postgres from 'postgres';
import { DATABASE_URL } from '$app/env/private';
import { LAYER_NAME, layerKey } from '#lib/contracts/layer-tiles.js';
import { versionedCacheControl } from './cache-headers.js';
import { CONTENT_TYPE, SHORT_CACHE, type TileId } from './road-tiles.js';

/**
 * Vector tiles for toggled layers (landscape sprint plan C4, package S2):
 * `GET /api/<plugin>/tiles/<layer>/{z}/{x}/{y}?v=`.
 *
 * A plugin adds a layer by exporting its definition (or a list of them) from
 * `#lib/server/<plugin>/tiles.ts`, found here by glob like the layer
 * registry's `def.ts`: the MVT layers its tiles carry, each read from one
 * table or view per zoom band (the plugin's build precomputes generalised
 * geometry per band), or its own `cut` for what a table can't say.
 *
 * - Cuts run on their own pool (3 connections, `statement_timeout` 3 s,
 *   read-only: `tilePoolOptions`), so a slow cut never holds up /api/meta,
 *   the road tiles or anything else on the shared pool.
 * - A cut that times out in the database, or isn't done within
 *   `DEADLINE_MS` (the wait for a connection included), answers an empty
 *   tile with a short cache, and isn't kept. So does a cut before the
 *   plugin's migration (a missing table, schema or column).
 * - Tiles are gzipped once and kept per version in one shared LRU (about
 *   120 MB) with a cap per layer, so one busy layer can't push the others
 *   out. Concurrent requests for a tile share its cut.
 * - Versions come from core.layer_version: each build writes a row
 *   (ingest/layer_version.py), and /api/meta reports the newest as
 *   `versions.layers['<plugin>.<layer>']`. With it as `?v=` a tile is
 *   immutable; otherwise `max-age=60`, as for road tiles. A layer with no
 *   version yet is cut afresh each time (still shared while in flight).
 *   As with the road tiles, a tile cut in the 15 s before /api/meta's memo
 *   sees a new build is kept under the old version.
 *
 * The road tiles (`/api/tiles/roads`, road-tiles.ts) are separate and
 * unchanged.
 */

/** The tile pool: its own connections, so cuts queue among themselves. */
export const POOL_MAX = 3;
/** The database stops any one cut after this long. */
export const STATEMENT_TIMEOUT_MS = 3_000;
/** The longest a request waits for its cut, the wait for a free connection included. */
export const DEADLINE_MS = 6_000;
/** The shared LRU's budget, in compressed bytes (plus a small allowance per entry). */
export const CACHE_BYTES = 120e6;
/** A layer's share of it, unless its definition says otherwise. */
export const LAYER_CACHE_BYTES = 40e6;
/** For an empty tile answered because the cut timed out or the layer's tables don't exist yet. */
export const EMPTY_CACHE = 'public, max-age=10';
/** MVT extent and the default buffer, in tile units (as the road tiles). */
export const EXTENT = 4096;
export const BUFFER = 64;
const ENTRY_OVERHEAD = 128;

/** One zoom band of an MVT layer: the table or view it's read from there. */
export interface TileSource {
	/** The zooms this source serves, inclusive. Bands of one MVT layer don't overlap; a zoom with none leaves the layer out. */
	minzoom: number;
	maxzoom: number;
	/** `schema.table`, or a view: the plugin's geometry for this band (generalised by its build). */
	table: string;
	/** The geometry column; `geom` unless given. */
	geom?: string;
	/** The geometry's SRID: 4326 (the default) or 3857 for a table already in web mercator (no transform per cut). */
	srid?: 4326 | 3857;
	/** An integer column used as the feature id (feature-state needs no `promoteId` then). */
	id?: string;
	/** Columns copied as feature properties, under the same names. A view renames or computes them. */
	columns?: readonly string[];
}

/** One MVT layer in the tile (a style's `source-layer`). */
export interface TileLayerPart {
	name: string;
	sources: readonly TileSource[];
	/** Tile units kept beyond the edge (default `BUFFER`); labels and wide strokes may want more. */
	buffer?: number;
}

/** A toggled layer's tiles: `/api/<plugin>/tiles/<layer>/{z}/{x}/{y}`. */
export interface TileLayerDef {
	/** The plugin (the folder under `#lib/server/`) and the layer's name, as in the URL and `versions.layers`. */
	plugin: string;
	layer: string;
	/** The zooms served; the client's source sets the same range and overzooms beyond `maxzoom`. */
	minzoom: number;
	maxzoom: number;
	/** This layer's cap in the shared LRU, in bytes (default `LAYER_CACHE_BYTES`). */
	cacheBytes?: number;
	/** The MVT layers, read from tables; or `cut` instead. */
	parts?: readonly TileLayerPart[];
	/**
	 * A cut of its own: raw MVT bytes for one tile, from the tile pool. Run
	 * queries through `cancelOnAbort(signal, ...)` so a cut past the deadline
	 * stops in the database too.
	 */
	cut?: (sql: postgres.Sql, t: TileId, signal: AbortSignal) => Promise<Uint8Array>;
}

const IDENT = /^[a-z_][a-z0-9_]{0,62}$/;
const TABLE = /^[a-z_][a-z0-9_]{0,62}\.[a-z_][a-z0-9_]{0,62}$/;
/** The tile geometry's column name in the cut; no property may use it. */
const GEOM_OUT = 'mvt_geom';
const MAX_ZOOM = 22;

const isZoom = (z: unknown): z is number => Number.isInteger(z) && (z as number) >= 0 && (z as number) <= MAX_ZOOM;

/** What's wrong with a definition (empty when nothing is). Identifiers end up in SQL, so they're strict. */
export function tileLayerProblems(def: TileLayerDef): string[] {
	const p: string[] = [];
	if (!LAYER_NAME.test(def.plugin ?? '')) p.push(`plugin name ${JSON.stringify(def.plugin)}`);
	if (!LAYER_NAME.test(def.layer ?? '')) p.push(`layer name ${JSON.stringify(def.layer)}`);
	if (!isZoom(def.minzoom) || !isZoom(def.maxzoom) || def.minzoom > def.maxzoom) p.push(`zooms ${def.minzoom}–${def.maxzoom}`);
	if (def.cacheBytes !== undefined && !(Number.isFinite(def.cacheBytes) && def.cacheBytes > 0)) p.push(`cacheBytes ${def.cacheBytes}`);
	if (!def.parts === !def.cut) p.push('give parts or cut, not both');
	if (def.cut !== undefined && typeof def.cut !== 'function') p.push('cut is not a function');
	if (def.parts && !def.parts.length) p.push('no parts');
	const names = new Set<string>();
	for (const part of def.parts ?? []) {
		const where = `part ${JSON.stringify(part.name)}`;
		if (!LAYER_NAME.test(part.name ?? '')) p.push(`${where}: its name`);
		if (names.has(part.name)) p.push(`${where}: named twice`);
		names.add(part.name);
		if (part.buffer !== undefined && !(Number.isInteger(part.buffer) && part.buffer >= 0 && part.buffer <= EXTENT)) p.push(`${where}: buffer ${part.buffer}`);
		if (!part.sources?.length) p.push(`${where}: no sources`);
		const bands = [...(part.sources ?? [])].sort((a, b) => a.minzoom - b.minzoom);
		bands.forEach((s, i) => {
			const at = `${where}, ${s.table}`;
			if (!isZoom(s.minzoom) || !isZoom(s.maxzoom) || s.minzoom > s.maxzoom) p.push(`${at}: zooms ${s.minzoom}–${s.maxzoom}`);
			else if (s.minzoom < def.minzoom || s.maxzoom > def.maxzoom) p.push(`${at}: zooms ${s.minzoom}–${s.maxzoom} outside the layer's`);
			if (i > 0 && s.minzoom <= bands[i - 1].maxzoom) p.push(`${at}: overlaps ${bands[i - 1].table}`);
			if (!TABLE.test(s.table ?? '')) p.push(`${at}: table must be schema.table in lower case`);
			if (s.srid !== undefined && s.srid !== 4326 && s.srid !== 3857) p.push(`${at}: srid ${s.srid}`);
			const cols = [s.geom ?? 'geom', ...(s.id ? [s.id] : []), ...(s.columns ?? [])];
			for (const c of cols) if (!IDENT.test(c ?? '')) p.push(`${at}: column ${JSON.stringify(c)}`);
			const props = [...(s.id ? [s.id] : []), ...(s.columns ?? [])];
			if (new Set(props).size !== props.length) p.push(`${at}: a column is listed twice`);
			if (props.includes(GEOM_OUT)) p.push(`${at}: ${GEOM_OUT} is reserved`);
		});
	}
	return p;
}

const q = (ident: string) => `"${ident}"`;

/** One MVT layer's cut from one source (identifiers already checked). */
function partSql(part: TileLayerPart, s: TileSource): string {
	const geom = `s.${q(s.geom ?? 'geom')}`;
	const buffer = part.buffer ?? BUFFER;
	const margin = buffer / EXTENT;
	const mercator = s.srid === 3857;
	const wide = `ST_TileEnvelope($1::int, $2::int, $3::int, margin => ${margin})`;
	const cols = [...(s.id ? [s.id] : []), ...(s.columns ?? [])].map((c) => `s.${q(c)}, `).join('');
	const asMvt = `ST_AsMVT(t, '${part.name}', ${EXTENT}, '${GEOM_OUT}'${s.id ? `, '${s.id}'` : ''})`;
	return (
		`(select coalesce(${asMvt}, ''::bytea) from (` +
		`select ${cols}ST_AsMVTGeom(${mercator ? geom : `ST_Transform(${geom}, 3857)`}, ST_TileEnvelope($1::int, $2::int, $3::int), ${EXTENT}, ${buffer}, true) as ${GEOM_OUT} ` +
		`from ${s.table.split('.').map(q).join('.')} s ` +
		`where ${geom} && ${mercator ? wide : `ST_Transform(${wide}, 4326)`}` +
		`) t where t.${GEOM_OUT} is not null)`
	);
}

const queries = new WeakMap<TileLayerDef, Map<number, string | null>>();

/**
 * The SQL that cuts a tile of a `parts` layer at zoom z ($1–$3 are z, x, y),
 * or null when no part has a source there. Each part is one MVT layer, and
 * MVT layers concatenate, so the tile is their `||`.
 */
export function tileQuery(def: TileLayerDef, z: number): string | null {
	let byZoom = queries.get(def);
	if (!byZoom) queries.set(def, (byZoom = new Map()));
	if (byZoom.has(z)) return byZoom.get(z)!;
	const cuts = (def.parts ?? []).flatMap((part) => {
		const s = part.sources.find((src) => z >= src.minzoom && z <= src.maxzoom);
		return s ? [partSql(part, s)] : [];
	});
	const text = cuts.length ? `select ${cuts.join(' || ')} as mvt` : null;
	byZoom.set(z, text);
	return text;
}

const cancelled = () => Object.assign(new Error('canceling statement due to user request'), { code: '57014' });

/**
 * Run a postgres.js query, cancelling it (in the database too) when signal
 * aborts; it then fails as a timeout. For a layer's own `cut`.
 */
export function cancelOnAbort<T extends readonly postgres.MaybeRow[]>(signal: AbortSignal, query: () => postgres.PendingQuery<T>): Promise<postgres.RowList<T>> {
	// A query cancelled before it's sent would still take a connection later, so don't start one.
	if (signal.aborted) return Promise.reject(cancelled());
	const pending = query();
	const stop = () => void pending.cancel();
	signal.addEventListener('abort', stop, { once: true });
	return Promise.resolve(pending).finally(() => signal.removeEventListener('abort', stop));
}

/** Raw MVT bytes for one tile of a layer: its own `cut`, or its parts' SQL on the tile pool. */
export async function cutLayerTile(sql: postgres.Sql, def: TileLayerDef, t: TileId, signal: AbortSignal): Promise<Uint8Array> {
	if (def.cut) return def.cut(sql, t, signal);
	const text = tileQuery(def, t.z);
	if (!text) return new Uint8Array();
	const [row] = await cancelOnAbort(signal, () => sql.unsafe(text, [t.z, t.x, t.y]));
	return row?.mvt ? new Uint8Array(row.mvt) : new Uint8Array();
}

/** The tile pool's postgres.js options. */
export function tilePoolOptions() {
	return {
		max: POOL_MAX,
		idle_timeout: 30,
		connect_timeout: 10,
		connection: { statement_timeout: STATEMENT_TIMEOUT_MS, default_transaction_read_only: true, application_name: 'tvt-app-tiles' }
	} satisfies postgres.Options<Record<string, never>>;
}

let pool: postgres.Sql | undefined;

/**
 * The tile pool: 3 connections of its own beside db.ts's shared 5, read-only,
 * each statement stopped after 3 s. Throws a 503 if no database is configured.
 */
export function tilesDb(): postgres.Sql {
	if (!DATABASE_URL) error(503, 'The database is not configured (set DATABASE_URL).');
	pool ??= postgres(DATABASE_URL, tilePoolOptions());
	return pool;
}

/** Why a failed cut is answered with an empty tile, or null when it's a real error. */
export function emptyReason(e: unknown): 'timeout' | 'missing' | null {
	const code = (e as { code?: unknown } | null)?.code;
	// query_canceled: statement_timeout, or our deadline.
	if (code === '57014') return 'timeout';
	// undefined_table, invalid_schema_name, undefined_column: before the plugin's migration.
	if (code === '42P01' || code === '3F000' || code === '42703') return 'missing';
	return null;
}

interface Entry {
	layer: string;
	value: Uint8Array;
	bytes: number;
}

/**
 * A least-recently-used cache shared by every layer, with a byte budget of
 * its own and a cap per layer: a layer over its cap drops its own oldest
 * tiles; the cache over its budget drops the oldest of anyone's.
 */
export class TileCache {
	#all = new Map<string, Entry>();
	#layers = new Map<string, { entries: Map<string, Entry>; bytes: number }>();
	#bytes = 0;
	constructor(readonly maxBytes: number = CACHE_BYTES) {}

	get(key: string): Uint8Array | undefined {
		const e = this.#all.get(key);
		if (!e) return undefined;
		// Most recently used last, in both orders.
		this.#all.delete(key);
		this.#all.set(key, e);
		const l = this.#layers.get(e.layer)!;
		l.entries.delete(key);
		l.entries.set(key, e);
		return e.value;
	}

	set(layer: string, key: string, value: Uint8Array, bytes: number, layerMax: number = LAYER_CACHE_BYTES): void {
		this.#drop(key);
		if (bytes > Math.min(layerMax, this.maxBytes)) return;
		let l = this.#layers.get(layer);
		if (!l) this.#layers.set(layer, (l = { entries: new Map(), bytes: 0 }));
		const e = { layer, value, bytes };
		this.#all.set(key, e);
		l.entries.set(key, e);
		l.bytes += bytes;
		this.#bytes += bytes;
		for (const k of l.entries.keys()) {
			if (l.bytes <= layerMax) break;
			this.#drop(k);
		}
		for (const k of this.#all.keys()) {
			if (this.#bytes <= this.maxBytes) break;
			this.#drop(k);
		}
	}

	#drop(key: string): void {
		const e = this.#all.get(key);
		if (!e) return;
		this.#all.delete(key);
		const l = this.#layers.get(e.layer)!;
		l.entries.delete(key);
		l.bytes -= e.bytes;
		this.#bytes -= e.bytes;
		if (!l.entries.size) this.#layers.delete(e.layer);
	}

	/** Bytes held for one layer. */
	layerBytes(layer: string): number {
		return this.#layers.get(layer)?.bytes ?? 0;
	}

	get size(): number {
		return this.#all.size;
	}

	get bytes(): number {
		return this.#bytes;
	}
}

/** The cache key of a tile: layer, version (`-` for none) and tile. */
export function tileKey(id: string, version: string | null, { z, x, y }: TileId): string {
	return `${id}/${version ?? '-'}/${z}/${x}/${y}`;
}

/** The tile in a route's params, inside the layer's zooms and the grid; null otherwise (a 404). */
export function parseLayerTile(params: { z?: string; x?: string; y?: string }, def: Pick<TileLayerDef, 'minzoom' | 'maxzoom'>): TileId | null {
	const [z, x, y] = [params.z, params.x, params.y].map((s) => (s !== undefined && /^\d+$/.test(s) ? Number(s) : NaN));
	if (![z, x, y].every(Number.isInteger) || z < def.minzoom || z > def.maxzoom || x >= 2 ** z || y >= 2 ** z) return null;
	return { z, x, y };
}

export interface LayerTileDeps {
	/** A layer's current version (/api/meta's `versions.layers[id]`), null when it has none. */
	version(id: string): Promise<string | null>;
	/** Raw MVT bytes for one tile; it should stop when signal aborts (the deadline). */
	cut(def: TileLayerDef, t: TileId, signal: AbortSignal): Promise<Uint8Array>;
	maxBytes?: number;
	deadlineMs?: number;
}

export interface LayerTileServer {
	respond(def: TileLayerDef, t: TileId, requestedVersion: string | null, acceptEncoding: string | null, ifNoneMatch?: string | null): Promise<Response>;
	readonly cache: TileCache;
	/** How many cuts were started (for tests and the performance harness). */
	readonly cuts: number;
}

type Cut = { gz: Uint8Array; ms?: number } | { empty: 'timeout' | 'missing' };

const gzip = promisify(gzipCb);
const gunzip = promisify(gunzipCb);
const TIMEOUT = Symbol('timeout');

/** Whether Accept-Encoding allows gzip (as the road tiles read it). */
export function acceptsGzip(h: string | null): boolean {
	return (
		!!h &&
		h.split(',').some((part) => {
			const [name, ...params] = part.trim().toLowerCase().split(';');
			if (name !== 'gzip' && name !== '*') return false;
			const weight = params.map((p) => p.trim()).find((p) => p.startsWith('q='));
			return !weight || Number(weight.slice(2)) > 0;
		})
	);
}

export function layerTileServer(deps: LayerTileDeps): LayerTileServer {
	const cache = new TileCache(deps.maxBytes ?? CACHE_BYTES);
	const inflight = new Map<string, Promise<Cut>>();
	const deadlineMs = deps.deadlineMs ?? DEADLINE_MS;
	let cuts = 0;

	/** The raw cut, or TIMEOUT once the deadline passes (the cut is then told to stop). */
	async function within(def: TileLayerDef, t: TileId): Promise<Uint8Array | typeof TIMEOUT> {
		const stop = new AbortController();
		let timer: ReturnType<typeof setTimeout> | undefined;
		const deadline = new Promise<typeof TIMEOUT>((resolve) => {
			timer = setTimeout(() => {
				stop.abort();
				resolve(TIMEOUT);
			}, deadlineMs);
		});
		const work = Promise.resolve().then(() => deps.cut(def, t, stop.signal));
		// A cut abandoned at the deadline may still fail later; nobody waits for it then.
		work.catch(() => {});
		try {
			return await Promise.race([work, deadline]);
		} finally {
			clearTimeout(timer);
		}
	}

	/** The tile gzipped (empty stays empty), from the cache or cut once; or why it's answered empty. */
	function tile(def: TileLayerDef, id: string, key: string, t: TileId, keep: boolean): Promise<Cut> {
		const hit = keep ? cache.get(key) : undefined;
		if (hit) return Promise.resolve({ gz: hit });
		let p = inflight.get(key);
		if (!p) {
			p = (async (): Promise<Cut> => {
				cuts++;
				const started = performance.now();
				let raw;
				try {
					raw = await within(def, t);
				} catch (e) {
					const why = emptyReason(e);
					if (why) return { empty: why };
					throw e;
				}
				if (raw === TIMEOUT) return { empty: 'timeout' };
				const gz = raw.length ? new Uint8Array(await gzip(raw, { level: constants.Z_BEST_COMPRESSION })) : raw;
				if (keep) cache.set(id, key, gz, gz.length + ENTRY_OVERHEAD, def.cacheBytes ?? LAYER_CACHE_BYTES);
				return { gz, ms: performance.now() - started };
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
		async respond(def, t, requestedVersion, acceptEncoding, ifNoneMatch) {
			const id = layerKey(def.plugin, def.layer);
			const current = await deps.version(id);
			const gzipOk = acceptsGzip(acceptEncoding);
			const headers = new Headers({ 'content-type': CONTENT_TYPE, vary: 'Accept-Encoding' });
			const etag = current ? `"${id}-${current}${gzipOk ? '-gz' : ''}"` : null;
			if (etag && ifNoneMatch && ifNoneMatch.split(',').some((v) => v.trim().replace(/^W\//, '') === etag)) {
				headers.set('cache-control', versionedCacheControl(requestedVersion, current, SHORT_CACHE));
				headers.set('etag', etag);
				return new Response(null, { status: 304, headers });
			}
			const r = await tile(def, id, tileKey(id, current, t), t, current !== null);
			if ('empty' in r) {
				headers.set('cache-control', EMPTY_CACHE);
				headers.set('x-tile-status', r.empty);
				return new Response(new Uint8Array(), { headers });
			}
			headers.set('cache-control', versionedCacheControl(requestedVersion, current, SHORT_CACHE));
			if (etag) headers.set('etag', etag);
			if (r.ms !== undefined) headers.set('server-timing', `cut;dur=${Math.round(r.ms)}`);
			if (r.gz.length && gzipOk) {
				headers.set('content-encoding', 'gzip');
				return new Response(r.gz as Uint8Array<ArrayBuffer>, { headers });
			}
			const body = r.gz.length ? new Uint8Array(await gunzip(r.gz)) : r.gz;
			return new Response(body as Uint8Array<ArrayBuffer>, { headers });
		}
	};
}

type Found = Record<string, { default: TileLayerDef | readonly TileLayerDef[] }>;

/**
 * The registry from the found modules, by `'<plugin>.<layer>'`. A definition
 * with problems, outside its plugin's folder or defined twice is left out
 * (logged), so it 404s alone; the registry test catches it first.
 */
export function buildRegistry(found: Found, log: (msg: string) => void = console.error): Map<string, TileLayerDef> {
	const out = new Map<string, TileLayerDef>();
	for (const [path, m] of Object.entries(found)) {
		const folder = path.split('/').at(-2);
		for (const def of ([] as TileLayerDef[]).concat(m.default ?? [])) {
			const id = layerKey(def.plugin, def.layer);
			const problems = tileLayerProblems(def);
			if (def.plugin !== folder) problems.push(`it's in ${folder}/, not ${def.plugin}/`);
			if (out.has(id)) problems.push('defined twice');
			if (problems.length) {
				log(`tile layer ${id} (${path}) left out: ${problems.join('; ')}`);
				continue;
			}
			out.set(id, def);
		}
	}
	return out;
}

/** Every toggled layer's tiles, from `#lib/server/<plugin>/tiles.ts`. */
export const TILE_LAYERS: ReadonlyMap<string, TileLayerDef> = buildRegistry(import.meta.glob('./*/tiles.ts', { eager: true }) as Found);

export function tileLayer(plugin: string | undefined, layer: string | undefined): TileLayerDef | undefined {
	return plugin && layer ? TILE_LAYERS.get(layerKey(plugin, layer)) : undefined;
}
