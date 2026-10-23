import { afterEach, describe, expect, it, vi } from 'vitest';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { DbPart } from './versions.js';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { assembleMeta, dataMeta, readDatabase, readTiles, resetMetaCache, shortHash } = await import('./versions.js');
const { META_CONTRACT } = await import('#lib/contracts/meta.js');
const { layerCredit, layerSource, layerTilesUrl, layerVersion } = await import('#lib/contracts/layer-tiles.js');

/** A toggled layer's build as readDatabase gives it. */
const build = (version: string, credit = 'USDA NRCS SSURGO') => ({ version, builtAt: 1_760_000_000, license: 'public domain', republish: 'yes' as const, credit });

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
		expect(await readTiles(dir)).toEqual({ basemap: '2026-10-05', terrain: '2026-10-04', imagery: null, buildings: null, landscape: null, ground: null });
		expect(await readTiles(join(dir, 'missing'))).toBeNull();
		expect(shortHash('x')).toHaveLength(12);
		await rm(dir, { recursive: true, force: true });
	});

	it('reads the landscape and ground build dates, only from a baked or painted entry', async () => {
		const dir = await mkdtemp(join(tmpdir(), 'tvt-meta-'));
		const write = (m: unknown) => writeFile(join(dir, 'manifest.json'), JSON.stringify(m));
		await write({ basemap: { built: '2026-10-05' }, landscape: { status: 'baked', built: '2026-10-20' }, ground: { status: 'painted', built: '2026-10-18' } });
		expect(await readTiles(dir)).toMatchObject({ landscape: '2026-10-20', ground: '2026-10-18' });
		// A newer manifest is read again (the cache goes by modification time).
		await new Promise((r) => setTimeout(r, 20));
		await write({ landscape: { status: 'empty', reason: 'nothing to bake', built: '2026-10-21' }, ground: { status: 'flat', reason: 'no soils', built: '2026-10-21' } });
		expect(await readTiles(dir)).toMatchObject({ landscape: null, ground: null });
		await rm(dir, { recursive: true, force: true });
	});

	it('stays contract 1: the versions as before, plus the optional layers and status', () => {
		const m = assembleMeta(1, 'ok', part(), null);
		expect(META_CONTRACT).toBe(1);
		expect(m.contract).toBe(1);
		expect(Object.keys(m.versions).sort()).toEqual(['calibrations', 'cameras', 'gtfs', 'layers', 'ribbons', 'roads', 'tiles']);
		expect(Object.keys(m).sort()).toEqual(
			['calibrations', 'cameras', 'contract', 'database', 'generatedAt', 'gtfs', 'layers', 'progress', 'ribbons', 'roads', 'status', 'tiles', 'versions']
		);
		// Layer versions and builds change nothing a client written before them reads.
		const { layers, ...before } = m.versions;
		const withSoils = assembleMeta(1, 'ok', part({ layers: { 'soils.units': build('s1') } }), null);
		const { layers: withLayers, ...after } = withSoils.versions;
		expect(layers).toEqual({});
		expect(withLayers).toEqual({ 'soils.units': 's1' });
		expect(after).toEqual(before);
		const { layers: builds, versions: _v, ...rest } = withSoils;
		const { layers: noBuilds, versions: _w, ...restBefore } = m;
		expect(noBuilds).toEqual({});
		expect(builds).toEqual({ 'soils.units': { builtAt: 1_760_000_000, license: 'public domain', republish: 'yes', credit: 'USDA NRCS SSURGO' } });
		expect(rest).toEqual(restBefore);
	});

	it("reports toggled layers' versions and credits as their builds wrote them", () => {
		const m = assembleMeta(1, 'ok', part({ layers: { 'soils.units': build('20261011T0412Z-3fa9c1'), 'farm.crop_fields': build('b7', '© OpenStreetMap contributors; USDA NASS') } }), null);
		expect(m.versions.layers).toEqual({ 'soils.units': '20261011T0412Z-3fa9c1', 'farm.crop_fields': 'b7' });
		expect(layerCredit(m, 'soils', 'units')).toBe('USDA NRCS SSURGO');
		expect(layerCredit(m, 'farm', 'crop_fields')).toBe('© OpenStreetMap contributors; USDA NASS');
		expect(layerCredit(m, 'trails', 'paths')).toBeNull();
		expect(layerCredit(null, 'soils', 'units')).toBeNull();
		expect(m.layers?.['farm.crop_fields']).not.toHaveProperty('version');
		expect(m.versions.roads).toBe(assembleMeta(1, 'ok', part(), null).versions.roads);
		expect(layerVersion(m, 'soils', 'units')).toBe('20261011T0412Z-3fa9c1');
		expect(layerVersion(m, 'trails', 'paths')).toBeNull();
		expect(layerVersion(null, 'soils', 'units')).toBeNull();
		expect(layerVersion({ versions: { ...m.versions, layers: undefined } }, 'soils', 'units')).toBeNull();
		expect(layerTilesUrl('https://x', 'soils', 'units', m)).toBe('https://x/api/soils/tiles/units/{z}/{x}/{y}?v=20261011T0412Z-3fa9c1');
		expect(layerTilesUrl('https://x', 'trails', 'paths', m)).toBe('https://x/api/trails/tiles/paths/{z}/{x}/{y}');
		// A toggled layer as a vector source: the versioned URL, the build's zooms and its credit.
		expect(layerSource('https://x', m, 'soils', 'units', { minzoom: 8, maxzoom: 15, promoteId: 'id' })).toEqual({
			type: 'vector',
			tiles: ['https://x/api/soils/tiles/units/{z}/{x}/{y}?v=20261011T0412Z-3fa9c1'],
			minzoom: 8,
			maxzoom: 15,
			promoteId: 'id',
			attribution: 'USDA NRCS SSURGO'
		});
		expect(layerSource('https://x', null, 'trails', 'paths', { minzoom: 10, maxzoom: 16 })).toEqual({
			type: 'vector',
			tiles: ['https://x/api/trails/tiles/paths/{z}/{x}/{y}'],
			minzoom: 10,
			maxzoom: 16
		});
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
						{ layer: 'soils.units', version: 's2', built_at: 1_760_000_000, license: 'public domain', republish: 'yes', credit: 'USDA NRCS SSURGO' },
						{ layer: 'trails.paths', version: 't1', built_at: 1_760_000_100, license: 'ODbL', republish: 'yes', credit: '© OpenStreetMap contributors' }
					];
				return [];
			}) as unknown as Parameters<typeof readDatabase>[0];
		const after = await readDatabase(fake(true));
		expect(after.layers).toEqual({
			'soils.units': build('s2'),
			'trails.paths': { version: 't1', builtAt: 1_760_000_100, license: 'ODbL', republish: 'yes', credit: '© OpenStreetMap contributors' }
		});
		expect(seen.some((t) => t.includes('to_regclass(\'core.layer_version\')'))).toBe(true);
		const read = seen.find((t) => t.includes('from core.layer_version'));
		expect(read).toContain('select distinct on (layer) layer, version,');
		expect(read).toContain('license, republish, credit from core.layer_version order by layer, id desc');
		seen.length = 0;
		const before = await readDatabase(fake(false));
		expect(before.layers).toEqual({});
		expect(seen.some((t) => t.includes('from core.layer_version'))).toBe(false);
		expect(assembleMeta(1, 'ok', before, null).versions.layers).toEqual({});
		expect(assembleMeta(1, 'ok', before, null).layers).toEqual({});
	});

	it('carries the status views (migration 0021), changing no version', () => {
		const status = {
			sources: { fresh: 41, late: 1, stale: 0, never: 0, failing: 0 },
			attention: [{ source: 'achd_roads', state: 'late' as const, lastOkAt: 1_759_000_000, everyS: 604_800, failures: 0 }],
			builds: [{ build: 'roads-build', state: 'pending' as const, lastOkAt: null, pendingSince: 1_760_000_000, lastRunAt: null }]
		};
		const m = assembleMeta(1, 'ok', part({ status }), null);
		expect(m.status).toEqual(status);
		expect(m.versions).toEqual(assembleMeta(1, 'ok', part(), null).versions);
		expect(assembleMeta(1, 'ok', part(), null).status).toBeNull();
		expect(assembleMeta(1, 'error', null, null).status).toBeNull();
	});

	it('reads the status views once they exist, and answers without them if they fail', async () => {
		const run = async (views: boolean, fail: boolean) => {
			const seen: string[] = [];
			const fake = (async (strings: TemplateStringsArray) => {
				const text = strings.join('$').replace(/\s+/g, ' ');
				seen.push(text);
				if (text.includes('to_regclass')) return [{ layer_versions: true, status: views, roads: true }];
				if (text.includes('from ops.source_status')) {
					if (fail) throw new Error('view broken');
					return [{ source: 'awc_metar', state: 'fresh', last_ok_at: 1_760_000_000, every_s: 600, failures: 0 }];
				}
				if (text.includes('from ops.build_status')) return [];
				if (text.includes('from core.road_segment')) return [{ segments: 3, total: 3, max_id: '3', last_seen: 1 }];
				return [];
			}) as unknown as Parameters<typeof readDatabase>[0];
			return { part: await readDatabase(fake), seen };
		};
		const quiet = vi.spyOn(console, 'error').mockImplementation(() => {});
		try {
			const ok = await run(true, false);
			expect(ok.part.status?.sources).toEqual({ fresh: 1, late: 0, stale: 0, never: 0, failing: 0 });
			expect(ok.seen[0]).toContain("to_regclass('ops.source_status') is not null and to_regclass('ops.build_status') is not null as status");
			const before = await run(false, false);
			expect(before.part.status).toBeNull();
			expect(before.seen.some((t) => t.includes('from ops.source_status'))).toBe(false);
			const broken = await run(true, true);
			expect(broken.part.status).toBeNull();
			expect(broken.part.roads).toEqual({ segments: 3, lastSeen: 1 });
			expect(quiet).toHaveBeenCalledOnce();
		} finally {
			quiet.mockRestore();
		}
	});
});
