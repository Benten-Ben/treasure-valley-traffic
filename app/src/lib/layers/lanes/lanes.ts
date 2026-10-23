/**
 * The Lanes layer's shared, browser-safe parts (landscape sprint plan v3 §4.2 P9): what the card API answers
 * (`/api/roads/piece/…`, built by `#lib/server/roads/piece`), the words the card, the legend and the tooltip use,
 * and the map parts that are pure (which tile feature opens which card, the turn arrows' image names). The server
 * and the card both import the types from here, as Water and Trees do.
 *
 * The rules the words keep:
 * - **Every lane count names its source.** OpenStreetMap's own count is used first, then ACHD's rule (which
 *   itself takes the Master Street Map, ITD's HPMS, OpenStreetMap or COMPASS's centerline, whichever it trusts for
 *   the road's class), then HPMS alone where no ACHD segment lies along the piece; a count nobody gave is
 *   "assumed" (DECISIONS, 2026-10-22, item 9).
 * - **A disagreement is flagged, never smoothed.** Where OpenStreetMap and ACHD's rule differ by more than a lane the
 *   piece carries a ▲ and the card shows both counts (the build's `lanes_conflict` review row). The ▲ is the build's
 *   flag; nothing here recounts it.
 * - **Estimates say so.** A width counted from the lanes or taken from a class default, a material nobody tagged,
 *   a lane split between the directions that the way didn't give: each says "estimated" with a warning sign.
 * - **The values rest on ACHD's and ITD's internal data**: the card says they are shown on this map only.
 */

import type { Selection } from '../types.js';

// -- the card API's answers -----------------------------------------------------------------------------------

/** How well a width is known (`roads.xsection.width_tier`). */
export type WidthTier = 'inventoried' | 'measured' | 'counted' | 'estimated';
/** Where a piece's lane count came from (`roads.xsection.lanes_source`). */
export type LanesSource = 'osm' | 'itd_hpms' | 'achd_msm' | 'osm_valley' | 'compass_centerline' | 'default';

/** A lane count in both directions as the line is drawn (forward runs along it). */
export interface LaneCount {
	fwd: number;
	bwd: number;
	total: number;
}

/** One side of a disagreement. */
export interface LaneClaim extends LaneCount {
	/** "OpenStreetMap" or "ACHD rule (Master Street Map)". */
	label: string;
}

/** What the card says about a flagged piece. */
export interface ConflictInfo {
	/** The two counts, when the review row has them (a missing key, or no row at all, leaves a side null). */
	osm: LaneClaim | null;
	other: LaneClaim | null;
	/** The segment rule's own sources disagree (no OpenStreetMap count in it). */
	rule_disagrees: boolean;
}

export interface PieceCard {
	kind: 'piece';
	/** The roads build the answer is from. */
	build: string;
	name: string | null;
	ref: string | null;
	/** highway=* as OpenStreetMap has it. */
	highway: string;
	/** The class in words ("Arterial"). */
	class_word: string;
	/** 'both', or the way one-way traffic runs as the line is drawn. */
	oneway: 'both' | 'forward' | 'backward';
	bridge: boolean;
	tunnel: boolean;
	roundabout: boolean;
	county: string | null;
	length_m: number;
	width: {
		total_m: number;
		total_ft: number;
		tier: WidthTier;
		tier_word: string;
		/** Counted or estimated: drawn soft-edged on the map. */
		estimated: boolean;
		source_word: string;
	};
	lanes: {
		fwd: number;
		bwd: number;
		centre_turn: boolean;
		total: number;
		source: LanesSource;
		/** "OpenStreetMap", "ACHD rule (Master Street Map)", "HPMS", "assumed". */
		source_label: string;
		/** Nobody gave the count. */
		assumed: boolean;
		/** The way gives a total only, and the split between the directions is ours. */
		split_estimated: boolean;
		/** Lane lines are drawn (only where a source gives the count). */
		markings: boolean;
	};
	/** Present only on a flagged piece (the build's `conflict` flag). */
	conflict: ConflictInfo | null;
	material: { value: string; estimated: boolean };
	/** The build's other flags that the card words (for example `other_direction_assumed`). */
	notes: string[];
	credit: string;
}

/** A junction's fill, an island or any surface with no road piece of its own: no lane counts. */
export interface JunctionCard {
	kind: 'junction';
	build: string;
	/** "Signalized junction", "Roundabout", "Traffic island", "Where roads meet". */
	title: string;
	/** How many road pieces meet here, when known. */
	pieces: number | null;
	credit: string;
}

export type PieceAnswer = PieceCard | JunctionCard;

/** What picked tile features can open: the card API's `<kind>-<id>`. */
export const PIECE_KINDS = ['surface', 'edge', 'marking', 'line'] as const;
export type PieceKind = (typeof PIECE_KINDS)[number];

/** The source-layer of the landscape file a kind comes from, for the build id in the manifest. */
export const KIND_BY_SOURCE_LAYER: Readonly<Record<string, PieceKind>> = {
	'roads.surfaces': 'surface',
	'roads.surfaces_z15': 'surface',
	'roads.edges': 'edge',
	'roads.markings': 'marking',
	'roads.crosswalks': 'marking',
	'roads.lines': 'line'
};

export const PIECE_CREDIT = '© OpenStreetMap contributors. Lane counts and widths rest on Ada County Highway District and Idaho Transportation Department data (internal: shown on this map only).';

// -- words ----------------------------------------------------------------------------------------------------

const SEGMENT_SOURCE_WORD: Readonly<Record<string, string>> = {
	achd_msm: 'Master Street Map',
	itd_hpms: 'ITD HPMS',
	osm_valley: 'OpenStreetMap',
	compass_centerline: 'COMPASS centerline'
};

/**
 * The label a lane count carries. `segment` says an ACHD segment lies along the piece: then every count but
 * OpenStreetMap's own came through ACHD's rule, and the label names the source the rule took it from.
 */
export function laneSourceLabel(source: string, segment: boolean): string {
	if (source === 'osm') return 'OpenStreetMap';
	if (source === 'default') return 'assumed';
	const word = SEGMENT_SOURCE_WORD[source] ?? source;
	if (segment) return `ACHD rule (${word})`;
	return source === 'itd_hpms' ? 'HPMS' : word;
}

/** The label of the other side of a disagreement, from the review row's key (always ACHD's rule). */
export function ruleLabel(sourceKey: string): string {
	return `ACHD rule (${SEGMENT_SOURCE_WORD[sourceKey] ?? sourceKey})`;
}

export const TIER_WORD: Readonly<Record<WidthTier, string>> = {
	inventoried: 'inventoried: an agency measured it',
	measured: 'measured',
	counted: 'counted from the lanes',
	estimated: 'estimated'
};

const WIDTH_SOURCE_WORD: Readonly<Record<string, string>> = {
	achd_bike_network: "ACHD's bike network",
	osm_width: 'OpenStreetMap width tag',
	itd_hpms: 'ITD HPMS',
	lanes: 'lane count at standard lane widths',
	class_default: "a default for this kind of road"
};

export function widthSourceWord(source: string): string {
	return WIDTH_SOURCE_WORD[source] ?? source.replace(/_/g, ' ');
}

const CLASS_WORD: Readonly<Record<string, string>> = {
	motorway: 'Freeway',
	trunk: 'Highway',
	primary: 'Major arterial',
	secondary: 'Arterial',
	tertiary: 'Collector',
	unclassified: 'Minor road',
	residential: 'Residential street',
	living_street: 'Living street',
	service: 'Service road',
	track: 'Track'
};

/** highway=* in words; a link is its road's ramp. */
export function classWord(highway: string, service: string | null = null): string {
	if (highway === 'service' && service === 'alley') return 'Alley';
	if (highway.endsWith('_link')) return 'Ramp or link';
	return CLASS_WORD[highway] ?? highway.replace(/_/g, ' ');
}

export function metresFeet(m: number): string {
	return `${round(m, 1)} m (${Math.round(m * 3.28084)} ft)`;
}

export function round(n: number, places = 0): number {
	const f = 10 ** places;
	return Math.round(n * f) / f;
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/**
 * A piece's lanes in words: "2 each way", "3 and 2 (one way each direction)", "2 lanes, one-way", plus
 * "and a centre turn lane".
 */
export function lanesPhrase(l: { fwd: number; bwd: number; centre_turn: boolean }, oneway: PieceCard['oneway']): string {
	let base: string;
	if (oneway !== 'both' || l.fwd === 0 || l.bwd === 0) base = `${plural(l.fwd + l.bwd, 'lane')}, one way`;
	else if (l.fwd === l.bwd) base = `${l.fwd} each way`;
	else base = `${l.fwd} and ${l.bwd}, one count for each direction`;
	return l.centre_turn ? `${base}, and a centre turn lane` : base;
}

/** A claim in the disagreement rows: "OpenStreetMap: 5 lanes (3 and 2)". */
export function claimText(c: LaneClaim): string {
	const split = c.fwd && c.bwd ? ` (${c.fwd} and ${c.bwd})` : '';
	return `${c.label}: ${plural(c.total, 'lane')}${split}`;
}

/** The card's heading: the name, or the class when the road has none ("Unnamed arterial"). */
export function pieceTitle(p: Pick<PieceCard, 'name' | 'ref' | 'class_word'>): string {
	if (p.name) return p.name;
	if (p.ref) return p.ref;
	return `Unnamed ${p.class_word.toLowerCase()}`;
}

/** The build's flags the card words (others are for the review list, not for a reader). */
export const NOTE_WORD: Readonly<Record<string, string>> = {
	other_direction_assumed: "One way's lane count is assumed to match the other's (ACHD draws this road as two one-way segments).",
	direction: "ACHD's count for this direction is missing, so the lanes are assumed.",
	single_lane: 'A single lane both ways: the lanes share the road.',
	carriageway_split: "ACHD's segment covers both carriageways of a divided road.",
	turn_slots: "The turn lanes OpenStreetMap lists don't match its lane count, so no turn arrows are drawn here."
};

// -- the review row ----------------------------------------------------------------------------------------------

const isCount = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0;

function claim(label: string, v: unknown): LaneClaim | null {
	if (!Array.isArray(v)) return null;
	const [fwd, bwd] = v;
	if (!isCount(fwd) || !isCount(bwd)) return null;
	return { label, fwd, bwd, total: fwd + bwd };
}

/** Keys of a `lanes_conflict` row's detail that are not a source's counts. */
const DETAIL_KEYS = new Set(['osm', 'road_segment_id', 'segment_rule', 'candidates']);

/**
 * What the card shows for a flagged piece, from its `lanes_conflict` review rows' details (roads/ingest/xsection.py):
 * `{osm: [fwd, bwd], <the rule's source>: [fwd, bwd], road_segment_id}`, or, where the segment rule's own sources
 * disagree, `{segment_rule, candidates, road_segment_id}`. Tolerant: a missing or oddly shaped key leaves that side
 * out, and the card says the numbers aren't on file.
 */
export function conflictInfo(details: readonly unknown[]): ConflictInfo {
	let osm: LaneClaim | null = null;
	let other: LaneClaim | null = null;
	let ruleDisagrees = false;
	for (const d of details) {
		if (!d || typeof d !== 'object' || Array.isArray(d)) continue;
		const row = d as Record<string, unknown>;
		osm ??= claim('OpenStreetMap', row.osm);
		if (!other) {
			for (const [key, value] of Object.entries(row)) {
				if (DETAIL_KEYS.has(key)) continue;
				other = claim(ruleLabel(key), value);
				if (other) break;
			}
		}
		if ('segment_rule' in row && !('osm' in row)) ruleDisagrees = true;
	}
	return { osm, other, rule_disagrees: ruleDisagrees };
}

// -- builds -------------------------------------------------------------------------------------------------------------

/**
 * Whether the map's tiles are from the roads build the database holds now. The tiles' ids are a build's own: a
 * piece's, a surface's and a marking's id mean different things in the next build, so a card must never be read
 * with another build's id.
 *
 * `mapBuild` is the landscape layer's `build` in `tiles/manifest.json`: the export's folder name, a UTC time
 * (`20261012T031500Z`, as `roads-export` names it), which is later than the build it read (the export waits for
 * a running build and reads the one that committed). So the tiles are current when no roads build finished after
 * that time; and a `mapBuild` equal to a roads build's own id (as the browser specs' fixture gives) is that
 * build. A name that is neither can't be matched, and counts as behind.
 */
export function mapIsCurrent(mapBuild: string, current: { id: string; finished_at: Date | string }): boolean {
	if (mapBuild === current.id) return true;
	const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z(?:-.+)?$/.exec(mapBuild);
	if (!m) return false;
	const at = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
	const finished = new Date(current.finished_at).getTime();
	return Number.isFinite(finished) && finished <= at + 999;
}

export const BEHIND_MESSAGE = 'The map is a build behind the road data. Reload the page to see the current roads.';

// -- the card API's route ------------------------------------------------------------------------------------------

/** A picked feature's address in the card API: `surface-2001`. */
export interface PieceRef {
	kind: PieceKind;
	id: number;
}

export const pieceRefId = (r: PieceRef): string => `${r.kind}-${r.id}`;

/** Parses the route's id; ids are the build's own integers (PostgreSQL's int4 range). */
export function parsePieceRef(raw: string): PieceRef | null {
	const m = /^(surface|edge|marking|line)-(\d{1,10})$/.exec(raw);
	if (!m) return null;
	const id = Number(m[2]);
	return id <= 2_147_483_647 ? { kind: m[1] as PieceKind, id } : null;
}

/** The map's build, from the query: letters, digits and a few separators only. */
export function parseBuild(raw: string | null): string | null {
	return raw && /^[0-9A-Za-z._-]{1,40}$/.test(raw) ? raw : null;
}

// -- paving ---------------------------------------------------------------------------------------------------------

/**
 * A paving feature's id in the card API (`/api/roads/paving/<lot|way>/<id>`), from the bake's. A lot's id is
 * `osm_id * 2` (a way) or `osm_id * 2 + 1` (a multipolygon relation) (plugins/roads/ingest/export.py); a way's is
 * its OpenStreetMap id. Null for an id that isn't an integer in range.
 */
export function pavingLotId(bakedId: number): string | null {
	if (!Number.isSafeInteger(bakedId) || bakedId < 0) return null;
	return `${bakedId % 2 === 1 ? 'r' : 'w'}${Math.floor(bakedId / 2)}`;
}

export function pavingWayId(bakedId: number): string | null {
	return Number.isSafeInteger(bakedId) && bakedId >= 0 ? String(bakedId) : null;
}

// -- turn arrows ----------------------------------------------------------------------------------------------------------

export type Turn = 'left' | 'through' | 'right' | 'uturn';
const TURN_ORDER: readonly Turn[] = ['left', 'through', 'right', 'uturn'];
const TURN_CODE: Readonly<Record<Turn, string>> = { left: 'L', through: 'T', right: 'R', uturn: 'U' };

/**
 * `'left;through'` as the arrows a lane carries, in the order left, through, right, U-turn. A match on the words
 * (so slight and sharp turns draw as plain ones), except that a lane that merges draws no left or right arrow
 * (`merge_to_left` is not a turn). `none` and any other value draw nothing. The style expression
 * (`arrowImageExpression` in `layers.ts`) makes the same choice from the tile's `turns`; a test holds them together.
 */
export function turnArrows(turns: string): Turn[] {
	const t = String(turns ?? '');
	const merges = t.includes('merge');
	const has: Record<Turn, boolean> = {
		left: !merges && t.includes('left'),
		through: t.includes('through'),
		right: !merges && t.includes('right'),
		uturn: t.includes('reverse')
	};
	return TURN_ORDER.filter((k) => has[k]);
}

export const ARROW_PREFIX = 'lanes-arrow:';

/** The style image a lane's arrow is drawn from: `lanes-arrow:LT` (left and through); null when it has no arrow. */
export function arrowImageId(turns: string): string | null {
	const t = turnArrows(turns);
	return t.length ? `${ARROW_PREFIX}${t.map((k) => TURN_CODE[k]).join('')}` : null;
}

/** The arrows an image id names (the inverse of `arrowImageId`); empty for any other id, or one with no arrow. */
export function arrowsOfImage(id: string): Turn[] {
	if (!id.startsWith(ARROW_PREFIX)) return [];
	const codes = id.slice(ARROW_PREFIX.length);
	return TURN_ORDER.filter((k) => codes.includes(TURN_CODE[k]));
}

/** The letters of an arrow image id, in drawing order. */
export const TURN_CODES = TURN_CODE;

// -- picking ----------------------------------------------------------------------------------------------------------------

/** What a Lanes selection's `data` carries. */
export type LanesSelectionData =
	| { type: 'piece'; ref: string; build: string }
	| { type: 'paving'; kind: 'lot' | 'way'; id: string };

const SURFACE_WORD: Readonly<Record<string, string>> = {
	carriageway: 'Road surface',
	junction: 'Junction',
	deck: 'Bridge deck',
	median: 'Median',
	island: 'Traffic island'
};
const EDGE_WORD: Readonly<Record<string, string>> = { curb: 'Curb', shoulder: 'Road shoulder', deck: 'Deck edge', island: 'Island curb' };
const MARKING_WORD: Readonly<Record<string, string>> = {
	edge: 'Edge line',
	lane: 'Lane line',
	centre_double: 'Centre line',
	twltl: 'Turn lane',
	bike: 'Bike lane line',
	stop_bar: 'Stop bar',
	crosswalk: 'Crosswalk'
};
const WAY_WORD: Readonly<Record<string, string>> = {
	service: 'Service road',
	driveway: 'Driveway',
	parking_aisle: 'Parking aisle',
	drive_through: 'Drive-through',
	emergency_access: 'Emergency access',
	sidewalk: 'Sidewalk',
	crossing: 'Crossing',
	access_aisle: 'Access aisle',
	traffic_island: 'Traffic island'
};

export const ROAD_SOURCE = 'OpenStreetMap, ACHD and ITD (internal)';
export const PAVING_SOURCE = 'OpenStreetMap';

type Props = Record<string, unknown> | null | undefined;
const word = (table: Readonly<Record<string, string>>, v: unknown, fallback: string) => (typeof v === 'string' && v in table ? table[v] : fallback);

/**
 * A road tile feature as a selection: what the heading and tooltip say until the card has fetched the piece (a
 * surface's, edge's or marking's kind; a piece line's class, lane count and ▲). Null for a feature with no integer id,
 * a source-layer no card is made from, or when the manifest gives no build to key the card by (the map can't say which
 * build it draws, so it can't ask).
 */
export function roadSelection(sourceLayer: string | undefined, props: Props, build: string | null): Selection | null {
	const kind = sourceLayer ? KIND_BY_SOURCE_LAYER[sourceLayer] : undefined;
	const id = Number(props?.id);
	if (!kind || !Number.isInteger(id) || id < 0 || !build) return null;
	const p = props ?? {};
	let title: string;
	let fact: string | undefined;
	switch (kind) {
		case 'surface':
			title = word(SURFACE_WORD, p.kind, 'Road surface');
			fact = p.tier === 'counted' || p.tier === 'estimated' ? 'Width estimated' : 'Width measured';
			break;
		case 'edge':
			title = word(EDGE_WORD, p.kind, 'Road edge');
			break;
		case 'marking':
			title = sourceLayer === 'roads.crosswalks' ? 'Crosswalk' : word(MARKING_WORD, p.kind, 'Road marking');
			break;
		case 'line': {
			title = classWord(String(p.class ?? 'road'));
			const lanes = Number(p.lanes);
			fact = [Number.isFinite(lanes) && lanes > 0 ? plural(lanes, 'lane') : null, p.conflict === true || p.conflict === 'true' ? 'sources disagree' : null].filter(Boolean).join(' · ') || undefined;
			break;
		}
	}
	return {
		kind: 'lane',
		id: `${kind}-${id}`,
		layer: 'lanes',
		title,
		...(fact ? { fact } : {}),
		source: ROAD_SOURCE,
		data: { type: 'piece', ref: `${kind}-${id}`, build } satisfies LanesSelectionData
	};
}

/** A paving tile feature (a lot or a way) as a selection; null for anything else, or an id that isn't one. */
export function pavingSelection(sourceLayer: string | undefined, props: Props): Selection | null {
	const id = Number(props?.id);
	if (!Number.isInteger(id)) return null;
	const p = props ?? {};
	const material = typeof p.material === 'string' && p.material !== 'unknown' ? p.material : undefined;
	if (sourceLayer === 'roads.paving_lots') {
		const lot = pavingLotId(id);
		if (!lot) return null;
		return { kind: 'paving', id: `lot:${lot}`, layer: 'lanes', title: 'Parking lot', ...(material ? { fact: material } : {}), source: PAVING_SOURCE, data: { type: 'paving', kind: 'lot', id: lot } satisfies LanesSelectionData };
	}
	if (sourceLayer === 'roads.paving_ways') {
		const way = pavingWayId(id);
		if (!way) return null;
		return { kind: 'paving', id: `way:${way}`, layer: 'lanes', title: word(WAY_WORD, p.kind, 'Paving'), ...(material ? { fact: material } : {}), source: PAVING_SOURCE, data: { type: 'paving', kind: 'way', id: way } satisfies LanesSelectionData };
	}
	return null;
}

export const WAY_WORDS = WAY_WORD;

// -- card requests ----------------------------------------------------------------------------------------------------------

/** An error from a card request: the server's own words, and its HTTP status (409: the map is behind the data; 404: gone). */
export class CardError extends Error {
	constructor(
		message: string,
		readonly status: number
	) {
		super(message);
	}
}

