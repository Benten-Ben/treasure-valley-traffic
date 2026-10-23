/**
 * What the water APIs share (landscape sprint plan v3 §4.2 P4-app): the SQL handle, the checks that a table is
 * there (before the water plugin's migration every answer is empty, never a 500), and small readers.
 *
 * Which rows are internal: IDWR's service areas (`water.canal_org`) have no licence stated, so only the card
 * of a canal reads them, on this tailnet map; they are never in the tiles, the bake or `/api/water/points`.
 * The City of Boise's hazards and E. coli results have none either (republish internal, a courtesy note due).
 */

/** A postgres.js tagged template, or a test's stand-in. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Sql = (strings: TemplateStringsArray, ...values: any[]) => Promise<any[]>;

export class BadRequest extends Error {}

/** The tables the hydrography answers read (plugins/water/migrations/0001). */
export interface Schema {
	/** reach, body, structure, canal and gauge: the drawn network. */
	network: boolean;
	/** reach_evidence. */
	evidence: boolean;
	/** canal_org: IDWR's service areas (internal). */
	orgs: boolean;
}

export async function schema(sql: Sql): Promise<Schema> {
	const [r] = await sql`
		select to_regclass('water.reach') is not null and to_regclass('water.body') is not null
		       and to_regclass('water.structure') is not null and to_regclass('water.canal') is not null
		       and to_regclass('water.gauge') is not null as network,
		       to_regclass('water.reach_evidence') is not null as evidence,
		       to_regclass('water.canal_org') is not null as orgs`;
	return { network: Boolean(r?.network), evidence: Boolean(r?.evidence), orgs: Boolean(r?.orgs) };
}

/** A whole number id from a path: digits only, within a double's exact range. */
export function parseId(raw: string | undefined): number {
	if (!raw || !/^\d{1,16}$/.test(raw)) throw new BadRequest('The id must be a whole number');
	const n = Number(raw);
	if (!Number.isSafeInteger(n)) throw new BadRequest('The id must be a whole number');
	return n;
}

/** A gauge's location id (NWS "LID"): letters and digits, as `BSEI1`. */
export function parseLid(raw: string | undefined): string {
	if (!raw || !/^[A-Za-z0-9]{2,10}$/.test(raw)) throw new BadRequest('The gauge id must be 2 to 10 letters and digits');
	return raw.toUpperCase();
}

export const num = (v: unknown): number | null => (v === null || v === undefined ? null : Number(v));
export const str = (v: unknown): string | null => (v === null || v === undefined || String(v).trim() === '' ? null : String(v));
export const iso = (v: unknown): string | null => (v === null || v === undefined ? null : new Date(v as string).toISOString());
export const round = (v: number, d: number) => Math.round(v * 10 ** d) / 10 ** d;

/** The status a thrown error means for a route: a bad id is a 400, anything else is the route's to raise. */
export const isBadRequest = (e: unknown): e is BadRequest => e instanceof BadRequest;
