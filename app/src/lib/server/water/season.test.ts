import { describe, expect, it } from 'vitest';
import type { Sql } from './common.js';
import { canalFromRow, emptySeason, season } from './season.js';

/**
 * The canal season API from a fake database: made-up canals, reach ids and a made-up gauge. Before water 0002
 * (or core's evt.event) the answer is an empty season, never an error; a canal with no current lifecycle reads
 * unknown; IDWR's legal window makes the answer internal.
 */

interface Seen {
	text: string;
	values: unknown[];
}

function fakeSql(o: { ready?: boolean; lifecycles?: unknown[]; reaches?: unknown[]; status?: string | null; noView?: boolean } = {}, seen: Seen[] = []): Sql {
	return (async (strings: TemplateStringsArray, ...values: unknown[]) => {
		const text = strings.join('$').replace(/\s+/g, ' ').trim();
		seen.push({ text, values });
		if (text.includes('to_regclass')) return [{ ok: o.ready ?? true, has_status: !o.noView }];
		if (text.includes('from ops.source_status')) return o.status ? [{ state: o.status }] : [];
		if (text.includes('from evt.event')) return o.lifecycles ?? [];
		if (text.includes('from water.reach')) return o.reaches ?? [];
		return [];
	}) as Sql;
}

const at = (iso: string) => new Date(iso);

/** A lifecycle row as evt.event gives it (attributes as the plugin writes them). */
const row = (canal_id: number, severity: string, attributes: Record<string, unknown>, o: { since?: string; until?: string | null; updated?: string } = {}) => ({
	severity,
	attributes: { canal_id, canal: `Example Canal ${canal_id}`, canal_kind: 'canal', state: severity, credit: ['© OpenStreetMap contributors', 'USGS National Hydrography Dataset'], republish: 'yes', ...attributes },
	since: at(o.since ?? '2030-03-01T00:00:00Z'),
	until: o.until === null || o.until === undefined ? null : at(o.until),
	updated_at: at(o.updated ?? '2030-03-01T00:00:00Z')
});

describe('before the plugin’s migration', () => {
	it('answers an empty season, and asks nothing of the lifecycles or the reaches', async () => {
		const seen: Seen[] = [];
		const s = await season(fakeSql({ ready: false }, seen));
		expect(s).toEqual(emptySeason());
		expect(seen.every((q) => q.text.includes('to_regclass'))).toBe(true);
	});

	it('answers an empty season with the tables and no rows', async () => {
		const s = await season(fakeSql());
		expect(s.canals).toEqual([]);
		expect(s.reaches).toEqual({ on: [], off: [], unknown: [] });
		expect(s.updated).toBeNull();
		expect(s.republish).toBe('yes');
	});
});

describe('the season', () => {
	const gauge = { basis: 'gauge', gauge: 'XTEST1', gauge_name: 'Example Canal Diversion', why: 'no flow since the shut-off', credit: ['NOAA National Weather Service (NWPS), gauge XTEST1', '© OpenStreetMap contributors'] };
	const legal = { basis: 'legal', season: '3/1 - 11/15', objectid: 7, why: 'IDWR legal season', credit: ["Idaho Department of Water Resources (IDWR), season of use", '© OpenStreetMap contributors'], republish: 'internal' };
	const always = { basis: 'always', why: 'a drain; drains and creeks never switch off' };

	it('sorts each canal’s reaches by its current state, and says what it rests on', async () => {
		const s = await season(
			fakeSql({
				lifecycles: [row(1, 'off', gauge, { updated: '2030-09-28T07:45:00Z' }), row(2, 'on', legal), row(3, 'on', always)],
				reaches: [
					{ id: '101', canal_id: '1' },
					{ id: '102', canal_id: '1' },
					{ id: '201', canal_id: '2' },
					{ id: '301', canal_id: '3' }
				]
			})
		);
		expect(s.reaches).toEqual({ on: [201, 301], off: [101, 102], unknown: [] });
		expect(s.canals.map((c) => [c.id, c.state, c.basis])).toEqual([[1, 'off', 'gauge'], [2, 'on', 'legal'], [3, 'on', 'always']]);
		expect(s.canals[0]).toMatchObject({ gauge: 'XTEST1', gauge_name: 'Example Canal Diversion', republish: 'yes', until: null });
		expect(s.canals[1]).toMatchObject({ season: '3/1 - 11/15', republish: 'internal' });
		expect(s.updated).toBe('2030-09-28T07:45:00.000Z');
	});

	it('makes the whole answer internal while any canal rests on IDWR’s legal window', async () => {
		const only = await season(fakeSql({ lifecycles: [row(1, 'off', gauge)], reaches: [{ id: 5, canal_id: 1 }] }));
		expect(only.republish).toBe('yes');
		const mixed = await season(fakeSql({ lifecycles: [row(1, 'off', gauge), row(2, 'on', legal)], reaches: [{ id: 5, canal_id: 1 }, { id: 6, canal_id: 2 }] }));
		expect(mixed.republish).toBe('internal');
		expect(mixed.license).toContain('IDWR');
	});

	it('reads the 48-hour silence as unknown, on the reaches and on the card', async () => {
		const s = await season(fakeSql({ lifecycles: [row(1, 'unknown', gauge)], reaches: [{ id: 101, canal_id: 1 }] }));
		expect(s.reaches).toEqual({ on: [], off: [], unknown: [101] });
		expect(s.canals[0]).toMatchObject({ state: 'unknown', basis: 'gauge', gauge: 'XTEST1' });
	});

	describe('when the hourly season job is behind', () => {
		const open = { until: null };
		const lifecycles = () => [row(1, 'off', gauge), row(2, 'on', gauge), row(3, 'on', legal), row(4, 'on', always), row(5, 'unknown', gauge)];
		const reaches = [1, 2, 3, 4, 5].map((c) => ({ id: 100 + c, canal_id: c }));

		for (const status of ['late', 'stale']) {
			it(`serves an open gauge span as unknown, saying why, when the source is ${status}`, async () => {
				const s = await season(fakeSql({ lifecycles: lifecycles(), reaches, status }));
				expect(s.canals.map((c) => [c.id, c.state, c.behind ?? false])).toEqual([[1, 'unknown', true], [2, 'unknown', true], [3, 'on', false], [4, 'on', false], [5, 'unknown', false]]);
				expect(s.canals[0].why).toContain('season job is behind');
				// The reaches are sorted by the state served, so the map draws the thin line, not the hollow one.
				expect(s.reaches).toEqual({ on: [103, 104], off: [], unknown: [101, 102, 105] });
				expect(s.canals[0]).toMatchObject({ basis: 'gauge', gauge: 'XTEST1', ...open });
			});
		}

		it('serves the readings as they are when the source is fresh, never ran (run by hand), or has no view yet', async () => {
			for (const o of [{ status: 'fresh' }, { status: 'never' }, { status: null }, { noView: true, status: 'stale' }]) {
				const s = await season(fakeSql({ lifecycles: lifecycles(), reaches, ...o }));
				expect(s.canals.map((c) => c.state), JSON.stringify(o)).toEqual(['off', 'on', 'on', 'on', 'unknown']);
				expect(s.canals.some((c) => c.behind)).toBe(false);
			}
		});

		it('keys on the run, not on the span’s age: a months-old off span stays off while the run is fresh', async () => {
			const s = await season(fakeSql({ lifecycles: [row(1, 'off', gauge, { since: '2030-01-01T00:00:00Z' })], reaches: [{ id: 1, canal_id: 1 }], status: 'fresh' }));
			expect(s.canals[0]).toMatchObject({ state: 'off', since: '2030-01-01T00:00:00.000Z' });
		});

		it('leaves a gauge span that has an end alone (a closed span carries its own end)', () => {
			const c = canalFromRow(row(1, 'off', gauge, { until: '2030-04-01T00:00:00Z' }), () => 0, true)!;
			expect(c).toMatchObject({ state: 'off' });
			expect(c.behind).toBeUndefined();
		});

		it('asks for the source’s status without any input of the caller’s', async () => {
			const seen: Seen[] = [];
			await season(fakeSql({ status: 'fresh' }, seen));
			const q = seen.find((x) => x.text.includes('from ops.source_status'))!;
			expect(q.text).toContain("source = 'canal_season'");
			expect(seen.every((x) => x.values.length === 0)).toBe(true);
		});
	});

	it('reads a canal with no current lifecycle as unknown, with nothing to say beyond that', async () => {
		const s = await season(fakeSql({ lifecycles: [], reaches: [{ id: 101, canal_id: 9 }, { id: 102, canal_id: 9 }] }));
		expect(s.reaches.unknown).toEqual([101, 102]);
		expect(s.canals).toEqual([expect.objectContaining({ id: 9, name: null, state: 'unknown', basis: 'none', credit: [] })]);
	});

	it('keeps a canal’s newest span when two are current, and draws a reach in one list only', async () => {
		const s = await season(fakeSql({ lifecycles: [row(1, 'on', gauge, { since: '2030-06-01T00:00:00Z' }), row(1, 'off', gauge, { since: '2030-01-01T00:00:00Z' })], reaches: [{ id: 1, canal_id: 1 }] }));
		expect(s.canals).toHaveLength(1);
		expect(s.canals[0].state).toBe('on');
		expect(s.reaches).toEqual({ on: [1], off: [], unknown: [] });
	});

	it('shares each credit once, by index', async () => {
		const s = await season(fakeSql({ lifecycles: [row(1, 'off', gauge), row(2, 'on', legal)], reaches: [] }));
		expect(new Set(s.credits).size).toBe(s.credits.length);
		for (const c of s.canals) for (const i of c.credit) expect(s.credits[i]).toBeTruthy();
		expect(s.credits).toContain('© OpenStreetMap contributors');
		expect(s.canals[0].credit.map((i) => s.credits[i])).toEqual(gauge.credit);
	});

	it('asks for the current span of active lifecycles only, with no input of the caller’s in the query', async () => {
		const seen: Seen[] = [];
		await season(fakeSql({}, seen));
		const q = seen.find((s) => s.text.includes('from evt.event'))!;
		expect(q.text).toContain("source = 'canal_season'");
		expect(q.text).toContain('and active');
		expect(q.text).toContain('declared @> now()');
		expect(seen.every((s) => s.values.length === 0)).toBe(true);
	});
});

describe('one lifecycle row', () => {
	const credit = () => 0;
	it('reads a state or a basis it does not know as unknown, never on', () => {
		expect(canalFromRow(row(1, 'maybe', { basis: 'gauge' }), credit)?.state).toBe('unknown');
		expect(canalFromRow(row(1, 'on', { basis: 'telepathy' }), credit)).toMatchObject({ state: 'unknown', basis: 'none' });
		expect(canalFromRow(row(1, 'on', {}), credit)).toMatchObject({ state: 'unknown', basis: 'none' });
	});

	it('refuses a row with no canal id, and reads an unknown republish class as internal', () => {
		expect(canalFromRow({ severity: 'on', attributes: {}, since: null, until: null }, credit)).toBeNull();
		expect(canalFromRow({ severity: 'on', attributes: { canal_id: 1.5 } }, credit)).toBeNull();
		expect(canalFromRow(row(1, 'on', { basis: 'gauge', republish: 'whatever' }), credit)?.republish).toBe('internal');
	});

	it('keeps text short and drops non-text credits', () => {
		const c = canalFromRow(row(1, 'on', { basis: 'always', why: 'x'.repeat(5000), credit: ['ok', 3, '', null] }), credit)!;
		expect(c.why!.length).toBe(300);
		expect(c.credit).toEqual([0]);
	});
});
