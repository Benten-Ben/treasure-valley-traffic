import type { ExpressionSpecification, FilterSpecification, LayerSpecification } from 'maplibre-gl';
import { metresPerPx } from '#lib/base/trails/paved.js';
import type { SlottedLayer } from '#lib/map/order.js';
import type { LineCard, WayCard } from '#lib/server/trails/card.js';
import type { AgencyState, Severity, TrailStatus } from '#lib/server/trails/status.js';
import type { Selection } from '../types.js';

/**
 * The Trails layer, as data (landscape sprint, package P6-app; plan §3.2 to §3.5, C9, C18; K7, K8):
 *
 * - **Tiles** (`/api/trails/tiles/<layer>/…`, #lib/server/trails/tiles.ts): `paths` (OpenStreetMap's drawn
 *   ways from z13, the named network at z10 to 12), `routes` and `agency` (the City's lines drawn by
 *   themselves, plus `marks`: their whole lines, for the status icons).
 * - **One trail umber** for every line, with a cream halo and never an ink casing (K7). The status of a
 *   trail is never told by color: it is a dash, and where it matters an icon (▲, ✕, an arrowhead), each
 *   named in the legend (K8). Ways take the state of the agency line that lies along them
 *   (`/api/trails/status`, applied as feature-state, so a state change re-cuts no tile); a state's
 *   look is its own layer, drawn where the feature's `sev` is that state (a filter can't read feature-state).
 * - **Lines** in `land`, rank 30 (they draw over Aerial, under the streets); **icons** in `points`
 *   and **names** in `labels` (no symbol layer sits below `anchor:routes`).
 * - At z10 to 12 the ways are OpenStreetMap's named network, plain, and only the agencies' own lines
 *   carry a state on top; from z13 ways take their line's state and the agencies' lines draw only what no
 *   way shows (the stretches along a way they don't paint, and their own line where no way lies along them).
 * - Informal ways come in at z16, dotted and worded "informal, not an official trail". Private and
 *   no-access ways, and canal banks, are not in the tiles at all (the data's `drawn`).
 */

export const SOURCE_NAME = 'OpenStreetMap, City of Boise Parks & Recreation (Ridge to Rivers)';
export const CREDIT_OSM = '© OpenStreetMap contributors';

// -- colors ---------------------------------------------------------------------------------------------------------

/** The one trail color: raw umber, darker than the dirt tread's 18% tint (`UNPAVED.dirt`), 7.4:1 against cream. */
export const UMBER = '#6b4a2b';
/** Names along the trails: a darker umber on a cream halo. */
export const UMBER_TEXT = '#4a321c';
export const CREAM = '#fffbf4';

// -- sources, source-layers, ids -----------------------------------------------------------------------------------

export const SRC = { paths: 'trails-paths', routes: 'trails-routes', agency: 'trails-agency' } as const;
export const SL = { paths: 'paths', routes: 'routes', agency: 'agency', marks: 'marks' } as const;
/** The tile layers' names (`/api/trails/tiles/<layer>`, `versions.layers['trails.<layer>']`). */
export const TILE_LAYERS = ['paths', 'routes', 'agency'] as const;
export const ZOOMS = { minzoom: 10, maxzoom: 16 } as const;
/** The first zoom of the ways in full detail and of the state on them; below it the named network and the agencies' whole lines. */
export const DETAIL_ZOOM = 13;
export const INFORMAL_ZOOM = 16;
/** Plan §3.2: trail lines and status in `land` at rank 30. Icons and names sit under Transit's (20). */
export const RANK_LINES = 30;
export const RANK_MARKS = 15;

export const L = {
	routes: 'trails-routes',
	halo: 'trails-halo',
	haloAgency: 'trails-halo-agency',
	ways: 'trails-ways',
	informal: 'trails-informal',
	selectedHalo: 'trails-selected-halo',
	selected: 'trails-selected',
	selectedHaloAgency: 'trails-selected-halo-agency',
	selectedAgency: 'trails-selected-agency',
	hitWays: 'trails-hit-ways',
	hitAgency: 'trails-hit-agency',
	names: 'trails-names',
	routeNames: 'trails-route-names',
	informalWords: 'trails-informal-words'
} as const;

// -- the states -------------------------------------------------------------------------------------------------------

export type Sev = Severity;
/** The states with a look of their own besides plain (open and no status). */
export const DASHED: readonly Sev[] = ['caution', 'do_not_use', 'closed', 'detour'];
/** Worst first (status.ts's SEVERITY_ORDER; a test checks they agree). */
export const SEVERITY_ORDER: readonly Sev[] = ['closed', 'do_not_use', 'caution', 'detour', 'open', 'not_evaluated'];

export interface Look {
	/** The state in a word (legend, card). */
	word: string;
	/** What the line looks like, in words (legend). */
	shape: string;
	/** MapLibre's dasharray in line widths, or null for solid. */
	dash: readonly number[] | null;
	cap: 'butt' | 'round';
	/** Line width times the base. */
	width: number;
	opacity: number;
	/** The icon on its line (the image's id), if any. */
	icon: string | null;
	/** One line on what it means. */
	about: string;
}

export const LOOKS: Record<Sev, Look> = {
	open: { word: 'Open', shape: 'Solid line', dash: null, cap: 'butt', width: 1, opacity: 1, icon: null, about: 'dry or frozen, or no status is posted' },
	not_evaluated: { word: 'Not evaluated', shape: 'Thin, pale solid line', dash: null, cap: 'butt', width: 0.7, opacity: 0.55, icon: null, about: 'Ridge to Rivers has not evaluated it' },
	caution: { word: 'Caution', shape: 'Long dashes and ▲', dash: [3, 1.8], cap: 'butt', width: 1.1, opacity: 1, icon: 'trails-caution', about: 'could be muddy in places' },
	do_not_use: { word: 'Muddy, stay off', shape: 'Dots and ■', dash: [0.1, 1.7], cap: 'round', width: 1.3, opacity: 1, icon: 'trails-muddy', about: 'Ridge to Rivers asks you to stay off' },
	closed: { word: 'Closed', shape: 'Dash and dot, and ✕', dash: [4, 1.4, 0.1, 1.4], cap: 'butt', width: 1.1, opacity: 1, icon: 'trails-closed', about: 'a closed trail, or a Greenbelt closure' },
	detour: { word: 'Detour', shape: 'Short dashes and arrowheads', dash: [1.6, 1.6], cap: 'butt', width: 1.1, opacity: 1, icon: 'trails-detour', about: "a Greenbelt detour; the arrows show the way" }
};

/** Informal ways: sparse dots (K8: each dash has its word in the legend). */
export const INFORMAL_LOOK = { word: 'Informal', shape: 'Sparse dots', dash: [0.1, 3.4] as readonly number[], about: 'informal, not an official trail' };
export const INFORMAL_WORDS = 'informal, not an official trail';

/** The images the icon layers use (canvas-made by images.ts), by state. */
export const ICON_IDS = ['trails-caution', 'trails-muddy', 'trails-closed', 'trails-detour'] as const;

// -- expressions ---------------------------------------------------------------------------------------------------

type Expr = ExpressionSpecification;
const expr = (e: unknown) => e as Expr;

/** The feature's state, from feature-state (set from /api/trails/status), 'none' when nothing says. */
const SEV: Expr = expr(['coalesce', ['feature-state', 'sev'], 'none']);
const sevIs = (...names: string[]): Expr => expr(['in', SEV, ['literal', names]]);
const only = (sev: Sev): Expr => expr(['case', ['==', SEV, sev], 1, 0]);


/**
 * Line width in px: thin at valley zoom, 1.5 px by z13, then the way's own width in metres from z16 (a
 * 3 m path is 3 m wide on the ground; steps up to z18), never under a minimum; times `scale`, plus `extra`
 * px (the halo's edge). OpenStreetMap's width where tagged, else the estimate by kind (`width_m`).
 */
export function lineWidth(scale: number | Expr = 1, extra = 0): Expr {
	const w: Expr = expr(['coalesce', ['get', 'width_m'], 1.5]);
	// `scale` may be an expression of the feature (a state's width): zoom stays the input of the one top-level interpolate.
	const times = (x: number | Expr, k = 1): number | Expr => (typeof scale === 'number' ? (typeof x === 'number' ? x * scale * k : ['*', x, scale * k]) : ['*', x, k === 1 ? scale : ['*', scale, k]]) as number | Expr;
	const plus = (x: number | Expr): number | Expr => (extra ? (typeof x === 'number' ? x + extra : ['+', x, extra]) : x) as number | Expr;
	return expr([
		'interpolate',
		['exponential', 2],
		['zoom'],
		10,
		plus(times(0.9)),
		13,
		plus(times(1.5)),
		15,
		plus(times(2.1)),
		16,
		plus(['max', times(2.3), times(['/', w, metresPerPx(16)] as Expr)]),
		18,
		plus(['max', times(4), times(['/', w, metresPerPx(18)] as Expr)])
	]);
}

/** The base layer's width: not-evaluated ways are drawn thinner (their feature-state, inside the zoom interpolation). */
const stateWidth: Expr = lineWidth(expr(['case', ['==', SEV, 'not_evaluated'], LOOKS.not_evaluated.width, 1]));

const hidden = { visibility: 'none' as const };
const round = { 'line-join': 'round' as const };

type LineOptions = Partial<Pick<LayerSpecification, 'minzoom' | 'maxzoom'>> & { filter?: FilterSpecification };

function line(id: string, source: string, sourceLayer: string, o: LineOptions, layout: Record<string, unknown>, paint: Record<string, unknown>): LayerSpecification {
	return {
		id,
		type: 'line',
		source,
		'source-layer': sourceLayer,
		...(o.minzoom !== undefined ? { minzoom: o.minzoom } : {}),
		...(o.maxzoom !== undefined ? { maxzoom: o.maxzoom } : {}),
		...(o.filter ? { filter: o.filter } : {}),
		layout: { ...hidden, ...round, ...layout },
		paint
	} as LayerSpecification;
}

/** A state's look as paint: its color, dashes, width and the feature-state opacity that picks the features in this state. */
function stateLine(sev: Sev, id: string, source: string, sourceLayer: string, o: LineOptions): LayerSpecification {
	const look = LOOKS[sev];
	return line(
		id,
		source,
		sourceLayer,
		o,
		{ 'line-cap': look.cap },
		{ 'line-color': UMBER, 'line-width': lineWidth(look.width), 'line-opacity': only(sev), ...(look.dash ? { 'line-dasharray': [...look.dash] } : {}) }
	);
}

/** The layer id of a state's line on ways, or on the agencies' lines. */
export const wayLayer = (sev: Sev) => `trails-ways-${sev}`;
export const agencyLayer = (sev: Sev) => `trails-agency-${sev}`;
export const markLayer = (sev: Sev) => `trails-mark-${sev}`;

const NOT_INFORMAL: FilterSpecification = expr(['!=', ['get', 'informal'], true]) as FilterSpecification;
const INFORMAL: FilterSpecification = expr(['==', ['get', 'informal'], true]) as FilterSpecification;
const HAS_NAME: FilterSpecification = expr(['has', 'name']) as FilterSpecification;
/** Routes that are walked or ridden on trails and the Greenbelt: not the bicycle routes along streets. */
const TRAIL_ROUTE: FilterSpecification = expr([
	'any',
	['in', ['get', 'route'], ['literal', ['hiking', 'foot', 'mtb', 'horse']]],
	['>=', ['index-of', 'Greenbelt', ['coalesce', ['get', 'name'], '']], 0]
]) as FilterSpecification;

const textLayout = {
	'symbol-placement': 'line' as const,
	'text-field': ['get', 'name'] as unknown as Expr,
	'text-font': ['Noto Sans Medium'],
	'text-size': ['interpolate', ['linear'], ['zoom'], 11, 10, 16, 12],
	'text-max-angle': 30,
	'text-padding': 4
};
const textPaint = { 'text-color': UMBER_TEXT, 'text-halo-color': CREAM, 'text-halo-width': 1.6 };

/** The icon layer for a state, on the agencies' whole lines (`marks`): one image, repeated along the line. */
function iconLayer(sev: Sev): LayerSpecification {
	const look = LOOKS[sev];
	const arrow = sev === 'detour';
	return {
		id: markLayer(sev),
		type: 'symbol',
		source: SRC.agency,
		'source-layer': SL.marks,
		minzoom: ZOOMS.minzoom,
		layout: {
			...hidden,
			'symbol-placement': 'line',
			// The closure's ✕ marks are the valley-zoom sign of a trail that is closed, where the dashes are too fine to read.
			'symbol-spacing': sev === 'closed' ? 140 : arrow ? 70 : 220,
			'icon-image': look.icon!,
			'icon-size': ['interpolate', ['linear'], ['zoom'], 10, sev === 'closed' ? 0.8 : 0.65, 13, 0.85, 16, 1],
			'icon-allow-overlap': true,
			'icon-ignore-placement': true,
			// Arrowheads follow the line; the other marks stay upright.
			'icon-rotation-alignment': arrow ? 'map' : 'viewport',
			'icon-keep-upright': false
		},
		paint: { 'icon-opacity': only(sev) }
	} as LayerSpecification;
}

/**
 * The layers, each with its slot: lines in `land` (rank 30), the status icons in `points` and the names in
 * `labels` (rank 15, under Transit's). All start hidden; the module shows them with the layer. The order here
 * is the drawing order within a slot: the routes' wash, the halos, the ways (plain, then each state), the
 * informal ways, the agencies' lines (same states), the selected trail, the invisible hit lines.
 */
export function trailLayers(): SlottedLayer[] {
	const land = (layer: LayerSpecification): SlottedLayer => ({ slot: 'land', layer });
	const lines: LayerSpecification[] = [
		// The routes (hiking, riding and the Greenbelt): a pale umber wash under the lines, so a route reads where it runs on a street or sidewalk.
		line(
			L.routes,
			SRC.routes,
			SL.routes,
			{ minzoom: ZOOMS.minzoom, filter: TRAIL_ROUTE },
			{ 'line-cap': 'round' },
			{ 'line-color': UMBER, 'line-opacity': 0.16, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 3, 13, 6, 16, 11] }
		),
		// A cream halo (never an ink casing, K7) lifts the umber off the lawn, bare soil and asphalt of the ground band.
		line(L.halo, SRC.paths, SL.paths, { minzoom: ZOOMS.minzoom, filter: NOT_INFORMAL }, { 'line-cap': 'round' }, { 'line-color': CREAM, 'line-opacity': 0.7, 'line-width': lineWidth(1, 2.4) }),
		line(L.haloAgency, SRC.agency, SL.agency, { minzoom: ZOOMS.minzoom }, { 'line-cap': 'round' }, {
			'line-color': CREAM,
			'line-opacity': ['case', ['==', SEV, 'ended'], 0, 0.7],
			'line-width': lineWidth(1, 2.4)
		}),
		// Ways: plain (no status, open, not evaluated), then a layer per state from z13. Below z13 the ways are the network, plain.
		line(
			L.ways,
			SRC.paths,
			SL.paths,
			{ minzoom: ZOOMS.minzoom, filter: NOT_INFORMAL },
			{ 'line-cap': 'round' },
			{
				'line-color': UMBER,
				'line-width': stateWidth,
				'line-opacity': ['step', ['zoom'], 1, DETAIL_ZOOM, ['case', sevIs(...DASHED), 0, ['==', SEV, 'not_evaluated'], LOOKS.not_evaluated.opacity, 1]]
			}
		),
		...DASHED.map((sev) => stateLine(sev, wayLayer(sev), SRC.paths, SL.paths, { minzoom: DETAIL_ZOOM, filter: NOT_INFORMAL })),
		// Informal ways: z16, sparse dots, not near a closure (feature-state `hide`, from the status).
		line(
			L.informal,
			SRC.paths,
			SL.paths,
			{ minzoom: INFORMAL_ZOOM, filter: INFORMAL },
			{ 'line-cap': 'round' },
			{
				'line-color': UMBER,
				'line-width': lineWidth(0.9),
				'line-opacity': ['case', ['to-boolean', ['feature-state', 'hide']], 0, 0.9],
				'line-dasharray': [...INFORMAL_LOOK.dash]
			}
		),
		// The agencies' lines: every state, over all zooms (below z13 they are the whole line, from z13 what no way shows).
		stateLine('open', agencyLayer('open'), SRC.agency, SL.agency, { minzoom: ZOOMS.minzoom }),
		line(
			agencyLayer('not_evaluated'),
			SRC.agency,
			SL.agency,
			{ minzoom: ZOOMS.minzoom },
			{ 'line-cap': 'butt' },
			{ 'line-color': UMBER, 'line-width': lineWidth(LOOKS.not_evaluated.width), 'line-opacity': ['case', ['==', SEV, 'not_evaluated'], LOOKS.not_evaluated.opacity, 0] }
		),
		...DASHED.map((sev) => stateLine(sev, agencyLayer(sev), SRC.agency, SL.agency, { minzoom: ZOOMS.minzoom })),
		// The selected trail: a cream halo under its umber line, filtered to the selection's id.
		line(L.selectedHalo, SRC.paths, SL.paths, { minzoom: ZOOMS.minzoom, filter: selectedFilter(null) }, { 'line-cap': 'round' }, { 'line-color': CREAM, 'line-width': lineWidth(1, 7) }),
		line(L.selected, SRC.paths, SL.paths, { minzoom: ZOOMS.minzoom, filter: selectedFilter(null) }, { 'line-cap': 'round' }, { 'line-color': UMBER, 'line-width': lineWidth(1.6) }),
		line(L.selectedHaloAgency, SRC.agency, SL.agency, { minzoom: ZOOMS.minzoom, filter: selectedFilter(null) }, { 'line-cap': 'round' }, { 'line-color': CREAM, 'line-width': lineWidth(1, 7) }),
		line(L.selectedAgency, SRC.agency, SL.agency, { minzoom: ZOOMS.minzoom, filter: selectedFilter(null) }, { 'line-cap': 'round' }, { 'line-color': UMBER, 'line-width': lineWidth(1.6) }),
		// Invisible, wide lines to click: a trail 2 px wide is hard to hit (queryRenderedFeatures ignores opacity).
		line(L.hitWays, SRC.paths, SL.paths, { minzoom: ZOOMS.minzoom }, { 'line-cap': 'round' }, { 'line-color': UMBER, 'line-opacity': 0, 'line-width': 14 }),
		line(L.hitAgency, SRC.agency, SL.agency, { minzoom: ZOOMS.minzoom }, { 'line-cap': 'round' }, { 'line-color': UMBER, 'line-opacity': 0, 'line-width': 14 })
	];
	const marks: SlottedLayer[] = DASHED.map((sev) => ({ slot: 'points' as const, layer: iconLayer(sev) }));
	const labels: SlottedLayer[] = [
		{
			slot: 'labels',
			layer: {
				id: L.routeNames,
				type: 'symbol',
				source: SRC.routes,
				'source-layer': SL.routes,
				minzoom: 11,
				filter: ['all', HAS_NAME, TRAIL_ROUTE],
				layout: { ...hidden, ...textLayout, 'symbol-spacing': 420 },
				paint: textPaint
			} as unknown as LayerSpecification
		},
		{
			slot: 'labels',
			layer: {
				id: L.names,
				type: 'symbol',
				source: SRC.paths,
				'source-layer': SL.paths,
				minzoom: 14,
				filter: ['all', HAS_NAME, NOT_INFORMAL],
				layout: { ...hidden, ...textLayout, 'symbol-spacing': 320 },
				paint: textPaint
			} as unknown as LayerSpecification
		},
		{
			slot: 'labels',
			layer: {
				id: L.informalWords,
				type: 'symbol',
				source: SRC.paths,
				'source-layer': SL.paths,
				minzoom: INFORMAL_ZOOM,
				filter: INFORMAL,
				layout: { ...hidden, ...textLayout, 'text-field': INFORMAL_WORDS, 'text-size': 10, 'symbol-spacing': 360 },
				paint: { ...textPaint, 'text-opacity': ['case', ['to-boolean', ['feature-state', 'hide']], 0, 1] }
			} as unknown as LayerSpecification
		}
	];
	return [...lines.map(land), ...marks, ...labels];
}

/** The filter that picks out the selected feature (none: an id no feature has). */
export function selectedFilter(id: number | null): FilterSpecification {
	return ['==', ['id'], id ?? -1];
}

export const TRAIL_LAYER_IDS: readonly string[] = trailLayers().map((l) => l.layer.id);
/** The layers a click on a way or a line can hit (the invisible wide ones). */
export const HIT_WAYS = [L.hitWays];
export const HIT_AGENCY = [L.hitAgency];

// -- status as feature-state ---------------------------------------------------------------------------------------

/** A feature-state to set: on one feature of one source-layer. */
export interface StateEntry {
	source: string;
	sourceLayer: string;
	id: number;
	state: Record<string, string | boolean>;
}

const key = (e: Pick<StateEntry, 'source' | 'sourceLayer' | 'id'>) => `${e.source}/${e.sourceLayer}/${e.id}`;

/** What a line's state paints (status.ts's wayState): its severity; R2R's unevaluated trails as not_evaluated; null for a row the City has ended. */
export function lineSev(a: Pick<AgencyState, 'source' | 'severity'>): Sev | null {
	if (a.severity) return a.severity;
	return a.source === 'r2r_trails' ? 'not_evaluated' : null;
}

/**
 * Every feature-state the status calls for: each painted way's `sev` (on the ways' tiles), each agency
 * line's `sev` (on its drawn parts and on its whole line for the icons: the key is the line's `line_id`, which is the
 * feature id in the agency tiles), `ended` for a row the City has set inactive (it draws nothing), and `hide`
 * on the informal ways near a closure (plan C18).
 */
export function stateEntries(s: Pick<TrailStatus, 'ways' | 'agencies' | 'hidden'>): StateEntry[] {
	const out = new Map<string, StateEntry>();
	const put = (e: StateEntry) => {
		const k = key(e);
		const was = out.get(k);
		out.set(k, was ? { ...e, state: { ...was.state, ...e.state } } : e);
	};
	for (const [id, sev] of Object.entries(s.ways)) put({ source: SRC.paths, sourceLayer: SL.paths, id: Number(id), state: { sev } });
	for (const a of s.agencies) {
		if (a.line_id === null || a.line_id === undefined) continue;
		const sev = lineSev(a) ?? 'ended';
		put({ source: SRC.agency, sourceLayer: SL.agency, id: a.line_id, state: { sev } });
		put({ source: SRC.agency, sourceLayer: SL.marks, id: a.line_id, state: { sev } });
	}
	for (const id of s.hidden) put({ source: SRC.paths, sourceLayer: SL.paths, id, state: { hide: true } });
	return [...out.values()];
}

/** What to change on the map to go from the feature-states applied to `next`: set the new and changed, remove the ones the status dropped. */
export function planStatus(applied: ReadonlyMap<string, StateEntry>, next: readonly StateEntry[]): { set: StateEntry[]; remove: StateEntry[] } {
	const set: StateEntry[] = [];
	const seen = new Set<string>();
	for (const e of next) {
		const k = key(e);
		seen.add(k);
		const was = applied.get(k);
		if (!was || JSON.stringify(was.state) !== JSON.stringify(e.state)) set.push(e);
	}
	const remove = [...applied].filter(([k]) => !seen.has(k)).map(([, e]) => e);
	return { set, remove };
}

export const stateKey = key;

// -- words ---------------------------------------------------------------------------------------------------------

export const KIND_WORD: Record<string, string> = {
	path: 'Path',
	footway: 'Footpath',
	cycleway: 'Bike path',
	track: 'Track',
	bridleway: 'Bridleway',
	steps: 'Steps',
	pedestrian: 'Pedestrian way'
};
export const SURFACE_WORD = { paved: 'Paved', gravel: 'Gravel', dirt: 'Dirt', unknown: 'Not mapped' } as const;

/** R2R's state codes in words (status.ts: dry, frozen, muddy_further_out, ...), the City's closures and detours, and ended rows. */
export const STATE_WORD: Record<string, string> = {
	dry: 'Dry',
	frozen: 'Frozen',
	muddy_further_out: 'Dry at the start, could be muddy further out',
	frozen_then_muddy: 'Frozen, then muddy',
	muddy: 'Muddy',
	closed: 'Closed',
	not_evaluated: 'Not evaluated',
	unset: 'No status set',
	closure: 'Closed for construction',
	detour: 'Detour',
	ended: 'No longer in effect'
};

export const kindWord = (kind: string) => KIND_WORD[kind] ?? 'Trail';
export const stateWord = (state: string, label?: string | null) => label || STATE_WORD[state] || state;

/** Metres, with feet. */
export function metresFeet(m: number): string {
	const ft = m * 3.28084;
	const r = (v: number) => (v < 10 ? v.toFixed(1) : String(Math.round(v)));
	return `${r(m)} m · ${r(ft)} ft`;
}

/** "since Oct 11" style dates for the card. */
export function dateText(iso: string | null): string {
	if (!iso) return '';
	const d = new Date(iso);
	return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'America/Boise' });
}

/** The surface line on a card: what it is, and where we got it (R2R's dirt default on the card only). */
export function surfaceText(c: Pick<WayCard, 'surface' | 'surface_from' | 'surface_default' | 'surface_tag'>): { text: string; how: string } {
	const word = SURFACE_WORD[c.surface] ?? 'Not mapped';
	if (c.surface_from === 'osm') return { text: word, how: c.surface_tag ? `tagged "${c.surface_tag}" in OpenStreetMap` : 'tagged in OpenStreetMap' };
	if (c.surface_from === 'default' && c.surface_default === 'Ridge to Rivers trail') return { text: word, how: 'assumed: a Ridge to Rivers trail runs along it, and OpenStreetMap does not say' };
	if (c.surface_from === 'default') return { text: word, how: `assumed: OpenStreetMap's default for a ${c.surface_default ?? 'way of this kind'}` };
	return { text: 'Not mapped', how: 'OpenStreetMap does not say' };
}

export function widthText(c: Pick<WayCard, 'width_m' | 'width_from'>): { text: string; how: string } | null {
	if (c.width_m === null || c.width_m === undefined) return null;
	return { text: metresFeet(c.width_m), how: c.width_from === 'osm' ? 'tagged in OpenStreetMap' : 'estimated from the kind of way' };
}

/** The strictest of the lines' severities on a way (a way carrying several shows the worst). */
export function worstSev(lines: readonly { severity: Severity | null; source: string; paints: boolean }[]): Sev | null {
	let best: Sev | null = null;
	for (const l of lines) {
		const sev = lineSev(l);
		if (!sev) continue;
		if (best === null || SEVERITY_ORDER.indexOf(sev) < SEVERITY_ORDER.indexOf(best)) best = sev;
	}
	return best;
}

// -- selections ----------------------------------------------------------------------------------------------------

/** What a click on a feature carries to the card. */
export type TrailData =
	| { type: 'way'; id: number; props: Record<string, unknown>; sev: Sev | null }
	| { type: 'line'; id: number; props: Record<string, unknown>; sev: Sev | null }
	| { type: 'area'; id: number; props: Record<string, unknown> };

interface PickedFeature {
	id?: number | string;
	properties?: Record<string, unknown> | null;
}

const idOf = (f: PickedFeature): number => Number(f.id ?? f.properties?.id);

/** Where a way's state is held for hover text: the module keeps the latest status and says each way's `sev`. */
export interface Statuses {
	way(id: number): Sev | null;
	line(id: number): { sev: Sev | null; label: string | null; state: string; name: string | null } | null;
}

export function waySelection(f: PickedFeature, status: Statuses): Selection | null {
	const id = idOf(f);
	if (!Number.isFinite(id) || id <= 0) return null;
	const p = f.properties ?? {};
	const sev = status.way(id);
	const kind = String(p.kind ?? 'path');
	const informal = p.informal === true || p.informal === 'true';
	const name = typeof p.name === 'string' && p.name ? p.name : null;
	return {
		kind: 'trail',
		id: `way:${id}`,
		layer: 'trails',
		title: name ?? (informal ? 'Informal path' : `Unnamed ${kindWord(kind).toLowerCase()}`),
		fact: informal ? INFORMAL_WORDS : sev && sev !== 'open' ? LOOKS[sev].word : kindWord(kind),
		source: CREDIT_OSM,
		data: { type: 'way', id, props: p, sev } satisfies TrailData
	};
}

export function lineSelection(f: PickedFeature, status: Statuses): Selection | null {
	const id = idOf(f);
	if (!Number.isFinite(id) || id <= 0) return null;
	const p = f.properties ?? {};
	const s = status.line(id);
	const name = (typeof p.name === 'string' && p.name) || s?.name || null;
	const kind = String(p.kind ?? 'trail');
	return {
		kind: 'trail',
		id: `line:${id}`,
		layer: 'trails',
		title: name ?? (kind === 'detour' ? 'Detour' : kind === 'closure' ? 'Closure' : 'Trail'),
		fact: s ? stateWord(s.state, s.label) : kindWord('path'),
		source: 'City of Boise Parks & Recreation',
		data: { type: 'line', id, props: p, sev: s?.sev ?? null } satisfies TrailData
	};
}

/** A paved tread or area from the base layers (`trails.paved_paths` and `paved_areas`): clickable only while Trails is on. */
export function pavedSelection(f: PickedFeature, area: boolean, status: Statuses): Selection | null {
	if (!area) return waySelection({ id: f.id ?? f.properties?.id as number, properties: { ...f.properties, surface: 'paved' } }, status);
	const id = idOf(f);
	if (!Number.isFinite(id)) return null;
	const p = f.properties ?? {};
	return {
		kind: 'paving',
		id: `area:${id}`,
		layer: 'trails',
		title: p.kind === 'pedestrian' ? 'Pedestrian plaza' : 'Paved footway area',
		fact: 'Paved',
		source: CREDIT_OSM,
		data: { type: 'area', id, props: p } satisfies TrailData
	};
}

/** The ids a selection stands for, for the highlight: a way's OSM id, or an agency line's id. */
export function selectedIds(s: Selection | null): { way: number | null; line: number | null } {
	if (!s || s.layer !== 'trails' || s.kind !== 'trail') return { way: null, line: null };
	const [what, id] = s.id.split(':');
	const n = Number(id);
	if (!Number.isFinite(n)) return { way: null, line: null };
	return { way: what === 'way' ? n : null, line: what === 'line' ? n : null };
}

// -- the card API's answers, for the card ---------------------------------------------------------------------------

export type { LineCard, WayCard };

/** The counts line for the legend: R2R's trails now, by what they are. */
export function countsText(counts: Record<string, number>): string[] {
	const n = (...keys: string[]) => keys.reduce((s, k) => s + (counts[k] ?? 0), 0);
	const out: string[] = [];
	const closed = n('closed');
	const mud = n('muddy');
	const caution = n('muddy_further_out', 'frozen_then_muddy');
	const open = n('dry', 'frozen');
	const unchecked = n('not_evaluated', 'unset', 'other');
	if (closed) out.push(`${closed} closed`);
	if (mud) out.push(`${mud} muddy`);
	if (caution) out.push(`${caution} with caution`);
	if (open) out.push(`${open} open`);
	if (unchecked) out.push(`${unchecked} not evaluated`);
	return out;
}
