import type postgres from 'postgres';

/**
 * The paving card API (landscape sprint plan §4.2 P8-app): one parking lot or one paving way, for the
 * Lanes layer's card. Reads the roads plugin's OpenStreetMap tables (`roads.osm_parking`,
 * `roads.osm_paving`, migration 0002), so a card is always OpenStreetMap's, with its credit.
 *
 * Ids: a lot is `w<osm id>` or `r<osm id>` (a closed way or a multipolygon, as OSM has it); a way is its
 * `osm_id`. Estimates are marked as such in the card: a stall count from area, a surface and a width
 * the tags don't give.
 */

export type Sql = postgres.Sql;

/** Area per stall used for the estimate. Not stated on the card: the card says "estimated from area". */
export const STALL_M2 = 30;
const M2_PER_ACRE = 4046.8564224;

export const PAVING_CREDIT = '© OpenStreetMap contributors';

export interface LotCard {
	kind: 'lot';
	osm: string;
	name: string | null;
	operator: string | null;
	access: string | null;
	fee: string | null;
	area_m2: number;
	acres: number;
	/** The tagged capacity, or null. */
	capacity: number | null;
	/** The estimate from area, when the capacity isn't tagged; null when there's no area to go on. */
	stalls_estimated: number | null;
	material: string;
	material_estimated: boolean;
	credit: string;
}

export interface WayCard {
	kind: 'way';
	osm: string;
	way_kind: string;
	surface: string | null;
	surface_estimated: boolean;
	width_m: number;
	width_estimated: boolean;
	length_m: number;
	credit: string;
}

export type PavingCard = LotCard | WayCard;

/** A lot's card from its row (pure: the database's values in, the card out). */
export function lotCard(r: {
	osm_type: string;
	osm_id: number | string;
	name: string | null;
	operator: string | null;
	access: string | null;
	fee: string | null;
	area_m2: number;
	capacity: number | null;
	material: string;
	material_source: string | null;
}): LotCard {
	const estimated = Math.round(r.area_m2 / STALL_M2);
	return {
		kind: 'lot',
		osm: `${r.osm_type}${r.osm_id}`,
		name: r.name,
		operator: r.operator,
		access: r.access,
		fee: r.fee,
		area_m2: round(r.area_m2),
		acres: round(r.area_m2 / M2_PER_ACRE, 2),
		capacity: r.capacity,
		stalls_estimated: r.capacity == null && r.area_m2 > 0 ? estimated : null,
		material: r.material,
		material_estimated: r.material_source === 'default',
		credit: PAVING_CREDIT
	};
}

/** A way's card from its row (pure). */
export function wayCard(r: {
	osm_id: number | string;
	kind: string;
	surface: string | null;
	material_source: string | null;
	width_m: number | null;
	width_est_m: number;
	width_source: string;
	length_m: number;
}): WayCard {
	return {
		kind: 'way',
		osm: String(r.osm_id),
		way_kind: r.kind,
		surface: r.surface,
		surface_estimated: r.material_source === 'default',
		width_m: round(r.width_m ?? r.width_est_m, 1),
		width_estimated: r.width_m == null || r.width_source === 'default',
		length_m: round(r.length_m, 1),
		credit: PAVING_CREDIT
	};
}

function round(n: number, places = 0): number {
	const f = 10 ** places;
	return Math.round(n * f) / f;
}

/** Parses the route's id: `w123` or `r123` for a lot, digits for a way; anything else is null. */
export function parseLotId(id: string): { osm_type: 'w' | 'r'; osm_id: string } | null {
	const m = /^([wr])(\d{1,18})$/.exec(id);
	return m ? { osm_type: m[1] as 'w' | 'r', osm_id: m[2] } : null;
}

export function parseWayId(id: string): string | null {
	return /^\d{1,18}$/.test(id) ? id : null;
}

/**
 * The card for one lot or way, or null when there's no such object or the paving tables aren't
 * there yet (before migration 0002 is applied, the card API is empty rather than an error).
 */
export async function pavingCard(sql: Sql, kind: 'lot' | 'way', id: string): Promise<PavingCard | null> {
	const table = kind === 'lot' ? 'roads.osm_parking' : 'roads.osm_paving';
	const [exists] = await sql<{ present: boolean }[]>`select to_regclass(${table}) is not null as present`;
	if (!exists?.present) return null;
	if (kind === 'lot') {
		const p = parseLotId(id);
		if (!p) return null;
		const [r] = await sql`
			select osm_type, osm_id, name, operator, access, fee, area_m2, capacity, material, material_source
			from roads.osm_parking
			where osm_type = ${p.osm_type} and osm_id = ${p.osm_id} and active`;
		return r ? lotCard(r as never) : null;
	}
	const w = parseWayId(id);
	if (!w) return null;
	const [r] = await sql`
		select osm_id, kind, surface, material_source, width_m, width_est_m, width_source,
			ST_Length(geom::geography) as length_m
		from roads.osm_paving
		where osm_id = ${w} and active`;
	return r ? wayCard(r as never) : null;
}
