import { gaugeCredits, readingFacts, sourceCredits, type GaugeDetail, type GaugeFlood, type GaugeReading, type GaugeSummary, type WaterPoints } from '#lib/layers/water/water.js';
import { CREDITS } from '#lib/layers/water/water.js';
import { iso, num, parseLid, round, schema, str, type Sql } from './common.js';

/**
 * Gauges for the Water layer (landscape sprint plan v3 §4.2 P4-app): the NWPS gauges the water plugin polls
 * (`nwps_gauges`) and what each measures (`water.gauge`, matched by the network build).
 *
 * - **The latest reading** is the newest `<LID>@<time>` record in `raw.record` (units kcfs and ft become cfs
 *   and ft in words, `readingFacts`).
 * - **The flood category** is the open `river_flood` episode in `evt.event`, if any: NWPS's category for the
 *   gauge's latest observation, at action stage or above. No open episode is not a statement that the river is
 *   safe, and the card says only what it knows.
 * - **The credit** follows the gauge's own record: NOAA NWS always, and USGS only where the metadata we keep
 *   names USGS (`namesUsgs`); the 13 of NWPS's 37 gauges that name none (BSEI1 among them) are credited to NOAA alone.
 *   A gauge's own card also names what it measures, so it credits the sources of that record (OpenStreetMap, NHD,
 *   HydroShare), as the cards of the reach, body or canal themselves do.
 * - Before the plugin's migration: empty, never a 500.
 */

const CATEGORIES = ['action', 'minor', 'moderate', 'major'] as const;
const asCategory = (v: unknown): GaugeFlood['category'] | null => (CATEGORIES as readonly string[]).includes(String(v)) ? (v as GaugeFlood['category']) : null;

/**
 * The newest reading we hold for a gauge. The lookup is by the record's own `lid` and `t`, which water 0003's partial
 * index (`record_nwps_gauge_reading`) serves. The `like` keeps the gauge's metadata record (source_id with no `@`,
 * no `t`) out of the result; `t is not null` keeps it out of the order too (nulls sort first under `desc`).
 */
export async function latestReading(sql: Sql, lid: string): Promise<GaugeReading | null> {
	const [r] = await sql`
		select payload from raw.record
		where source = 'nwps_gauges' and payload->>'lid' = ${lid} and payload->>'t' is not null and source_id like ${lid + '@%'}
		order by payload->>'t' desc limit 1`;
	const p = r?.payload as { pe?: string | null; t?: string; primary?: number | null; secondary?: number | null; units?: (string | null)[] } | undefined;
	if (!p?.t) return null;
	const facts = readingFacts(p.pe ?? null, p.units ?? [], [num(p.primary), num(p.secondary)]);
	return facts.length ? { at: new Date(p.t).toISOString(), facts } : null;
}

/** The open flood episode at a gauge, or null. */
export async function openFlood(sql: Sql, lid: string): Promise<GaugeFlood | null> {
	const [r] = await sql`
		select severity, attributes, lower(declared) as since from evt.event
		where source = 'nwps_gauges' and kind = 'river_flood' and active and attributes->>'lid' = ${lid}
		order by updated_at desc limit 1`;
	const category = asCategory(r?.severity);
	return r && category ? { category, peak: str(r.attributes?.peak_category), since: iso(r.since) } : null;
}

/**
 * Whether NWPS's record for the gauge names USGS: a `usgsId`, or a `dataAttribution` entry that does. BSEI1 (the
 * New York Canal's diversion) has neither: its record holds an empty `usgsId` and an empty `dataAttribution` (read
 * from the stored record, Oct 23, 2026), so it is credited to NOAA alone.
 */
export function namesUsgs(payload: { usgsId?: unknown; dataAttribution?: unknown } | null | undefined): boolean {
	if (!payload) return false;
	if (str(payload.usgsId)) return true;
	return Array.isArray(payload.dataAttribution) && payload.dataAttribution.some((a) => /geological survey|usgs/i.test(JSON.stringify(a ?? '')));
}

async function recordNamesUsgs(sql: Sql, lid: string): Promise<boolean> {
	const [r] = await sql`
		select payload from raw.record
		where source = 'nwps_gauges' and source_id = ${lid} order by last_seen desc limit 1`;
	return namesUsgs(r?.payload);
}

interface GaugeRow {
	lid: string;
	name: string;
	method: 'name' | 'nearest' | 'none';
	distance_m: number | null;
	measures: GaugeSummary['measures'];
	/** The sources behind the measured record's name and shape, for the card's credit. */
	named_from: string[];
}

async function gaugeRow(sql: Sql, lid: string): Promise<GaugeRow | null> {
	const [g] = await sql`
		select g.lid, g.name, g.method, g.distance_m, g.reach_id, g.body_id, g.canal_id,
		       r.name as reach_name, r.kind as reach_kind, r.geometry_from as reach_geometry, r.name_from as reach_name_from,
		       b.name as body_name, b.kind as body_kind, b.geometry_from as body_geometry,
		       c.name as canal_name, c.kind as canal_kind, c.sources as canal_sources
		from water.gauge g
		left join water.reach r on r.id = g.reach_id
		left join water.body b on b.id = g.body_id
		left join water.canal c on c.id = g.canal_id
		where g.lid = ${lid}`;
	if (!g) return null;
	// A canal is what a canal gauge measures; else the body, else the reach.
	const measures: GaugeSummary['measures'] =
		g.canal_id !== null && g.canal_id !== undefined
			? { type: 'canal', id: Number(g.canal_id), name: str(g.canal_name), kind: String(g.canal_kind) }
			: g.body_id !== null && g.body_id !== undefined
				? { type: 'body', id: Number(g.body_id), name: str(g.body_name), kind: String(g.body_kind) }
				: g.reach_id !== null && g.reach_id !== undefined
					? { type: 'reach', id: Number(g.reach_id), name: str(g.reach_name), kind: String(g.reach_kind) }
					: null;
	const named_from: string[] =
		measures?.type === 'canal'
			? (g.canal_sources ?? []).map(String)
			: measures?.type === 'body'
				? [g.body_geometry === 'osm' ? 'osm_waterways' : 'nhd_hr']
				: measures?.type === 'reach'
					? [g.reach_geometry === 'osm' ? 'osm_waterways' : 'nhd_hr', g.reach_name_from === 'hydroshare' ? 'hydroshare_canals' : '']
					: [];
	return {
		lid: String(g.lid),
		name: String(g.name),
		method: g.method,
		distance_m: g.distance_m === null ? null : round(Number(g.distance_m), 0),
		measures,
		named_from
	};
}

/** A gauge for a card: what it measures, its latest reading and any open flood episode. Null when unknown. */
export async function gaugeSummary(sql: Sql, lidRaw: string): Promise<GaugeSummary | null> {
	const lid = parseLid(lidRaw);
	if (!(await schema(sql)).network) return null;
	const g = await gaugeRow(sql, lid);
	if (!g) return null;
	const [reading, flood, usgs] = await Promise.all([latestReading(sql, lid), openFlood(sql, lid), recordNamesUsgs(sql, lid)]);
	return { lid: g.lid, name: g.name, measures: g.measures, reading, flood, usgs };
}

/** `GET /api/water/gauge/<lid>`. */
export async function gaugeDetail(sql: Sql, lidRaw: string): Promise<GaugeDetail | null> {
	const lid = parseLid(lidRaw);
	if (!(await schema(sql)).network) return null;
	const g = await gaugeRow(sql, lid);
	if (!g) return null;
	const [reading, flood, usgs] = await Promise.all([latestReading(sql, lid), openFlood(sql, lid), recordNamesUsgs(sql, lid)]);
	return { lid: g.lid, name: g.name, measures: g.measures, reading, flood, method: g.method, distance_m: g.distance_m, usgs, credit: [...gaugeCredits(usgs), ...sourceCredits(g.named_from)] };
}

/** `GET /api/water/points`: every structure and gauge the map draws. */
export async function waterPoints(sql: Sql): Promise<WaterPoints> {
	const credit = [CREDITS.osm, CREDITS.nhd, CREDITS.nwps];
	if (!(await schema(sql)).network) return { structures: [], gauges: [], credit };
	const [structures, gauges, floods] = await Promise.all([
		sql`
			select id, kind, name, minzoom, ST_X(geom) as lng, ST_Y(geom) as lat
			from water.structure where kind <> 'gauge' order by id`,
		sql`select lid, name, ST_X(geom) as lng, ST_Y(geom) as lat from water.gauge order by lid`,
		sql`
			select attributes->>'lid' as lid, severity from evt.event
			where source = 'nwps_gauges' and kind = 'river_flood' and active`
	]);
	const flood = new Map<string, GaugeFlood['category']>();
	for (const f of floods) {
		const c = asCategory(f.severity);
		if (c && f.lid) flood.set(String(f.lid), c);
	}
	return {
		structures: structures.map((s) => ({ id: Number(s.id), kind: s.kind, name: str(s.name), minzoom: Number(s.minzoom), lng: round(Number(s.lng), 6), lat: round(Number(s.lat), 6) })),
		gauges: gauges.map((g) => ({ lid: String(g.lid), name: String(g.name), lng: round(Number(g.lng), 6), lat: round(Number(g.lat), 6), flood: flood.get(String(g.lid)) ?? null })),
		credit
	};
}
