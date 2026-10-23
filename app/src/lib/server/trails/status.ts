/**
 * Trail status for the Trails layer (landscape sprint, package P6-data):
 * `GET /api/trails/status`. The status the trails plugin already polls, put
 * on OpenStreetMap's ways: Ridge to Rivers' condition per trail (every 30
 * minutes) and the Greenbelt's closures and detours (hourly), each with the
 * ways `trails-match` linked its line to. The map applies it with
 * feature-state, so a status change never re-cuts a tile (docs/14 §14.8:
 * paint state, not data).
 *
 * - `agencies`: one entry per agency line, in R2R's or the City's own words
 *   (`label`), with `ways` (the ways it paints: they lie along it, so they take
 *   its state) and `partial` (ways it's linked to that run on past it, or are
 *   longer than it: a 120 m closure on a 1 km way). Wherever no way it paints
 *   shows it, the line draws itself in the `trails.agency` tiles (`drawn`,
 *   feature id `-line_id`; the view trails.agency_drawn from z13): the
 *   stretches of its partial ways that lie along it (`along_m`), and its own
 *   line elsewhere (`gap_m`). So every metre of it shows its state, and no way
 *   shows it more than 20 m beyond it. At z10-12 the same tiles carry its whole
 *   line (trails.agency_lo), with the same id.
 * - `ways`: each painted way's state, the worst of the lines it carries:
 *   closed, do_not_use, caution, detour, open, then not_evaluated. The ways'
 *   tiles (`trails.paths`) are OpenStreetMap's alone; this is the only place
 *   the City's lines reach them.
 * - `hidden`: informal ways near a closure (plan C18), which the map hides.
 * - `counts`: R2R's states now, for the legend's count line.
 * - `polled`: each source's last good poll, the legend's "as of".
 *
 * The City's rows have no licence (republish aggregates): internal, like the
 * tailnet map that shows them: a public build leaves this
 * route, the card routes (/api/trails/way/<id> and /api/trails/line/<id>, which list a way's City rows) and the
 * agency tiles out. Before the plugin's migration it answers
 * empty, never a 500. `no-cache` with an ETag: the map asks again on the
 * pollers' cadence, and an unchanged answer is a 304.
 */

/** A postgres.js tagged template, or a test's stand-in. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Sql = (strings: TemplateStringsArray, ...values: any[]) => Promise<any[]>;

export type Severity = 'closed' | 'do_not_use' | 'caution' | 'detour' | 'open' | 'not_evaluated';

/** Worst first: a way carrying several lines shows the first of theirs here. */
export const SEVERITY_ORDER: Severity[] = ['closed', 'do_not_use', 'caution', 'detour', 'open', 'not_evaluated'];

/** How near a closed line an informal way is hidden, in metres ("inside" a closure, plan C18). */
export const HIDDEN_NEAR_M = 100;

export const SOURCES = ['r2r_trails', 'boise_greenbelt_closures'] as const;
export const CREDIT = 'City of Boise Parks & Recreation (Ridge to Rivers); City of Boise Parks and Recreation';
export const LICENSE = 'none stated (City of Boise disclaimer only)';

export interface AgencyState {
	source: string;
	id: string;
	kind: 'trail' | 'closure' | 'detour';
	name: string | null;
	system: string | null;
	/** R2R's state (dry, frozen, muddy_further_out, frozen_then_muddy, muddy, closed, not_evaluated, unset, other), or closure, detour, ended. */
	state: string;
	severity: Severity | null;
	/** The agency's own words for it. */
	label: string | null;
	/** When staff set it (R2R), as ISO text. */
	set_at: string | null;
	/** Since when we've seen it. */
	since: string | null;
	/** The ways it paints (feature-state on the whole way). */
	ways: number[];
	/** The other ways it's linked to: their stretch along it is drawn in the agency tiles. */
	partial: number[];
	line_id: number | null;
	/** Whether it draws anything itself from z13 (feature -line_id in the trails.agency tiles). */
	drawn: boolean;
	/** How much of its own line it draws, in metres. */
	gap_m: number;
	/** How much of the ways it doesn't paint it draws in its state, in metres. */
	along_m: number;
	/** The share of its line within 15 m of the ways it paints or draws on (null when no way matched it, or before trails-match). */
	covered: number | null;
}

export interface TrailStatus {
	agencies: AgencyState[];
	ways: Record<string, Severity>;
	hidden: number[];
	counts: Record<string, number>;
	polled: Record<string, string | null>;
	credit: string;
	license: string;
	republish: 'aggregates';
}

const iso = (v: unknown): string | null => (v === null || v === undefined ? null : new Date(v as string).toISOString());
const ids = (v: unknown): number[] => (Array.isArray(v) ? v.map(Number) : []);

/** What a line's state paints on its ways: its severity, with R2R's unevaluated trails as not_evaluated; null when it paints nothing (ended). */
export function wayState(a: Pick<AgencyState, 'source' | 'state' | 'severity'>): Severity | null {
	if (a.severity) return a.severity;
	if (a.source === 'r2r_trails') return 'not_evaluated';
	return null;
}

/** Each painted way's state: the worst among the lines it carries. */
export function wayStates(agencies: AgencyState[]): Record<string, Severity> {
	const rank = (s: Severity) => SEVERITY_ORDER.indexOf(s);
	const out: Record<string, Severity> = {};
	for (const a of agencies) {
		const s = wayState(a);
		if (!s) continue;
		for (const w of a.ways) {
			const k = String(w);
			if (!(k in out) || rank(s) < rank(out[k])) out[k] = s;
		}
	}
	return out;
}

function empty(): TrailStatus {
	return { agencies: [], ways: {}, hidden: [], counts: {}, polled: {}, credit: CREDIT, license: LICENSE, republish: 'aggregates' };
}

export async function trailStatus(sql: Sql): Promise<TrailStatus> {
	const [r] = await sql`select to_regclass('trails.agency_state') is not null as ready`;
	if (!r?.ready) return empty();
	const rows = await sql`
		select source, source_id, kind, name, system, state, severity, label, set_at, since, ways, partial,
		       line_id, links, line_m, covered_m, gap_m, along_m
		from trails.agency_state order by source, name, source_id`;
	const agencies: AgencyState[] = rows.map((x) => ({
		source: String(x.source),
		id: String(x.source_id),
		kind: x.kind,
		name: x.name ?? null,
		system: x.system ?? null,
		state: String(x.state),
		severity: (x.severity ?? null) as Severity | null,
		label: x.label ?? null,
		set_at: iso(x.set_at),
		since: iso(x.since),
		ways: ids(x.ways),
		partial: ids(x.partial),
		line_id: x.line_id === null || x.line_id === undefined ? null : Number(x.line_id),
		drawn: Number(x.gap_m ?? 0) > 0 || Number(x.along_m ?? 0) > 0,
		gap_m: Math.round(Number(x.gap_m ?? 0)),
		along_m: Math.round(Number(x.along_m ?? 0)),
		covered: x.line_m && x.covered_m !== null && x.covered_m !== undefined ? Math.round((Number(x.covered_m) / Number(x.line_m)) * 1000) / 1000 : null
	}));
	const hidden = (await sql`select osm_id from trails.hidden_informal(${HIDDEN_NEAR_M}) order by osm_id`).map((h) => Number(h.osm_id));
	const polled: Record<string, string | null> = Object.fromEntries(SOURCES.map((s) => [s, null]));
	for (const p of await sql`
		select source, max(started_at) as at from ops.fetch
		where source in ('r2r_trails', 'boise_greenbelt_closures') and ok group by source`)
		polled[String(p.source)] = iso(p.at);
	const counts: Record<string, number> = {};
	for (const a of agencies) if (a.source === 'r2r_trails') counts[a.state] = (counts[a.state] ?? 0) + 1;
	return { agencies, ways: wayStates(agencies), hidden, counts, polled, credit: CREDIT, license: LICENSE, republish: 'aggregates' };
}
