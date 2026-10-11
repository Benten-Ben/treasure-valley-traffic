import { afterAll, describe, expect, it } from 'vitest';
import postgres from 'postgres';
import { trailStatus, type Sql } from './status.js';

/**
 * /api/trails/status against the real views of trails 0001 (trails.agency_state,
 * trails.hidden_informal), with made-up trails, ways and links inside a
 * transaction that's rolled back. Runs only with TVT_TEST_DATABASE_URL, a test
 * database migrated through trails 0001 (never `tvt`); skips before the
 * migration.
 */
const URL = process.env.TVT_TEST_DATABASE_URL;
const sql = URL ? postgres(URL, { max: 2, onnotice: () => {} }) : null;

afterAll(async () => {
	await sql?.end();
});

class Rollback extends Error {}

const LINE = 'SRID=4326;LINESTRING(-116.2 43.7, -116.2 43.7054)';
const B = 9_600_000_000;

describe.skipIf(!URL)('trail status (database)', () => {
	it('reads the views as the contract says', async ({ skip }) => {
		const [{ ready }] = await sql!`select to_regclass('trails.agency_state') is not null as ready`;
		if (!ready) skip('trails.agency_state is missing: apply trails 0001');
		await expect(
			sql!.begin(async (tx) => {
				for (const name of ['r2r_trails', 'boise_greenbelt_closures'])
					await tx`insert into ops.source (name, title, url, access) values (${name}, ${name}, 'https://example.test/', 'open')
					         on conflict (name) do nothing`;
				await tx`delete from evt.event where source in ('r2r_trails', 'boise_greenbelt_closures')`;
				await tx`delete from raw.record where source in ('r2r_trails', 'boise_greenbelt_closures')`;
				await tx`delete from trails.link`;
				await tx`delete from trails.matched_line`;
				await tx`update trails.osm_path set active = false`;
				const t0 = new Date('2026-10-11T12:00:00Z');
				await tx`insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen)
				         values ('r2r_trails', 'test-1', '\\x01', ${tx.json({ TrailName: 'Example Ridge', SystemName: 'Ridge to Rivers', _geom: 'fp1' })},
				                 ST_GeomFromEWKT(${LINE}), ${t0}, ${t0}),
				                ('r2r_trails', 'test-2', '\\x02', ${tx.json({ TrailName: 'Closed Gulch', _geom: 'fp2' })},
				                 ST_GeomFromEWKT('SRID=4326;LINESTRING(-116.19 43.7, -116.19 43.703)'), ${t0}, ${t0})`;
				await tx`insert into evt.event (source, source_id, kind, geom, declared, observed, active, severity, description,
				                                attributes, content_hash, updated_at)
				         values ('r2r_trails', 'test-1/1/dry', 'trail_condition', null, tstzrange(${t0}, null), tstzrange(${t0}, null),
				                 true, 'open', 'Dry / Tacky - Enjoy', ${tx.json({ trail: 'test-1', state: 'dry' })}, '\\x01', ${t0}),
				                ('r2r_trails', 'test-2/1/closed', 'trail_condition', null, tstzrange(${t0}, null), tstzrange(${t0}, null),
				                 true, 'closed', 'CLOSED', ${tx.json({ trail: 'test-2', state: 'closed' })}, '\\x02', ${t0})`;
				await tx`insert into trails.osm_path (osm_id, kind, surface, surface_from, width_est_m, no_access, informal, tags, geom)
				         values (${B + 1}, 'path', 'dirt', 'osm', 0.8, false, false, '{"highway": "path"}', ST_GeomFromEWKT(${LINE})),
				                (${B + 9}, 'path', 'unknown', 'none', 0.8, false, true, '{"highway": "path", "informal": "yes"}',
				                 ST_GeomFromEWKT('SRID=4326;LINESTRING(-116.1895 43.7, -116.1895 43.703)'))`;
				await tx`insert into trails.link (source, source_id, osm_id, share, off_m, method, paints, matched_at)
				         values ('r2r_trails', 'test-1', ${B + 1}, 1, 0, 'pieces150_buffer15_bearing20', true, ${t0})`;
				await tx`insert into trails.matched_line (source, source_id, kind, name, line_fp, line_m, covered_m, gap, gap_m, links, matched_at, matched_by)
				         values ('r2r_trails', 'test-1', 'trail', 'Example Ridge', 'fp1', 600, 600, null, 0, 1, ${t0}, 'trails-match'),
				                ('r2r_trails', 'test-2', 'trail', 'Closed Gulch', 'fp2', 333, null,
				                 ST_Multi(ST_GeomFromEWKT('SRID=4326;LINESTRING(-116.19 43.7, -116.19 43.703)')), 333, 0, ${t0}, 'trails-match')`;
				const got = await trailStatus(tx as unknown as Sql);
				const ridge = got.agencies.find((a) => a.id === 'test-1')!;
				expect(ridge).toMatchObject({ kind: 'trail', name: 'Example Ridge', state: 'dry', severity: 'open', ways: [B + 1], drawn: false, covered: 1 });
				expect(typeof ridge.line_id).toBe('number');
				expect(ridge.set_at).toBe('2026-10-11T12:00:00.000Z');
				expect(got.agencies.find((a) => a.id === 'test-2')).toMatchObject({ state: 'closed', drawn: true, gap_m: 333, along_m: 0, covered: null, ways: [] });
				expect(got.ways).toEqual({ [String(B + 1)]: 'open' });
				expect(got.hidden).toEqual([B + 9]);                       // informal, about 40 m from the closed trail
				expect(got.counts).toEqual({ dry: 1, closed: 1 });
				throw new Rollback();
			})
		).rejects.toBeInstanceOf(Rollback);
	});
});
