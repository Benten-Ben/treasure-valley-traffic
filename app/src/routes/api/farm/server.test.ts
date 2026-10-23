import { describe, expect, it, vi } from 'vitest';
import { existsSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gunzipSync } from 'node:zlib';

/**
 * /api/farm/year, /api/farm/fields/<id> (the card) and the tile URL beside them. The tile URL is the generic
 * route's (`/api/[plugin]/tiles/...`); a static `api/farm/` folder doesn't stop it reaching that route as long
 * as `api/farm/` has no `tiles/` of its own, which this checks, and that the route answers a crop-fields tile.
 */
const { sqlRows, tileCalls, versions } = vi.hoisted(() => ({
	sqlRows: { tables: [] as string[], rows: {} as Record<string, unknown[]> },
	tileCalls: { n: 0, texts: [] as string[] },
	versions: { roads: 'r1', layers: { 'farm.crop_fields': 'f1' } as Record<string, string> }
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
			unsafe: (text: string) => (tileCalls.n++, tileCalls.texts.push(text), Promise.resolve([{ mvt: Buffer.from('farm tile'), version: versions.layers['farm.crop_fields'] }])),
			begin: async (_o: string, fn: (tx: unknown) => unknown) => fn({ unsafe: () => (tileCalls.n++, Promise.resolve([{ mvt: Buffer.from('year tile'), version: versions.layers['farm.crop_fields'] }])) })
		})
	};
});

const folder = join(dirname(fileURLToPath(import.meta.url)));

describe('GET /api/farm/year', () => {
	it('says not built before the migration, and the crop year after', async () => {
		const route = await import('./year/+server.js');
		sqlRows.tables = [];
		const before = await route.GET({ request: new Request('http://x/api/farm/year') } as never);
		expect(await before.json()).toMatchObject({ built: false, year: null });
		sqlRows.tables = ['farm.crop_year'];
		sqlRows.rows = { 'from farm.crop_year': [{ year: 2025, label: "2025 (USDA's newest)", first_year: 2018, edition: 'e' }] };
		const res = await route.GET({ request: new Request('http://x/api/farm/year') } as never);
		expect(res.headers.get('cache-control')).toBe('no-cache');
		expect(await res.json()).toMatchObject({ built: true, year: 2025, label: "2025 (USDA's newest)" });
	});
});

describe('GET /api/farm/fields/[id]', () => {
	const ask = async (id: string) => {
		const route = await import('./fields/[id]/+server.js');
		try {
			return await route.GET({ params: { id }, request: new Request(`http://x/api/farm/fields/${id}`) } as never);
		} catch (e) {
			return e as { status: number };
		}
	};

	it('answers empty before the migration: 404, never a 500', async () => {
		sqlRows.tables = [];
		sqlRows.rows = {};
		expect((await ask('5')).status).toBe(404);
	});

	it('400s ids that cannot be one', async () => {
		for (const id of ['x', '0', '-3', '1.5', '12345678901']) expect((await ask(id)).status, id).toBe(400);
	});

	it('serves a field with an ETag', async () => {
		sqlRows.tables = ['farm.field'];
		sqlRows.rows = {
			'from farm.field f where f.id': [{ id: 5, acres: 24, county: 'Canyon', first_year: 2018, crops: [36], agree: {}, july: null, growth: 'farmed', growth_detail: null, plat: null, valid_to: null, lng: -116.6, lat: 43.6, w: -116.61, s: 43.59, e: -116.59, n: 43.61 }],
			'from farm.crop_class': [{ code: 36, name: 'Alfalfa', grp: 'hay' }]
		};
		const res = (await ask('5')) as Response;
		expect(res.status).toBe(200);
		expect(res.headers.get('etag')).toBeTruthy();
		expect(await res.json()).toMatchObject({ id: 5, acres: 24, county: 'Canyon', years: [{ year: 2018, name: 'Alfalfa', group: 'hay' }] });
		const again = (await ask('5')) as Response;
		const nm = await (await import('./fields/[id]/+server.js')).GET({ params: { id: '5' }, request: new Request('http://x', { headers: { 'if-none-match': res.headers.get('etag')! } }) } as never);
		expect(again.headers.get('etag')).toBe(res.headers.get('etag'));
		expect(nm.status).toBe(304);
	});
});

describe('the tile URL beside the card API', () => {
	it('has no tiles folder of its own under api/farm, so the generic route answers', () => {
		expect(existsSync(join(folder, 'tiles'))).toBe(false);
		expect(readdirSync(folder).sort()).toEqual(expect.arrayContaining(['fields', 'year']));
	});

	it('answers /api/farm/tiles/crop_fields/{z}/{x}/{y} and a year layer through the generic route', async () => {
		const route = await import('../[plugin]/tiles/[layer]/[z]/[x]/[y]/+server.js');
		const get = async (params: Record<string, string>, search = '') => {
			const url = new URL(`http://x/api/${params.plugin}/tiles/${params.layer}/${params.z}/${params.x}/${params.y}${search}`);
			try {
				return (await route.GET({ url, params, request: new Request(url, { headers: { 'accept-encoding': 'gzip' } }) } as never)) as Response;
			} catch (e) {
				return e as Response & { status: number };
			}
		};
		const fields = await get({ plugin: 'farm', layer: 'crop_fields', z: '11', x: '359', y: '747' }, '?v=f1');
		expect(fields.status).toBe(200);
		expect(fields.headers.get('etag')).toBe('"farm.crop_fields-f1-gz"');
		expect(gunzipSync(new Uint8Array(await fields.arrayBuffer())).toString()).toBe('farm tile');
		expect(tileCalls.texts[0]).toContain('"farm"."crop_fields" s');
		// An earlier year is its own layer with the fields layer's version.
		const year = await get({ plugin: 'farm', layer: 'crop_year_2019', z: '10', x: '179', y: '373' }, '?v=f1');
		expect(year.status).toBe(200);
		expect(year.headers.get('etag')).toBe('"farm.crop_year_2019-f1-gz"');
		expect(year.headers.get('cache-control')).toContain('immutable');
		expect(gunzipSync(new Uint8Array(await year.arrayBuffer())).toString()).toBe('year tile');
		// The year cuts stop at z10, the fields at z14; there is no 2025 cut (the fields layer is the newest year).
		expect((await get({ plugin: 'farm', layer: 'crop_year_2019', z: '11', x: '359', y: '747' })).status).toBe(404);
		expect((await get({ plugin: 'farm', layer: 'crop_fields', z: '15', x: '0', y: '0' })).status).toBe(404);
		expect((await get({ plugin: 'farm', layer: 'crop_year_2025', z: '10', x: '179', y: '373' })).status).toBe(404);
	});
});
