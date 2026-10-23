import { describe, expect, it, vi } from 'vitest';
import type { DataMeta } from '#lib/contracts/meta.js';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const server = await import('#lib/server/farm/tiles.js');
const mvt = await import('#lib/server/mvt.js');
const client = await import('./tiles.js');

const meta = { versions: { layers: { 'farm.crop_fields': '20261011T1306Z-1d7b99' } }, layers: { 'farm.crop_fields': { credit: 'USDA NASS CSB' } } } as unknown as DataMeta;

describe('the crop fields tile URLs', () => {
	it('agree with the server definitions: plugin, layer, zooms, MVT layer and the years with a cut', () => {
		expect(client.PLUGIN).toBe(server.PLUGIN);
		expect(client.FIELDS_LAYER).toBe(server.FIELDS_LAYER);
		expect(client.MVT_LAYER).toBe(server.MVT_LAYER);
		expect(client.FIELDS_FROM).toBe(server.FIELDS_FROM);
		expect(client.MAX_ZOOM).toBe(server.LAYER_MAXZOOM);
		expect([...client.CUT_YEARS]).toEqual([...server.YEARS]);
		expect(client.YEAR_MAX_ZOOM).toBe(server.LO_ZOOMS.at(-1));
		const defs = server.default;
		expect(defs[0].minzoom).toBe(client.MIN_ZOOM);
		expect(defs[0].maxzoom).toBe(client.MAX_ZOOM);
		for (const d of defs.slice(1)) expect(d.layer).toBe(client.yearLayer(Number(d.layer.slice(-4))));
		expect(mvt.versionKey(defs[1])).toBe('farm.crop_fields');
	});

	it('versions the fields tiles, and the earlier years by the fields layer\'s version', () => {
		expect(client.fieldsUrl('http://x', meta)).toBe('http://x/api/farm/tiles/crop_fields/{z}/{x}/{y}?v=20261011T1306Z-1d7b99');
		expect(client.yearUrl('http://x', meta, 2019)).toBe('http://x/api/farm/tiles/crop_year_2019/{z}/{x}/{y}?v=20261011T1306Z-1d7b99');
		// No build yet: no version, as for any layer.
		expect(client.fieldsUrl('http://x', null)).toBe('http://x/api/farm/tiles/crop_fields/{z}/{x}/{y}');
		expect(client.yearUrl('http://x', null, 2019)).toBe('http://x/api/farm/tiles/crop_year_2019/{z}/{x}/{y}');
		expect(client.fieldsCredit(meta)).toBe('USDA NASS CSB');
		expect(client.hasCut(2018)).toBe(true);
		expect(client.hasCut(2025)).toBe(false);
	});
});
