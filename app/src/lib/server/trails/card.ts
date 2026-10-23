import { CREDIT, LICENSE, type Severity, type Sql } from './status.js';

/**
 * The trail card's data (landscape sprint, package P6-app): what the Trails layer's card says about a
 * way or an agency line, from the plugin's views.
 *
 * - `GET /api/trails/way/<osm id>`: one OpenStreetMap way that the layer draws: its kind, name, surface
 *   (with Ridge to Rivers' default where OpenStreetMap says nothing and an R2R trail runs along it:
 *   `trails.way_agency`, on the card only), width (tagged or estimated), whether it is informal, and the
 *   agencies' lines linked to it with their states and who said so.
 * - `GET /api/trails/line/<line id>`: one agency line (an R2R trail, a Greenbelt closure or detour) that
 *   draws itself, where no way shows it.
 *
 * A way that is not drawn (closed to the public, a canal bank) has no card: its row is not returned, so
 * the layer never describes what it does not draw (plan C18). The City's rows are internal (republish
 * aggregates), like the status API and the tailnet map that shows them. Before the plugin's migration
 * both answer null (the route says 404), never a 500.
 */

export interface LineOnWay {
	source: string;
	kind: 'trail' | 'closure' | 'detour';
	name: string | null;
	system: string | null;
	state: string;
	severity: Severity | null;
	/** The agency's own words for the state. */
	label: string | null;
	set_at: string | null;
	since: string | null;
	line_id: number | null;
	/** true: the line paints this whole way; false: the way is only partly along it. */
	paints: boolean;
}

export interface WayCard {
	id: number;
	kind: string;
	name: string | null;
	ref: string | null;
	surface: 'paved' | 'gravel' | 'dirt' | 'unknown';
	/** 'osm' (tagged), 'default' (OpenStreetMap's default for the kind), 'none' (not said). */
	surface_from: 'osm' | 'default' | 'none';
	/** The kind that gave the default, or "Ridge to Rivers trail" when the City's line gave it. */
	surface_default: string | null;
	surface_tag: string | null;
	width_m: number | null;
	width_from: 'osm' | 'estimated';
	informal: boolean;
	greenbelt: boolean;
	bridge: boolean;
	length_m: number | null;
	lines: LineOnWay[];
}

export interface LineCard {
	line_id: number;
	source: string;
	kind: 'trail' | 'closure' | 'detour';
	name: string | null;
	system: string | null;
	state: string;
	severity: Severity | null;
	label: string | null;
	set_at: string | null;
	since: string | null;
	line_m: number | null;
	/** How much of it draws itself, in metres (no way shows it). */
	drawn_m: number;
	ways: number;
}

export const CARD_CREDIT = { agencies: CREDIT, license: LICENSE, osm: '© OpenStreetMap contributors' } as const;

const iso = (v: unknown): string | null => (v === null || v === undefined ? null : new Date(v as string).toISOString());
const num = (v: unknown): number | null => (v === null || v === undefined ? null : Number(v));

async function ready(sql: Sql): Promise<boolean> {
	const [r] = await sql`select to_regclass('trails.path') is not null and to_regclass('trails.agency_state') is not null as ready`;
	return Boolean(r?.ready);
}

function line(x: Record<string, unknown>): LineOnWay {
	return {
		source: String(x.source),
		kind: x.kind as LineOnWay['kind'],
		name: (x.name as string) ?? null,
		system: (x.system as string) ?? null,
		state: String(x.state),
		severity: (x.severity ?? null) as Severity | null,
		label: (x.label as string) ?? null,
		set_at: iso(x.set_at),
		since: iso(x.since),
		line_id: num(x.line_id),
		paints: Boolean(x.paints)
	};
}

/** One drawn way's card, or null (not drawn, not here, or before the migration). */
export async function wayCard(sql: Sql, id: number): Promise<WayCard | null> {
	if (!Number.isSafeInteger(id) || id <= 0) return null;
	if (!(await ready(sql))) return null;
	const [w] = await sql`
		select p.osm_id, p.kind, p.name, p.ref,
		       coalesce(a.surface, p.surface) as surface, coalesce(a.surface_from, p.surface_from) as surface_from,
		       coalesce(a.surface_default, p.surface_default) as surface_default, p.tags->>'surface' as surface_tag,
		       p.width_m, p.width_from, p.informal, p.greenbelt, p.bridge, p.length_m
		from trails.path p left join trails.way_agency a on a.osm_id = p.osm_id
		where p.osm_id = ${id} and p.drawn`;
	if (!w) return null;
	const lines = await sql`
		select s.source, s.kind, s.name, s.system, s.state, s.severity, s.label, s.set_at, s.since, s.line_id, k.paints
		from trails.link k join trails.agency_state s on s.source = k.source and s.source_id = k.source_id
		where k.osm_id = ${id}
		order by k.paints desc, s.source, s.name, s.line_id`;
	return {
		id: Number(w.osm_id),
		kind: String(w.kind),
		name: w.name ?? null,
		ref: w.ref ?? null,
		surface: w.surface,
		surface_from: w.surface_from,
		surface_default: w.surface_default ?? null,
		surface_tag: w.surface_tag ?? null,
		width_m: num(w.width_m),
		width_from: w.width_from,
		informal: Boolean(w.informal),
		greenbelt: Boolean(w.greenbelt),
		bridge: Boolean(w.bridge),
		length_m: num(w.length_m) === null ? null : Math.round(Number(w.length_m)),
		lines: lines.map(line)
	};
}

/** One agency line's card, or null. */
export async function lineCard(sql: Sql, lineId: number): Promise<LineCard | null> {
	if (!Number.isSafeInteger(lineId) || lineId <= 0) return null;
	if (!(await ready(sql))) return null;
	const [s] = await sql`
		select line_id, source, kind, name, system, state, severity, label, set_at, since, line_m, gap_m, along_m,
		       coalesce(array_length(ways, 1), 0) + coalesce(array_length(partial, 1), 0) as ways
		from trails.agency_state where line_id = ${lineId}`;
	if (!s) return null;
	return {
		line_id: Number(s.line_id),
		source: String(s.source),
		kind: s.kind,
		name: s.name ?? null,
		system: s.system ?? null,
		state: String(s.state),
		severity: (s.severity ?? null) as Severity | null,
		label: s.label ?? null,
		set_at: iso(s.set_at),
		since: iso(s.since),
		line_m: num(s.line_m) === null ? null : Math.round(Number(s.line_m)),
		drawn_m: Math.round(Number(s.gap_m ?? 0) + Number(s.along_m ?? 0)),
		ways: Number(s.ways ?? 0)
	};
}
