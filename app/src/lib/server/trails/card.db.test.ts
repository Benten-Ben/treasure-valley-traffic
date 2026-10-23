import { afterAll, describe, expect, it } from 'vitest';
import postgres from 'postgres';
import { lineCard, wayCard } from './card.js';
import type { Sql } from './status.js';

/**
 * The trail card against the real views of trails 0001 (trails.path, trails.way_agency,
 * trails.agency_state), with made-up trails and ways inside a transaction that's rolled back.
 * Runs only with TVT_TEST_DATABASE_URL, a test database migrated through trails 0001 (never `tvt`);
 * skips before the migration.
 */
const URL = process.env.TVT_TEST_DATABASE_URL;
const sql = URL ? postgres(URL, { max: 2, onnotice: () => {} }) : null;

afterAll(async () => {
	await sql?.end();
});

class Rollback extends Error {}

const LINE = 'SRID=4326;LINESTRING(-116.2 43.7, -116.2 43.7054)';
const B = 9_600_000_000;

describe.skipIf(!URL)('trail card (database)', () => {
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
				                 ST_GeomFromEWKT(${LINE}), ${t0}, ${t0})`;
				await tx`insert into evt.event (source, source_id, kind, geom, declared, observed, active, severity, description,
				                                attributes, content_hash, updated_at)
				         values ('r2r_trails', 'test-1/1/muddy', 'trail_condition', null, tstzrange(${t0}, null), tstzrange(${t0}, null),
				                 true, 'do_not_use', 'Muddy - Stay Off', ${tx.json({ trail: 'test-1', state: 'muddy' })}, '\\x01', ${t0})`;
				// An untagged path an R2R trail runs along (dirt by default on the card), a private track, and an informal way.
				await tx`insert into trails.osm_path (osm_id, kind, name, surface, surface_from, width_est_m, no_access, informal, tags, geom)
				         values (${B + 1}, 'path', 'Example Ridge Trail', 'unknown', 'none', 0.8, false, false, '{"highway": "path"}', ST_GeomFromEWKT(${LINE})),
				                (${B + 2}, 'track', null, 'dirt', 'default', 3.0, true, false, '{"highway": "track", "access": "private"}', ST_GeomFromEWKT(${LINE})),
				                (${B + 3}, 'path', null, 'unknown', 'none', 0.8, false, true, '{"highway": "path", "informal": "yes"}', ST_GeomFromEWKT(${LINE}))`;
				await tx`insert into trails.link (source, source_id, osm_id, share, off_m, method, paints, matched_at)
				         values ('r2r_trails', 'test-1', ${B + 1}, 1, 0, 'pieces150_buffer15_bearing20', true, ${t0})`;
				await tx`insert into trails.matched_line (source, source_id, kind, name, line_fp, line_m, covered_m, gap_m, along_m, links, matched_at, matched_by)
				         values ('r2r_trails', 'test-1', 'trail', 'Example Ridge', 'fp1', 600, 600, 12, 30, 1, ${t0}, 'trails-match')`;
				const way = await wayCard(tx as unknown as Sql, B + 1);
				expect(way).toMatchObject({
					id: B + 1,
					kind: 'path',
					name: 'Example Ridge Trail',
					surface: 'dirt',
					surface_from: 'default',
					surface_default: 'Ridge to Rivers trail',
					width_m: 0.8,
					width_from: 'estimated',
					informal: false
				});
				expect(way!.lines).toHaveLength(1);
				expect(way!.lines[0]).toMatchObject({ source: 'r2r_trails', kind: 'trail', state: 'muddy', severity: 'do_not_use', label: 'Muddy - Stay Off', paints: true });
				expect(way!.lines[0].line_id).toEqual(expect.any(Number));
				// Closed to the public: no card (the layer doesn't draw it).
				expect(await wayCard(tx as unknown as Sql, B + 2)).toBeNull();
				// Informal: a card, saying so.
				expect(await wayCard(tx as unknown as Sql, B + 3)).toMatchObject({ informal: true, lines: [] });
				expect(await wayCard(tx as unknown as Sql, B + 99)).toBeNull();
				const line = await lineCard(tx as unknown as Sql, way!.lines[0].line_id!);
				expect(line).toMatchObject({ source: 'r2r_trails', name: 'Example Ridge', state: 'muddy', severity: 'do_not_use', line_m: 600, drawn_m: 42, ways: 1 });
				expect(await lineCard(tx as unknown as Sql, 999_999_999)).toBeNull();
				throw new Rollback();
			})
		).rejects.toBeInstanceOf(Rollback);
	});
});
