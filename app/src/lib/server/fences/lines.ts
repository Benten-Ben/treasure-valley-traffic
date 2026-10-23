import { createHash } from 'node:crypto';
import { constants, gunzip as gunzipCb, gzip as gzipCb } from 'node:zlib';
import { promisify } from 'node:util';
import { versionedCacheControl } from '../cache-headers.js';

/**
 * GET /api/fences/lines?v= (plan P10): the valley's mapped fences, walls, retaining walls, guard rails and jersey
 * barriers as one GeoJSON, from `fences.fence` (the fences plugin; OpenStreetMap, ODbL). It feeds both the 2D line and
 * the 3D static batch, so the app asks for it once.
 *
 * - Every active line but hedges (hedges are stored for the shrubs' hedge check and aren't drawn as fences): about
 *   1,500 lines, a few hundred KB, gzipped here once per version and kept.
 * - The version is the newest `fences.lines` row of `core.layer_version`, which each OpenStreetMap load writes (the same
 *   one /api/meta reports as `versions.layers['fences.lines']`). Asked for with it as `?v=`, the answer is immutable;
 *   without it, or with an older one, it is the current data under `no-cache`. An ETag either way.
 * - Before the plugin's migration (or before its first load) the collection is empty, never a 500.
 *
 * Properties are short, since there are thousands of them: see `FenceProps`.
 */

const gzip = promisify(gzipCb);
const gunzip = promisify(gunzipCb);

export const CONTENT_TYPE = 'application/geo+json';
/** Answered while there is no version to name: ask again soon. */
export const UNVERSIONED_CACHE = 'no-cache';

/** A postgres.js tagged template, or a test's stand-in. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Sql = (strings: TemplateStringsArray, ...values: any[]) => Promise<any[]>;

export type FenceType = 'fence' | 'wall' | 'retaining_wall' | 'guard_rail' | 'jersey_barrier' | 'other';

/** What each feature carries. */
export interface FenceProps {
	/** `osm:w<way id>`. */
	id: string;
	type: FenceType;
	/** Solid or see-through, read from the tags ((caution) a reading, not a survey). */
	look: 'solid' | 'open';
	/** Height in metres. */
	h: number;
	/** `tagged`: the height is in OpenStreetMap; `default`: estimated by type ((caution)). */
	hs: 'tagged' | 'default';
	/** Material, as tagged. */
	m: string | null;
	/** The fence_type tag (chain_link, wood, ...), as tagged. */
	ft: string | null;
	/** Length in metres. */
	len: number;
	/** The name, when a contributor gave one. */
	name: string | null;
}

export type FenceFeature = GeoJSON.Feature<GeoJSON.LineString, FenceProps>;
export type FenceCollection = GeoJSON.FeatureCollection<GeoJSON.LineString, FenceProps>;

export const EMPTY: FenceCollection = { type: 'FeatureCollection', features: [] };

const TYPES: ReadonlySet<string> = new Set(['fence', 'wall', 'retaining_wall', 'guard_rail', 'jersey_barrier', 'other']);

/** One row of the query as a feature (null for a row that can't be drawn). */
export function fenceFeature(r: Record<string, unknown>): FenceFeature | null {
	const type = String(r.type);
	if (!TYPES.has(type)) return null;
	let geometry: unknown = r.geometry;
	if (typeof geometry === 'string') geometry = JSON.parse(geometry);
	const g = geometry as GeoJSON.LineString | null;
	if (!g || g.type !== 'LineString' || g.coordinates.length < 2) return null;
	const h = Number(r.height_m);
	if (!(h > 0)) return null;
	const num1 = (v: unknown) => Math.round(Number(v) * 10) / 10;
	return {
		type: 'Feature',
		id: String(r.fence_id),
		geometry: g,
		properties: {
			id: String(r.fence_id),
			type: type as FenceType,
			look: r.look === 'open' ? 'open' : 'solid',
			h: Math.round(h * 100) / 100,
			hs: r.height_source === 'tagged' ? 'tagged' : 'default',
			m: r.material ? String(r.material) : null,
			ft: r.fence_type ? String(r.fence_type) : null,
			len: num1(r.length_m ?? 0),
			name: r.name ? String(r.name) : null
		}
	};
}

/** Every active line but hedges, or an empty collection when the table isn't here. */
export async function readFenceLines(sql: Sql): Promise<FenceCollection> {
	const [has] = await sql`select to_regclass('fences.fence') is not null as fences`;
	if (!has?.fences) return EMPTY;
	// Six decimals is about 0.1 m.
	const rows = await sql`
		select fence_id, type, look, height_m, height_source, material, fence_type, name, length_m,
		       ST_AsGeoJSON(geom, 6) as geometry
		from fences.fence
		where active and type <> 'hedge'
		order by fence_id`;
	const features: FenceFeature[] = [];
	for (const r of rows) {
		const f = fenceFeature(r);
		if (f) features.push(f);
	}
	return { type: 'FeatureCollection', features };
}

export interface LinesDeps {
	sql(): Sql;
	/** The current `fences.lines` version (`versions.layers['fences.lines']` of /api/meta), null when there is none. */
	version(): Promise<string | null>;
}

export interface LinesServer {
	respond(requestedVersion: string | null, acceptEncoding: string | null, ifNoneMatch?: string | null): Promise<Response>;
	/** How many times the table was read (tests). */
	readonly reads: number;
}

interface Built {
	gz: Uint8Array;
	hash: string;
}

const acceptsGzip = (h: string | null) =>
	!!h &&
	h.split(',').some((part) => {
		const [name, ...params] = part.trim().toLowerCase().split(';');
		if (name !== 'gzip' && name !== '*') return false;
		const q = params.map((p) => p.trim()).find((p) => p.startsWith('q='));
		return !q || Number(q.slice(2)) > 0;
	});

export function fenceLinesServer(deps: LinesDeps): LinesServer {
	let kept: { version: string; built: Built } | null = null;
	let inflight: { version: string | null; p: Promise<Built> } | null = null;
	let reads = 0;

	async function build(): Promise<Built> {
		reads++;
		const text = JSON.stringify(await readFenceLines(deps.sql()));
		return {
			gz: new Uint8Array(await gzip(text, { level: constants.Z_BEST_COMPRESSION })),
			hash: createHash('sha1').update(text).digest('base64url').slice(0, 16)
		};
	}

	/** The answer for `version`: kept per version, one read for concurrent callers; never kept without a version. */
	function builtFor(version: string | null): Promise<Built> {
		if (version && kept?.version === version) return Promise.resolve(kept.built);
		if (inflight && inflight.version === version) return inflight.p;
		const p = build().then((built) => {
			if (version) kept = { version, built };
			return built;
		});
		const entry = { version, p };
		inflight = entry;
		const done = () => {
			if (inflight === entry) inflight = null;
		};
		p.then(done, done);
		return p;
	}

	return {
		get reads() {
			return reads;
		},
		async respond(requested, acceptEncoding, ifNoneMatch) {
			const current = await deps.version();
			const built = await builtFor(current);
			const encode = acceptsGzip(acceptEncoding);
			const tag = `"fences-${current ?? `none-${built.hash}`}${encode ? '-gz' : ''}"`;
			const headers = new Headers({
				'content-type': CONTENT_TYPE,
				'cache-control': versionedCacheControl(requested, current, UNVERSIONED_CACHE),
				vary: 'Accept-Encoding',
				etag: tag
			});
			if (ifNoneMatch && ifNoneMatch.split(',').some((v) => v.trim().replace(/^W\//, '') === tag)) return new Response(null, { status: 304, headers });
			if (encode) {
				headers.set('content-encoding', 'gzip');
				return new Response(built.gz as Uint8Array<ArrayBuffer>, { headers });
			}
			return new Response(new Uint8Array(await gunzip(built.gz)) as Uint8Array<ArrayBuffer>, { headers });
		}
	};
}
