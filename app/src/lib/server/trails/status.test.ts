import { describe, expect, it } from 'vitest';
import { CREDIT, HIDDEN_NEAR_M, SEVERITY_ORDER, trailStatus, wayStates, type AgencyState, type Sql } from './status.js';

/**
 * The trail status API (/api/trails/status) from a fake database: made-up
 * trails, ids and dates (no real records). Before the plugin's migration it
 * answers empty, never a 500.
 */

interface Seen {
	text: string;
	values: unknown[];
}

function fakeSql(o: { ready?: boolean; rows?: Record<string, unknown>[]; hidden?: number[] } = {}, seen: Seen[] = []): Sql {
	return (async (strings: TemplateStringsArray, ...values: unknown[]) => {
		const text = strings.join('$').replace(/\s+/g, ' ').trim();
		seen.push({ text, values });
		if (text.includes('to_regclass')) return [{ ready: o.ready ?? true }];
		if (text.includes('from trails.agency_state')) return o.rows ?? [];
		if (text.includes('trails.hidden_informal')) return (o.hidden ?? []).map((osm_id) => ({ osm_id: String(osm_id) }));
		if (text.includes('from ops.fetch')) return [{ source: 'r2r_trails', at: new Date('2026-10-11T18:30:00Z') }];
		throw new Error(`unexpected query: ${text}`);
	}) as Sql;
}

const row = (o: Record<string, unknown>) => ({
	source: 'r2r_trails',
	source_id: 'test-1',
	kind: 'trail',
	name: 'Example Ridge',
	system: 'Ridge to Rivers',
	state: 'dry',
	severity: 'open',
	label: 'Dry / Tacky - Enjoy',
	set_at: new Date('2026-09-11T14:00:00Z'),
	since: new Date('2026-10-07T12:00:00Z'),
	ways: ['9500000001', '9500000002'],
	partial: [],
	line_id: '7',
	links: 2,
	line_m: 600,
	covered_m: 597.4,
	gap_m: 0,
	along_m: 0,
	...o
});

describe('trailStatus', () => {
	it('answers empty before the migration', async () => {
		const seen: Seen[] = [];
		const got = await trailStatus(fakeSql({ ready: false }, seen));
		expect(got).toEqual({ agencies: [], ways: {}, hidden: [], counts: {}, polled: {}, credit: CREDIT, license: expect.any(String), republish: 'aggregates' });
		expect(seen).toHaveLength(1);
	});

	it('puts each line on its ways, worst state first', async () => {
		const seen: Seen[] = [];
		const got = await trailStatus(
			fakeSql(
				{
					rows: [
						row({}),
						row({ source_id: 'test-2', name: 'Sample Gulch', state: 'closed', severity: 'closed', label: 'CLOSED', ways: ['9500000002'], line_id: '8', links: 1 }),
						row({ source_id: 'test-3', name: 'Lonely Trail', state: 'not_evaluated', severity: null, ways: [], line_id: '9', links: 0, covered_m: null, gap_m: 600 }),
						row({
							source: 'boise_greenbelt_closures',
							source_id: 'construction:1',
							kind: 'closure',
							name: 'Example repair',
							system: null,
							state: 'closure',
							severity: 'closed',
							label: 'Example repair',
							set_at: null,
							ways: [],
							partial: ['9500000005'],
							line_id: '10',
							links: 1,
							line_m: 120,
							covered_m: 119.6,
							gap_m: 0,
							along_m: 121.4
						})
					],
					hidden: [9500000009]
				},
				seen
			)
		);
		expect(got.ways).toEqual({ '9500000001': 'open', '9500000002': 'closed' });
		expect(got.hidden).toEqual([9500000009]);
		expect(got.counts).toEqual({ dry: 1, closed: 1, not_evaluated: 1 });
		expect(got.polled).toEqual({ r2r_trails: '2026-10-11T18:30:00.000Z', boise_greenbelt_closures: null });
		const ridge = got.agencies[0];
		expect(ridge).toMatchObject({ id: 'test-1', ways: [9500000001, 9500000002], line_id: 7, drawn: false, covered: 0.996, set_at: '2026-09-11T14:00:00.000Z' });
		expect(got.agencies[2]).toMatchObject({ drawn: true, gap_m: 600, along_m: 0, covered: null, severity: null });
		// A closure on part of a longer way: it paints no way, and draws itself on the way's stretch along it.
		expect(got.agencies[3]).toMatchObject({ kind: 'closure', partial: [9500000005], ways: [], drawn: true, gap_m: 0, along_m: 121, covered: 0.997 });
		expect(seen.find((s) => s.text.includes('hidden_informal'))?.values).toEqual([HIDDEN_NEAR_M]);
		expect(got.republish).toBe('aggregates');
	});
});

describe('wayStates', () => {
	const a = (severity: AgencyState['severity'], ways: number[], source = 'r2r_trails'): AgencyState => ({
		source,
		id: 'x',
		kind: 'trail',
		name: null,
		system: null,
		state: 'x',
		severity,
		label: null,
		set_at: null,
		since: null,
		ways,
		partial: [],
		line_id: null,
		drawn: false,
		gap_m: 0,
		along_m: 0,
		covered: null
	});

	it('ranks the states', () => {
		expect(SEVERITY_ORDER).toEqual(['closed', 'do_not_use', 'caution', 'detour', 'open', 'not_evaluated']);
		expect(wayStates([a('open', [1]), a('caution', [1]), a(null, [1, 2]), a('detour', [2], 'boise_greenbelt_closures')])).toEqual({ '1': 'caution', '2': 'detour' });
	});

	it('an ended closure paints nothing; an unevaluated trail reads as such', () => {
		expect(wayStates([a(null, [3], 'boise_greenbelt_closures'), a(null, [4])])).toEqual({ '4': 'not_evaluated' });
	});
});
