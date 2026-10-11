import { afterEach, describe, expect, it, vi } from 'vitest';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { DbPart } from './versions.js';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { assembleMeta, dataMeta, readDatabase, readTiles, resetMetaCache, shortHash } = await import('./versions.js');
const { META_CONTRACT } = await import('#lib/contracts/meta.js');
const { layerTilesUrl, layerVersion } = await import('#lib/contracts/layer-tiles.js');

const part = (over: Partial<DbPart> = {}): DbPart => ({
	gtfs: { feedVersion: '457', routes: 20, updatedAt: 1_759_700_000 },
	ribbons: null,
	progress: { available: false },
	roads: { segments: 38_727, lastSeen: 1_759_700_000 },
	cameras: { cameras: 228, views: 210, withImage: 210 },
	calibrations: { current: 11, latestId: 21, latestAt: 1_759_718_838 },
	inputs: { roads: [38_727, 38_727, '38727', 1_759_700_000], cameras: 'abc/def', calibrations: [11, 21, 1_759_700_100] },
	...over
});

afterEach(() => resetMetaCache());

describe('/api/meta', () => {
	it("reads ribbons as 'none' before migration 0006 or a first build", () => {
		const m = assembleMeta(1, 'ok', part(), null);
		expect(m.contract).toBe(1);
		expect(m.versions.ribbons).toBe('none');
		expect(m.ribbons).toBeNull();
		expect(m.versions.gtfs).toBe('457');
	});

	it('reports a ribbon build and progress once they exist', () => {
		const m = assembleMeta(1, 'ok', part({ ribbons: { build: 'f00d', segments: 412 }, progress: { available: true } }), null);
		expect(m.versions.ribbons).toBe('f00d');
		expect(m.ribbons).toEqual({ build: 'f00d', segments: 412 });
		expect(m.progress.available).toBe(true);
	});

	it('changes the cameras version when a calibration changes, not the roads version', () => {
		const a = assembleMeta(1, 'ok', part(), null);
		const b = assembleMeta(1, 'ok', part({ inputs: { ...part().inputs, calibrations: [12, 22, 1_759_700_100] } }), null);
		expect(b.versions.calibrations).not.toBe(a.versions.calibrations);
		expect(b.versions.cameras).not.toBe(a.versions.cameras);
		expect(b.versions.roads).toBe(a.versions.roads);
		expect(a.versions.cameras).toMatch(/^[0-9a-f]{12}$/);
	});

	it('keeps internal version inputs out of the response', () => {
		const m = assembleMeta(1, 'ok', part(), null);
		expect(JSON.stringify(m)).not.toContain('inputs');
		expect(Object.keys(m.roads!)).toEqual(['segments', 'lastSeen']);
	});

	it('still answers without a database', async () => {
		const m = await dataMeta();
		expect(m.database).toBe('unconfigured');
		expect(m.versions).toMatchObject({ gtfs: null, ribbons: 'none', cameras: null, calibrations: null });
		expect(m.progress.available).toBe(false);
	});

	it('memoizes for 15 s', async () => {
		const a = dataMeta(1_000_000);
		expect(dataMeta(1_014_000)).toBe(a);
		expect(dataMeta(1_016_000)).not.toBe(a);
	});

	it("reads the tiles' build dates from the manifest", async () => {
		const dir = await mkdtemp(join(tmpdir(), 'tvt-meta-'));
		await writeFile(join(dir, 'manifest.json'), JSON.stringify({
			basemap: { built: '2026-10-05' }, terrain: { built: '2026-10-04' }
		}));
		expect(await readTiles(dir)).toEqual({ basemap: '2026-10-05', terrain: '2026-10-04', imagery: null, buildings: null });
		expect(await readTiles(join(dir, 'missing'))).toBeNull();
		expect(shortHash('x')).toHaveLength(12);
		await rm(dir, { recursive: true, force: true });
	});

	it('stays contract 1: the versions as before, plus the optional layers', () => {
		const m = assembleMeta(1, 'ok', part(), null);
		expect(META_CONTRACT).toBe(1);
		expect(m.contract).toBe(1);
		expect(Object.keys(m.versions).sort()).toEqual(['calibrations', 'cameras', 'gtfs', 'layers', 'ribbons', 'roads', 'tiles']);
		expect(Object.keys(m).sort()).toEqual(
			['calibrations', 'cameras', 'contract', 'database', 'generatedAt', 'gtfs', 'progress', 'ribbons', 'roads', 'tiles', 'versions']
		);
		// Layer versions change nothing a client written before them reads.
		const { layers, ...before } = m.versions;
		const { layers: withLayers, ...after } = assembleMeta(1, 'ok', part({ layers: { 'soils.units': 's1' } }), null).versions;
		expect(layers).toEqual({});
		expect(withLayers).toEqual({ 'soils.units': 's1' });
		expect(after).toEqual(before);
	});

	it("reports toggled layers' versions as their builds wrote them", () => {
		const m = assembleMeta(1, 'ok', part({ layers: { 'soils.units': '20261011T0412Z-3fa9c1', 'farm.crop_fields': 'b7' } }), null);
		expect(m.versions.layers).toEqual({ 'soils.units': '20261011T0412Z-3fa9c1', 'farm.crop_fields': 'b7' });
		expect(m.versions.roads).toBe(assembleMeta(1, 'ok', part(), null).versions.roads);
		expect(layerVersion(m, 'soils', 'units')).toBe('20261011T0412Z-3fa9c1');
		expect(layerVersion(m, 'trails', 'paths')).toBeNull();
		expect(layerVersion(null, 'soils', 'units')).toBeNull();
		expect(layerVersion({ versions: { ...m.versions, layers: undefined } }, 'soils', 'units')).toBeNull();
		expect(layerTilesUrl('https://x', 'soils', 'units', m)).toBe('https://x/api/soils/tiles/units/{z}/{x}/{y}?v=20261011T0412Z-3fa9c1');
		expect(layerTilesUrl('https://x', 'trails', 'paths', m)).toBe('https://x/api/trails/tiles/paths/{z}/{x}/{y}');
		expect(assembleMeta(1, 'error', null, null).versions.layers).toEqual({});
	});

	it('reads each layer\'s newest version, and none before migration 0020', async () => {
		const seen: string[] = [];
		const fake = (layerTable: boolean) =>
			(async (strings: TemplateStringsArray) => {
				const text = strings.join('$').replace(/\s+/g, ' ');
				seen.push(text);
				if (text.includes('to_regclass')) return [{ layer_versions: layerTable }];
				if (text.includes('core.layer_version'))
					return [
						{ layer: 'soils.units', version: 's2' },
						{ layer: 'trails.paths', version: 't1' }
					];
				return [];
			}) as unknown as Parameters<typeof readDatabase>[0];
		const after = await readDatabase(fake(true));
		expect(after.layers).toEqual({ 'soils.units': 's2', 'trails.paths': 't1' });
		expect(seen.some((t) => t.includes('to_regclass(\'core.layer_version\')'))).toBe(true);
		expect(seen.find((t) => t.includes('from core.layer_version'))).toContain('distinct on (layer) layer, version from core.layer_version order by layer, id desc');
		seen.length = 0;
		const before = await readDatabase(fake(false));
		expect(before.layers).toEqual({});
		expect(seen.some((t) => t.includes('from core.layer_version'))).toBe(false);
		expect(assembleMeta(1, 'ok', before, null).versions.layers).toEqual({});
	});
});
