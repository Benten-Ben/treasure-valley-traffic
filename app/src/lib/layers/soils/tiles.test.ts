import { describe, expect, it, vi } from 'vitest';
import type { DataMeta } from '#lib/contracts/meta.js';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const server = await import('#lib/server/soils/tiles.js');
const client = await import('./tiles.js');

const meta = { versions: { layers: { 'soils.units': '20261011T1228Z-3dc4b3' } }, layers: { 'soils.units': { credit: 'Soils: USDA NRCS, SSURGO' } } } as unknown as DataMeta;

describe('the Soils tile URL', () => {
	it('agrees with the server definition: plugin, layer, zooms, MVT layers and where each band starts', () => {
		expect(client.PLUGIN).toBe(server.PLUGIN);
		expect(client.LAYER).toBe(server.LAYER);
		expect(client.MVT_UNITS).toBe(server.MVT_UNITS);
		expect(client.MVT_SURVEY).toBe(server.MVT_SURVEY);
		expect(client.MVT_LABELS).toBe(server.MVT_LABELS);
		expect(client.MIN_ZOOM).toBe(server.MIN_ZOOM);
		expect(client.MAX_ZOOM).toBe(server.MAX_ZOOM);
		expect(client.WASH_FROM).toBe(server.WASH_FROM);
		expect(client.SURVEY_TO).toBe(server.SURVEY_MAX_ZOOM + 1);
		expect(client.SYMBOLS_FROM).toBe(server.LABELS_FROM);
		expect(server.default.minzoom).toBe(client.MIN_ZOOM);
		expect(server.default.maxzoom).toBe(client.MAX_ZOOM);
	});

	it("versions the tiles by the layer's version, and credits the build", () => {
		expect(client.unitsUrl('http://x', meta)).toBe('http://x/api/soils/tiles/units/{z}/{x}/{y}?v=20261011T1228Z-3dc4b3');
		expect(client.unitsUrl('http://x', null)).toBe('http://x/api/soils/tiles/units/{z}/{x}/{y}');
		expect(client.unitsCredit(meta)).toBe('Soils: USDA NRCS, SSURGO');
		expect(client.built(meta)).toBe(true);
		expect(client.built(null)).toBe(false);
		expect(client.built({ versions: { layers: {} } } as unknown as DataMeta)).toBe(false);
	});
});
