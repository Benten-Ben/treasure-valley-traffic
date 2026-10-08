import { beforeEach, describe, expect, it } from 'vitest';
import { BadRequest, LIMIT_DEFAULT, LIMIT_MAX, parseBbox, parseLimit, schema, treeAreas, treeDetail, treesInBox, type Sql } from './trees.server.js';

/**
 * The trees API's queries and answers (docs/19 §19.6), from a fake database:
 * made-up trees and a FAKE catalogue row (invented species and sizes; no
 * real records). Before the plugin's migration nothing is built (empty
 * lists, no 500); without the private catalogue table, `catalogue` is null.
 */

interface Seen {
	text: string;
	values: unknown[];
}

let seen: Seen[];

/** A fake postgres.js: answers by the query's text; records each query with its values. */
function fakeSql(o: { trees?: boolean; catalogue?: boolean; rows?: Record<string, unknown>[]; catRow?: Record<string, unknown> | null } = {}): Sql {
	return (async (strings: TemplateStringsArray, ...values: unknown[]) => {
		const text = strings.join('$').replace(/\s+/g, ' ').trim();
		seen.push({ text, values });
		if (text.includes('to_regclass')) return [{ trees: o.trees ?? true, catalogue: o.catalogue ?? false }];
		if (text.includes('ST_MakeEnvelope')) return o.rows ?? [];
		if (text.includes('ST_Extent'))
			return [{ area: 'c', trees: 191, w: -116.2098617, s: 43.6268641, e: -116.2079695, n: 43.6282312, built_at: new Date('2026-10-08T15:32:40Z') }];
		if (text.includes('from trees.tree where tree_id'))
			return [
				{
					tree_id: 'boise-fake-1',
					area: 'c',
					kind: 'catalogued',
					type: 'broadleaf',
					height_m: 26.83,
					crown_radius_m: 9.45,
					ground_m: 823.2,
					lidar: 'USGS 3DEP QL1 lidar (flown 2023)',
					fit: { trunk_to_crown_m: 2.44 },
					build_id: 'test-build',
					catalogue: 'boise',
					catalogue_id: 'fake-1'
				}
			];
		if (text.includes('from trees.tree_log'))
			return [
				{ at: new Date('2026-10-08T15:32:14Z'), event: 'matched', detail: {} },
				{ at: new Date('2023-10-24T12:00:00Z'), event: 'measured', detail: { height_m: 26.83, crown_width_m: 18.9 } }
			];
		if (text.includes('from city_trees.tree'))
			return o.catRow === null
				? []
				: [
						o.catRow ?? {
							catalogue_id: 'fake-1',
							common_name: 'Test linden (synthetic)',
							genus: 'Exemplia',
							species: 'fictus',
							dbh_in: 14,
							installed: '2009-04-15',
							last_verified: '2024-06-01',
							condition: 'Good',
							site_type: 'Street'
						}
					];
		throw new Error(`unexpected query: ${text}`);
	}) as unknown as Sql;
}

beforeEach(() => {
	seen = [];
});

describe('parsing the request', () => {
	it('takes bbox=w,s,e,n in degrees, west of east and south of north', () => {
		expect(parseBbox('-116.21,43.62,-116.2,43.63')).toEqual([-116.21, 43.62, -116.2, 43.63]);
		for (const bad of [null, '', '1,2,3', '1,2,3,x', '-116.2,43.62,-116.21,43.63', '-116.21,43.63,-116.2,43.62', '-190,0,0,1', '-118,43,-116,44', '1,,3,4'])
			expect(() => parseBbox(bad), String(bad)).toThrow(BadRequest);
	});

	it('takes limit as a whole number, 4,000 by default and at most 8,000', () => {
		expect(parseLimit(null)).toBe(LIMIT_DEFAULT);
		expect(LIMIT_DEFAULT).toBe(4000);
		expect(parseLimit('250')).toBe(250);
		expect(parseLimit('100000')).toBe(LIMIT_MAX);
		expect(LIMIT_MAX).toBe(8000);
		for (const bad of ['0', '-3', '2.5', 'many']) expect(() => parseLimit(bad), bad).toThrow(BadRequest);
	});
});

describe('GET /api/trees?bbox=…', () => {
	const rows = [
		{ id: 'c-1', kind: 'placed', type: 'narrow', lng: -116.20912341234, lat: 43.62712345678, h: 24.8312, r: 4.9612, a: 0.95213, n: 2.0891 },
		{ id: 'c-2', kind: 'estimated', type: 'broadleaf', lng: -116.208, lat: 43.627, h: 5.06, r: 2.69, a: null, n: null },
		{ id: 'c-3', kind: 'catalogued', type: 'broadleaf', lng: -116.207, lat: 43.628, h: 3.1, r: 1.5, a: 0.45, n: 1.64 }
	];

	it('asks PostGIS for the points in the box, tallest first, one more than the limit', async () => {
		await treesInBox(fakeSql({ rows }), [-116.21, 43.62, -116.2, 43.63], 2);
		const q = seen.find((s) => s.text.includes('ST_MakeEnvelope'))!;
		expect(q.text).toContain('from trees.tree');
		expect(q.text).toContain('geom && ST_MakeEnvelope($, $, $, $, 4326)');
		expect(q.text).toContain('order by height_m desc, tree_id');
		expect(q.values).toEqual([-116.21, 43.62, -116.2, 43.63, 3]);
	});

	it('answers { trees: [{ id, kind, type, lng, lat, h, r, a, n }], truncated }, cut to the limit', async () => {
		const out = await treesInBox(fakeSql({ rows }), [-116.21, 43.62, -116.2, 43.63], 2);
		expect(out.truncated).toBe(true);
		expect(out.trees).toEqual([
			{ id: 'c-1', kind: 'placed', type: 'narrow', lng: -116.2091234, lat: 43.6271235, h: 24.83, r: 4.96, a: 0.952, n: 2.089 },
			{ id: 'c-2', kind: 'estimated', type: 'broadleaf', lng: -116.208, lat: 43.627, h: 5.06, r: 2.69, a: null, n: null }
		]);
		const all = await treesInBox(fakeSql({ rows }), [-116.21, 43.62, -116.2, 43.63], 3);
		expect(all.truncated).toBe(false);
		expect(all.trees).toHaveLength(3);
	});

	it('answers as if nothing is built before the trees migration (no 500)', async () => {
		expect(await treesInBox(fakeSql({ trees: false }), [-116.21, 43.62, -116.2, 43.63], 10)).toEqual({ trees: [], truncated: false });
		expect(seen.map((s) => s.text).some((t) => t.includes('ST_MakeEnvelope'))).toBe(false);
	});
});

describe('GET /api/trees/areas', () => {
	it('lists each area with its box, count and build time', async () => {
		expect(await treeAreas(fakeSql())).toEqual({
			areas: [{ area: 'c', bounds: [-116.2098617, 43.6268641, -116.2079695, 43.6282312], trees: 191, built_at: '2026-10-08T15:32:40.000Z' }]
		});
		const q = seen.find((s) => s.text.includes('ST_Extent'))!;
		expect(q.text).toContain('group by area');
		expect(q.text).toContain('from trees.build');
	});

	it('is empty before the trees migration', async () => {
		expect(await treeAreas(fakeSql({ trees: false }))).toEqual({ areas: [] });
	});
});

describe('GET /api/trees/<id>', () => {
	it('checks for the private catalogue with to_regclass first', async () => {
		expect(await schema(fakeSql({ catalogue: true }))).toEqual({ trees: true, catalogue: true });
		expect(seen[0].text).toContain("to_regclass('city_trees.tree')");
		expect(seen[0].text).toContain("to_regclass('trees.tree')");
	});

	it('gives the tree, its catalogue entry (when the private table is here) and its log, newest first', async () => {
		const d = await treeDetail(fakeSql({ catalogue: true }), 'boise-fake-1');
		expect(d).toMatchObject({
			id: 'boise-fake-1',
			area: 'c',
			kind: 'catalogued',
			type: 'broadleaf',
			height_m: 26.83,
			crown_radius_m: 9.45,
			ground_m: 823.2,
			fit: { trunk_to_crown_m: 2.44 },
			build_id: 'test-build',
			catalogue: {
				catalogue: 'boise',
				catalogue_id: 'fake-1',
				common_name: 'Test linden (synthetic)',
				genus: 'Exemplia',
				species: 'fictus',
				dbh_in: 14,
				installed: '2009-04-15',
				last_verified: '2024-06-01',
				condition: 'Good',
				site_type: 'Street'
			}
		});
		expect(d!.log).toEqual([
			{ at: '2026-10-08T15:32:14.000Z', event: 'matched', detail: {} },
			{ at: '2023-10-24T12:00:00.000Z', event: 'measured', detail: { height_m: 26.83, crown_width_m: 18.9 } }
		]);
		const log = seen.find((s) => s.text.includes('from trees.tree_log'))!;
		expect(log.text).toContain('order by at desc');
		expect(log.values).toEqual(['boise-fake-1']);
		const cat = seen.find((s) => s.text.includes('from city_trees.tree'))!;
		expect(cat.values).toEqual(['fake-1']);
		// Dates as plain dates, so they never move a day by time zone.
		expect(cat.text).toContain('installed::text');
	});

	it('gives catalogue: null when the private table is missing, without asking it', async () => {
		const d = await treeDetail(fakeSql({ catalogue: false }), 'boise-fake-1');
		expect(d?.catalogue).toBeNull();
		expect(d?.log).toHaveLength(2);
		expect(seen.some((s) => s.text.includes('city_trees.tree where'))).toBe(false);
	});

	it('gives catalogue: null when the catalogue has no such row', async () => {
		expect((await treeDetail(fakeSql({ catalogue: true, catRow: null }), 'boise-fake-1'))?.catalogue).toBeNull();
	});

	it('is null (a 404) before the trees migration', async () => {
		expect(await treeDetail(fakeSql({ trees: false }), 'boise-fake-1')).toBeNull();
		expect(seen).toHaveLength(1);
	});
});
