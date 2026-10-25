import { beforeEach, describe, expect, it } from 'vitest';
import { BadRequest, type Sql } from './trees.server.js';
import { parseCentre, parseShrubLimit, shrubAreas, shrubsInBox, shrubSchema } from './shrubs.server.js';

/**
 * The shrubs API's queries and answers (docs/19 §19.8), from a fake database of made-up shrubs. Before the shrub tables
 * exist (an older database) nothing is built: empty lists, never a 500.
 */

let seen: { text: string; values: unknown[] }[];

function fakeSql(o: { shrubs?: boolean; rows?: Record<string, unknown>[] } = {}): Sql {
	return (async (strings: TemplateStringsArray, ...values: unknown[]) => {
		const text = strings.join('$').replace(/\s+/g, ' ').trim();
		seen.push({ text, values });
		if (text.includes('to_regclass')) return [{ shrubs: o.shrubs ?? true }];
		if (text.includes('from trees.shrub s')) return o.rows ?? [];
		if (text.includes('from trees.shrub_area'))
			return [{ area: 'c', shrubs: 412, built_at: new Date('2026-10-12T10:00:00Z'), w: -116.2101, s: 43.6262, e: -116.2072, n: 43.6291 }];
		throw new Error(`unexpected query: ${text}`);
	}) as unknown as Sql;
}

const row = (i: number, look = 'bush') => ({ id: `c-${i}`, look, lng: -116.2089 + i * 1e-6, lat: 43.6275, h: 1.234, w: 1.987 });

beforeEach(() => {
	seen = [];
});

describe('the shrubs API’s parameters', () => {
	it('reads the centre as two numbers in range', () => {
		expect(parseCentre('-116.209,43.6275')).toEqual([-116.209, 43.6275]);
		for (const bad of [null, '', '1', '1,2,3', 'a,b', '200,10', '10,95']) expect(() => parseCentre(bad)).toThrow(BadRequest);
	});
	it('reads the limit: 1,500 by default and at most', () => {
		expect(parseShrubLimit(null)).toBe(1500);
		expect(parseShrubLimit('')).toBe(1500);
		expect(parseShrubLimit('20')).toBe(20);
		expect(parseShrubLimit('9000')).toBe(1500);
		for (const bad of ['0', '-3', '1.5', 'x']) expect(() => parseShrubLimit(bad)).toThrow(BadRequest);
	});
});

describe('the shrubs in a box', () => {
	it('gives empty lists before the shrub tables exist, and runs no other query', async () => {
		const sql = fakeSql({ shrubs: false });
		expect(await shrubSchema(sql)).toBe(false);
		expect(await shrubsInBox(sql, [0, 0, 1, 1], [0.5, 0.5], 10)).toEqual({ shrubs: [], truncated: false });
		expect(await shrubAreas(sql)).toEqual({ areas: [] });
		expect(seen.every((s) => s.text.includes('to_regclass'))).toBe(true);
	});

	it('asks for the current build, republish "yes", within 300 m of the centre, nearest first', async () => {
		await shrubsInBox(fakeSql(), [-116.21, 43.62, -116.2, 43.63], [-116.209, 43.6275], 1500);
		const q = seen.find((s) => s.text.includes('from trees.shrub s'))!;
		expect(q.text).toContain('join trees.shrub_area a on a.area = s.area and a.build_id = s.build_id');
		expect(q.text).toContain("a.republish = 'yes'");
		expect(q.text).toMatch(/order by ST_Distance\(.*\), s\.shrub_id/);
		expect(q.values).toContain(300);
		expect(q.values).toContain(1501);
		expect(q.values).toContain(-116.209);
	});

	it('rounds, names the looks and says when it cut the list', async () => {
		const sql = fakeSql({ rows: [row(1), row(2, 'sage'), row(3)] });
		const all = await shrubsInBox(sql, [0, 0, 1, 1], [0.5, 0.5], 5);
		expect(all.truncated).toBe(false);
		expect(all.shrubs[0]).toEqual({ id: 'c-1', look: 'bush', lng: -116.208899, lat: 43.6275, h: 1.23, w: 1.99 });
		expect(all.shrubs.map((s) => s.look)).toEqual(['bush', 'sage', 'bush']);
		const cut = await shrubsInBox(sql, [0, 0, 1, 1], [0.5, 0.5], 2);
		expect(cut.truncated).toBe(true);
		expect(cut.shrubs.map((s) => s.id)).toEqual(['c-1', 'c-2']);
	});
});

describe('where shrubs are built', () => {
	it('gives each area’s outline, count and build time, republish "yes" only', async () => {
		const out = await shrubAreas(fakeSql());
		expect(out.areas).toEqual([{ area: 'c', bounds: [-116.2101, 43.6262, -116.2072, 43.6291], shrubs: 412, built_at: '2026-10-12T10:00:00.000Z' }]);
		expect(seen.find((s) => s.text.includes('from trees.shrub_area'))!.text).toContain("republish = 'yes'");
	});
});
