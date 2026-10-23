import { describe, expect, it } from 'vitest';
import { lineCard, wayCard } from './card.js';
import type { Sql } from './status.js';

/**
 * The trail card's data (card.ts) from a fake database: made-up ways, lines and dates (no real
 * records). Before the plugin's migration both answer null, never a 500.
 */

interface Seen {
	text: string;
	values: unknown[];
}

function fakeSql(o: { ready?: boolean; way?: Record<string, unknown> | null; lines?: Record<string, unknown>[]; line?: Record<string, unknown> | null } = {}, seen: Seen[] = []): Sql {
	return (async (strings: TemplateStringsArray, ...values: unknown[]) => {
		const text = strings.join('$').replace(/\s+/g, ' ').trim();
		seen.push({ text, values });
		if (text.includes('to_regclass')) return [{ ready: o.ready ?? true }];
		if (text.includes('from trails.path p')) return o.way === null ? [] : [o.way ?? WAY];
		if (text.includes('from trails.link k')) return o.lines ?? [];
		if (text.includes('from trails.agency_state where line_id')) return o.line === null ? [] : [o.line ?? LINE];
		throw new Error(`unexpected query: ${text}`);
	}) as Sql;
}

const WAY = {
	osm_id: '9500000001',
	kind: 'path',
	name: 'Example Ridge Trail',
	ref: null,
	surface: 'dirt',
	surface_from: 'default',
	surface_default: 'Ridge to Rivers trail',
	surface_tag: null,
	width_m: 0.8,
	width_from: 'estimated',
	informal: false,
	greenbelt: false,
	bridge: false,
	length_m: 412.4
};
const LINE = {
	line_id: '7',
	source: 'r2r_trails',
	kind: 'trail',
	name: 'Example Ridge',
	system: 'Ridge to Rivers',
	state: 'muddy',
	severity: 'do_not_use',
	label: 'Muddy - Stay Off',
	set_at: new Date('2026-10-11T14:00:00Z'),
	since: new Date('2026-10-11T14:30:00Z'),
	line_m: 600.2,
	gap_m: 12.4,
	along_m: 30.1,
	ways: 3
};

describe('wayCard', () => {
	it('answers null before the migration, asking once', async () => {
		const seen: Seen[] = [];
		expect(await wayCard(fakeSql({ ready: false }, seen), 9500000001)).toBeNull();
		expect(seen).toHaveLength(1);
		expect(await lineCard(fakeSql({ ready: false }), 7)).toBeNull();
	});

	it('asks nothing for an id that is not a way id', async () => {
		const seen: Seen[] = [];
		for (const id of [0, -3, 1.5, NaN, Number.MAX_SAFE_INTEGER + 2]) expect(await wayCard(fakeSql({}, seen), id)).toBeNull();
		expect(seen).toEqual([]);
	});

	it('reads only drawn ways: a private way or a canal bank has no card', async () => {
		const seen: Seen[] = [];
		expect(await wayCard(fakeSql({ way: null }, seen), 5)).toBeNull();
		const q = seen.find((s) => s.text.includes('from trails.path p'))!;
		expect(q.text).toContain('p.drawn');
		expect(q.values).toEqual([5]);
		// The card reads the default surface from the City's links, which the tile login may not; it is the app's own login here.
		expect(q.text).toContain('left join trails.way_agency a on a.osm_id = p.osm_id');
	});

	it('gives the way’s kind, name, surface with R2R’s default, width, and the lines on it', async () => {
		const got = await wayCard(
			fakeSql({
				lines: [
					{ ...LINE, paints: true },
					{ source: 'boise_greenbelt_closures', kind: 'closure', name: 'Greenbelt closure', system: null, state: 'closure', severity: 'closed', label: null, set_at: null, since: new Date('2026-10-01T00:00:00Z'), line_id: '9', paints: false }
				]
			}),
			9500000001
		);
		expect(got).toMatchObject({
			id: 9500000001,
			kind: 'path',
			name: 'Example Ridge Trail',
			surface: 'dirt',
			surface_from: 'default',
			surface_default: 'Ridge to Rivers trail',
			width_m: 0.8,
			width_from: 'estimated',
			informal: false,
			length_m: 412
		});
		expect(got!.lines).toHaveLength(2);
		expect(got!.lines[0]).toMatchObject({ source: 'r2r_trails', state: 'muddy', severity: 'do_not_use', label: 'Muddy - Stay Off', line_id: 7, paints: true, set_at: '2026-10-11T14:00:00.000Z' });
		expect(got!.lines[1]).toMatchObject({ kind: 'closure', paints: false, set_at: null, line_id: 9 });
	});
});

describe('lineCard', () => {
	it('gives an agency line’s state, who set it and how much of it draws itself', async () => {
		const got = await lineCard(fakeSql({}), 7);
		expect(got).toEqual({
			line_id: 7,
			source: 'r2r_trails',
			kind: 'trail',
			name: 'Example Ridge',
			system: 'Ridge to Rivers',
			state: 'muddy',
			severity: 'do_not_use',
			label: 'Muddy - Stay Off',
			set_at: '2026-10-11T14:00:00.000Z',
			since: '2026-10-11T14:30:00.000Z',
			line_m: 600,
			drawn_m: 43,
			ways: 3
		});
		expect(await lineCard(fakeSql({ line: null }), 8)).toBeNull();
		expect(await lineCard(fakeSql({}), 0)).toBeNull();
	});
});
