import { beforeEach, describe, expect, it, vi } from 'vitest';
import { gunzipSync } from 'node:zlib';
import { IMMUTABLE } from '#lib/server/cache-headers.js';
import { SHORT_CACHE } from '#lib/server/road-tiles.js';

/**
 * GET /api/[plugin]/tiles/[layer]/[z]/[x]/[y] (#lib/server/mvt; plan C4):
 * the route with /api/meta, the registry and the tile pool replaced by
 * fakes, and one made-up layer.
 */
const { versions, rows, units } = vi.hoisted(() => ({
	versions: { roads: 'road1', layers: { 'soils.units': 's1' } as Record<string, string> },
	rows: { calls: 0, mvt: Buffer.from('soils tile') },
	units: {
		plugin: 'soils',
		layer: 'units',
		minzoom: 8,
		maxzoom: 16,
		parts: [{ name: 'units', sources: [{ minzoom: 8, maxzoom: 16, table: 'soils.unit', id: 'gid', columns: ['musym'] }] }]
	}
}));

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
vi.mock('#lib/server/versions.js', () => ({ dataMeta: async () => ({ versions }) }));
vi.mock('#lib/server/mvt.js', async (original) => {
	const real = await original<typeof import('#lib/server/mvt.js')>();
	const layers = real.buildRegistry({ './soils/tiles.ts': { default: units } });
	return {
		...real,
		tileLayer: (p?: string, l?: string) => (p && l ? layers.get(`${p}.${l}`) : undefined),
		tilesDb: () => ({ unsafe: () => (rows.calls++, Promise.resolve([{ mvt: rows.mvt }])) })
	};
});

async function get(params: Record<string, string>, search = '') {
	const route = await import('./+server.js');
	const url = new URL(`http://x/api/${params.plugin}/tiles/${params.layer}/${params.z}/${params.x}/${params.y}${search}`);
	try {
		return await route.GET({ url, params, request: new Request(url, { headers: { 'accept-encoding': 'gzip' } }) } as never);
	} catch (e) {
		return e as { status: number };
	}
}

describe('GET /api/[plugin]/tiles/[layer]/[z]/[x]/[y]', () => {
	beforeEach(() => (rows.calls = 0));

	it('serves a registered layer, immutable for the version /api/meta reports', async () => {
		const tile = { plugin: 'soils', layer: 'units', z: '12', x: '760', y: '1490' };
		const res = (await get(tile, '?v=s1')) as Response;
		expect(res.status).toBe(200);
		expect(res.headers.get('content-type')).toBe('application/vnd.mapbox-vector-tile');
		expect(res.headers.get('cache-control')).toBe(IMMUTABLE);
		expect(res.headers.get('etag')).toBe('"soils.units-s1-gz"');
		expect(gunzipSync(new Uint8Array(await res.arrayBuffer())).toString()).toBe('soils tile');
		const old = (await get(tile, '?v=s0')) as Response;
		expect(old.headers.get('cache-control')).toBe(SHORT_CACHE);
		expect(rows.calls).toBe(1); // one cut served both
	});

	it('404s an unknown layer, and a tile outside its zooms or the grid', async () => {
		expect((await get({ plugin: 'soils', layer: 'nope', z: '12', x: '0', y: '0' })).status).toBe(404);
		expect((await get({ plugin: 'cameras', layer: 'units', z: '12', x: '0', y: '0' })).status).toBe(404);
		expect((await get({ plugin: 'soils', layer: 'units', z: '17', x: '0', y: '0' })).status).toBe(404);
		expect((await get({ plugin: 'soils', layer: 'units', z: '12', x: '4096', y: '0' })).status).toBe(404);
		expect(rows.calls).toBe(0);
	});
});
