import {
	CREDITS,
	gaugeCredits,
	reachCredits,
	sourceCredits,
	type BodyDetail,
	type CanalDetail,
	type Evidence,
	type ReachDetail,
	type StructureDetail
} from '#lib/layers/water/water.js';
import { gaugeSummary } from './gauges.js';
import { num, parseId, round, schema, str, type Sql } from './common.js';

/**
 * The drawn network's cards (landscape sprint plan v3 §4.2 P4-app), from the water plugin's tables
 * (`water.reach`, `water.body`, `water.structure`, `water.canal` and what hangs off them):
 *
 * - `GET /api/water/reach/<id>`: a reach (kind, name and where the name came from, flow, width and how we know
 *   it, where its line came from and what agrees with it) and, when it belongs to a named canal, the canal
 *   (length, what its head leaves, the structure at its head, the gauge that measures it with the latest
 *   reading) and the **irrigation service areas it runs through**;
 * - `GET /api/water/body/<id>`: a lake, pond, reservoir, wetland and the rest;
 * - `GET /api/water/structure/<id>`: a dam, weir, gate, waterfall or spring.
 *
 * **Internal:** the service areas come from IDWR's layer, which states no licence, so they are read here, for a
 * canal's card on this tailnet map, and nowhere else: never an export, a tile or `/api/water/points`
 * (`water.canal_org` is internal). A service area is where an organization may deliver water rights; it doesn't
 * say who runs the canal, and the API never calls it that.
 *
 * Before the plugin's migration, or for an id the build no longer has: null (the route answers 404).
 */

const evidenceRank: Record<Evidence['role'], number> = { geometry: 0, attributes: 1, name: 2, agrees: 3 };

async function canalDetail(sql: Sql, id: number, orgs: boolean): Promise<CanalDetail | null> {
	const [c] = await sql`
		select c.id, c.name, c.kind, c.length_m, c.piped_m, c.reaches, c.source_kind, c.sources, c.gauge_lid,
		       c.head_structure_id, hs.kind as head_kind, hs.name as head_name,
		       coalesce(sc.name, sr.name) as source_name, sc.sources as source_sources,
		       case when sc.id is null then sr.name_from end as source_name_from
		from water.canal c
		left join water.structure hs on hs.id = c.head_structure_id
		left join water.canal sc on sc.id = c.source_canal_id
		left join water.reach sr on sr.id = c.source_reach_id
		where c.id = ${id}`;
	if (!c) return null;
	const areas = orgs
		? await sql`select name, share, at_head from water.canal_org where canal_id = ${id} order by share desc, name`
		: [];
	let lid = str(c.gauge_lid);
	if (!lid) {
		const [g] = await sql`select lid from water.gauge where canal_id = ${id} order by lid limit 1`;
		lid = str(g?.lid);
	}
	return {
		id: Number(c.id),
		name: String(c.name),
		kind: c.kind,
		length_m: round(Number(c.length_m), 0),
		piped_m: round(Number(c.piped_m ?? 0), 0),
		reaches: Number(c.reaches),
		source: {
			kind: c.source_kind,
			name: str(c.source_name),
			// What the name "Leaves <name>" rests on: the source canal's sources, or the source reach's name source.
			sources: (c.source_sources ?? []).map(String),
			name_from: c.source_name_from ?? null
		},
		head_structure: c.head_structure_id === null || c.head_structure_id === undefined ? null : { id: Number(c.head_structure_id), kind: c.head_kind, name: str(c.head_name) },
		sources: (c.sources ?? []).map(String),
		gauge: lid ? await gaugeSummary(sql, lid) : null,
		service_areas: areas.map((a) => ({ name: String(a.name), share: round(Number(a.share), 3), at_head: Boolean(a.at_head) }))
	};
}

/** `GET /api/water/reach/<id>`. */
export async function reachDetail(sql: Sql, idRaw: string): Promise<ReachDetail | null> {
	const id = parseId(idRaw);
	const s = await schema(sql);
	if (!s.network) return null;
	const [r] = await sql`
		select id, kind, name, name_from, flow, piped, width_m, width_from, stream_order, geometry_from, confirmed,
		       length_m, canal_id
		from water.reach where id = ${id}`;
	if (!r) return null;
	const evidence: Evidence[] = s.evidence
		? (await sql`select source, source_id, role, share, distance_m from water.reach_evidence where reach_id = ${id}`)
				.map((e) => ({ source: e.source, source_id: String(e.source_id), role: e.role, share: num(e.share), distance_m: e.distance_m === null || e.distance_m === undefined ? null : round(Number(e.distance_m), 1) }))
				.sort((a, b) => evidenceRank[a.role as Evidence['role']] - evidenceRank[b.role as Evidence['role']] || (b.share ?? 0) - (a.share ?? 0))
		: [];
	const canal = r.canal_id === null || r.canal_id === undefined ? null : await canalDetail(sql, Number(r.canal_id), s.orgs);
	// A gauge on the reach itself (a river), when the canal's isn't the one.
	let gauge = null;
	if (!canal?.gauge) {
		const [g] = await sql`select lid from water.gauge where reach_id = ${id} order by lid limit 1`;
		gauge = g ? await gaugeSummary(sql, String(g.lid)) : null;
	}
	const detail: ReachDetail = {
		id: Number(r.id),
		kind: r.kind,
		name: str(r.name),
		name_from: r.name_from ?? null,
		flow: r.flow,
		piped: Boolean(r.piped),
		width_m: round(Number(r.width_m), 2),
		width_from: r.width_from,
		stream_order: num(r.stream_order),
		geometry_from: r.geometry_from,
		confirmed: Boolean(r.confirmed),
		length_m: round(Number(r.length_m), 0),
		evidence,
		canal,
		gauge,
		credit: []
	};
	detail.credit = reachCredits(detail);
	return detail;
}

/** `GET /api/water/body/<id>`. */
export async function bodyDetail(sql: Sql, idRaw: string): Promise<BodyDetail | null> {
	const id = parseId(idRaw);
	if (!(await schema(sql)).network) return null;
	const [b] = await sql`
		select id, kind, name, intermittent, area_m2, geometry_from, confirmed, osm_type, osm_id, gauge_lid,
		       -- the wetland columns arrive with water 0004: before it every body reads as not thin
		       coalesce((to_jsonb(b) ->> 'thin')::boolean, false) as thin
		from water.body b where id = ${id}`;
	if (!b) return null;
	let lid = str(b.gauge_lid);
	if (!lid) {
		const [g] = await sql`select lid from water.gauge where body_id = ${id} order by lid limit 1`;
		lid = str(g?.lid);
	}
	const osmType = ({ n: 'node', w: 'way', r: 'relation' } as Record<string, string>)[String(b.osm_type)];
	const gauge = lid ? await gaugeSummary(sql, lid) : null;
	const credit: string[] = [];
	if (b.geometry_from === 'osm') credit.push(CREDITS.osm);
	if (b.geometry_from === 'nwi') credit.push(CREDITS.nwi);
	else credit.push(CREDITS.nhd);
	if (gauge) credit.push(...gaugeCredits(gauge.usgs));
	return {
		id: Number(b.id),
		kind: b.kind,
		name: str(b.name),
		intermittent: Boolean(b.intermittent),
		area_m2: round(Number(b.area_m2), 0),
		geometry_from: b.geometry_from,
		confirmed: Boolean(b.confirmed),
		thin: Boolean(b.thin),
		osm: osmType && b.osm_id !== null && b.osm_id !== undefined ? `${osmType} ${b.osm_id}` : null,
		gauge,
		credit
	};
}

/** `GET /api/water/structure/<id>`. */
export async function structureDetail(sql: Sql, idRaw: string): Promise<StructureDetail | null> {
	const id = parseId(idRaw);
	if (!(await schema(sql)).network) return null;
	const [s] = await sql`
		select s.id, s.kind, s.name, s.source, s.gauge_lid, s.reach_id, r.kind as reach_kind, r.name as reach_name,
		       r.geometry_from as reach_geometry, r.name_from as reach_name_from
		from water.structure s left join water.reach r on r.id = s.reach_id
		where s.id = ${id}`;
	if (!s) return null;
	const heads = await sql`select id, name, sources from water.canal where head_structure_id = ${id} order by length_m desc, id limit 12`;
	const gauge = s.gauge_lid ? await gaugeSummary(sql, String(s.gauge_lid)) : null;
	// The structure's own source, and the sources of the records it lists: the reach it is on and the canals it heads.
	const credit: string[] = sourceCredits([
		s.source === 'nwps_gauges' ? null : s.source === 'nhd_hr' ? 'nhd_hr' : 'osm_waterways',
		s.reach_id === null || s.reach_id === undefined ? null : s.reach_geometry === 'osm' ? 'osm_waterways' : 'nhd_hr',
		s.reach_name_from === 'hydroshare' ? 'hydroshare_canals' : null,
		...heads.flatMap((h) => (h.sources ?? []).map(String))
	]);
	// A gauge's reading is credited as its own card credits it (NWPS, and USGS where its record names a site).
	if (gauge || s.source === 'nwps_gauges') credit.push(...gaugeCredits(gauge?.usgs ?? false));
	return {
		id: Number(s.id),
		kind: s.kind,
		name: str(s.name),
		source: s.source,
		reach: s.reach_id === null || s.reach_id === undefined ? null : { id: Number(s.reach_id), kind: s.reach_kind, name: str(s.reach_name) },
		head_of: heads.map((h) => ({ id: Number(h.id), name: String(h.name) })),
		gauge,
		credit
	};
}
