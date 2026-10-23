import { afterAll, describe, expect, it } from 'vitest';
import postgres from 'postgres';
import { CREDITS, gaugeCredits } from '#lib/layers/water/water.js';
import type { Sql } from './common.js';
import { gaugeDetail, gaugeSummary, waterPoints } from './gauges.js';
import { bodyDetail, reachDetail, structureDetail } from './network.js';
import { notices } from './notices.js';

/**
 * The water APIs against the real tables of water 0001 (water.reach, canal, canal_org, body, structure, gauge,
 * reach_evidence) and core's raw.record and evt.event, with made-up rows (ids from 9e15 up, invented names,
 * a made-up gauge) inside a transaction that's rolled back. Runs only with TVT_TEST_DATABASE_URL, a test
 * database migrated through water 0001 (never `tvt`); skips before the migration.
 */
const URL = process.env.TVT_TEST_DATABASE_URL;
const sql = URL ? postgres(URL, { max: 2, onnotice: () => {} }) : null;

afterAll(async () => {
	await sql?.end();
});

class Rollback extends Error {}

const B = 9_000_000_000_000_000; // ids of made-up rows, far above any real one (below 2^53)
const T0 = new Date('2030-07-01T12:00:00Z');
const LINE = (x: number) => `SRID=4326;LINESTRING(${x} 43.6, ${x + 0.01} 43.601)`;

describe.skipIf(!URL)('the water APIs (database)', () => {
	it('reads the plugin’s tables as the contracts say, with made-up rows', async ({ skip }) => {
		const [{ ready }] = await sql!`select to_regclass('water.canal_org') is not null and to_regclass('evt.event') is not null as ready`;
		if (!ready) skip('water.canal_org is missing: apply water 0001');
		await expect(
			sql!.begin(async (tx) => {
				const db = tx as unknown as Sql;
				for (const name of ['nwps_gauges', 'boise_river_hazards', 'boise_ecoli', 'osm_waterways'])
					await tx`insert into ops.source (name, title, url, access) values (${name}, ${name}, 'https://example.test/', 'open') on conflict (name) do nothing`;
				await tx`delete from raw.record where source in ('nwps_gauges', 'boise_ecoli', 'boise_river_hazards')`;
				await tx`delete from evt.event where source in ('nwps_gauges', 'boise_river_hazards')`;
				await tx`delete from ops.fetch where source in ('boise_river_hazards', 'boise_ecoli')`;
				for (const t of ['canal_org', 'reach_evidence', 'gauge', 'structure', 'canal', 'body', 'reach']) await tx.unsafe(`delete from water.${t}`);
				const [{ id: build }] = await tx`insert into water.build (note) values ('made-up test build') returning id`;

				// The network: a river with a gauge, a main canal leaving it at a diversion dam, and a piped lateral.
				await tx`insert into water.reach (id, kind, name, name_from, flow, piped, width_m, width_from, stream_order, minzoom, geometry_from,
				                                   confirmed, canal_id, length_m, geom, build_id)
				         values (${B + 1}, 'river', 'Example River', 'osm', 'perennial', false, 14, 'order', 7, 9, 'osm', true, null, 5200, ST_GeomFromEWKT(${LINE(-116.3)}), ${build}),
				                (${B + 2}, 'canal', 'Example Canal', 'hydroshare', 'unknown', false, 8, 'kind', null, 10, 'osm', true, ${B + 2}, 4100, ST_GeomFromEWKT(${LINE(-116.2)}), ${build}),
				                (${B + 3}, 'lateral', null, null, 'intermittent', true, 2.5, 'kind', null, 16, 'nhd', false, null, 300, ST_GeomFromEWKT(${LINE(-116.1)}), ${build})`;
				await tx`insert into water.reach_evidence (reach_id, source, source_id, role, share, distance_m)
				         values (${B + 2}, 'osm_waterways', 'w900', 'geometry', 1, null),
				                (${B + 2}, 'nhd_hr', 'NHD-X', 'attributes', 0.93, 4.2),
				                (${B + 2}, 'hydroshare_canals', 'N7', 'name', 0.8, 6.1),
				                (${B + 2}, 'nhd_hr', 'NHD-Y', 'agrees', 0.5, 9)`;
				await tx`insert into water.structure (id, kind, name, source, source_id, reach_id, gauge_lid, minzoom, geom, build_id)
				         values (${B + 10}, 'dam', 'Example Diversion Dam', 'osm_waterways', 'w5', ${B + 1}, null, 11, ST_GeomFromEWKT('SRID=4326;POINT(-116.31 43.6)'), ${build}),
				                (${B + 11}, 'gauge', 'XTEST1 gauge', 'nwps_gauges', 'XTEST1', ${B + 2}, 'XTEST1', 12, ST_GeomFromEWKT('SRID=4326;POINT(-116.19 43.6)'), ${build}),
				                (${B + 12}, 'dam', 'Example Gauged Dam', 'osm_waterways', 'w6', null, 'XTEST2', 14, ST_GeomFromEWKT('SRID=4326;POINT(-116.28 43.6)'), ${build})`;
				await tx`insert into water.canal (id, name, kind, length_m, piped_m, reaches, head_reach_id, head_structure_id, source_kind, source_reach_id,
				                                   gauge_lid, sources, build_id)
				         values (${B + 2}, 'Example Canal', 'main_canal', 23100, 800, 12, ${B + 2}, ${B + 10}, 'river', ${B + 1}, 'XTEST1',
				                 ${tx.array(['osm_waterways', 'nhd_hr', 'hydroshare_canals'])}, ${build})`;
				await tx`insert into water.gauge (lid, name, reach_id, body_id, canal_id, method, distance_m, geom, build_id)
				         values ('XTEST1', 'Example Canal Diversion', ${B + 2}, null, ${B + 2}, 'name', 12.4, ST_GeomFromEWKT('SRID=4326;POINT(-116.19 43.6)'), ${build}),
				                ('XTEST2', 'Example River at Nowhere', ${B + 1}, null, null, 'nearest', 140, ST_GeomFromEWKT('SRID=4326;POINT(-116.29 43.6)'), ${build})`;
				await tx`insert into water.body (id, kind, name, intermittent, area_m2, minzoom, geometry_from, confirmed, osm_type, osm_id, gauge_lid, geom, build_id)
				         values (${B + 20}, 'pond', 'Example Pond', false, 12500, 11, 'osm', true, 'w', 777, null, ST_Multi(ST_GeomFromEWKT('SRID=4326;POLYGON((-116.2 43.6, -116.199 43.6, -116.199 43.601, -116.2 43.6))')), ${build}),
				                (${B + 21}, 'wetland', null, true, 800, 14, 'nhd', false, null, null, null, ST_Multi(ST_GeomFromEWKT('SRID=4326;POLYGON((-116.1 43.6, -116.099 43.6, -116.099 43.601, -116.1 43.6))')), ${build}),
				                (${B + 22}, 'lake', 'Example Gauged Lake', false, 90000, 10, 'nhd', false, null, null, 'XTEST2', ST_Multi(ST_GeomFromEWKT('SRID=4326;POLYGON((-116.3 43.6, -116.299 43.6, -116.299 43.601, -116.3 43.6))')), ${build})`;
				// IDWR's service areas, internal.
				await tx`insert into water.canal_org (canal_id, objectid, name, share, at_head, build_id)
				         values (${B + 2}, 90001, 'Example Irrigation District', 0.62, true, ${build}), (${B + 2}, 90002, 'Sample Ditch Company', 0.38, false, ${build})`;

				// Readings, the gauge record and a flood episode.
				const reading = (t: string, primary: number | null, secondary: number | null) => ({ lid: 'XTEST1', pe: 'HGIRZZZ', t, primary, secondary, units: ['ft', 'kcfs'] });
				for (const [t, p, s] of [['2030-07-01T10:00:00Z', 7.1, 1.55], ['2030-07-01T11:45:00Z', 7.33, 1.66], ['2030-06-30T23:00:00Z', 4.0, 0.2]] as const)
					await tx`insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen)
					         values ('nwps_gauges', ${'XTEST1@' + t}, ${Buffer.from(t)}, ${tx.json(reading(t, p, s))}, ST_GeomFromEWKT('SRID=4326;POINT(-116.19 43.6)'), ${T0}, ${T0})`;
				await tx`insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen)
				         values ('nwps_gauges', 'XTEST1', '\\x01', ${tx.json({ lid: 'XTEST1', usgsId: '', dataAttribution: [] })}, null, ${T0}, ${T0}),
				                ('nwps_gauges', 'XTEST2', '\\x02', ${tx.json({ lid: 'XTEST2', usgsId: '13200000' })}, null, ${T0}, ${T0}),
				                ('nwps_gauges', ${'XTEST2@2030-07-01T11:00:00Z'}, '\\x03', ${tx.json({ lid: 'XTEST2', pe: 'HGIRZZZ', t: '2030-07-01T11:00:00Z', primary: 3.2, secondary: null, units: ['ft', null] })}, null, ${T0}, ${T0})`;
				await tx`insert into evt.event (source, source_id, kind, geom, declared, observed, active, severity, description, attributes, content_hash, updated_at)
				         values ('nwps_gauges', 'XTEST2:2030-07-01T09:00:00Z', 'river_flood', ST_GeomFromEWKT('SRID=4326;POINT(-116.29 43.6)'), tstzrange(${T0}, null), tstzrange(${T0}, null), true,
				                 'minor', 'Example River: minor flooding', ${tx.json({ lid: 'XTEST2', category: 'minor', peak_category: 'moderate' })}, '\\x01', ${T0})`;

				// The City's notices.
				await tx`insert into evt.event (source, source_id, kind, geom, declared, observed, active, severity, description, attributes, content_hash, updated_at)
				         values ('boise_river_hazards', '101', 'river_hazard', ST_GeomFromEWKT('SRID=4326;POINT(-116.21 43.61)'), tstzrange(${T0}, null), tstzrange(${T0}, null), true,
				                 'temporary', 'Fallen tree: Tree across the right channel', ${tx.json({ type: 'temporary', status: 'active', name: 'Fallen tree', mile_marker: '4.2', edited: '2030-07-01T08:00:00Z' })}, '\\x11', ${T0}),
				                ('boise_river_hazards', '102', 'river_hazard', ST_GeomFromEWKT('SRID=4326;POINT(-116.22 43.612)'), tstzrange(${T0}, null), tstzrange(${T0}, null), true,
				                 'extreme', 'Example Diversion', ${tx.json({ type: 'extreme', status: 'potential', name: 'Example Diversion', mile_marker: null })}, '\\x12', ${T0}),
				                ('boise_river_hazards', '103', 'river_hazard', null, tstzrange(${T0}, null), tstzrange(${T0}, null), false,
				                 'temporary', 'Ended', ${tx.json({ type: 'temporary', status: 'active', name: 'Ended' })}, '\\x13', ${T0})`;
				const sample = (name: string, day: string, result: number, lab: string) => ({ SampleName: name, SampleDescription: `${name} site`, SampleDatetime: day, FinalResultNumeric: result, Units: 'MPN/100 mL', LabNumber: lab, MostRecent: 'Y' });
				for (const [name, day, result, lab, x] of [
					['TESTPOND1', '2030-06-24', 12, 'L1', -116.2],
					['TESTPOND1', '2030-07-01', 456.7, 'L2', -116.2],
					['TESTRIVER1', '2030-07-01', 3, 'L3', -116.21]
				] as const)
					await tx`insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen)
					         values ('boise_ecoli', ${`${name}|${day}|${lab}`}, ${Buffer.from(lab)}, ${tx.json(sample(name, day, result, lab))}, ST_GeomFromEWKT(${`SRID=4326;POINT(${x} 43.605)`}), ${T0}, ${T0})`;
				await tx`insert into ops.fetch (source, started_at, ok) values ('boise_ecoli', ${T0}, true), ('boise_river_hazards', ${new Date('2030-07-01T13:00:00Z')}, true)`;

				// -- a reach: its canal, the service areas, the gauge and its reading -----------------------------------
				const reach = (await reachDetail(db, String(B + 2)))!;
				expect(reach).toMatchObject({ id: B + 2, kind: 'canal', name: 'Example Canal', name_from: 'hydroshare', flow: 'unknown', width_m: 8, width_from: 'kind', geometry_from: 'osm', confirmed: true, length_m: 4100 });
				expect(reach.evidence.map((e) => `${e.role}:${e.source}`)).toEqual(['geometry:osm_waterways', 'attributes:nhd_hr', 'name:hydroshare_canals', 'agrees:nhd_hr']);
				expect(reach.evidence[1]).toMatchObject({ share: 0.93, distance_m: 4.2 });
				expect(reach.canal).toMatchObject({ id: B + 2, name: 'Example Canal', kind: 'main_canal', length_m: 23100, piped_m: 800, reaches: 12, source: { kind: 'river', name: 'Example River' } });
				expect(reach.canal?.head_structure).toEqual({ id: B + 10, kind: 'dam', name: 'Example Diversion Dam' });
				expect(reach.canal?.service_areas).toEqual([
					{ name: 'Example Irrigation District', share: 0.62, at_head: true },
					{ name: 'Sample Ditch Company', share: 0.38, at_head: false }
				]);
				expect(reach.canal?.gauge).toMatchObject({ lid: 'XTEST1', name: 'Example Canal Diversion', measures: { type: 'canal', id: B + 2, name: 'Example Canal' }, flood: null });
				// The newest reading by its own time (not the order stored), with units in words.
				expect(reach.canal?.gauge?.reading).toEqual({
					at: '2030-07-01T11:45:00.000Z',
					facts: [
						{ label: 'Stage', value: 7.33, unit: 'ft' },
						{ label: 'Flow', value: 1660, unit: 'cfs' }
					]
				});
				expect(reach.gauge).toBeNull();
				expect(reach.credit).toEqual(expect.arrayContaining(['© OpenStreetMap contributors', 'USGS National Hydrography Dataset']));
				expect(reach.credit.some((c) => c.includes('HydroShare'))).toBe(true);
				expect(reach.credit.some((c) => c.includes('Idaho Department of Water Resources'))).toBe(true);
				expect(reach.credit.some((c) => c.includes('Geological Survey'))).toBe(false); // its gauge's record names no USGS site
				// A reach with no canal: no service areas anywhere, and the gauge on the river itself.
				const river = (await reachDetail(db, String(B + 1)))!;
				expect(river.canal).toBeNull();
				expect(river.gauge).toMatchObject({ lid: 'XTEST2', flood: { category: 'minor', peak: 'moderate' } });
				expect(river.credit.some((c) => c.includes('Idaho Department of Water Resources'))).toBe(false);
				expect(river.credit.some((c) => c.includes('courtesy of the U.S. Geological Survey'))).toBe(true); // the gauge's own credit, as on its card
				const piped = (await reachDetail(db, String(B + 3)))!;
				expect(piped).toMatchObject({ piped: true, flow: 'intermittent', geometry_from: 'nhd', name: null, canal: null, evidence: [] });
				expect(await reachDetail(db, String(B + 99))).toBeNull();

				// -- a body, a structure -----------------------------------------------------------------------------
				expect(await bodyDetail(db, String(B + 20))).toMatchObject({ kind: 'pond', name: 'Example Pond', area_m2: 12500, osm: 'way 777', gauge: null, intermittent: false });
				expect(await bodyDetail(db, String(B + 21))).toMatchObject({ kind: 'wetland', name: null, intermittent: true, geometry_from: 'nhd', osm: null });
				const dam = (await structureDetail(db, String(B + 10)))!;
				expect(dam).toMatchObject({ kind: 'dam', name: 'Example Diversion Dam', source: 'osm_waterways', reach: { id: B + 1, kind: 'river', name: 'Example River' } });
				expect(dam.head_of).toEqual([{ id: B + 2, name: 'Example Canal' }]);
				// The credits follow the records each card shows: a gauge's reading brings NWPS (and USGS only where its record names a site).
				const nwpsOnly = gaugeCredits(false);
				const nwpsUsgs = gaugeCredits(true);
				expect(nwpsUsgs[0]).toContain('Geological Survey');
				expect((await bodyDetail(db, String(B + 20)))!.credit).toEqual([CREDITS.osm, CREDITS.nhd]); // no gauge
				const lake = (await bodyDetail(db, String(B + 22)))!; // a USGS gauge
				expect(lake.gauge?.lid).toBe('XTEST2');
				expect(lake.credit).toEqual([CREDITS.nhd, ...nwpsUsgs]);
				const gaugeStructure = (await structureDetail(db, String(B + 11)))!; // the gauge's own marker, on a HydroShare-named canal reach
				expect(gaugeStructure.gauge?.lid).toBe('XTEST1');
				expect(gaugeStructure.credit).toEqual([CREDITS.osm, CREDITS.hydroshare, ...nwpsOnly]);
				expect(dam.credit).toEqual([CREDITS.osm, CREDITS.nhd, CREDITS.hydroshare]); // its reach, and the canal it heads (names from HydroShare), no gauge
				const gaugedDam = (await structureDetail(db, String(B + 12)))!; // an OSM dam with a USGS gauge
				expect(gaugedDam.credit).toEqual([CREDITS.osm, ...nwpsUsgs]);

				// -- gauges ----------------------------------------------------------------------------------------------
				const g1 = (await gaugeDetail(db, 'xtest1'))!;
				expect(g1).toMatchObject({ lid: 'XTEST1', method: 'name', distance_m: 12, usgs: false, flood: null });
				// The record names no USGS site; the card names the canal it measures, so it credits that canal's sources.
				expect(g1.credit).toEqual([...gaugeCredits(false), CREDITS.osm, CREDITS.nhd, CREDITS.hydroshare]);
				const g2 = (await gaugeDetail(db, 'XTEST2'))!;
				expect(g2.usgs).toBe(true);
				expect(g2.credit).toEqual([...gaugeCredits(true), CREDITS.osm]); // and the OSM river it measures
				expect(g2.reading?.facts).toEqual([{ label: 'Stage', value: 3.2, unit: 'ft' }]);
				expect(g2.flood).toMatchObject({ category: 'minor', peak: 'moderate' });
				expect(g2.flood?.since).toBe('2030-07-01T12:00:00.000Z');
				expect(await gaugeSummary(db, 'NOPE9')).toBeNull();

				// -- the map's points: public sources only ---------------------------------------------------------------
				const points = await waterPoints(db);
				expect(points.structures.map((s) => s.id)).toEqual([B + 10, B + 12]); // the gauge-kind structure is the gauge
				expect(points.structures[0]).toMatchObject({ kind: 'dam', minzoom: 11 });
				expect(points.gauges.map((g) => [g.lid, g.flood])).toEqual([['XTEST1', null], ['XTEST2', 'minor']]);
				expect(JSON.stringify(points)).not.toMatch(/Irrigation|IDWR|service area/i);

				// -- the City's notices -----------------------------------------------------------------------------------
				const n = await notices(db);
				expect(n.hazards.map((h) => [h.id, h.kind, h.status, h.name, h.description])).toEqual([
					['102', 'extreme', 'potential', 'Example Diversion', null],
					['101', 'temporary', 'active', 'Fallen tree', 'Tree across the right channel']
				]);
				expect(n.hazards[1]).toMatchObject({ mile_marker: '4.2', lng: -116.21, lat: 43.61 });
				expect(n.ecoli.map((s) => [s.id, s.sampled, s.result, s.history.length])).toEqual([['TESTPOND1', '2030-07-01', 456.7, 1], ['TESTRIVER1', '2030-07-01', 3, 0]]);
				expect(n.ecoli[0]).toMatchObject({ site: 'TESTPOND1 site', units: 'MPN/100 mL', history: [{ sampled: '2030-06-24', result: 12, units: 'MPN/100 mL' }], lng: -116.2, lat: 43.605 });
				expect(n.polled).toEqual({ boise_river_hazards: '2030-07-01T13:00:00.000Z', boise_ecoli: '2030-07-01T12:00:00.000Z' });
				expect(n.republish).toBe('internal');
				throw new Rollback();
			})
		).rejects.toBeInstanceOf(Rollback);
	});
});
