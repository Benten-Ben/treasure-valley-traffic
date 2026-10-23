import { describe, expect, it, vi } from 'vitest';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { BUFFER, buildRegistry, EXTENT, tileLayerProblems } = await import('../mvt.js');
const units = (await import('./tiles.js')).default;
const tiles = await import('./tiles.js');

const flat = (s: string | null) => s?.replace(/\s+/g, ' ') ?? '';

describe('the Soils tile definition', () => {
	it('is valid, in the soils folder, and registered as soils.units', () => {
		expect(tileLayerProblems(units)).toEqual([]);
		const log = vi.fn();
		const r = buildRegistry({ './soils/tiles.ts': { default: units } }, log);
		expect(log).not.toHaveBeenCalled();
		expect([...r.keys()]).toEqual(['soils.units']);
		expect([units.minzoom, units.maxzoom]).toEqual([8, 14]);
	});

	it("writes out mvt.ts's tile extent and buffer (it can't import them at load time)", () => {
		expect(tiles.EXTENT).toBe(EXTENT);
		expect(tiles.BUFFER).toBe(BUFFER);
		expect(flat(tiles.tileSql(9))).toContain(`${EXTENT}, ${BUFFER}, true`);
		expect(flat(tiles.tileSql(9))).toContain(`margin => ${BUFFER / EXTENT}`);
	});

	it('reads the plugin README\'s bands: map units by zoom, then polygons, labels at the top', () => {
		const at = (z: number) => flat(tiles.tileSql(z));
		// z8: the survey bounds only (the wash comes in at z9: the busiest z8 tile was over the byte budget).
		expect(at(8)).toContain('from soils.survey_area s');
		expect(at(8)).not.toContain('soils.map_unit');
		expect(tiles.WASH_FROM).toBe(9);
		// z9: geom_z8, z10-11: geom_z10, with the survey bounds.
		for (const z of [9]) {
			expect(at(z)).toContain('from soils.map_unit m where m.geom_z8 &&');
			expect(at(z)).toContain('from soils.survey_area s');
		}
		for (const z of [10, 11]) {
			expect(at(z)).toContain('from soils.map_unit m where m.geom_z10 &&');
			expect(at(z)).toContain('from soils.survey_area s');
		}
		// z12-13: the 5 m polygons, no survey bounds.
		for (const z of [12, 13]) {
			expect(at(z)).toContain('from soils.polygon p join soils.map_unit m using (mukey) where p.geom_lo &&');
			expect(at(z)).not.toContain('survey_area');
			expect(at(z)).not.toContain('label_pt');
		}
		// z14: whole polygons and the labels' points.
		expect(at(14)).toContain('where p.geom &&');
		expect(at(14)).toContain('p.label_pt');
		expect(at(14)).toContain("'soil_labels'");
		for (const z of [7, 15, 22, 9.5]) expect(tiles.tileSql(z)).toBeNull();
	});

	it('carries only what the map draws, and names the MVT layers the client reads', () => {
		const sql = flat(tiles.tileSql(12));
		expect(sql).toContain("ST_AsMVT(t, 'soils', 4096, 'mvt_geom')");
		for (const c of ['m.mukey', 'm.musym as symbol', 'm.c_restr as restr', 'm.c_drain as drain', 'm.c_aws as aws', 'm.c_farm as farm', 'm.c_hsg as hsg']) expect(sql).toContain(c);
		// Not the survey area's name, the geometry's area or the names of every component.
		for (const c of ['muname', 'area_in_box', 'compname', 'areaname']) expect(sql).not.toContain(c);
		expect(flat(tiles.tileSql(14))).toContain("split_part(m.muname, ',', 1) as name"); // the labels' names only
		expect(flat(tiles.tileSql(10))).toContain("ST_AsMVT(t, 'survey'");
	});

	it('reads only the soils schema (the tile login can read nothing else)', () => {
		for (const z of [8, 9, 10, 12, 14]) {
			const tables = [...flat(tiles.tileSql(z)).matchAll(/(?:from|join) ([a-z_]+)\.([a-z_]+)/g)].map((m) => m[1]);
			expect(new Set(tables)).toEqual(new Set(['soils']));
		}
	});

	it('runs the cut with the tile as parameters and returns its bytes', async () => {
		const calls: unknown[][] = [];
		const sql = {
			unsafe: (text: string, params: unknown[]) => {
				calls.push([text, params]);
				return Promise.resolve([{ mvt: Buffer.from('tile') }]);
			}
		};
		const out = await units.cut!(sql as never, { z: 12, x: 710, y: 1493 }, new AbortController().signal);
		expect(out).toEqual(new Uint8Array(Buffer.from('tile')));
		expect(calls).toEqual([[tiles.tileSql(12), [12, 710, 1493]]]);
		// Outside the layer's zooms: empty, and nothing is asked of the database.
		const never = vi.fn();
		expect((await units.cut!({ unsafe: never } as never, { z: 7, x: 1, y: 1 }, new AbortController().signal)).length).toBe(0);
		expect(never).not.toHaveBeenCalled();
		// No rows: an empty tile.
		const empty = { unsafe: () => Promise.resolve([{ mvt: Buffer.alloc(0) }]) };
		expect((await units.cut!(empty as never, { z: 12, x: 1, y: 1 }, new AbortController().signal)).length).toBe(0);
		// Cancelled before it starts: no query, and a timeout (57014), as mvt.ts's cancelOnAbort.
		const stopped = new AbortController();
		stopped.abort();
		await expect(units.cut!({ unsafe: never } as never, { z: 12, x: 1, y: 1 }, stopped.signal)).rejects.toMatchObject({ code: '57014' });
		expect(never).not.toHaveBeenCalled();
	});
});
