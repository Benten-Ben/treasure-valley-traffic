import { promisify } from 'node:util';
import { constants, gunzip as gunzipCb, gzip as gzipCb } from 'node:zlib';
import { error } from '@sveltejs/kit';
import postgres from 'postgres';
import { DATABASE_URL, TILES_DB_ROLE } from '$app/env/private';
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
 * - Tiles go to anyone who can open the map, so they read only the plugin's
 *   own schema and core (plan C3), never `restricted` or a private plugin's
 *   schema: definitions are checked against that (`tileLayerProblems`), and
 *   with TILES_DB_ROLE set the tile pool reads as the role
 *   deploy/tvt_tiles.sql grants only those schemas, so the database refuses
 *   the rest (a layer's own `cut` included).
 * - Cuts run on their own pool (3 connections, `statement_timeout` 3 s,
 *   read-only: `tilePoolOptions`), so a slow cut never holds up /api/meta,
 *   the road tiles or anything else on the shared pool.
 * - A cut that times out in the database, or isn't done within
 *   `DEADLINE_MS` (the wait for a connection included), answers an empty
 *   tile with a short cache, and isn't kept. So does a cut before the
 *   plugin's migration (a missing table, schema or column), one the
 *   database refuses (`denied`), and any tile of a layer with no version
 *   yet (`unversioned`: its build hasn't recorded its licence, so nothing is
 *   served). Each is logged: the first per layer and reason, then at most
 *   once a minute.
 * - Tiles are gzipped once and kept per version in one shared LRU (about
 *   120 MB) with a cap per layer, so one busy layer can't push the others
 *   out. Concurrent requests for a tile share its cut.
 * - Versions come from core.layer_version: each build writes a row
 *   (ingest/layer_version.py), and /api/meta reports the newest as
 *   `versions.layers['<plugin>.<layer>']`. With it as `?v=` a tile is
 *   immutable; otherwise `max-age=60`, as for road tiles. Each cut also
 *   reads the layer's version in its own snapshot: a tile whose data is
 *   newer (or older) than the version /api/meta's 15 s memo still reports is
 *   sent with `max-age=60` and not kept, so a version only ever names its
 *   own build's tiles.
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
/** For an empty tile answered because the cut timed out, the layer's tables don't exist yet, or it has no version. */
export const EMPTY_CACHE = 'public, max-age=10';
/** An empty answer is logged the first time per layer and reason, then at most this often. */
export const LOG_EVERY_MS = 60_000;
/** MVT extent and the default buffer, in tile units (as the road tiles). */
export const EXTENT = 4096;
export const BUFFER = 64;
const ENTRY_OVERHEAD = 128;

/** One zoom band of an MVT layer: the table or view it's read from there. */
export interface TileSource {
	/** The zooms this source serves, inclusive. Bands of one MVT layer don't overlap; a zoom with none leaves the layer out. */
	minzoom: number;
	maxzoom: number;
	/**
	 * `schema.table`, or a view: the plugin's geometry for this band (generalised
	 * by its build). The schema is the plugin's own or core (`tileSchemas`).
	 */
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
	 * A cut of its own: raw MVT bytes for one tile. It runs in a read-only,
	 * repeatable-read transaction on the tile pool (so it sees the data of the
	 * version read beside it), and reads only the plugin's own schema and core,
	 * as `parts` do; with TILES_DB_ROLE set the database holds it to that. Run
	 * queries through `cancelOnAbort(signal, ...)` so a cut past the deadline
	 * stops in the database too.
	 */
	cut?: (sql: postgres.TransactionSql, t: TileId, signal: AbortSignal) => Promise<Uint8Array>;
}

/** Schemas every plugin's tiles may read besides its own (plan C3: one schema per plugin). */
export const SHARED_TILE_SCHEMAS: readonly string[] = ['core'];

/**
 * Whether tiles must never read a schema: `restricted` (personal or
 * do-not-redistribute data, docs/12 §12.8) and private plugins' schemas
 * (`private_<name>`, docs/15 §15.2; `city_trees`, the City of Boise's
 * trees, predates that naming). deploy/tvt_tiles.sql revokes the same.
 */
export function neverTiled(schema: string): boolean {
	return schema === 'restricted' || schema === 'city_trees' || schema.startsWith('private_');
}

/** The schemas a plugin's tiles may read: its own and core, never one of `neverTiled`. */
export function tileSchemas(plugin: string): string[] {
	return [plugin, ...SHARED_TILE_SCHEMAS].filter((s) => !neverTiled(s));
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
	else if (neverTiled(def.plugin)) p.push(`plugin ${def.plugin}: its data is never tiled`);
	if (!LAYER_NAME.test(def.layer ?? '')) p.push(`layer name ${JSON.stringify(def.layer)}`);
	const schemas = tileSchemas(def.plugin ?? '');
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
			else {
				const schema = s.table.split('.')[0];
				if (neverTiled(schema)) p.push(`${at}: schema ${schema} is never tiled`);
				else if (!schemas.includes(schema)) p.push(`${at}: schema ${schema} isn't the plugin's own or ${SHARED_TILE_SCHEMAS.join(', ')}`);
			}
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

/** The layer's newest version (core.layer_version, migration 0020), read in the cut's own snapshot. */
const VERSION_SQL = (param: string) => `(select version from core.layer_version where layer = ${param} order by id desc limit 1)`;

/**
 * The SQL that cuts a tile of a `parts` layer at zoom z ($1–$3 are z, x, y;
 * $4 is `'<plugin>.<layer>'`), or null when no part has a source there. Each
 * part is one MVT layer, and MVT layers concatenate, so the tile is their
 * `||`. The layer's current version comes from the same statement, so it
 * names the data the tile was cut from.
 */
export function tileQuery(def: TileLayerDef, z: number): string | null {
	let byZoom = queries.get(def);
	if (!byZoom) queries.set(def, (byZoom = new Map()));
	if (byZoom.has(z)) return byZoom.get(z)!;
	const cuts = (def.parts ?? []).flatMap((part) => {
		const s = part.sources.find((src) => z >= src.minzoom && z <= src.maxzoom);
		return s ? [partSql(part, s)] : [];
	});
	const text = cuts.length ? `select ${cuts.join(' || ')} as mvt, ${VERSION_SQL('$4')} as version` : null;
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

/**
 * One tile's raw MVT bytes, and the layer's version in the snapshot it was
 * cut from (null: no version row; undefined: not read, as at a zoom with no
 * source, where the tile is empty whatever the version).
 */
export interface LayerCut {
	mvt: Uint8Array;
	version?: string | null;
}

/**
 * Cut one tile of a layer on the tile pool: its parts' SQL as one statement,
 * or its own `cut` in a read-only, repeatable-read transaction that reads the
 * version first, so both see one snapshot.
 */
export async function cutLayerTile(sql: postgres.Sql, def: TileLayerDef, t: TileId, signal: AbortSignal): Promise<LayerCut> {
	const id = layerKey(def.plugin, def.layer);
	const own = def.cut;
	if (own) {
		return sql.begin('isolation level repeatable read read only', async (tx) => {
			const [row] = await cancelOnAbort(signal, () => tx.unsafe(`select ${VERSION_SQL('$1')} as version`, [id]));
			return { mvt: await own(tx, t, signal), version: row?.version ?? null };
		}) as Promise<LayerCut>;
	}
	const text = tileQuery(def, t.z);
	if (!text) return { mvt: new Uint8Array() };
	const [row] = await cancelOnAbort(signal, () => sql.unsafe(text, [t.z, t.x, t.y, id]));
	return { mvt: row?.mvt ? new Uint8Array(row.mvt) : new Uint8Array(), version: row?.version ?? null };
}

/** The tile pool's postgres.js options; with `role`, its connections read as that role (deploy/tvt_tiles.sql). */
export function tilePoolOptions(role?: string) {
	return {
		max: POOL_MAX,
		idle_timeout: 30,
		connect_timeout: 10,
		connection: {
			statement_timeout: STATEMENT_TIMEOUT_MS,
			default_transaction_read_only: true,
			application_name: 'tvt-app-tiles',
			...(role ? { role } : {})
		}
	} satisfies postgres.Options<Record<string, never>>;
}

let pool: postgres.Sql | undefined;

/**
 * The tile pool: 3 connections of its own beside db.ts's shared 5, read-only,
 * each statement stopped after 3 s, reading as TILES_DB_ROLE when it's set
 * (the server sets tvt_tiles). Throws a 503 if no database is configured.
 */
export function tilesDb(): postgres.Sql {
	if (!DATABASE_URL) error(503, 'The database is not configured (set DATABASE_URL).');
	if (!pool) {
		if (!TILES_DB_ROLE)
			console.warn(
				"Toggled layers' tiles read as the app's own role: set TILES_DB_ROLE=tvt_tiles (deploy/tvt_tiles.sql) " +
					'so the database keeps them out of restricted and private schemas.'
			);
		pool = postgres(DATABASE_URL, tilePoolOptions(TILES_DB_ROLE));
	}
	return pool;
}

/** Why a tile is answered empty (sent as `x-tile-status`). */
export type EmptyReason = 'timeout' | 'missing' | 'denied' | 'unversioned';

/** Why a failed cut is answered with an empty tile, or null when it's a real error. */
export function emptyReason(e: unknown): Exclude<EmptyReason, 'unversioned'> | null {
	const code = (e as { code?: unknown } | null)?.code;
	// query_canceled: statement_timeout, or our deadline.
	if (code === '57014') return 'timeout';
	// undefined_table, invalid_schema_name, undefined_column: before the plugin's migration (or a typo).
	if (code === '42P01' || code === '3F000' || code === '42703') return 'missing';
	// insufficient_privilege: the tile role may not read it (deploy/tvt_tiles.sql).
	if (code === '42501') return 'denied';
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

/** The cache key of a tile: layer, version and tile. */
export function tileKey(id: string, version: string, { z, x, y }: TileId): string {
	return `${id}/${version}/${z}/${x}/${y}`;
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
	/** One tile's raw MVT bytes and the version they were cut at; it should stop when signal aborts (the deadline). */
	cut(def: TileLayerDef, t: TileId, signal: AbortSignal): Promise<LayerCut>;
	maxBytes?: number;
	deadlineMs?: number;
	/** Where empty answers are noted (default console.warn), and the clock that spaces the notes. */
	log?: (msg: string) => void;
	now?: () => number;
}

export interface LayerTileServer {
	respond(def: TileLayerDef, t: TileId, requestedVersion: string | null, acceptEncoding: string | null, ifNoneMatch?: string | null): Promise<Response>;
	readonly cache: TileCache;
	/** How many cuts were started (for tests and the performance harness). */
	readonly cuts: number;
}

/** A tile gzipped (an empty one stays empty), `stale` when cut at another version than its key's; or why it's empty. */
type Cut = { gz: Uint8Array; ms?: number; stale?: boolean } | { empty: EmptyReason; detail: string };

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

/** A failed cut's code and message, for the log. */
const errorText = (e: unknown) => {
	const { code, message } = (e ?? {}) as { code?: unknown; message?: unknown };
	return `${code ?? '?'} ${message ?? e}`;
};

export function layerTileServer(deps: LayerTileDeps): LayerTileServer {
	const cache = new TileCache(deps.maxBytes ?? CACHE_BYTES);
	const inflight = new Map<string, Promise<Cut>>();
	const deadlineMs = deps.deadlineMs ?? DEADLINE_MS;
	const log = deps.log ?? console.warn;
	const now = deps.now ?? Date.now;
	const noted = new Map<string, { at: number; since: number }>();
	let cuts = 0;

	/**
	 * Log an empty answer: the first per layer and reason, then at most once
	 * a minute (with how many went unlogged), so a misspelled table or a
	 * layer that keeps timing out shows in the app's log.
	 */
	function note(id: string, why: EmptyReason, t: TileId, detail: string) {
		const key = `${id} ${why}`;
		const last = noted.get(key);
		const at = now();
		if (last && at - last.at < LOG_EVERY_MS) {
			last.since++;
			return;
		}
		const more = last?.since ? ` (and ${last.since} more since the last note)` : '';
		log(`tile layer ${id}: answered empty (${why}) at ${t.z}/${t.x}/${t.y}: ${detail}${more}`);
		noted.set(key, { at, since: 0 });
	}

	/** The cut, or TIMEOUT once the deadline passes (the cut is then told to stop). */
	async function within(def: TileLayerDef, t: TileId): Promise<LayerCut | typeof TIMEOUT> {
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
	function tile(def: TileLayerDef, id: string, version: string, t: TileId): Promise<Cut> {
		const key = tileKey(id, version, t);
		const hit = cache.get(key);
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
					if (why) return { empty: why, detail: errorText(e) };
					throw e;
				}
				if (raw === TIMEOUT) return { empty: 'timeout', detail: `no answer within ${deadlineMs} ms` };
				const gz = raw.mvt.length ? new Uint8Array(await gzip(raw.mvt, { level: constants.Z_BEST_COMPRESSION })) : raw.mvt;
				// Cut at another version than /api/meta reported (a build committed in its 15 s memo): send it, don't keep it.
				const stale = raw.version !== undefined && raw.version !== version;
				if (!stale) cache.set(id, key, gz, gz.length + ENTRY_OVERHEAD, def.cacheBytes ?? LAYER_CACHE_BYTES);
				return { gz, ms: performance.now() - started, stale };
			})().finally(() => inflight.delete(key));
			inflight.set(key, p);
		}
		return p;
	}

	/** An empty tile with a short cache, never kept, saying why. */
	function empty(headers: Headers, why: EmptyReason): Response {
		headers.set('cache-control', EMPTY_CACHE);
		headers.set('x-tile-status', why);
		return new Response(new Uint8Array(), { headers });
	}

	return {
		cache,
		get cuts() {
			return cuts;
		},
		async respond(def, t, requestedVersion, acceptEncoding, ifNoneMatch) {
			const id = layerKey(def.plugin, def.layer);
			const current = await deps.version(id);
			const headers = new Headers({ 'content-type': CONTENT_TYPE, vary: 'Accept-Encoding' });
			// No version row: its build hasn't recorded the layer's licence and republish (plan C3), so nothing is served.
			if (current === null) {
				note(id, 'unversioned', t, 'no row in core.layer_version yet (its build records one with ingest/layer_version.py)');
				return empty(headers, 'unversioned');
			}
			const gzipOk = acceptsGzip(acceptEncoding);
			const etag = `"${id}-${current}${gzipOk ? '-gz' : ''}"`;
			if (ifNoneMatch && ifNoneMatch.split(',').some((v) => v.trim().replace(/^W\//, '') === etag)) {
				headers.set('cache-control', versionedCacheControl(requestedVersion, current, SHORT_CACHE));
				headers.set('etag', etag);
				return new Response(null, { status: 304, headers });
			}
			const r = await tile(def, id, current, t);
			if ('empty' in r) {
				note(id, r.empty, t, r.detail);
				return empty(headers, r.empty);
			}
			if (r.stale) headers.set('cache-control', SHORT_CACHE);
			else {
				headers.set('cache-control', versionedCacheControl(requestedVersion, current, SHORT_CACHE));
				headers.set('etag', etag);
			}
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

/** The modules found by glob: each `<plugin>/tiles.ts` beside this file, by path. */
export type TileModules = Record<string, { default: TileLayerDef | readonly TileLayerDef[] }>;

/**
 * The registry from the found modules, by `'<plugin>.<layer>'`. A definition
 * with problems, outside its plugin's folder or defined twice is left out
 * (logged), so it 404s alone; mvt.test.ts's registry test runs this over the
 * same files and fails on any of them first.
 */
export function buildRegistry(found: TileModules, log: (msg: string) => void = console.error): Map<string, TileLayerDef> {
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
export const TILE_LAYERS: ReadonlyMap<string, TileLayerDef> = buildRegistry(import.meta.glob('./*/tiles.ts', { eager: true }) as TileModules);

export function tileLayer(plugin: string | undefined, layer: string | undefined): TileLayerDef | undefined {
	return plugin && layer ? TILE_LAYERS.get(layerKey(plugin, layer)) : undefined;
}
