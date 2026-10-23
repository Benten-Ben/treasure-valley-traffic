import { describe, expect, it, vi } from 'vitest';
import { existsSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gunzipSync } from 'node:zlib';

/**
 * /api/soils/at, /api/soils/mapunit/<mukey> (the card) and the tile URL beside them. The tile URL is the
 * generic route's (`/api/[plugin]/tiles/...`); a static `api/soils/` folder doesn't stop it reaching that
 * route as long as `api/soils/` has no `tiles/` of its own, which this checks, and that the route answers a
 * Soils tile. Before the migration both APIs answer empty, never a 500.
 */
const { sqlRows, tileCalls, versions } = vi.hoisted(() => ({
	sqlRows: { tables: [] as string[], rows: {} as Record<string, unknown[]> },
	tileCalls: { n: 0, texts: [] as string[] },
	versions: { roads: 'r1', layers: { 'soils.units': 's1' } as Record<string, string> }
}));

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
vi.mock('#lib/server/db.js', () => ({
	db: () => async (strings: TemplateStringsArray, ...values: unknown[]) => {
		const text = strings.join('?').replace(/\s+/g, ' ');
		if (text.includes('to_regclass')) return [{ ok: sqlRows.tables.includes(String(values[0])) }];
		const key = Object.keys(sqlRows.rows).find((k) => text.includes(k));
		return key ? sqlRows.rows[key] : [];
	}
}));
vi.mock('#lib/server/versions.js', () => ({ dataMeta: async () => ({ versions }) }));
vi.mock('#lib/server/mvt.js', async (original) => {
	const real = await original<typeof import('#lib/server/mvt.js')>();
	return {
		...real,
		tilesDb: () => ({
			begin: async (_o: string, fn: (tx: unknown) => unknown) =>
				fn({ unsafe: (text: string) => (tileCalls.n++, tileCalls.texts.push(text), Promise.resolve([{ mvt: Buffer.from('soil tile'), version: versions.layers['soils.units'] }])) })
		})
	};
});

const folder = join(dirname(fileURLToPath(import.meta.url)));

const UNIT = { mukey: '2700001', musym: 'TeA', muname: 'Testville silt loam', mukind: 'Consociation', farmlndcl: null, slopegraddcp: 1, aws0100wta: 12, drclassdcd: 'Well drained', hydgrpdcd: 'B', hydclprs: 0, restr_kind: null, restr_top_cm: null, restr_hard: null, c_aws: 2, hsg_dual: false, area_in_box_ha: 10, dom_cokey: 'c1', misc: null, areasymbol: 'ID001', areaname: 'Ada County Area, Idaho', saverest: '2025-09-23', saversion: 24, scale: 24000 };

describe('GET /api/soils/at', () => {
	const ask = async (query: string) => {
		const route = await import('./at/+server.js');
		try {
			return (await route.GET({ url: new URL(`http://x/api/soils/at?${query}`), request: new Request(`http://x/api/soils/at?${query}`) } as never)) as Response;
		} catch (e) {
			return e as { status: number };
		}
	};

	it('answers { unit: null } before the migration, never a 500', async () => {
		sqlRows.tables = [];
		sqlRows.rows = {};
		const res = (await ask('lng=-116.39&lat=43.6')) as Response;
		expect(res.status).toBe(200);
		expect(await res.json()).toEqual({ unit: null });
		expect(res.headers.get('cache-control')).toBe('no-cache');
	});

	it('400s a point that cannot be one', async () => {
		for (const q of ['', 'lng=1', 'lat=1', 'lng=x&lat=1', 'lng=-116&lat=95', 'lng=200&lat=43']) expect((await ask(q)).status, q).toBe(400);
	});

	it('names the unit under a point, with an ETag', async () => {
		sqlRows.tables = ['soils.polygon'];
		sqlRows.rows = { 'from soils.polygon p': [{ mukey: '2700001', musym: 'TeA', muname: 'Testville silt loam', misc: null }] };
		const res = (await ask('lng=-116.39&lat=43.6')) as Response;
		expect(await res.json()).toEqual({ unit: { mukey: '2700001', symbol: 'TeA', name: 'Testville silt loam', surveyed: true } });
		const again = (await ask('lng=-116.39&lat=43.6')) as Response;
		expect(again.headers.get('etag')).toBe(res.headers.get('etag'));
	});
});

describe('GET /api/soils/mapunit/[mukey]', () => {
	const ask = async (mukey: string, headers: Record<string, string> = {}) => {
		const route = await import('./mapunit/[mukey]/+server.js');
		try {
			return (await route.GET({ params: { mukey }, request: new Request(`http://x/api/soils/mapunit/${mukey}`, { headers }) } as never)) as Response;
		} catch (e) {
			return e as { status: number };
		}
	};

	it('answers empty before the migration: 404, never a 500', async () => {
		sqlRows.tables = [];
		sqlRows.rows = {};
		expect((await ask('2700001')).status).toBe(404);
	});

	it('400s keys that cannot be one', async () => {
		for (const k of ['x', '0x1', '-3', '1.5', '12345678901', '%27']) expect((await ask(k)).status, k).toBe(400);
	});

	it('serves a card with an ETag, and a 304 for the same one', async () => {
		sqlRows.tables = ['soils.map_unit'];
		sqlRows.rows = {
			'from soils.map_unit m': [UNIT],
			'from soils.component c': [{ cokey: 'c1', compname: 'Testville', comppct_r: 100, majcomp: true, drainagecl: 'Well drained', slope_r: 1, hydricrating: 'No', texture: 'Silt loam' }]
		};
		const res = (await ask('2700001')) as Response;
		expect(res.status).toBe(200);
		const body = await res.json();
		expect(body).toMatchObject({ mukey: '2700001', surveyed: true, note: 'Mapped soil, not a site test; not for regulatory decisions', dominant: { name: 'Testville' } });
		const again = (await ask('2700001', { 'if-none-match': res.headers.get('etag')! })) as Response;
		expect(again.status).toBe(304);
	});
});

describe('the tile URL beside the APIs', () => {
	it('has no tiles folder of its own under api/soils, so the generic route answers', () => {
		expect(existsSync(join(folder, 'tiles'))).toBe(false);
		expect(readdirSync(folder).sort()).toEqual(expect.arrayContaining(['at', 'mapunit']));
	});

	it('answers /api/soils/tiles/units/{z}/{x}/{y} through the generic route, and stops at z14', async () => {
		const route = await import('../[plugin]/tiles/[layer]/[z]/[x]/[y]/+server.js');
		const get = async (params: Record<string, string>, search = '') => {
			const url = new URL(`http://x/api/${params.plugin}/tiles/${params.layer}/${params.z}/${params.x}/${params.y}${search}`);
			try {
				return (await route.GET({ url, params, request: new Request(url, { headers: { 'accept-encoding': 'gzip' } }) } as never)) as Response;
			} catch (e) {
				return e as Response & { status: number };
			}
		};
		const tile = await get({ plugin: 'soils', layer: 'units', z: '12', x: '710', y: '1493' }, '?v=s1');
		expect(tile.status).toBe(200);
		expect(tile.headers.get('etag')).toBe('"soils.units-s1-gz"');
		expect(tile.headers.get('cache-control')).toContain('immutable');
		expect(gunzipSync(new Uint8Array(await tile.arrayBuffer())).toString()).toBe('soil tile');
		expect(tileCalls.texts.join('\n')).toContain('soils.polygon');
		expect((await get({ plugin: 'soils', layer: 'units', z: '15', x: '0', y: '0' })).status).toBe(404);
		expect((await get({ plugin: 'soils', layer: 'units', z: '7', x: '0', y: '0' })).status).toBe(404);
	});
});
