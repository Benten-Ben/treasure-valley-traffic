import { mixOklab } from '#lib/map/color.js';
import type { SlottedLayer } from '#lib/map/order.js';
import type { MeshKind, SceneInstance } from '#lib/scene/index.js';
import { PRIORITY, type Selection } from '../types.js';

/**
 * The trees layer's shared pieces (docs/19 §19.6): the API's shapes, how a
 * tree becomes a 3D model or a crown disc, its colors, and the words the
 * legend and the tree panel use. Pure, so it's tested without a map.
 *
 * - **Close up** (z15 and in, with the 3D scene running): one scene instance
 *   per tree, by type (broadleaf, conifer, narrow), scaled to its crown and
 *   height, with a soft shadow.
 * - **Farther out** (or without the scene): crown discs, a MapLibre circle
 *   layer sized in metres.
 * - **Kinds** are told apart by tone, as buildings tell measured from
 *   estimated heights (§13.8): catalogued in its full green, placed lighter,
 *   estimated lightest (mixed toward cream, drawn solid: the dither is only
 *   for the disc-to-model crossfade); and by name in the legend, the
 *   tooltip and the panel, never by color alone.
 */

// --- the API (GET /api/trees, /api/trees/areas, /api/trees/<id>) ------------------------------------

export type TreeKind = 'catalogued' | 'placed' | 'estimated';
export type TreeType = 'broadleaf' | 'conifer' | 'narrow';

/** One tree in a view (GET /api/trees?bbox=w,s,e,n&limit=N): h height, r crown radius (m), a/n the top's shape. */
export interface TreeRow {
	id: string;
	kind: TreeKind;
	type: TreeType;
	lng: number;
	lat: number;
	h: number;
	r: number;
	a: number | null;
	n: number | null;
}

export interface TreesInView {
	trees: TreeRow[];
	/** More trees are in the box than `limit`: these are the tallest. */
	truncated: boolean;
}

/** Where trees are built (GET /api/trees/areas). */
export interface TreeArea {
	area: string;
	/** [west, south, east, north] of its trees. */
	bounds: [number, number, number, number];
	trees: number;
	built_at: string | null;
}

/** The private catalogue's attributes (the owner's site only; null elsewhere). */
export interface TreeCatalogue {
	catalogue: string;
	catalogue_id: string;
	common_name: string | null;
	genus: string | null;
	species: string | null;
	dbh_in: number | null;
	installed: string | null;
	last_verified: string | null;
	condition: string | null;
	site_type: string | null;
}

export interface TreeLogEntry {
	at: string;
	event: string;
	detail: Record<string, unknown>;
}

/** One tree (GET /api/trees/<id>). */
export interface TreeDetail {
	id: string;
	area: string;
	kind: TreeKind;
	type: TreeType;
	height_m: number;
	crown_radius_m: number;
	ground_m: number | null;
	lidar: string | null;
	fit: Record<string, unknown>;
	build_id: string;
	catalogue: TreeCatalogue | null;
	/** Newest first. */
	log: TreeLogEntry[];
}

export const KINDS: readonly TreeKind[] = ['catalogued', 'placed', 'estimated'];
export const TYPES: readonly TreeType[] = ['broadleaf', 'conifer', 'narrow'];

// --- drawing ---------------------------------------------------------------------------------------

/** The MapLibre source and the crown-disc layer. */
export const SOURCE = 'trees';
export const DISCS = 'trees-discs';
/**
 * A layer on the source that draws nothing, at every zoom the trees draw:
 * MapLibre credits a source only while one of its layers is shown, and the
 * discs stop at z15 once the models take over.
 */
export const CREDIT_LAYER = 'trees-credit';
/** The map's attribution while Trees is on. */
export const CREDIT = 'Trees: USGS 3DEP lidar, City of Boise, US Forest Service';
/** The scene's group of tree models. */
export const TREES_3D = 'trees-3d';

/**
 * Tone by kind (§19.1): how much cream is mixed into the tree's green (in
 * OKLab). Catalogued its own green, placed a quarter lighter, estimated half
 * (with the discs' dark edge, its legend swatch keeps 3:1 against the card).
 * Every kind draws solid, as buildings show estimates in a lighter tone.
 */
export const KIND_TONE: Record<TreeKind, number> = { catalogued: 0, placed: 0.25, estimated: 0.5 };

/** The model for each type (#lib/scene/meshes.ts). */
export const MESH_OF_TYPE: Record<TreeType, MeshKind> = { broadleaf: 'tree-broad', conifer: 'tree-cone', narrow: 'tree-column' };

/**
 * The trees' greens, by type, three each: the concept models' (Oct 8)
 * shifted a little warmer, toward olive, so every one sits at least ΔE 10
 * from every route color (route aqua #1baf7a the nearest), 12 from the
 * cameras' teal, and 15 from the ghosts, the parks and the ground: they
 * aren't a signal (docs/14's color budget keeps categorical hue for Transit
 * and teal for cameras). The conifers are the darkest.
 * Each tree takes one from its id, so the variation is small and stable.
 */
export const TREE_GREENS: Record<TreeType, readonly [string, string, string]> = {
	broadleaf: ['#6d8d49', '#768f42', '#7d9142'],
	conifer: ['#3a6747', '#426f4e', '#47714a'],
	narrow: ['#80923e', '#85953f', '#8d9a3f']
};
/** The crown discs' edge. */
export const DISC_EDGE = '#3f4f2e';
export const INK = '#2b2a33';
export const CREAM = '#fffbf4';

/** Models from z15 (§19.6), dithered in over the 0.3 zoom before it, as the 3D cameras do. */
export const MODELS_ZOOM = 15;
export const MODELS_FADE = 0.3;
/** Ask for the scene a little before the models show. */
export const SCENE_FROM_ZOOM = 14.5;
/** Discs from z13: a 5 m crown is under a pixel farther out. */
export const DISCS_ZOOM = 13;
/** Trees asked for per view: the API's default limit close up, its maximum for the discs farther out. */
export const LIMIT_3D = 4000;
export const LIMIT_DISCS = 8000;
/**
 * At most this many trees go to the scene: the tallest in view (the legend
 * says so when it applies). Measured on the owner's laptop (M1 GPU, Oct 8;
 * docs/19 §19.6): 4,000 in the scene (about 2,500 drawn) held 60 fps while
 * rotating, at 3–4 ms of the scene's JS a frame (4 ms with Transit, Cameras
 * and Streets on too; 4.1 ms with the hit capsules).
 */
export const SCENE_CAP = 4000;

const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));

/** The models' share of the dither-in (0 at 14.7, 1 at 15). */
export const modelFade = (zoom: number) => clamp((zoom - (MODELS_ZOOM - MODELS_FADE)) / MODELS_FADE, 0, 1);

/** FNV-1a, 32 bits: a stable number from a tree's id. */
export function hashId(id: string): number {
	let h = 0x811c9dc5;
	for (let i = 0; i < id.length; i++) {
		h ^= id.charCodeAt(i);
		h = Math.imul(h, 0x01000193);
	}
	return h >>> 0;
}

/** The tree's green: its type's, picked by its id, so the same everywhere (disc and model). */
export const treeGreen = (id: string, type: TreeType): string => {
	const greens = TREE_GREENS[type] ?? TREE_GREENS.broadleaf;
	return greens[hashId(id) % greens.length];
};

/** Each type's greens in each kind's tone. */
export const TREE_TONES = Object.fromEntries(
	(Object.keys(TREE_GREENS) as TreeType[]).map((type) => [
		type,
		Object.fromEntries((Object.keys(KIND_TONE) as TreeKind[]).map((kind) => [kind, TREE_GREENS[type].map((g) => (KIND_TONE[kind] ? mixOklab(g, CREAM, KIND_TONE[kind]) : g))]))
	])
) as Record<TreeType, Record<TreeKind, string[]>>;

/** The tree's color: its green (treeGreen) in its kind's tone, the same on the disc, the model and the panel. */
export const treeColor = (id: string, type: TreeType, kind: TreeKind): string => {
	const tones = (TREE_TONES[type] ?? TREE_TONES.broadleaf)[kind] ?? TREE_TONES.broadleaf.catalogued;
	return tones[hashId(id) % tones.length];
};

export const TYPE_NAME: Record<TreeType, string> = { broadleaf: 'Broadleaf tree', conifer: 'Conifer', narrow: 'Narrow tree' };
export const KIND_WORD: Record<TreeKind, string> = { catalogued: 'Catalogued', placed: 'Placed', estimated: 'Estimated' };

/** What a click on the tree selects (the card fetches the rest). */
export function treeSelection(t: TreeRow): Selection {
	return {
		kind: 'tree',
		id: t.id,
		layer: 'trees',
		title: TYPE_NAME[t.type],
		fact: `${fmtM(t.h)} tall · ${KIND_WORD[t.kind].toLowerCase()}`,
		// The tooltip's source: the lidar, and the inventory and Urban Tree Database where they apply.
		source: credits(t.kind, t.kind === 'placed' ? null : 'boise')
			.map((c) => c.replace(' (McPherson, van Doorn & Peper 2016)', ''))
			.join(' · '),
		at: [t.lng, t.lat],
		data: t
	};
}

/** Scene instance ids are the tree's id after this (the scene's ids are shared by every group). */
export const TREE_PREFIX = 'tree:';

/**
 * The tree as a scene instance: its type's model, scaled [r, r, h] (the
 * meshes are a unit crown radius and height), a soft shadow, its color
 * (treeColor: its kind's tone), solid but for the dither-in, and a hit
 * capsule as wide as its crown from trunk to top (the bounding sphere of a
 * tree three times taller than wide would catch clicks metres off it).
 * Selected, it stays on the ground at its size: the ground ring marks it.
 */
export function treeInstance(t: TreeRow, fade = 1, pick: Selection | null = treeSelection(t)): SceneInstance {
	return {
		id: `${TREE_PREFIX}${t.id}`,
		mesh: MESH_OF_TYPE[t.type],
		lng: t.lng,
		lat: t.lat,
		scale: [t.r, t.r, t.h],
		color: treeColor(t.id, t.type, t.kind),
		opacity: fade,
		shadow: true,
		pick,
		pickRadius: t.r,
		grounded: true
	};
}

/** The crown disc's feature. */
export function discFeature(t: TreeRow): GeoJSON.Feature<GeoJSON.Point> {
	return {
		type: 'Feature',
		geometry: { type: 'Point', coordinates: [t.lng, t.lat] },
		properties: { id: t.id, kind: t.kind, type: t.type, h: t.h, r: t.r, c: treeColor(t.id, t.type, t.kind) }
	};
}

export function discCollection(trees: readonly TreeRow[]): GeoJSON.FeatureCollection<GeoJSON.Point> {
	return { type: 'FeatureCollection', features: trees.map(discFeature) };
}

/** Metres of ground per CSS px at zoom 0 on the equator, for 512 px tiles. */
const M_PER_PX_Z0 = 78271.517;
/** The pilot's latitude (the North End): the disc radius uses it everywhere in the valley (under 0.5% off). */
export const DISC_LAT = 43.62;

/** A crown radius (m) in px at a zoom. */
export const metresToPx = (m: number, zoom: number, lat = DISC_LAT) => (m * 2 ** zoom) / (M_PER_PX_Z0 * Math.cos((lat * Math.PI) / 180));

/**
 * The disc's radius in px: its crown radius in metres at every zoom (an
 * exponential-2 interpolation between whole zooms is exact), and at least
 * 1 px so the far discs don't vanish.
 */
export function discRadius(): unknown[] {
	const stops: unknown[] = [];
	for (let z = DISCS_ZOOM - 1; z <= 22; z++) stops.push(z, ['max', 1, ['*', ['get', 'r'], metresToPx(1, z)]]);
	return ['interpolate', ['exponential', 2], ['zoom'], ...stops];
}

/**
 * The disc's opacity: solid (the kind is in its color); with models, fading
 * out as they dither in. Zoom alone, never a feature's value: MapLibre
 * evaluates a zoom-and-feature expression only at whole zooms and blends
 * between them, which would start the fade at z14 instead of 14.7.
 */
export function discOpacity(withModels: boolean): unknown {
	if (!withModels) return 1;
	return ['interpolate', ['linear'], ['zoom'], MODELS_ZOOM - MODELS_FADE, 1, MODELS_ZOOM, 0];
}

/**
 * The crown discs, in the scene slot: above the buildings with the 3D models
 * (they take turns by zoom), under the 2D points (stop capsules, camera
 * icons) and the labels. A circle layer isn't draped, so it never splits the
 * terrain's draped run. The taller tree's disc is drawn over the shorter.
 * And the credit layer (CREDIT_LAYER), which matches no tree.
 */
export function treeLayers(): SlottedLayer[] {
	return [
		{
			slot: 'scene',
			layer: {
				id: DISCS,
				type: 'circle',
				source: SOURCE,
				minzoom: DISCS_ZOOM,
				layout: { visibility: 'none', 'circle-sort-key': ['get', 'h'] },
				paint: {
					'circle-radius': discRadius() as never,
					'circle-color': ['get', 'c'],
					'circle-opacity': discOpacity(false) as never,
					'circle-stroke-color': ['case', ['boolean', ['feature-state', 'hover'], false], INK, DISC_EDGE],
					'circle-stroke-width': ['case', ['boolean', ['feature-state', 'hover'], false], 2, 0.75],
					'circle-stroke-opacity': discOpacity(false) as never,
					'circle-pitch-alignment': 'map',
					'circle-pitch-scale': 'map'
				}
			}
		},
		{
			slot: 'scene',
			layer: {
				id: CREDIT_LAYER,
				type: 'circle',
				source: SOURCE,
				minzoom: DISCS_ZOOM,
				filter: ['==', ['get', 'kind'], ''],
				layout: { visibility: 'none' },
				paint: { 'circle-radius': 0, 'circle-opacity': 0, 'circle-stroke-width': 0 }
			}
		}
	];
}

export const TREE_PRIORITY = PRIORITY.tree;

// --- fetching by view ------------------------------------------------------------------------------

export type Box = [number, number, number, number];

/** Grid the fetched boxes snap out to (degrees), so small pans ask for the same URL. */
export const SNAP_DEG = 0.002;

const snapDown = (x: number) => Math.floor(x / SNAP_DEG) * SNAP_DEG;
const snapUp = (x: number) => Math.ceil(x / SNAP_DEG) * SNAP_DEG;
const r6 = (x: number) => Math.round(x * 1e6) / 1e6;

/**
 * The box to ask for: the view grown by a quarter each way, kept within
 * `radiusM` of the centre (in a tilted view the bounds reach the horizon,
 * where trees are too small to see), snapped out to the grid.
 */
export function wantedBox(view: Box, centre: [number, number], radiusM: number): Box {
	let [w, s, e, n] = view;
	const dx = (e - w) / 4;
	const dy = (n - s) / 4;
	w -= dx;
	e += dx;
	s -= dy;
	n += dy;
	const kx = radiusM / (111_320 * Math.cos((centre[1] * Math.PI) / 180));
	const ky = radiusM / 110_574;
	w = Math.max(w, centre[0] - kx);
	e = Math.min(e, centre[0] + kx);
	s = Math.max(s, centre[1] - ky);
	n = Math.min(n, centre[1] + ky);
	return [r6(snapDown(w)), r6(snapDown(s)), r6(snapUp(e)), r6(snapUp(n))];
}

export const boxArea = (b: Box) => Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
export const contains = (outer: Box, inner: Box) => outer[0] <= inner[0] && outer[1] <= inner[1] && outer[2] >= inner[2] && outer[3] >= inner[3];
export const inBox = (b: Box, lng: number, lat: number) => lng >= b[0] && lng <= b[2] && lat >= b[1] && lat <= b[3];
export const intersects = (a: Box, b: Box) => a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];

/**
 * Whether what was fetched still serves the view: it covers the wanted box
 * at the same limit, and, when it was cut to the tallest, it isn't more than
 * twice the size (zoomed in that far, the smaller box has more trees to show).
 */
export function stillServes(fetched: { box: Box; limit: number; truncated: boolean } | null, want: Box, limit: number): boolean {
	if (!fetched || fetched.limit !== limit || !contains(fetched.box, want)) return false;
	return !fetched.truncated || boxArea(fetched.box) <= 2 * boxArea(want);
}

export const treesUrl = (b: Box, limit: number) => `/api/trees?bbox=${b.join(',')}&limit=${limit}`;

// --- words -----------------------------------------------------------------------------------------

/** The test areas' names (the pilot is area c, the North End box; docs/19 §19.7). */
export const AREA_NAMES: Record<string, string> = { c: 'the North End' };
export const areaName = (area: string) => AREA_NAMES[area] ?? `area ${area}`;

/** "the North End", "the North End and area d", "a, b and c". */
export function listNames(names: readonly string[]): string {
	if (names.length <= 1) return names[0] ?? '';
	return `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`;
}

/** Where trees are built, in words (the legend; never filled in from another source). */
export function builtText(areas: readonly TreeArea[]): string {
	if (!areas.length) return 'No trees are built yet.';
	const names = listNames(areas.map((a) => areaName(a.area)));
	return `Trees are built for ${names} so far.`;
}

const FT_PER_M = 3.28084;
export const fmtM = (m: number) => `${m >= 10 ? Math.round(m) : m.toFixed(1)} m`;
/** "26.8 m · 88 ft". */
export const metresFeet = (m: number) => `${m.toFixed(1)} m · ${Math.round(m * FT_PER_M)} ft`;
export const fmtCount = (n: number) => n.toLocaleString('en-US');

/** The catalogue's name in words. */
export const CATALOGUE_NAME: Record<string, string> = { boise: 'City of Boise' };

/** The lidar's year: from its name ("…flown Sep-Oct 2023…"), else from its log entry, else 2023 (the pilot's survey). */
export function lidarYear(d: Pick<TreeDetail, 'lidar' | 'log'>): string {
	const m = /\b(20\d\d)\b(?!.*\b20\d\d\b)/.exec(d.lidar ?? '');
	if (m) return m[1];
	const e = d.log.find((x) => x.event === 'measured' || x.event === 'placed');
	return e ? e.at.slice(0, 4) : '2023';
}

/** The kind, explained in plain words (§19.1). */
export function kindText(kind: TreeKind, year = '2023', catalogue = 'City of Boise'): string {
	switch (kind) {
		case 'catalogued':
			return `In the ${catalogue}'s inventory, measured by the ${year} lidar`;
		case 'placed':
			return `Found in the ${year} lidar; position and crown estimated by placement`;
		case 'estimated':
			return `In the ${catalogue === 'City of Boise' ? 'City' : catalogue}'s inventory but not seen in the ${year} lidar; sized from its species and trunk diameter`;
	}
}

/** The panel's title: the species' common name for catalogued and estimated trees (when the catalogue is here), else the type. */
export function treeTitle(d: Pick<TreeDetail, 'kind' | 'type' | 'catalogue'>): string {
	const name = d.kind !== 'placed' ? d.catalogue?.common_name?.trim() : null;
	return name || TYPE_NAME[d.type];
}

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** How we know, in plain words (§19.3): the lidar, the trunk point's distance to the crown, or the placement's fit. */
export function howWeKnow(d: Pick<TreeDetail, 'kind' | 'fit' | 'lidar' | 'log'>): string[] {
	const year = lidarYear(d);
	const f = d.fit ?? {};
	const out: string[] = [];
	if (d.kind === 'catalogued') {
		out.push(`Its height is the ${year} lidar's highest point over its crown.`);
		const off = num(f.trunk_to_crown_m);
		if (off !== null)
			out.push(off < 0.5 ? 'The crown sits right over the trunk point in the inventory.' : `The crown's top is ${off.toFixed(1)} m from the trunk point in the inventory (crowns lean and grow away from neighbours).`);
		out.push("Its crown width comes from its species' size for its trunk, checked against the lidar.");
	} else if (d.kind === 'placed') {
		out.push(`Its height is measured by the ${year} lidar.`);
		out.push("Its position and crown were estimated by placement: the crown that best explains the lidar's canopy there.");
		const sd = num(f.width_vs_typical_sd);
		if (sd !== null)
			out.push(Math.abs(sd) < 0.5 ? 'Its crown is a typical width for its height.' : `Its crown is ${Math.abs(sd).toFixed(1)} standard deviations ${sd > 0 ? 'wider' : 'narrower'} than typical for its height.`);
		if (f.crowded === true) out.push('It stands in a cluster, so its crown meets its neighbours high up.');
	} else {
		out.push(`The ${year} lidar doesn't show it (planted after the flight, or under 3 m), so its height and crown are estimated from its species and trunk diameter (US Forest Service Urban Tree Database, Boise).`);
		const there = num(f.lidar_height_there_m);
		if (f.under_taller_crown === true) out.push(`It stands under a taller tree's crown${there !== null ? ` (the lidar there is ${fmtM(there)})` : ''}.`);
	}
	return out;
}

/** Readable names for the log's events. */
export const EVENT_NAMES: Record<string, string> = {
	measured: 'Measured by lidar',
	placed: 'Placed from the lidar',
	estimated: 'Sized from species and trunk',
	matched: 'Matched to the inventory',
	catalogued: 'Matched to the inventory',
	removed: 'Gone from newer lidar',
	measured_2005: 'Measured by the US Forest Service (2005)'
};

export function eventName(e: string): string {
	if (EVENT_NAMES[e]) return EVENT_NAMES[e];
	const s = e.replace(/[_-]+/g, ' ').trim();
	return s ? s[0].toUpperCase() + s.slice(1) : 'Event';
}

/** One line on what the event recorded ("26.8 m tall, crown 18.9 m wide"). */
export function eventDetail(e: TreeLogEntry): string {
	const d = e.detail ?? {};
	const parts: string[] = [];
	const h = num(d.height_m);
	const w = num(d.crown_width_m);
	if (h !== null) parts.push(`${fmtM(h)} tall`);
	if (w !== null) parts.push(`crown ${fmtM(w)} wide`);
	const dbh = num(d.dbh_in);
	if (dbh !== null) parts.push(`trunk ${Math.round(dbh)} in`);
	if (typeof d.why === 'string' && d.why) parts.push(d.why);
	return parts.join(', ');
}

/** A date in words, at noon UTC so a plain date never moves a day ("Oct 24, 2023"). */
export function dateText(s: string | null | undefined): string | null {
	if (!s) return null;
	const iso = /^\d{4}-\d{2}-\d{2}$/.test(s) ? `${s}T12:00:00Z` : s;
	const t = new Date(iso);
	if (Number.isNaN(t.getTime())) return s;
	return t.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
}

/** The trunk's diameter in inches: the catalogue's, else the one an estimate was sized from. */
export function trunkIn(d: Pick<TreeDetail, 'catalogue' | 'fit'>): number | null {
	return num(d.catalogue?.dbh_in) ?? num(d.fit?.dbh_in);
}

/** The panel's credits by kind: the lidar always; the City for catalogued and estimated trees; the Urban Tree Database for estimated ones. */
export function credits(kind: TreeKind, catalogue: string | null, year = '2023'): string[] {
	const out = [`USGS 3DEP lidar (${year})`];
	if (kind !== 'placed') out.push(`${catalogue ? (CATALOGUE_NAME[catalogue] ?? catalogue) : 'City of Boise'} tree inventory`);
	if (kind === 'estimated') out.push('US Forest Service Urban Tree Database (McPherson, van Doorn & Peper 2016)');
	return out;
}
