/**
 * The crop fields' API (landscape sprint P3-app), from the farm plugin's tables (plugins/farm/README.md,
 * "Crop fields"):
 *
 * - `GET /api/farm/year`: the crop year the map shows (`farm.crop_year`: the newest year of the newest CSB
 *   edition loaded, "2025 (USDA's newest)"), the years the year switcher offers and the ones with a z8-10 cut
 *   of their own;
 * - `GET /api/farm/fields/<id>`: one field's card: acres, county, its crop in each year, how sure USDA's map is
 *   (the CDL agreement), its July state, and the growth and plat flags as `farm-derive` stored them.
 *
 * Fields are estimated outlines (CSB models them from 30 m pixels) and are never joined to parcels or owners.
 * Before the farm migration, or before a load, both answer "not built" and "no such field", never a 500.
 */

/** A postgres.js tagged template, or a test's stand-in. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Sql = (strings: TemplateStringsArray, ...values: any[]) => Promise<any[]>;

export type Growth = 'farmed' | 'built_over' | 'being_built';
export type JulyState = 'green' | 'growing' | 'bare';

export interface YearInfo {
	/** false before the migration or the first load: nothing else is set. */
	built: boolean;
	/** The newest crop year ("2025"), its label ("2025 (USDA's newest)"), and the edition's first year. */
	year: number | null;
	label: string | null;
	first_year: number | null;
	edition: string | null;
}

export interface FieldYear {
	year: number;
	code: number;
	name: string | null;
	/** The crop group (`farm.crop_class.grp`), or 'other' for a code we have no class for. */
	group: string;
}

export interface FieldPlat {
	approved: number;
	pending: number;
	built: number;
	plats: { id: number; name: string | null; status: string; applied_on: string | null; share: number }[];
}

export interface FieldCard {
	id: number;
	acres: number | null;
	county: string | null;
	/** One entry per year of the edition's window, oldest first (the last is the crop year). */
	years: FieldYear[];
	/** The CDL's agreement with the field's code, per year held (0-1). */
	agree: Record<string, number>;
	july: { year: number; state: JulyState; ndvi: number | null } | null;
	growth: Growth | null;
	growth_detail: { developed_by?: number; permits?: number | null; permit_years?: (number | null)[]; unconfirmed?: string; [k: string]: unknown } | null;
	plat: FieldPlat | null;
	/** Closed by a newer edition: the date, else null (current). */
	valid_to: string | null;
	/** A point inside the field and its box, for the deep link. */
	centre: [number, number];
	bbox: [number, number, number, number];
	/** The tiles' credit, licence and republish, as the layer's build recorded them. */
	credit: string | null;
	license: string | null;
}

const has = async (sql: Sql, name: string): Promise<boolean> => (await sql`select to_regclass(${name}) is not null as ok`)[0]?.ok === true;

/** The crop year and the edition behind it; `built: false` before the migration or a load. */
export async function yearInfo(sql: Sql): Promise<YearInfo> {
	const none: YearInfo = { built: false, year: null, label: null, first_year: null, edition: null };
	if (!(await has(sql, 'farm.crop_year'))) return none;
	const [r] = await sql`select year, label, first_year, edition from farm.crop_year`;
	if (!r) return none;
	return { built: true, year: Number(r.year), label: String(r.label), first_year: Number(r.first_year), edition: String(r.edition) };
}

const num = (x: unknown): number | null => (x === null || x === undefined || Number.isNaN(Number(x)) ? null : Number(x));

/** One field, or null when there is none (or the farm tables aren't here). `id` is `farm.field.id`. */
export async function fieldCard(sql: Sql, id: number): Promise<FieldCard | null> {
	if (!Number.isSafeInteger(id) || id < 1 || !(await has(sql, 'farm.field'))) return null;
	const [f] = await sql`
		select f.id, f.acres, f.county, f.first_year, f.crops, f.agree, f.july, f.growth, f.growth_detail, f.plat,
		       f.valid_to::text as valid_to,
		       ST_X(ST_PointOnSurface(f.geom)) as lng, ST_Y(ST_PointOnSurface(f.geom)) as lat,
		       ST_XMin(f.geom) as w, ST_YMin(f.geom) as s, ST_XMax(f.geom) as e, ST_YMax(f.geom) as n
		from farm.field f where f.id = ${id}`;
	if (!f) return null;
	const classes = await sql`
		select c.code, c.name, c.grp from farm.crop_class c
		where c.code in (select unnest(g.crops) from farm.field g where g.id = ${id})`;
	const byCode = new Map<number, { name: string; grp: string }>(classes.map((c) => [Number(c.code), { name: String(c.name), grp: String(c.grp) }]));
	const first = Number(f.first_year);
	const years: FieldYear[] = (f.crops as number[]).map((code, i) => {
		const c = byCode.get(Number(code));
		return { year: first + i, code: Number(code), name: c?.name ?? null, group: c?.grp ?? 'other' };
	});
	let credit: string | null = null;
	let license: string | null = null;
	if (await has(sql, 'core.layer_version')) {
		const [v] = await sql`select credit, license from core.layer_version where layer = 'farm.crop_fields' order by id desc limit 1`;
		credit = v?.credit ?? null;
		license = v?.license ?? null;
	}
	const july = f.july && typeof f.july === 'object' && f.july.state ? { year: Number(f.july.year), state: f.july.state as JulyState, ndvi: num(f.july.ndvi) } : null;
	return {
		id: Number(f.id),
		acres: num(f.acres),
		county: f.county ?? null,
		years,
		agree: Object.fromEntries(Object.entries((f.agree ?? {}) as Record<string, unknown>).map(([y, v]) => [y, Number(v)])),
		july,
		growth: (f.growth as Growth | null) ?? null,
		growth_detail: f.growth_detail ?? null,
		plat: f.plat ?? null,
		valid_to: f.valid_to ?? null,
		centre: [Number(f.lng), Number(f.lat)],
		bbox: [Number(f.w), Number(f.s), Number(f.e), Number(f.n)],
		credit,
		license
	};
}
