import { describe, expect, it } from 'vitest';
import { BadRequest, isBadRequest, parseId, parseLid, schema, type Sql } from './common.js';
import { gaugeDetail, gaugeSummary, latestReading, namesUsgs, waterPoints } from './gauges.js';
import { bodyDetail, reachDetail, structureDetail } from './network.js';
import { hazardText, notices } from './notices.js';

/**
 * The water APIs from a fake database: made-up ids and rows, no real records. Before the plugin's migration
 * every answer is empty (or null, which the route turns into a 404), never a 500; bad ids are a 400.
 */

interface Seen {
	text: string;
	values: unknown[];
}

function fakeSql(answers: { ready?: boolean; rows?: (text: string) => unknown[] | undefined } = {}, seen: Seen[] = []): Sql {
	return (async (strings: TemplateStringsArray, ...values: unknown[]) => {
		const text = strings.join('$').replace(/\s+/g, ' ').trim();
		seen.push({ text, values });
		if (text.includes('to_regclass')) {
			const ready = answers.ready ?? true;
			return [{ network: ready, evidence: ready, orgs: ready }];
		}
		return answers.rows?.(text) ?? [];
	}) as Sql;
}

describe('ids', () => {
	it('reads whole numbers up to 2^53 and refuses everything else', () => {
		expect(parseId('7001')).toBe(7001);
		expect(parseId('2251799813686239')).toBe(2251799813686239);
		for (const bad of [undefined, '', 'abc', '-1', '1.5', '1e3', '12345678901234567', '9007199254740993', ' 1', '1; drop table water.reach']) expect(() => parseId(bad), String(bad)).toThrow(BadRequest);
		expect(isBadRequest(new BadRequest('x'))).toBe(true);
		expect(isBadRequest(new Error('x'))).toBe(false);
	});

	it('reads a gauge id as upper-case letters and digits', () => {
		expect(parseLid('bsei1')).toBe('BSEI1');
		for (const bad of [undefined, '', 'a', 'BSEI1%', "BSEI1'", 'A'.repeat(11), 'BS EI']) expect(() => parseLid(bad), String(bad)).toThrow(BadRequest);
	});
});

describe('before the plugin’s migration', () => {
	const none = () => fakeSql({ ready: false });

	it('answers empty, never an error', async () => {
		expect(await schema(none())).toEqual({ network: false, evidence: false, orgs: false });
		expect(await reachDetail(none(), '7001')).toBeNull();
		expect(await bodyDetail(none(), '8001')).toBeNull();
		expect(await structureDetail(none(), '9')).toBeNull();
		expect(await gaugeDetail(none(), 'BSEI1')).toBeNull();
		expect(await gaugeSummary(none(), 'BSEI1')).toBeNull();
		const p = await waterPoints(none());
		expect(p.structures).toEqual([]);
		expect(p.gauges).toEqual([]);
		expect(p.credit.length).toBeGreaterThan(0);
	});

	it('asks nothing of the drawn tables', async () => {
		const seen: Seen[] = [];
		await reachDetail(fakeSql({ ready: false }, seen), '1');
		expect(seen.every((s) => s.text.includes('to_regclass'))).toBe(true);
	});
});

describe('with the tables but no such row', () => {
	it('is null for an id the build no longer has', async () => {
		const sql = fakeSql({});
		expect(await reachDetail(sql, '1')).toBeNull();
		expect(await bodyDetail(sql, '1')).toBeNull();
		expect(await structureDetail(sql, '1')).toBeNull();
		expect(await gaugeDetail(sql, 'ZZZZ9')).toBeNull();
	});

	it('refuses a bad id before it asks anything', async () => {
		const seen: Seen[] = [];
		await expect(reachDetail(fakeSql({}, seen), 'x')).rejects.toBeInstanceOf(BadRequest);
		await expect(gaugeDetail(fakeSql({}, seen), "x'; --")).rejects.toBeInstanceOf(BadRequest);
		expect(seen).toEqual([]);
	});
});

describe('readings', () => {
	it('read the newest record of a gauge by its own time, and say nothing when it holds none or no value', async () => {
		const sql = (payload: unknown) => fakeSql({ rows: (t) => (t.includes("source_id like") ? (payload === undefined ? [] : [{ payload }]) : undefined) });
		expect(await latestReading(sql(undefined), 'XTEST1')).toBeNull();
		expect(await latestReading(sql({ lid: 'XTEST1', t: '2030-07-01T10:00:00Z', primary: null, secondary: null, units: [null, null] }), 'XTEST1')).toBeNull();
		expect(await latestReading(sql({ lid: 'XTEST1', pe: 'HPIRZZZ', t: '2030-07-01T10:00:00Z', primary: 3200.5, secondary: null, units: ['ft', null] }), 'XTEST1')).toEqual({
			at: '2030-07-01T10:00:00.000Z',
			facts: [{ label: 'Pool elevation', value: 3200.5, unit: 'ft' }]
		});
	});

	it('ask for the gauge’s own records only (the id is a validated literal, its % is ours)', async () => {
		const seen: Seen[] = [];
		await latestReading(fakeSql({}, seen), 'BSEI1');
		expect(seen[0].values).toEqual(['BSEI1', 'BSEI1@%']);
	});
});

describe('gauge credits', () => {
	it('name USGS only when the gauge’s record does (BSEI1’s names none: an empty usgsId and no attribution)', () => {
		expect(namesUsgs({ usgsId: '', dataAttribution: [] })).toBe(false);
		expect(namesUsgs({ usgsId: '   ' })).toBe(false);
		expect(namesUsgs(null)).toBe(false);
		expect(namesUsgs({ usgsId: '13206000' })).toBe(true);
		expect(namesUsgs({ usgsId: '', dataAttribution: [{ title: 'US Geological Survey', abbrev: 'USGS' }] })).toBe(true);
		expect(namesUsgs({ usgsId: '', dataAttribution: [{ title: 'Bureau of Reclamation' }] })).toBe(false);
	});
});

describe('notices', () => {
	it('answers empty lists before there are rows', async () => {
		const n = await notices(fakeSql({}));
		expect(n).toMatchObject({ hazards: [], ecoli: [], polled: { boise_river_hazards: null, boise_ecoli: null }, republish: 'internal' });
		expect(n.credit.join(' ')).toContain('City of Boise');
	});

	it('cuts the name off the front of the City’s description, and shortens a very long one', () => {
		expect(hazardText('Fallen tree', 'Fallen tree: Tree across the right channel')).toBe('Tree across the right channel');
		expect(hazardText('Fallen tree', 'Fallen tree')).toBeNull();
		expect(hazardText(null, 'Just words')).toBe('Just words');
		expect(hazardText('A', null)).toBeNull();
		expect(hazardText(null, 'x'.repeat(2000))!.length).toBe(600);
	});

	it('keeps a site’s earlier results as history, newest first, and skips samples with no site or day', async () => {
		const rows = [
			{ source_id: 'S1|2030-07-01|L3', payload: { SampleName: 'S1', SampleDescription: 'Pond', SampleDatetime: '2030-07-01', FinalResultNumeric: '12.5', Units: 'MPN/100 mL' }, lng: -116.2, lat: 43.6 },
			{ source_id: 'S1|2030-06-24|L2', payload: { SampleName: 'S1', SampleDatetime: '2030-06-24', FinalResultNumeric: 4, Units: 'MPN/100 mL' }, lng: -116.2, lat: 43.6 },
			{ source_id: 'S1|2030-06-24|L2b', payload: { SampleName: 'S1', SampleDatetime: '2030-06-24', FinalResultNumeric: null }, lng: null, lat: null },
			{ source_id: 'bad', payload: { SampleDatetime: '2030-06-24' }, lng: null, lat: null },
			{ source_id: 'bad2', payload: { SampleName: 'S2' }, lng: null, lat: null }
		];
		const n = await notices(fakeSql({ rows: (t) => (t.includes("'boise_ecoli'") && t.includes('raw.record') ? rows : undefined) }));
		expect(n.ecoli).toHaveLength(1);
		expect(n.ecoli[0]).toMatchObject({ id: 'S1', site: 'Pond', sampled: '2030-07-01', result: 12.5, units: 'MPN/100 mL' });
		expect(n.ecoli[0].history.map((h) => [h.sampled, h.result])).toEqual([['2030-06-24', 4], ['2030-06-24', null]]);
	});
});
