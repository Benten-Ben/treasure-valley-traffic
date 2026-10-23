import { asState, BASES, type Season, type SeasonBasis, type SeasonCanal, type SeasonState } from '#lib/base/water/season.js';
import { iso, num, str, type Sql } from './common.js';

/**
 * The canal season for the baked reaches and the canal card (landscape sprint plan v3 §4.2 P5, P5-app):
 * `GET /api/water/season`, from the lifecycles the water plugin's `canal_season` source keeps in `evt.event`
 * (plugins/water/README.md, "The canal season"): each canal's current span (`declared` holds now), its state
 * (`severity`: on, off or unknown), what it rests on (`basis`: its gauge, its district's dates, IDWR's legal
 * window, or always) and the credits, with the ids of the canal's reaches (`water.reach`) by state, which is
 * what the map sets as feature-state `season` on the baked reaches.
 *
 * - **A canal with no current lifecycle** (none was derived, or its span has not begun or has ended) reads
 *   unknown, with basis `none`: the plugin's rule ("Nothing: no lifecycle, which reads as unknown").
 * - **Internal:** a lifecycle on IDWR's legal season of use is IDWR's (no licence stated), `republish: internal`,
 *   so the whole answer says internal while any canal rests on it. It is for this tailnet map, credited; never in
 *   the bake, the tiles or the public data.
 * - **Before the plugin's migration** (water 0002, or core's `evt.event`), or with no water build: an empty season,
 *   never a 500.
 * - The answer carries no clock, so its ETag holds until a lifecycle changes.
 */

const LICENSE =
	"derived: NWPS readings (public domain), the water network (ODbL; HydroShare's canal names CC BY 4.0), the districts' dates (cited), and IDWR's season of use (no licence stated: internal)";
/** The republish classes, loosest to strictest (core's `manifest.REPUBLISH`). */
const REPUBLISH = ['yes', 'aggregates', 'internal', 'no'] as const;
const strictest = (a: string, b: string) => (REPUBLISH.indexOf(b as never) > REPUBLISH.indexOf(a as never) ? b : a);
/** Longest text kept from a lifecycle's attributes (the card shows a sentence). */
const TEXT = 300;

export const emptySeason = (): Season => ({ canals: [], reaches: { on: [], off: [], unknown: [] }, credits: [], updated: null, republish: 'yes', license: LICENSE });

const text = (v: unknown) => str(v)?.slice(0, TEXT) ?? null;

/** One lifecycle row as a canal's season (a basis or state it doesn't know reads unknown, never on). */
export function canalFromRow(row: Record<string, unknown>, credits: (c: string) => number): SeasonCanal | null {
	const a = (row.attributes ?? {}) as Record<string, unknown>;
	const id = num(a.canal_id);
	if (id === null || !Number.isSafeInteger(id)) return null;
	const basis = (BASES as readonly unknown[]).includes(a.basis) ? (a.basis as SeasonBasis) : 'none';
	const state: SeasonState = basis === 'none' ? 'unknown' : asState(row.severity);
	const republish = REPUBLISH.includes(a.republish as never) ? String(a.republish) : 'internal';
	return {
		id,
		name: text(a.canal),
		state,
		basis,
		since: iso(row.since),
		until: row.until === null || row.until === undefined ? null : iso(row.until),
		why: text(a.why),
		gauge: text(a.gauge),
		gauge_name: text(a.gauge_name),
		district: text(a.district),
		off_announced: typeof a.off_announced === 'boolean' ? a.off_announced : null,
		end_from: a.end_from === 'legal' ? 'legal' : null,
		season: text(a.season),
		credit: (Array.isArray(a.credit) ? a.credit : [])
			.filter((c): c is string => typeof c === 'string')
			.map(text)
			.filter((c): c is string => c !== null)
			.map(credits),
		republish
	};
}

export async function season(sql: Sql): Promise<Season> {
	const [ready] = await sql`
		select to_regclass('water.reach') is not null and to_regclass('water.canal_date') is not null
		       and to_regclass('evt.event') is not null as ok`;
	if (!ready?.ok) return emptySeason();

	const [lifecycles, reaches] = await Promise.all([
		sql`
			select attributes, severity, lower(declared) as since, upper(declared) as until, updated_at
			from evt.event
			where source = 'canal_season' and kind = 'canal_season' and active and declared @> now()
			order by lower(declared) desc, source_id`,
		sql`select id, canal_id from water.reach where canal_id is not null order by canal_id, id`
	]);

	const credits: string[] = [];
	const credit = (c: string) => {
		let i = credits.indexOf(c);
		if (i < 0) i = credits.push(c) - 1;
		return i;
	};
	// Newest span first: the first of a canal is its current one.
	const byCanal = new Map<number, SeasonCanal>();
	let updated: string | null = null;
	for (const row of lifecycles) {
		const c = canalFromRow(row, credit);
		if (!c || byCanal.has(c.id)) continue;
		byCanal.set(c.id, c);
		const at = iso(row.updated_at);
		if (at && (!updated || at > updated)) updated = at;
	}

	const out: Season['reaches'] = { on: [], off: [], unknown: [] };
	const ids = new Set<number>();
	for (const r of reaches) {
		const canalId = Number(r.canal_id);
		ids.add(canalId);
		out[byCanal.get(canalId)?.state ?? 'unknown'].push(Number(r.id));
	}
	// A canal with reaches and no lifecycle reads unknown, with nothing to say beyond that.
	for (const id of ids)
		if (!byCanal.has(id))
			byCanal.set(id, { id, name: null, state: 'unknown', basis: 'none', since: null, until: null, why: null, gauge: null, gauge_name: null, district: null, off_announced: null, end_from: null, season: null, credit: [], republish: 'yes' });

	const canals = [...byCanal.values()].sort((a, b) => a.id - b.id);
	return {
		canals,
		reaches: out,
		credits,
		updated,
		republish: canals.reduce((r, c) => strictest(r, c.republish), 'yes'),
		license: LICENSE
	};
}
