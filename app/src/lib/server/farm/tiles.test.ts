import { describe, expect, it, vi } from 'vitest';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { BUFFER, buildRegistry, EXTENT, tileLayerProblems, tileQuery, versionKey } = await import('../mvt.js');
const tiles = (await import('./tiles.js')).default;
const { FIELDS_FROM, YEAR_SQL, YEARS, yearLayer } = await import('./tiles.js');

const flat = (s: string | null) => s?.replace(/\s+/g, ' ');

describe('the crop fields tile definitions', () => {
	it('are valid, in the farm folder, and registered together', () => {
		for (const d of tiles) expect(tileLayerProblems(d), d.layer).toEqual([]);
		const log = vi.fn();
		const r = buildRegistry({ './farm/tiles.ts': { default: tiles } }, log);
		expect(log).not.toHaveBeenCalled();
		expect([...r.keys()]).toEqual(['farm.crop_fields', ...YEARS.map((y) => `farm.crop_year_${y}`)]);
	});

	it('read the views by zoom: three dissolves, then a feature per field', () => {
		const fields = tiles[0];
		for (const z of [8, 9, 10]) {
			const sql = flat(tileQuery(fields, z))!;
			expect(sql).toContain(`from "farm"."crop_fields_lo${z}" s`);
			expect(sql).toContain('s."g", s."s", ST_AsMVTGeom(s."geom", ST_TileEnvelope');
			expect(sql).not.toContain('ST_Transform'); // the dissolves are in web mercator already
		}
		for (const z of [FIELDS_FROM, 12, 14]) {
			const sql = flat(tileQuery(fields, z))!;
			expect(sql).toContain('from "farm"."crop_fields" s');
			expect(sql).toContain(`ST_AsMVT(t, 'fields', 4096, 'mvt_geom', 'id')`);
			for (const c of ['a', 'g', 'n', 'y', 's', 'st', 'p']) expect(sql).toContain(`s."${c}"`);
		}
		expect(tileQuery(fields, 7)).toBeNull();
		expect(fields.maxzoom).toBe(14);
	});

	it("give one cut-over-field_lo layer to each earlier year, taking the fields' version", () => {
		const earlier = tiles.slice(1);
		expect(earlier.map((d) => d.layer)).toEqual(YEARS.map(yearLayer));
		for (const d of earlier) {
			expect([d.minzoom, d.maxzoom]).toEqual([8, 10]);
			expect(versionKey(d)).toBe('farm.crop_fields');
			expect(d.cut).toBeTypeOf('function');
		}
		// The newest year is the fields layer's own: no cut for it.
		expect(YEARS).not.toContain(2025);
		const sql = flat(YEAR_SQL);
		expect(sql).toContain('from farm.field_lo s where s.z = $1::int and s.yr = $4::int');
		expect(sql).toContain('margin => 0.015625');
		// (written out in tiles.ts, which mvt.ts loads: these are mvt.ts's own)
		expect(sql).toContain(`${EXTENT}, ${BUFFER}, true`);
		expect(BUFFER / EXTENT).toBe(0.015625);
	});

	it("run a year's cut with the tile and the year as parameters, and return its bytes", async () => {
		const calls: unknown[][] = [];
		const sql = {
			unsafe: (text: string, params: unknown[]) => {
				calls.push([text, params]);
				return Promise.resolve([{ mvt: Buffer.from('tile') }]);
			}
		};
		const d = tiles.find((x) => x.layer === 'crop_year_2020')!;
		const out = await d.cut!(sql as never, { z: 10, x: 177, y: 369 }, new AbortController().signal);
		expect(out).toEqual(new Uint8Array(Buffer.from('tile')));
		expect(calls).toEqual([[YEAR_SQL, [10, 177, 369, 2020]]]);
		// No rows: an empty tile.
		// Cancelled before it starts: no query, and a timeout (57014), as mvt.ts's cancelOnAbort.
		const stopped = new AbortController();
		stopped.abort();
		const never = vi.fn();
		await expect(d.cut!({ unsafe: never } as never, { z: 9, x: 1, y: 1 }, stopped.signal)).rejects.toMatchObject({ code: '57014' });
		expect(never).not.toHaveBeenCalled();
		const empty = { unsafe: () => Promise.resolve([{ mvt: Buffer.alloc(0) }]) };
		expect((await d.cut!(empty as never, { z: 9, x: 1, y: 1 }, new AbortController().signal)).length).toBe(0);
	});
});
