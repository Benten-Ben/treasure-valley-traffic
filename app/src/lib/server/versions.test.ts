import { afterEach, describe, expect, it, vi } from 'vitest';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { DbPart } from './versions.js';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { assembleMeta, dataMeta, readTiles, resetMetaCache, shortHash } = await import('./versions.js');

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
});
