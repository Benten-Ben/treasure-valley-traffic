import { afterAll, describe, expect, it, vi } from 'vitest';
import postgres from 'postgres';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { readStatus, readStatusRows, summarize } = await import('./status.js');
const { readDatabase } = await import('./versions.js');

/**
 * /api/meta's `status` against the real views of migration 0021
 * (ops.source_status, ops.build_status), with made-up sources, fetches,
 * runs and marks inside a transaction that's rolled back. Runs only with
 * TVT_TEST_DATABASE_URL, a test database migrated through 0021 (never `tvt`);
 * skips before the migration.
 */
const URL = process.env.TVT_TEST_DATABASE_URL;
const sql = URL ? postgres(URL, { max: 2, onnotice: () => {} }) : null;

afterAll(async () => {
	await sql?.end();
});

class Rollback extends Error {}

describe.skipIf(!URL)('status views (database)', () => {
	it('reads the views as the contract says', async ({ skip }) => {
		const [{ ready }] = await sql!`select to_regclass('ops.source_status') is not null as ready`;
		if (!ready) skip('ops.source_status is missing: apply migration 0021');
		const p = `tvt_test_${Math.random().toString(16).slice(2, 8)}`;
		const b = p.replace(/_/g, '-');
		await expect(
			sql!.begin(async (tx) => {
				await tx`insert into ops.source (name, title, url, access, schedule) values
				         (${p + '_late'}, 'Late', 'https://example.test/', 'open', '10 minutes'),
				         (${p + '_never'}, 'Never', 'https://example.test/', 'open', '1 hour')`;
				await tx`insert into ops.fetch (source, started_at, finished_at, ok, error) values
				         (${p + '_late'}, now() - interval '30 min', now() - interval '29 min', true, null),
				         (${p + '_late'}, now() - interval '5 min', now() - interval '4 min', false, 'HTTPError: 502'),
				         (${p + '_never'}, now() - interval '5 min', now() - interval '4 min', false, 'key=secret in a URL')`;
				await tx`insert into ops.build_pending (build, marked_by, reason) values (${b + '-roads'}, 'osm_street', 'a reason')`;
				await tx`insert into ops.build_run (build, started_at, finished_at, ok, note) values
				         (${b + '-water'}, now() - interval '2 h', now() - interval '1 h', true, '12 reaches')`;
				// Marked, then its run failed (a failed run clears nothing): failed, still marked.
				await tx`insert into ops.build_pending (build, marked_by, reason) values (${b + '-bake'}, 'roads-build', 'roads built')`;
				await tx`insert into ops.build_run (build, started_at, finished_at, ok, error) values
				         (${b + '-bake'}, now() - interval '20 min', now() - interval '10 min', false, 'MemoryError: out of memory')`;
				// Only this test's rows: a copy of production (the scratch database) has its own late sources,
				// which could push these past the attention list's cap.
				const rows = await readStatusRows(tx as unknown as postgres.Sql);
				const s = summarize(
					rows.sources.filter((r) => r.source.startsWith(p)),
					rows.builds.filter((r) => r.build.startsWith(b))
				);
				expect(s.sources).toEqual({ fresh: 0, late: 1, stale: 0, never: 1, failing: 2 });
				const mine = s.attention;
				expect(mine.map((a) => [a.source.slice(p.length + 1), a.state, a.failures, a.everyS])).toEqual([
					['never', 'never', 1, 3600],
					['late', 'late', 1, 600]
				]);
				expect(mine[1].lastOkAt).toBeGreaterThan(Date.now() / 1000 - 31 * 60);
				expect(mine[0].lastOkAt).toBeNull();
				const builds = s.builds.filter((x) => x.build.startsWith(b));
				expect(builds.map((x) => [x.build.slice(b.length + 1), x.state])).toEqual([
					['bake', 'failed'],
					['roads', 'pending'],
					['water', 'built']
				]);
				expect(builds[0].pendingSince).toBeGreaterThan(Date.now() / 1000 - 3600);
				expect(builds[0].lastRunAt).toBeGreaterThan(Date.now() / 1000 - 21 * 60);
				expect(builds[1].pendingSince).toBeGreaterThan(Date.now() / 1000 - 3600);
				expect(JSON.stringify(s)).not.toMatch(/secret|HTTPError|a reason|12 reaches|MemoryError|roads built/);
				const whole = await readStatus(tx as unknown as postgres.Sql);
				const scheduled = await tx`select count(*)::int as n from ops.source where schedule is not null`;
				const { failing, ...states } = whole.sources;
				expect(Object.values(states).reduce((x, y) => x + y, 0)).toBe(scheduled[0].n);
				expect(failing).toBeGreaterThanOrEqual(2);
				const part = await readDatabase(tx as unknown as postgres.Sql);
				expect(part.status?.sources).toEqual(whole.sources);
				throw new Rollback();
			})
		).rejects.toBeInstanceOf(Rollback);
	});
});
