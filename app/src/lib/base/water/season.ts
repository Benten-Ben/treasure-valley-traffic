import type { BaseLive } from '#lib/base/types.js';
import { lineWidth, RIBBON_FROM_ZOOM } from './palette.js';

/**
 * The canal season on the baked reaches (landscape sprint plan v3 §4.2 P5, K5; P5-app): each canal reads
 * on, off or unknown, from its lifecycles (`GET /api/water/season`, `#lib/server/water/season.ts`), and the
 * solid reach layer draws it through feature-state `season`:
 *
 * - **On**, or no state: today's line.
 * - **Off**: a hollow inside the reach's own line, at its true footprint. Where the on width is 3 px or more,
 *   two thin edges (a quarter of the width, between 0.6 and 1.2 px each) with a gap between them, so the
 *   footprint (gap plus two edges) is exactly the true width. The colour stays the reach's own tone: never a
 *   casing, never a second line under the same features.
 * - **Unknown**: over the same range, a solid centre hairline of about 0.8 px in the reach's tone (no dash:
 *   `line-dasharray` takes no feature-state).
 * - Under 3 px the line draws as today, so below about z15 (main canals), z16 (named canals) or z17 (laterals)
 *   the line carries no season cue, and the card and the legend carry it. No opacity fallback: lightness alone
 *   would be colour alone.
 *
 * The dashed layers (intermittent, NHD-only, piped) get no hollow: their dashes are multiples of their width.
 *
 * Reaches with no canal have no state and draw as today. The lower New York Canal and the laterals draw
 * whatever their lifecycles say. Legal-window states are IDWR's, internal: this is for the tailnet map.
 */

export type SeasonState = 'on' | 'off' | 'unknown';
/** What a lifecycle rests on (`none`: the canal has no lifecycle, which reads as unknown). */
export type SeasonBasis = 'gauge' | 'district' | 'legal' | 'always' | 'none';

export const STATES: readonly SeasonState[] = ['on', 'off', 'unknown'];
export const BASES: readonly SeasonBasis[] = ['gauge', 'district', 'legal', 'always', 'none'];

/** One canal's current lifecycle, as `/api/water/season` answers it. */
export interface SeasonCanal {
	/** `water.canal.id` (follows the water build). */
	id: number;
	name: string | null;
	state: SeasonState;
	basis: SeasonBasis;
	/** When this span began, ISO. */
	since: string | null;
	/** When it ends, ISO; null while it holds until a reading changes it (the gauge's span, `always`). */
	until: string | null;
	/** Why, in the lifecycle's own words (the gauge's rule, the district's dates, a drain). */
	why: string | null;
	/** `basis` gauge: the gauge and its name. */
	gauge: string | null;
	gauge_name: string | null;
	/** `basis` district: who announced it, whether a shut-off is announced, and whether the span ends on IDWR's date. */
	district: string | null;
	off_announced: boolean | null;
	end_from: 'legal' | null;
	/** `basis` legal, or a district span ending on IDWR's date: the legal season's own text, `3/1 - 11/15`. */
	season: string | null;
	/** Indexes into the answer's `credits`. */
	credit: number[];
	/** The strictest republish class of what it rests on: `internal` for IDWR's legal window. */
	republish: string;
}

export interface Season {
	canals: SeasonCanal[];
	/** The ids of the baked reaches (`water.reaches`) of each state's canals. */
	reaches: Record<SeasonState, number[]>;
	/** Every credit the canals cite. */
	credits: string[];
	/** When the newest lifecycle changed; null with none. Stable between changes, so the answer's ETag holds. */
	updated: string | null;
	/** The strictest of the canals' republish classes: IDWR's legal window makes the answer internal. */
	republish: string;
	license: string;
}

export const SEASON_URL = '/api/water/season';
/** The hook polls this often (the lifecycles change a few times a season, and when the gauge's 48 hours pass). */
export const POLL_MS = 15 * 60_000;
/** After a failed poll, try again this soon. */
export const RETRY_MS = 60_000;
/** The gauge's silence that makes its canal unknown (plugins/water/ingest/season.py, `STALE`). */
export const GAUGE_SILENT_HOURS = 48;

/** The source and source-layer whose features carry the state. */
export const SEASON_SOURCE = 'landscape';
export const SEASON_SOURCE_LAYER = 'water.reaches';

// -- the paint -----------------------------------------------------------------------------------------------

/** The hollow and the hairline read only where the line is at least this wide (on), px. */
export const HOLLOW_FROM_PX = 3;
/** An off line's edges: a quarter of the width, never under 0.6 or over 1.2 px. */
export const EDGE_SHARE = 1 / 4;
export const EDGE_MIN_PX = 0.6;
export const EDGE_MAX_PX = 1.2;
/** The unknown line's centre hairline, px. */
export const HAIRLINE_PX = 0.8;

type Expr = unknown[];

const season: Expr = ['feature-state', 'season'];
const is = (state: SeasonState): Expr => ['==', season, state];

/** Where a stop's second half sits just before the next stop, so the hollow switches at a whole zoom, never mid-way. */
const STEP_EPS = 0.001;

/**
 * The width `lineWidth()` gives at a whole zoom between its z15 and z22 stops, as an expression over those two: its
 * exponential base 2 interpolation is affine in 2^zoom, so this is the same value (the 0.6 px floor included), and
 * interpolating between whole zooms is exact.
 */
const between = (zoom: number, at15: Expr, at22: Expr): Expr => ['+', at15, ['*', (2 ** (zoom - RIBBON_FROM_ZOOM) - 1) / (2 ** (22 - RIBBON_FROM_ZOOM) - 1), ['-', at22, at15]]];

/**
 * The solid reach layer's `line-width` and `line-gap-width`: `lineWidth()`'s own stops, each one reading the
 * feature's season. On, no state, or under 3 px: the width as today and a gap of 0. Off from 3 px: an edge of
 * `clamp(0.6, w / 4, 1.2)` and a gap of `w - 2 * edge`, so the footprint is the true width. Unknown from 3 px:
 * the hairline, no gap.
 *
 * MapLibre draws a line with a gap as two lines (footprint: gap plus two widths) and one without as a single
 * line (footprint: the width), so a style that interpolated between a plain stop and a hollow one would draw a
 * doubled line in between. The stops are therefore whole zooms (a ribbon's width doubles each zoom, so
 * interpolating between them is exact, and the on width stays `lineWidth()`'s own, the 0.6 px floor included),
 * and each interval keeps the look its first stop has: the second value, just before the next stop, is the next
 * stop's width in the same look. A line turns hollow at the first whole zoom where its width reaches 3 px, with
 * its footprint unchanged.
 */
export function seasonPaint(): { 'line-width': Expr; 'line-gap-width': Expr } {
	const base = lineWidth() as unknown[];
	const head = base.slice(0, 3);
	const stopAt = (zoom: number) => base[base.indexOf(zoom) + 1] as Expr;
	const stops: [number, Expr][] = [];
	for (let i = 3; i < base.length; i += 2) {
		const zoom = base[i] as number;
		// The whole zooms between the last ribbon stop and the final one.
		if (zoom === 22) for (let z = RIBBON_FROM_ZOOM + 1; z < 22; z++) stops.push([z, between(z, stopAt(RIBBON_FROM_ZOOM), stopAt(22))]);
		stops.push([zoom, base[i + 1] as Expr]);
	}
	// `look` is the stop whose width decides plain or hollow; `at` is the stop whose width the value follows.
	const cell = (look: Expr, at: Expr, kind: 'width' | 'gap'): Expr => {
		const wide: Expr = ['>=', ['var', 'look'], HOLLOW_FROM_PX];
		const w: Expr = ['var', 'at'];
		const edge: Expr = ['max', EDGE_MIN_PX, ['min', EDGE_MAX_PX, ['*', EDGE_SHARE, w]]];
		const hollow: Expr = ['all', wide, is('off')];
		const body: Expr =
			kind === 'width'
				? ['case', hollow, edge, ['all', wide, is('unknown')], HAIRLINE_PX, w]
				: ['case', hollow, ['-', w, ['*', 2, edge]], 0];
		return ['let', 'look', look, 'at', at, body];
	};
	const width: unknown[] = [];
	const gap: unknown[] = [];
	stops.forEach(([zoom, w], i) => {
		width.push(zoom, cell(w, w, 'width'));
		gap.push(zoom, cell(w, w, 'gap'));
		const next = stops[i + 1];
		if (next) {
			width.push(next[0] - STEP_EPS, cell(w, next[1], 'width'));
			gap.push(next[0] - STEP_EPS, cell(w, next[1], 'gap'));
		}
	});
	return { 'line-width': [...head, ...width], 'line-gap-width': [...head, ...gap] };
}

// -- the answer's reading --------------------------------------------------------------------------------------

/** What an answer's field should be if it is a state (anything else is unknown, never on). */
export const asState = (v: unknown): SeasonState => (v === 'on' || v === 'off' || v === 'unknown' ? v : 'unknown');

/** The canal's lifecycle in an answer, or null when the answer has none for it. */
export function canalSeason(season: Season | null, canalId: number): SeasonCanal | null {
	return season?.canals.find((c) => c.id === canalId) ?? null;
}

/** The state each reach id has in an answer (a reach in two lists, which a build never makes, reads unknown). */
export function reachStates(season: Season): Map<number, SeasonState> {
	const out = new Map<number, SeasonState>();
	for (const state of STATES) for (const id of season.reaches[state] ?? []) out.set(id, out.has(id) ? 'unknown' : state);
	return out;
}

// -- the words ---------------------------------------------------------------------------------------------------

/** IDWR's window as the card writes it: `3/1 – 11/15`. */
export const windowText = (text: string | null): string => (text ?? '').replace(/\s+-\s+/g, ' – ');

/**
 * The card's words for a canal's state and what it rests on, never colour alone: "off (gauge BSEI1, New York
 * Canal Diversion at Boise)", "unknown: no reading for 48 hours (gauge BSEI1)", and for the legal window "in
 * IDWR's legal irrigation season (3/1 – 11/15), not delivery dates" (the window is IDWR's legal season of
 * use, which shows water on until Nov 15 at most heads, not the districts' delivery dates).
 */
export function seasonWords(c: SeasonCanal | null): string {
	if (!c) return 'unknown: no season is known for this canal';
	const on = c.state === 'on';
	switch (c.basis) {
		case 'gauge': {
			const gauge = [c.gauge, c.gauge_name].filter(Boolean).join(', ');
			if (c.state === 'unknown') return `unknown: no reading for ${GAUGE_SILENT_HOURS} hours${c.gauge ? ` (gauge ${c.gauge})` : ''}`;
			return `${c.state}${gauge ? ` (gauge ${gauge})` : ''}`;
		}
		case 'district': {
			const who = c.district ? `${c.district}'s dates` : "the district's dates";
			if (c.end_from === 'legal') return `on (${who}; no shut-off announced yet, so until IDWR's legal season ends${c.season ? `, ${windowText(c.season)}` : ''})`;
			if (on && c.off_announced === false) return `on (${who}; no shut-off announced yet)`;
			return `${c.state} (${who})`;
		}
		case 'legal':
			return `${on ? 'in' : 'outside'} IDWR's legal irrigation season${c.season ? ` (${windowText(c.season)})` : ''}, not delivery dates`;
		case 'always':
			return `on all year${c.why ? ` (${c.why})` : ''}`;
		default:
			return 'unknown: no season rule applies to this canal';
	}
}

/** Whether a canal's state rests on IDWR's legal window (an estimate of the season, not of delivery). */
export const isLegalWindow = (c: SeasonCanal | null): boolean => c?.basis === 'legal' || c?.end_from === 'legal';

/** The words the legend and the card give for why a state shows only from a zoom. */
export const SEASON_ZOOM_NOTE = 'The line shows a canal’s season only when it is wide enough (about z15 for main canals, z16 for named canals, z17 for laterals); its card always says.';

// -- fetching and drawing ----------------------------------------------------------------------------------------

type Fetch = (url: string) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;

/** Check an answer's shape before the map or the card trusts it. */
export function readSeason(raw: unknown): Season {
	const r = raw as Partial<Season> | null;
	const ids = (v: unknown): number[] => (Array.isArray(v) ? v.filter((n): n is number => Number.isSafeInteger(n)) : []);
	if (!r || typeof r !== 'object' || !Array.isArray(r.canals)) throw new Error('The canal season answer is malformed');
	return {
		canals: r.canals.map((c) => ({ ...c, state: asState(c.state), credit: ids(c.credit) })) as SeasonCanal[],
		reaches: { on: ids(r.reaches?.on), off: ids(r.reaches?.off), unknown: ids(r.reaches?.unknown) },
		credits: Array.isArray(r.credits) ? r.credits.map(String) : [],
		updated: r.updated ?? null,
		republish: r.republish ?? 'internal',
		license: r.license ?? ''
	};
}

const MIN_CACHE_MS = 60_000;
let cached: { at: number; promise: Promise<Season> } | null = null;

/**
 * The season, from `/api/water/season` (the browser revalidates by its ETag, so an unchanged answer costs a 304).
 * One request serves the hook and every card for a minute; `fresh` asks again.
 */
export function loadSeason(o: { fetch?: Fetch; fresh?: boolean; now?: number } = {}): Promise<Season> {
	const now = o.now ?? Date.now();
	if (!o.fresh && cached && now - cached.at < MIN_CACHE_MS) return cached.promise;
	const get = o.fetch ?? ((url) => fetch(url));
	const promise = get(SEASON_URL).then(async (res) => {
		if (!res.ok) throw new Error(`The canal season answered HTTP ${res.status}`);
		return readSeason(await res.json());
	});
	const entry = { at: now, promise };
	cached = entry;
	promise.catch(() => {
		if (cached === entry) cached = null;
	});
	return promise;
}

/** Forget the kept answer (tests). */
export function forgetSeason(): void {
	cached = null;
}

/** What the hook needs of a map (a test passes a fake). */
export interface SeasonMap {
	getSource(id: string): unknown;
	setFeatureState(target: { source: string; sourceLayer: string; id: number }, state: { season: SeasonState }): void;
	removeFeatureState(target: { source: string; sourceLayer: string; id: number }, key?: string): void;
	getFeatureState(target: { source: string; sourceLayer: string; id: number }): { season?: SeasonState } | undefined;
	on(type: string, listener: () => void): unknown;
	off(type: string, listener: () => void): unknown;
}

const target = (id: number) => ({ source: SEASON_SOURCE, sourceLayer: SEASON_SOURCE_LAYER, id });

/**
 * Put an answer's states on the reaches, changing only what differs from `prev` (the states put before); returns
 * the states now on the map. A reach that has left the answer loses its state and draws as today.
 */
export function applySeason(map: SeasonMap, next: ReadonlyMap<number, SeasonState>, prev: ReadonlyMap<number, SeasonState>): Map<number, SeasonState> {
	if (!map.getSource(SEASON_SOURCE)) return new Map(prev);
	for (const id of prev.keys()) if (!next.has(id)) map.removeFeatureState(target(id), 'season');
	for (const [id, state] of next) if (prev.get(id) !== state) map.setFeatureState(target(id), { season: state });
	return new Map(next);
}

/**
 * The base contribution's `live` hook: load the season, put it on the reaches, and again every 15 minutes (a
 * minute after a failure). It keeps what it last drew when a poll fails, never draws a state it didn't read,
 * puts the states back if the style change drops them, and stops its timer and removes its states on cleanup.
 */
export function seasonLive({ map }: BaseLive, o: { fetch?: Fetch; pollMs?: number; retryMs?: number } = {}): () => void {
	const m = map as unknown as SeasonMap;
	let drawn: Map<number, SeasonState> = new Map();
	let wanted: Map<number, SeasonState> | null = null;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let stopped = false;

	const draw = (next: Map<number, SeasonState>) => {
		wanted = next;
		try {
			drawn = applySeason(m, next, drawn);
		} catch {
			// The map may be torn down already; the reaches then simply draw as today.
		}
	};

	// A style change that rebuilds the source drops its feature-state: one reach tells us.
	const guard = () => {
		if (stopped || !wanted?.size || !m.getSource(SEASON_SOURCE)) return;
		const [id, state] = wanted.entries().next().value as [number, SeasonState];
		let now: SeasonState | undefined;
		try {
			now = m.getFeatureState(target(id))?.season;
		} catch {
			return;
		}
		if (now !== state) {
			drawn = new Map();
			draw(wanted);
		}
	};

	const poll = async () => {
		if (stopped) return;
		let wait = o.pollMs ?? POLL_MS;
		try {
			const season = await loadSeason({ fetch: o.fetch, fresh: true });
			if (stopped) return;
			draw(reachStates(season));
		} catch {
			// Keep what is drawn; the next poll comes sooner.
			wait = o.retryMs ?? RETRY_MS;
		}
		if (!stopped) timer = setTimeout(poll, wait);
	};

	m.on('styledata', guard);
	void poll();

	return () => {
		stopped = true;
		if (timer) clearTimeout(timer);
		try {
			m.off('styledata', guard);
			for (const id of drawn.keys()) m.removeFeatureState(target(id), 'season');
		} catch {
			// The map may be torn down already; there is then no state left to remove.
		}
		drawn = new Map();
		wanted = null;
	};
}
