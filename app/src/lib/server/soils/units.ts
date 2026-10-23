/**
 * The soil APIs (landscape sprint P1-app), from the soils plugin's tables (plugins/soils/README.md):
 *
 * - `GET /api/soils/at?lng=&lat=`: the map unit at a point, `{ unit: null }` before the migration, before a
 *   load, outside the survey or in the sea;
 * - `GET /api/soils/mapunit/<mukey>`: the soil card: the dominant component and its share, the other
 *   components ("62% Purdam silt loam, 38% Power silt loam"), texture, drainage, the shallowest restriction,
 *   farmland class, the hydric rating as a row (owner, Oct 22: no map layer for it), the survey area and its
 *   version, and the credit.
 *
 * It is mapped soil, never a site test, and not for regulatory decisions: the card says so. Before the soils
 * migration both answer empty (a null unit, a 404), never a 500.
 */

/** A postgres.js tagged template, or a test's stand-in. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Sql = (strings: TemplateStringsArray, ...values: any[]) => Promise<any[]>;

/** The wording the card and the legend carry, and the credit when the build recorded none. */
export const REGULATORY = 'Mapped soil, not a site test; not for regulatory decisions';
export const CREDIT = 'Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)';

export interface UnitAt {
	mukey: string;
	symbol: string | null;
	name: string | null;
	/** NRCS's NOTCOM, "No Digital Data Available": not surveyed. */
	surveyed: boolean;
}

export interface SoilComponent {
	name: string;
	/** Percent of the map unit (NRCS's representative value), or null. */
	percent: number | null;
	major: boolean;
	/** The surface (topmost mineral) horizon's texture, "Silt loam". */
	texture: string | null;
	drainage: string | null;
	slope: number | null;
	hydric: string | null;
	/** "62% Purdam silt loam". */
	label: string;
}

export interface SoilRestriction {
	kind: string;
	/** Depth to its top, cm. */
	top_cm: number | null;
	hard: string | null;
}

export interface SoilCard {
	mukey: string;
	symbol: string | null;
	name: string | null;
	kind: string | null;
	/** false for NRCS's "No Digital Data Available" area: nothing else is set. */
	surveyed: boolean;
	area_ha: number | null;
	dominant: SoilComponent | null;
	/** The dominant component's share of the map unit, percent. */
	dominant_share: number | null;
	/** Every component, largest first (the dominant included). */
	components: SoilComponent[];
	/** "62% Purdam silt loam, 38% Power silt loam", or null when there is only one. */
	mix: string | null;
	drainage: string | null;
	/** The hydrologic group of the dominant condition: "B", "B/D". */
	hydrologic_group: string | null;
	/** A dual group (A/D, B/D, C/D): D where undrained. */
	hydrologic_dual: boolean;
	farmland: string | null;
	/** Available water in the top metre, cm. */
	water_cm: number | null;
	/** The class of that figure under our scaling to the top metre (0 palest to 4). */
	water_class: number | null;
	restriction: SoilRestriction | null;
	/** The dominant component's hydric rating, as NRCS gives it ("Yes", "No", "Partially hydric"), and the percent of hydric components. */
	hydric: string | null;
	hydric_percent: number | null;
	slope_percent: number | null;
	survey: { symbol: string; name: string; saverest: string | null; version: number | null; scale: number | null } | null;
	/** The tiles' credit, licence and republish, as the layer's build recorded them. */
	credit: string;
	license: string | null;
	/** A point inside the map unit's largest polygon, and its box, for flying there. */
	centre: [number, number] | null;
	note: string;
}

const has = async (sql: Sql, name: string): Promise<boolean> => (await sql`select to_regclass(${name}) is not null as ok`)[0]?.ok === true;
const num = (x: unknown): number | null => (x === null || x === undefined || Number.isNaN(Number(x)) ? null : Number(x));
const str = (x: unknown): string | null => (x === null || x === undefined || x === '' ? null : String(x));

/** The map unit at a point, or `null` (not surveyed here, the sea, no soils tables). */
export async function unitAt(sql: Sql, lng: number, lat: number): Promise<UnitAt | null> {
	if (!Number.isFinite(lng) || !Number.isFinite(lat) || Math.abs(lng) > 180 || Math.abs(lat) > 90) return null;
	if (!(await has(sql, 'soils.polygon'))) return null;
	const [r] = await sql`
		select m.mukey, m.musym, m.muname, t.misc
		from soils.polygon p
		join soils.map_unit m on m.mukey = p.mukey
		left join soils.ground_type t on t.id = m.ground_type
		where p.geom && ST_SetSRID(ST_MakePoint(${lng}, ${lat}), 4326) and ST_Intersects(p.geom, ST_SetSRID(ST_MakePoint(${lng}, ${lat}), 4326))
		order by p.id
		limit 1`;
	if (!r) return null;
	return { mukey: String(r.mukey), symbol: str(r.musym), name: str(r.muname), surveyed: r.misc !== 'nodata' };
}

/** What the card says about the water a soil holds, by class: our scaling of NRCS's classes to the top metre. */
export const WATER_CLASS_TEXT = ['under 5 cm', '5 to 10 cm', '10 to 15 cm', '15 to 20 cm', '20 cm or more'] as const;

const lower = (s: string | null): string => (s ? s.charAt(0).toLowerCase() + s.slice(1) : '');

/** "62% Purdam silt loam". */
export function componentLabel(c: { name: string; percent: number | null; texture: string | null }): string {
	const tex = c.texture ? ` ${lower(c.texture)}` : '';
	return `${c.percent === null ? '' : `${Math.round(c.percent)}% `}${c.name}${tex}`;
}

/** The mix of components: "62% Purdam silt loam, 38% Power silt loam" (the dominant first), null when there is one. */
export function mixText(components: readonly Pick<SoilComponent, 'label'>[]): string | null {
	return components.length > 1 ? components.map((c) => c.label).join(', ') : null;
}

/** One map unit's card, or null when there is none (or the soils tables aren't here). */
export async function mapUnitCard(sql: Sql, mukey: string): Promise<SoilCard | null> {
	if (!/^\d{1,9}$/.test(mukey) || !(await has(sql, 'soils.map_unit'))) return null;
	const [m] = await sql`
		select m.mukey, m.musym, m.muname, m.mukind, m.farmlndcl, m.slopegraddcp, m.aws0100wta, m.drclassdcd, m.hydgrpdcd,
		       m.hydclprs, m.restr_kind, m.restr_top_cm, m.restr_hard, m.c_aws, m.hsg_dual, m.area_in_box_ha, m.dom_cokey,
		       t.misc,
		       a.areasymbol, a.areaname, a.saverest::text as saverest, a.saversion, a.scale
		from soils.map_unit m
		left join soils.ground_type t on t.id = m.ground_type
		left join soils.survey_area a on a.areasymbol = m.areasymbol
		where m.mukey = ${mukey}`;
	if (!m) return null;
	const [vers] = (await has(sql, 'core.layer_version'))
		? await sql`select credit, license from core.layer_version where layer = 'soils.units' order by id desc limit 1`
		: [];
	const base = {
		mukey: String(m.mukey),
		symbol: str(m.musym),
		name: str(m.muname),
		kind: str(m.mukind),
		credit: str(vers?.credit) ?? CREDIT,
		license: str(vers?.license),
		note: REGULATORY,
		survey: m.areasymbol
			? { symbol: String(m.areasymbol), name: String(m.areaname), saverest: str(m.saverest), version: num(m.saversion), scale: num(m.scale) }
			: null
	};
	const [where] = await sql`
		select ST_X(ST_PointOnSurface(p.geom)) as lng, ST_Y(ST_PointOnSurface(p.geom)) as lat
		from soils.polygon p where p.mukey = ${mukey} order by p.area_in_box_m2 desc nulls last, p.id limit 1`;
	const centre: [number, number] | null = where ? [Number(where.lng), Number(where.lat)] : null;
	if (m.misc === 'nodata') {
		return {
			...base,
			surveyed: false,
			area_ha: num(m.area_in_box_ha),
			dominant: null,
			dominant_share: null,
			components: [],
			mix: null,
			drainage: null,
			hydrologic_group: null,
			hydrologic_dual: false,
			farmland: null,
			water_cm: null,
			water_class: null,
			restriction: null,
			hydric: null,
			hydric_percent: null,
			slope_percent: null,
			centre
		};
	}
	const rows = await sql`
		select c.cokey, c.compname, c.comppct_r, c.majcomp, c.drainagecl, c.slope_r, c.hydricrating,
		       (select h.texture from soils.horizon h
		         where h.cokey = c.cokey and coalesce(h.hzname, '') !~ '^O' and h.texture is not null
		         order by h.top_cm nulls last, h.chkey limit 1) as texture
		from soils.component c where c.mukey = ${mukey}
		order by c.comppct_r desc nulls last, c.majcomp desc, c.cokey`;
	const components: SoilComponent[] = rows.map((c) => {
		const part = { name: String(c.compname), percent: num(c.comppct_r), texture: str(c.texture) };
		return {
			...part,
			major: c.majcomp === true,
			drainage: str(c.drainagecl),
			slope: num(c.slope_r),
			hydric: str(c.hydricrating),
			label: componentLabel(part)
		};
	});
	const domRow = rows.find((c) => c.cokey === m.dom_cokey);
	const dominant = (domRow ? components[rows.indexOf(domRow)] : components[0]) ?? null;
	// The mix lists the dominant first, then the others by share.
	const ordered = dominant ? [dominant, ...components.filter((c) => c !== dominant)] : components;
	const restriction: SoilRestriction | null = m.restr_kind ? { kind: String(m.restr_kind), top_cm: num(m.restr_top_cm), hard: str(m.restr_hard) } : null;
	return {
		...base,
		surveyed: true,
		area_ha: num(m.area_in_box_ha),
		dominant,
		dominant_share: dominant?.percent ?? null,
		components: ordered,
		mix: mixText(ordered),
		drainage: str(m.drclassdcd) ?? dominant?.drainage ?? null,
		hydrologic_group: str(m.hydgrpdcd),
		hydrologic_dual: m.hsg_dual === true,
		farmland: str(m.farmlndcl),
		water_cm: num(m.aws0100wta),
		water_class: num(m.c_aws),
		restriction,
		hydric: dominant?.hydric ?? null,
		hydric_percent: num(m.hydclprs),
		slope_percent: num(m.slopegraddcp),
		centre
	};
}
