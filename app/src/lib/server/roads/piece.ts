import type postgres from 'postgres';
import {
	classWord,
	conflictInfo,
	laneSourceLabel,
	mapIsCurrent,
	NOTE_WORD,
	PIECE_CREDIT,
	round,
	TIER_WORD,
	widthSourceWord,
	type JunctionCard,
	type LanesSource,
	type PieceAnswer,
	type PieceCard,
	type PieceRef,
	type WidthTier
} from '#lib/layers/lanes/lanes.js';

/**
 * The road piece card API (landscape sprint plan v3 §4.2 P9): what a click on a road surface, a deck, an edge, a
 * marking or a piece line opens in the Lanes layer. It reads what the roads build already stores
 * (`roads.piece` joined to `roads.xsection`, and `roads.review`'s `lanes_conflict` rows), so no migration.
 *
 * **The key is the build's.** A piece's, surface's, edge's and marking's ids are one build's own: the next build
 * numbers them again. So the route takes the picked feature's kind and id and the build the map's tiles are from
 * (`tiles/manifest.json`'s landscape layer), resolves the id through `roads.surface`, `roads.edge`, `roads.marking`
 * (each keeps its `piece_id`) or `roads.piece`, and answers only while the tiles are from the current build
 * (`mapIsCurrent`); a map a build behind gets "reload" and never another build's road. Every read is in one
 * repeatable-read transaction, so a build that commits between two of them can't mix its rows with the last one's.
 *
 * A junction's fill (no `piece_id`) and an island get a short card with no lane counts.
 *
 * Before the tables exist (the roads migrations not applied, no build yet) every answer is empty, not an error, as
 * the paving card's is.
 */

export type Sql = postgres.Sql;

export type PieceResult =
	/** Nothing to answer from: the tables or the build aren't there yet, or no such feature in this build. */
	| { status: 'none' }
	/** The map's tiles are not from the current build. */
	| { status: 'behind'; current: string }
	/** A roads build holds the tables (its TRUNCATE locks them until it commits), or a read ran too long: ask again. */
	| { status: 'busy' }
	| { status: 'ok'; card: PieceAnswer };

interface PieceRow {
	id: number;
	osm_id: number | string;
	highway: string;
	service: string | null;
	name: string | null;
	ref: string | null;
	oneway: number;
	roundabout: boolean;
	bridge: boolean;
	tunnel: boolean;
	county: string | null;
	road_segment_id: number | string | null;
	length_m: number;
	lanes_fwd: number;
	lanes_bwd: number;
	centre_turn: boolean;
	lanes_source: LanesSource;
	total_w_m: number;
	width_tier: WidthTier;
	width_source: string;
	material: string;
	material_source: string | null;
	markings: boolean;
	flags: string[] | null;
}

const ACHD_RULE_NOTES: ReadonlySet<string> = new Set(['direction', 'other_direction_assumed']);

/** The pure part: one piece's row (and its flagged lane-count disagreement) as the card. */
export function pieceCard(r: PieceRow, build: string, conflicts: readonly unknown[]): PieceCard {
	const flags = r.flags ?? [];
	const hasSegment = r.road_segment_id != null;
	const oneway = r.oneway === 1 ? 'forward' : r.oneway === -1 ? 'backward' : 'both';
	const tier = r.width_tier;
	return {
		kind: 'piece',
		build,
		name: r.name,
		ref: r.ref,
		highway: r.highway,
		class_word: classWord(r.highway, r.service),
		oneway,
		bridge: r.bridge,
		tunnel: r.tunnel,
		roundabout: r.roundabout,
		county: r.county,
		length_m: round(r.length_m, 1),
		width: {
			total_m: round(r.total_w_m, 1),
			total_ft: Math.round(r.total_w_m * 3.28084),
			tier,
			tier_word: TIER_WORD[tier] ?? String(tier),
			estimated: tier === 'counted' || tier === 'estimated',
			source_word: widthSourceWord(r.width_source)
		},
		lanes: {
			fwd: r.lanes_fwd,
			bwd: r.lanes_bwd,
			centre_turn: r.centre_turn,
			total: r.lanes_fwd + r.lanes_bwd + (r.centre_turn ? 1 : 0),
			source: r.lanes_source,
			source_label: laneSourceLabel(r.lanes_source, hasSegment),
			assumed: r.lanes_source === 'default',
			split_estimated: flags.includes('split_estimated'),
			markings: r.markings
		},
		// The ▲ is the build's own flag; the counts only fill the card in.
		conflict: flags.includes('conflict') ? conflictInfo(conflicts) : null,
		material: { value: r.material, estimated: r.material_source !== 'surface' },
		// 'direction' and 'other_direction_assumed' are about ACHD's rule; the build sets them even where OpenStreetMap's
		// own count won, and then the card must not say the lanes are assumed.
		notes: flags.filter((f) => f in NOTE_WORD && !(r.lanes_source === 'osm' && ACHD_RULE_NOTES.has(f))),
		credit: PIECE_CREDIT
	};
}

const JUNCTION_TITLE: Record<string, string> = {
	signal: 'Signalized junction',
	roundabout: 'Roundabout',
	interchange: 'Interchange',
	plain: 'Where roads meet'
};

/** A junction's, an island's or a surface with no road piece's short card. */
export function junctionCard(build: string, junction: { kind: string; pieces: number } | null, island: boolean): JunctionCard {
	return {
		kind: 'junction',
		build,
		title: island ? 'Traffic island' : junction ? (JUNCTION_TITLE[junction.kind] ?? 'Where roads meet') : 'Where roads meet',
		pieces: junction ? junction.pieces : null,
		credit: PIECE_CREDIT
	};
}

/**
 * The card for one picked feature of the map's tiles, as the map's `mapBuild` says they are, or why there isn't one.
 */
export async function pieceAnswer(sql: Sql, ref: PieceRef, mapBuild: string): Promise<PieceResult> {
	try {
		const result = await sql.begin('isolation level repeatable read read only', async (tx) => {
			const t = tx as unknown as Sql;
			// A roads build truncates these tables inside its one transaction, and a read waits for it. The app's pool is
			// small and shared by every /api route, so a card must give up quickly rather than hold a connection.
			await t.unsafe(`set local lock_timeout = '${LOCK_TIMEOUT_MS}ms'`);
			await t.unsafe(`set local statement_timeout = '${STATEMENT_TIMEOUT_MS}ms'`);
			return readTables(t, ref, mapBuild);
		});
		return result as PieceResult;
	} catch (e) {
		if (isBusy(e)) return { status: 'busy' };
		throw e;
	}
}

/** How long a card read waits for a lock, and how long one statement may run, before the card is told to try again. */
export const LOCK_TIMEOUT_MS = 2000;
export const STATEMENT_TIMEOUT_MS = 5000;

/** lock_not_available (55P03) and query_canceled (57014, a statement_timeout): the build has the tables, not a fault. */
export function isBusy(e: unknown): boolean {
	const code = (e as { code?: unknown } | null)?.code;
	return code === '55P03' || code === '57014';
}

async function readTables(sql: Sql, ref: PieceRef, mapBuild: string): Promise<PieceResult> {
	const [present] = await sql<{ present: boolean; review: boolean }[]>`
		select to_regclass('roads.build') is not null and to_regclass('roads.piece') is not null
		       and to_regclass('roads.xsection') is not null and to_regclass('roads.surface') is not null
		       and to_regclass('roads.edge') is not null and to_regclass('roads.marking') is not null
		       and to_regclass('roads.junction') is not null as present,
		       to_regclass('roads.review') is not null as review`;
	if (!present?.present) return { status: 'none' };
	const [current] = await sql<{ id: string; finished_at: Date }[]>`select id, finished_at from roads.build where current`;
	if (!current) return { status: 'none' };
	if (!mapIsCurrent(mapBuild, current)) return { status: 'behind', current: current.id };

	let target: { piece_id: number | null; junction_id: number | null; island: boolean } | undefined;
	switch (ref.kind) {
		case 'line': {
			const [r] = await sql<{ id: number }[]>`select id from roads.piece where id = ${ref.id}`;
			target = r ? { piece_id: r.id, junction_id: null, island: false } : undefined;
			break;
		}
		case 'surface': {
			const [r] = await sql<{ piece_id: number | null; junction_id: number | null; kind: string }[]>`select piece_id, junction_id, kind from roads.surface where id = ${ref.id}`;
			target = r ? { piece_id: r.piece_id, junction_id: r.junction_id, island: r.kind === 'island' } : undefined;
			break;
		}
		case 'edge': {
			const [r] = await sql<{ piece_id: number | null; junction_id: number | null; kind: string }[]>`select piece_id, junction_id, kind from roads.edge where id = ${ref.id}`;
			target = r ? { piece_id: r.piece_id, junction_id: r.junction_id, island: r.kind === 'island' } : undefined;
			break;
		}
		case 'marking': {
			const [r] = await sql<{ piece_id: number | null; junction_id: number | null }[]>`select piece_id, junction_id from roads.marking where id = ${ref.id}`;
			target = r ? { piece_id: r.piece_id, junction_id: r.junction_id, island: false } : undefined;
			break;
		}
	}
	if (!target) return { status: 'none' };

	if (target.piece_id == null) {
		let junction: { kind: string; pieces: number } | null = null;
		if (target.junction_id != null) {
			const [j] = await sql<{ kind: string; pieces: number | null }[]>`select kind, coalesce(array_length(pieces, 1), 0) as pieces from roads.junction where id = ${target.junction_id}`;
			if (j) junction = { kind: j.kind, pieces: j.pieces ?? 0 };
		}
		return { status: 'ok', card: junctionCard(current.id, junction, target.island) };
	}

	const [row] = await sql<PieceRow[]>`
		select p.id, p.osm_id, p.highway, p.service, p.name, p.ref, p.oneway, p.roundabout, p.bridge, p.tunnel, p.county,
		       p.road_segment_id, p.length_m,
		       x.lanes_fwd, x.lanes_bwd, x.centre_turn, x.lanes_source, x.total_w_m, x.width_tier, x.width_source,
		       x.material, x.material_source, x.markings, x.flags
		from roads.piece p join roads.xsection x on x.piece_id = p.id
		where p.id = ${target.piece_id}`;
	if (!row) return { status: 'none' };
	let conflicts: unknown[] = [];
	if (present.review && (row.flags ?? []).includes('conflict')) {
		const rows = await sql<{ detail: unknown }[]>`select detail from roads.review where piece_id = ${row.id} and kind = 'lanes_conflict' order by id`;
		conflicts = rows.map((r) => r.detail);
	}
	return { status: 'ok', card: pieceCard(row, current.id, conflicts) };
}
