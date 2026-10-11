import { describe, expect, it } from 'vitest';
import { ATTENTION_MAX, BUILDS_MAX, readStatus, summarize, type BuildRow, type SourceRow } from './status.js';

const src = (source: string, state: string, lastOkAt: number | null, failures = 0, everyS = 600): SourceRow => ({
	source,
	state,
	last_ok_at: lastOkAt,
	every_s: everyS,
	failures
});
const bld = (build: string, state: string, over: Partial<BuildRow> = {}): BuildRow => ({
	build,
	state,
	last_ok_at: null,
	pending_since: null,
	last_run_at: null,
	...over
});

describe('status for /api/meta', () => {
	it('counts sources by state and lists the ones worth a look, worst first', () => {
		const s = summarize(
			[
				src('awc_metar', 'fresh', 1000),
				src('nws_wwa', 'fresh', 990, 2),
				src('achd_roads', 'late', 500, 0, 7 * 86400),
				src('compass_plats', 'late', 400, 1, 7 * 86400),
				src('usgs_quakes', 'stale', 300, 5, 3600),
				src('new_source', 'never', null, 1, 3600),
				src('odd', 'sideways', 1)
			],
			[]
		);
		expect(s.sources).toEqual({ fresh: 2, late: 2, stale: 1, never: 1, failing: 4 });
		expect(s.attention.map((a) => a.source)).toEqual(['usgs_quakes', 'new_source', 'compass_plats', 'achd_roads', 'nws_wwa']);
		expect(s.attention[0]).toEqual({ source: 'usgs_quakes', state: 'stale', lastOkAt: 300, everyS: 3600, failures: 5 });
		expect(s.attention[1].lastOkAt).toBeNull();
		expect(s.builds).toEqual([]);
	});

	it('orders builds failed, running, pending (oldest mark first), built, and keeps no reasons', () => {
		const s = summarize(
			[],
			[
				bld('water-build', 'built', { last_ok_at: 100, last_run_at: 90 }),
				bld('roads-build', 'pending', { pending_since: 500, last_ok_at: 50 }),
				bld('trails-match', 'pending', { pending_since: 300 }),
				bld('landscape-bake', 'running', { last_run_at: 700 }),
				bld('soils-build', 'failed', { last_ok_at: 10, last_run_at: 600 }),
				bld('farm-build', 'failed', { pending_since: 200, last_run_at: 650 }),
				bld('weird', 'unheard-of')
			]
		);
		expect(s.builds.map((b) => [b.build, b.state])).toEqual([
			['farm-build', 'failed'],
			['soils-build', 'failed'],
			['landscape-bake', 'running'],
			['trails-match', 'pending'],
			['roads-build', 'pending'],
			['water-build', 'built']
		]);
		expect(Object.keys(s.builds[0]).sort()).toEqual(['build', 'lastOkAt', 'lastRunAt', 'pendingSince', 'state']);
		expect(s.builds[0]).toEqual({ build: 'farm-build', state: 'failed', lastOkAt: null, pendingSince: 200, lastRunAt: 650 });
		expect(s.builds[4]).toEqual({ build: 'roads-build', state: 'pending', lastOkAt: 50, pendingSince: 500, lastRunAt: null });
	});

	it('trims long lists', () => {
		const many = Array.from({ length: 50 }, (_, i) => src(`s${String(i).padStart(2, '0')}`, 'late', i));
		const builds = Array.from({ length: 60 }, (_, i) => bld(`b${i}`, 'built'));
		const s = summarize(many, builds);
		expect(s.sources.late).toBe(50);
		expect(s.attention).toHaveLength(ATTENTION_MAX);
		expect(s.attention[0].source).toBe('s00');
		expect(s.builds).toHaveLength(BUILDS_MAX);
	});

	it('reads both views, as numbers', async () => {
		const seen: string[] = [];
		const fake = (async (strings: TemplateStringsArray) => {
			const text = strings.join('$').replace(/\s+/g, ' ');
			seen.push(text);
			if (text.includes('from ops.source_status'))
				return [{ source: 'awc_metar', state: 'late', last_ok_at: '1760000000.5', every_s: '600', failures: '2' }];
			if (text.includes('from ops.build_status'))
				return [{ build: 'roads-build', state: 'pending', last_ok_at: null, pending_since: 1_760_000_100, last_run_at: null }];
			return [];
		}) as unknown as Parameters<typeof readStatus>[0];
		const s = await readStatus(fake);
		expect(s.sources).toEqual({ fresh: 0, late: 1, stale: 0, never: 0, failing: 1 });
		expect(s.attention).toEqual([{ source: 'awc_metar', state: 'late', lastOkAt: 1_760_000_000.5, everyS: 600, failures: 2 }]);
		expect(s.builds).toEqual([{ build: 'roads-build', state: 'pending', lastOkAt: null, pendingSince: 1_760_000_100, lastRunAt: null }]);
		expect(seen.find((t) => t.includes('ops.source_status'))).toContain('extract(epoch from schedule)::float8 as every_s');
		// No error text or reasons leave the server.
		expect(seen.join(' ')).not.toMatch(/last_error|reason|pending_by/);
	});
});
