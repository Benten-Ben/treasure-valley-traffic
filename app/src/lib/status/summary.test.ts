import { describe, expect, it } from 'vitest';
import type { BuildStatus, DataStatus, SourceStatus } from '#lib/contracts/meta.js';
import { LINES_MAX, PENDING_LATE_S, RUNNING_LATE_S, span, statusChip } from './summary.js';

const NOW = 1_760_000_000;
const counts = (over: Partial<DataStatus['sources']> = {}) => ({ fresh: 40, late: 0, stale: 0, never: 0, failing: 0, ...over });
const source = (name: string, state: SourceStatus['state'], agoS: number | null, failures = 0, everyS = 600): SourceStatus => ({
	source: name,
	state,
	lastOkAt: agoS === null ? null : NOW - agoS,
	everyS,
	failures
});
const build = (name: string, state: BuildStatus['state'], over: Partial<BuildStatus> = {}): BuildStatus => ({
	build: name,
	state,
	lastOkAt: null,
	pendingSince: null,
	lastRunAt: null,
	...over
});
const chip = (status: DataStatus | null) => statusChip({ status }, NOW);

describe('the status chip', () => {
	it('says fresh when all is', () => {
		const c = chip({ sources: counts(), attention: [], builds: [build('water-build', 'built', { lastOkAt: NOW - 3600 })] });
		expect([c.level, c.shape, c.headline]).toEqual(['fresh', '●', 'Data fresh']);
		expect(c.lines).toEqual(['40 scheduled sources, all fresh']);
		expect(c.color).toBe('var(--accent-2)');
		expect(c.count).toBeNull();
	});

	it('counts what the headline counts, for the compact chip', () => {
		const stale = chip({
			sources: counts({ fresh: 24, never: 16 }),
			attention: [],
			builds: [build('roads-build', 'pending', { pendingSince: NOW - 3600 })]
		});
		expect([stale.shape, stale.count]).toEqual(['■', 17]);
		expect(statusChip(null, NOW).count).toBeNull();
	});

	it('is unknown without a status, in a word and a hollow shape', () => {
		for (const meta of [null, undefined, {}, { status: null }]) {
			const c = statusChip(meta as never, NOW);
			expect([c.level, c.shape, c.headline]).toEqual(['unknown', '◌', 'Status unknown']);
			expect(c.lines).toHaveLength(1);
		}
		expect(statusChip(null, NOW).lines[0]).toBe("The server didn't answer");
	});

	it('goes ▲ for a late or failing source and ■ for a stale or never-fetched one', () => {
		const late = chip({
			sources: counts({ fresh: 39, late: 1, failing: 1 }),
			attention: [source('achd_roads', 'late', 9 * 86_400, 0, 7 * 86_400), source('nws_wwa', 'fresh', 300, 2)],
			builds: []
		});
		expect([late.level, late.shape, late.headline]).toEqual(['late', '▲', '1 source late · 1 source failing']);
		expect(late.lines).toEqual([
			'achd_roads: late, last good fetch 9 days ago (every 7 days)',
			'nws_wwa: failing, last good fetch 5 min ago (every 10 min), 2 failed tries since'
		]);
		const stale = chip({
			sources: counts({ fresh: 38, stale: 1, never: 1, failing: 2 }),
			attention: [source('usgs_quakes', 'stale', 5 * 3600, 4, 3600), source('new_one', 'never', null, 1, 3600)],
			builds: []
		});
		expect([stale.level, stale.shape, stale.color]).toEqual(['stale', '■', 'var(--alert)']);
		expect(stale.headline).toBe('1 source stale · 1 source never fetched');
		expect(stale.lines[1]).toBe('new_one: no good fetch yet (every 60 min), 1 failed try since');
	});

	it('names waiting builds, and raises the level only after a long wait', () => {
		const fresh = chip({
			sources: counts(),
			attention: [],
			builds: [build('roads-build', 'pending', { pendingSince: NOW - 5 * 3600, lastOkAt: NOW - 9 * 86_400 })]
		});
		expect([fresh.level, fresh.headline]).toEqual(['fresh', '1 build waiting']);
		expect(fresh.lines).toEqual(['roads-build: waiting 5 h for a run; last built 9 days ago']);
		const long = chip({
			sources: counts(),
			attention: [],
			builds: [build('roads-build', 'pending', { pendingSince: NOW - PENDING_LATE_S - 60 })]
		});
		expect([long.level, long.lines[0]]).toEqual(['late', 'roads-build: waiting 2 days for a run; never built']);
		const failed = chip({
			sources: counts(),
			attention: [],
			builds: [
				build('landscape-bake', 'running', { lastRunAt: NOW - 1200, lastOkAt: NOW - 86_400 }),
				build('soils-build', 'failed', { lastOkAt: NOW - 3 * 86_400 }),
				build('water-build', 'built', { lastOkAt: NOW - 60 })
			]
		});
		expect([failed.level, failed.headline]).toEqual(['late', '1 build failed']);
		expect(failed.lines).toEqual([
			'landscape-bake: running for 20 min; last built 24 h ago',
			'soils-build: its last run failed; last built 3 days ago'
		]);
	});

	it('raises a build whose run failed while it was marked, the usual way a build fails', () => {
		const c = chip({
			sources: counts(),
			attention: [],
			builds: [
				build('landscape-bake', 'failed', { pendingSince: NOW - 3600, lastRunAt: NOW - 600, lastOkAt: NOW - 9 * 86_400 }),
				build('roads-build', 'built', { lastOkAt: NOW - 7200 })
			]
		});
		expect([c.level, c.shape, c.headline]).toEqual(['late', '▲', '1 build failed']);
		expect(c.lines).toEqual(['landscape-bake: its last run failed; marked 60 min ago; last built 9 days ago']);
	});

	it('raises a run that has gone on longer than any should', () => {
		const going = (agoS: number) =>
			chip({ sources: counts(), attention: [], builds: [build('landscape-bake', 'running', { lastRunAt: NOW - agoS })] });
		const normal = going(3 * 3600);
		expect([normal.level, normal.headline]).toEqual(['fresh', 'Data fresh']);
		expect(normal.lines).toEqual(['landscape-bake: running for 3 h; never built']);
		const long = going(RUNNING_LATE_S + 60);
		expect([long.level, long.shape, long.headline]).toEqual(['late', '▲', '1 build running long']);
		expect(long.lines).toEqual(['landscape-bake: running for 18 h, longer than a run should take; never built']);
	});

	it('keeps the headline and the tooltip short', () => {
		const attention = Array.from({ length: 12 }, (_, i) => source(`s${i}`, 'late', 3600));
		const c = chip({
			sources: counts({ fresh: 28, late: 12, stale: 1 }),
			attention: [source('x', 'stale', 86_400), ...attention],
			builds: [build('roads-build', 'pending', { pendingSince: NOW - 60 })]
		});
		expect(c.headline).toBe('1 source stale · 12 sources late · …');
		expect(c.lines).toHaveLength(LINES_MAX);
		expect(c.lines.at(-1)).toBe(`and ${13 + 1 - LINES_MAX + 1} more`);
	});

	it('spans read as people say them', () => {
		expect([span(40), span(89), span(90), span(12 * 60), span(3600), span(66 * 60), span(90 * 60), span(5 * 3600), span(36 * 3600), span(86_400 * 3), span(-5)]).toEqual([
			'40 s', '89 s', '2 min', '12 min', '60 min', '66 min', '2 h', '5 h', '2 days', '3 days', '0 s'
		]);
		expect(span(30 * 3600)).toBe('30 h');
	});
});
