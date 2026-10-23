import type * as Protomaps from '@protomaps/basemaps';
import type { LayerSpecification, LineLayerSpecification, Map as GlMap, StyleSpecification } from 'maplibre-gl';
import type * as Flavors from './flavors.js';
import type { FlavorName, PaintChange } from './flavors.js';
import { BUILDING_BASE, BUILDING_HEIGHT, ESTIMATED_FILTER, MEASURED_FILTER } from './buildings.js';
import { anchorLayer, ANCHORS, insertSlotted } from './order.js';
import type { BaseContribution, BaseState } from '#lib/base/types.js';
import { BASE_CONTRIBUTIONS } from '#lib/base/registry.js';
import type { DataMeta } from '#lib/contracts/meta.js';
import { DEFAULT_HILLSHADE, type HillshadeMode } from '#lib/perf/flags.js';

/** Where the basemap build (basemap/) publishes its output. Same origin, no third-party hosts. */
export const TILES_PATH = '/tiles';

/** Layer ids of the aerial imagery, toggled together by the Map/Aerial switch (added on first use). */
export const IMAGERY_LAYERS = ['aerial', 'aerial-detail'];

/** Layer id of the 3D buildings with a measured height. */
export const BUILDINGS_LAYER = 'buildings-3d';

/** Layer id of the 3D buildings drawn at an estimated height, in a lighter tone (`#lib/map/buildings`). */
export const BUILDINGS_ESTIMATED_LAYER = 'buildings-3d-estimated';

/**
 * Both 3D building layers, measured then estimated. The Buildings switch,
 * Aerial's opacity and the flavors treat them as one.
 */
export const BUILDINGS_LAYERS: readonly string[] = [BUILDINGS_LAYER, BUILDINGS_ESTIMATED_LAYER];

/** Layer id of the hillshade. */
export const HILLSHADE_LAYER = 'hillshade';

/**
 * Building opacity: cream blocks in Valley, see-through in Clay (docs/14
 * §14.5), and lower still over the aerial photo in either flavor, where the
 * photo's own roofs show through and buildings near the edge of a tilted view
 * don't hide the ground points a calibration needs.
 */
export const BUILDING_OPACITY = { valley: 0.9, clay: 0.55, aerial: 0.3 } as const;

export function buildingOpacity(aerial: boolean, flavor: FlavorName = 'valley'): number {
	return aerial ? BUILDING_OPACITY.aerial : BUILDING_OPACITY[flavor];
}

let protomaps: typeof Protomaps | null = null;
let flavors: typeof Flavors | null = null;

/**
 * The Protomaps style module (about 16 KB gzip) and the base flavors
 * (`#lib/map/flavors`), loaded apart from the initial JavaScript to keep it
 * within its budget (docs/14 §14.9, WP2). The imports start as soon as this
 * module runs, in parallel with the manifest fetch, and `loadManifest`
 * resolves only once they're here, so `buildStyle` (which needs them) can
 * stay synchronous.
 */
export const basemapReady: Promise<void> = Promise.all([import('@protomaps/basemaps'), import('./flavors.js')]).then(([m, f]) => {
	protomaps = m;
	flavors = f;
});

function basemap(): typeof Protomaps {
	if (!protomaps) throw new Error('The basemap style module has not loaded yet: await basemapReady (loadManifest does).');
	return protomaps;
}

/**
 * The base flavors module, once `basemapReady` has resolved (it has whenever a
 * map exists: the map is built from `buildStyle`).
 */
export function flavorKit(): typeof Flavors {
	if (!flavors) throw new Error('The base flavors have not loaded yet: await basemapReady (loadManifest does).');
	return flavors;
}

interface TileFile {
	/** File name relative to /tiles/, e.g. "valley.pmtiles". */
	file: string;
	attribution: string;
	/** ISO date the file was built. */
	built: string;
}

/**
 * Contract between the basemap build and the app: basemap/ writes
 * manifest.json listing what it has built, and the map shows exactly that.
 */
export interface BasemapManifest {
	/** [west, south, east, north] of the extract. */
	bounds: [number, number, number, number];
	center: [number, number];
	zoom: number;
	/** Protomaps OpenStreetMap vector tiles. */
	basemap: TileFile & { flavor: string };
	/** Glyph template relative to /tiles/, e.g. "fonts/{fontstack}/{range}.pbf". */
	glyphs: string;
	/** Sprite path relative to /tiles/, e.g. "sprites/v4/light". */
	sprite: string;
	/** Terrain-RGB elevation tiles built from the USGS 3DEP 1 m DEM. */
	terrain?: TileFile & { encoding: 'mapbox' | 'terrarium'; tileSize: number; exaggeration: number };
	/** Building footprints with heights (metres) for extrusion. */
	buildings?: TileFile & { sourceLayer: string; minzoom: number };
	/**
	 * Aerial imagery (NAIP), shown in the Aerial view: valley-wide up to
	 * `maxzoom`, plus an optional sharper file around the cameras.
	 */
	imagery?: TileFile & {
		tileSize: number;
		maxzoom: number;
		detail?: { file: string; minzoom: number; maxzoom: number; points: number; radius: number };
	};
	/** The landscape base layers (one shared vector file); absent: not built yet. */
	landscape?: LandscapeEntry;
	/** The painted ground; absent: not built yet. */
	ground?: GroundEntry;
}

/**
 * The landscape file's entry (basemap/landscape/README.md, "The tiles-manifest entry"): one vector file
 * holding every base layer the plugins export, written last by the bake. `layers` lists exactly the
 * source-layers in the file, each with at least one feature; one whose export held none is under
 * `empty` and is not in the file.
 */
export interface LandscapeLayerInfo {
	plugin: string;
	layer: string;
	build: string;
	geometry: string;
	features: number;
	fields: Record<string, string>;
	minzoom: number;
	maxzoom: number;
	licence: string;
	republish: string;
	credit: string[];
}

export type LandscapeEntry =
	| {
			status: 'baked';
			file: string;
			digest: string;
			format: string;
			minzoom: number;
			maxzoom: number;
			promoteId: string;
			layers: Record<string, LandscapeLayerInfo>;
			empty: string[];
			attribution: string;
			licences: string[];
			republish: string;
			access: 'tailnet' | 'public';
			inputs: string[];
			built: string;
			spec: number;
			previous: string | null;
	  }
	/** Nothing to bake yet, or every base layer is empty. */
	| { status: 'empty'; reason: string; previous: string | null; built: string; spec: number };

/**
 * The painted ground's entry (basemap/ground/README.md): `painted` with a valley-wide raster file and
 * a sharper one around the key spots, or `flat` with the reason (the app then keeps the flat ground and
 * says why). No entry at all: not built yet.
 */
export type GroundEntry =
	| {
			status: 'painted';
			file: string;
			tileSize: number;
			format: string;
			minzoom: number;
			maxzoom: number;
			detail: { file: string; minzoom: number; maxzoom: number; boxes: string[] };
			attribution: string;
			licence: string;
			republish: string;
			inputs: string[];
			fallbacks: string[];
			built: string;
			spec: number;
	  }
	| { status: 'flat'; reason: string; built: string; spec: number };

export type ManifestResult =
	| { ok: true; manifest: BasemapManifest }
	| { ok: false; reason: string };

/** The manifest; an ok result also means the basemap style module has loaded (`basemapReady`). */
export async function loadManifest(fetchFn: typeof fetch = fetch): Promise<ManifestResult> {
	let res: Response;
	try {
		res = await fetchFn(`${TILES_PATH}/manifest.json`);
	} catch (e) {
		return { ok: false, reason: `Could not reach ${TILES_PATH}/manifest.json: ${e}` };
	}
	if (res.status === 404) {
		return { ok: false, reason: 'The basemap has not been built yet. See basemap/README.md.' };
	}
	if (!res.ok) {
		return { ok: false, reason: `${TILES_PATH}/manifest.json returned HTTP ${res.status}.` };
	}
	const manifest = (await res.json()) as BasemapManifest;
	try {
		await basemapReady;
	} catch (e) {
		return { ok: false, reason: `The basemap style failed to load (reload to try again): ${e}` };
	}
	return { ok: true, manifest };
}

export const pmtilesUrl = (origin: string, file: string) => `pmtiles://${origin}${TILES_PATH}/${file}`;

const RAIL = '#6f6a75';

/** A railway as a track line plus cross-ties (from zoom 13), replacing the basemap's rail layer. */
export function railLayers(l: LineLayerSpecification): LineLayerSpecification[] {
	const track: LineLayerSpecification = {
		...l,
		id: 'rail-track',
		paint: {
			'line-color': RAIL,
			'line-opacity': 0.9,
			'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.6, 12, 1.2, 15, 2, 18, 3.5]
		}
	};
	const ties: LineLayerSpecification = {
		...l,
		id: 'rail-ties',
		minzoom: Math.max(13, l.minzoom ?? 0),
		paint: {
			'line-color': RAIL,
			'line-opacity': 0.75,
			'line-width': ['interpolate', ['linear'], ['zoom'], 13, 5, 18, 11],
			// Dash lengths scale with the line width: thin ties, wide gaps.
			'line-dasharray': [0.12, 1.6]
		}
	};
	return [track, ties];
}

/**
 * Named groups of the basemap's layer ids (S3a). A landscape layer or base contribution hides a group
 * while it draws its own version (`suppressGroups`). Checked against Protomaps' own list in
 * `style.test.ts`, so a Protomaps update that renames a layer fails a test, not the map.
 */
export const PROTOMAPS_GROUPS = {
	/** Land cover and every land-use fill: the "landcover and landuse" run under `anchor:areas`. */
	landcover: [
		'landcover',
		'landuse_park',
		'landuse_urban_green',
		'landuse_hospital',
		'landuse_industrial',
		'landuse_school',
		'landuse_beach',
		'landuse_zoo',
		'landuse_aerodrome',
		'landuse_runway',
		'landuse_pedestrian',
		'landuse_pier'
	],
	/** Water fills and lines, the run under `anchor:water`. */
	water: ['water', 'water_stream', 'water_river'],
	'water-labels': ['water_waterway_label', 'water_label_lakes'],
	/** Every road line except rail, runway, taxiway and pier (tunnels, bridges and casings included). */
	roads: [
		'roads_tunnels_other_casing',
		'roads_tunnels_minor_casing',
		'roads_tunnels_link_casing',
		'roads_tunnels_major_casing',
		'roads_tunnels_highway_casing',
		'roads_tunnels_other',
		'roads_tunnels_minor',
		'roads_tunnels_link',
		'roads_tunnels_major',
		'roads_tunnels_highway',
		'roads_minor_service_casing',
		'roads_minor_casing',
		'roads_link_casing',
		'roads_major_casing_late',
		'roads_highway_casing_late',
		'roads_other',
		'roads_link',
		'roads_minor_service',
		'roads_minor',
		'roads_major_casing_early',
		'roads_major',
		'roads_highway_casing_early',
		'roads_highway',
		'roads_bridges_other_casing',
		'roads_bridges_link_casing',
		'roads_bridges_minor_casing',
		'roads_bridges_major_casing',
		'roads_bridges_other',
		'roads_bridges_minor',
		'roads_bridges_link',
		'roads_bridges_major',
		'roads_bridges_highway_casing',
		'roads_bridges_highway'
	],
	/** Service roads (alleys, driveways, parking aisles) and their casing. */
	service: ['roads_minor_service', 'roads_minor_service_casing'],
	/** Footpaths, cycleways and tracks. */
	paths: ['roads_other']
} as const satisfies Record<string, readonly string[]>;

export type ProtomapsGroup = keyof typeof PROTOMAPS_GROUPS;

// Protomaps draws these three after its water (or over the runway lines), so they stay in the 'rest' run
// in its own order; they are in the landcover group only so a landscape layer can suppress them.
const OVER_WATER_IDS: ReadonlySet<string> = new Set(['landuse_runway', 'landuse_pedestrian', 'landuse_pier']);
const LAND_IDS: ReadonlySet<string> = new Set(PROTOMAPS_GROUPS.landcover.filter((id) => !OVER_WATER_IDS.has(id)));
const WATER_IDS: ReadonlySet<string> = new Set(PROTOMAPS_GROUPS.water);

/**
 * The basemap's own layers in a flavor (docs/14 §14.5: Valley or Clay over the
 * manifest's Protomaps flavor). The fills and lines come in four runs, which the
 * landscape slots separate (docs/14 §14.8, "Layer order"): `head` (background and
 * earth), the `land` fills, the `water` layers, and the `rest` (road lines, rail,
 * flat buildings, boundaries); the labels above them.
 */
function basemapLayers(
	m: BasemapManifest,
	flavor: FlavorName
): { head: LayerSpecification[]; land: LayerSpecification[]; water: LayerSpecification[]; rest: LayerSpecification[]; labels: LayerSpecification[] } {
	const { layers, namedFlavor } = basemap();
	let base = layers('protomaps', flavorKit().flavorOf(namedFlavor(m.basemap.flavor), flavor), { lang: 'en' });
	if (m.buildings) {
		// Our extruded buildings take over from the basemap's flat footprints.
		const minzoom = m.buildings.minzoom;
		base = base.map((l) => (l.id === 'buildings' ? { ...l, maxzoom: minzoom } : l));
	}
	// Railways: the basemap's faint dashed gray is easy to miss, so draw them as
	// classic railroad marks instead, a solid track line with cross-ties.
	base = base.flatMap((l) => (l.id === 'roads_rail' && l.type === 'line' ? railLayers(l) : [l]));
	const firstSymbol = base.findIndex((l) => l.type === 'symbol');
	const below = firstSymbol === -1 ? base : base.slice(0, firstSymbol);
	const head: LayerSpecification[] = [];
	const land: LayerSpecification[] = [];
	const water: LayerSpecification[] = [];
	const rest: LayerSpecification[] = [];
	for (const l of below) {
		if (l.id === 'background' || l.id === 'earth') head.push(l);
		else if (LAND_IDS.has(l.id)) land.push(l);
		else if (WATER_IDS.has(l.id)) water.push(l);
		else rest.push(l);
	}
	return { head, land, water, rest, labels: firstSymbol === -1 ? [] : base.slice(firstSymbol) };
}

/**
 * The layer the aerial imagery goes right after: the hillshade when there's
 * terrain, else the end of the base slot (`anchor:base`, right after the
 * basemap's fills and lines). Imagery sits above the basemap's fills and
 * roads and below everything the app adds.
 */
export function aerialAfter(m: BasemapManifest): string {
	return m.terrain ? 'hillshade' : ANCHORS.base;
}

/**
 * The imagery sources and layers: NAIP, plus the sharper detail file around
 * the cameras. In Clay the photo is muted (§14.5).
 */
function imagery(m: BasemapManifest, origin: string, visible: boolean, saturation = 0) {
	const paint = { 'raster-saturation': saturation };
	const sources: StyleSpecification['sources'] = {};
	const out: LayerSpecification[] = [];
	if (!m.imagery) return { sources, layers: out };
	sources.imagery = {
		type: 'raster',
		url: pmtilesUrl(origin, m.imagery.file),
		tileSize: m.imagery.tileSize,
		attribution: m.imagery.attribution
	};
	out.push({
		id: IMAGERY_LAYERS[0],
		type: 'raster',
		source: 'imagery',
		layout: { visibility: visible ? 'visible' : 'none' },
		paint: { ...paint }
	});
	// Sharper imagery around the cameras, over the valley layer: where it
	// has no tile, the valley imagery below shows through.
	const detail = m.imagery.detail;
	if (detail) {
		sources.imageryDetail = {
			type: 'raster',
			url: pmtilesUrl(origin, detail.file),
			tileSize: m.imagery.tileSize
		};
		out.push({
			id: IMAGERY_LAYERS[1],
			type: 'raster',
			source: 'imageryDetail',
			minzoom: detail.minzoom,
			layout: { visibility: visible ? 'visible' : 'none' },
			paint: { ...paint }
		});
	}
	return { sources, layers: out };
}

/** The 3D terrain's DEM source. */
export const TERRAIN_SOURCE = 'terrain';

/** The second DEM source, which exists only with `?hillshade=capped`. */
export const HILLSHADE_SOURCE = 'hillshade';

/**
 * The capped second source's highest zoom: up to it the hillshade is as sharp
 * as with two full sources (and costs as much); above it, it overzooms these
 * tiles instead of fetching the terrain's z13–z14 a second time.
 */
export const HILLSHADE_CAP_ZOOM = 12;

let hillshade: HillshadeMode = DEFAULT_HILLSHADE;

/**
 * Where maps built from now on take the hillshade's elevations from (the boot
 * sets it from `?hillshade=`, before the map exists). See `terrainSources`.
 */
export function setHillshadeMode(mode: HillshadeMode): void {
	hillshade = mode;
}

export function hillshadeMode(): HillshadeMode {
	return hillshade;
}

/**
 * The DEM sources and the hillshade's source (docs/14 §14.9, fix 1; the
 * owner's Q7 answer).
 *
 * - `terrain` (default): one source. The hillshade reads the tiles the 3D
 *   surface already loaded, so each DEM tile downloads and decodes once. Those
 *   are the mesh's tiles, one zoom level below the view's (MapLibre's terrain
 *   `deltaZoom`), so the shading is a little softer up to z14 and the same
 *   from z15, where both stop at the file's z14. MapLibre logs a one-time
 *   warning about the shared source; that's this choice, not a fault.
 * - `capped`: a second source for the hillshade, as MapLibre recommends, but
 *   with `maxzoom` capped at `HILLSHADE_CAP_ZOOM`: full-zoom shading up to z12
 *   (twice the DEM bytes there), overzoomed above it.
 */
export function terrainSources(
	m: BasemapManifest,
	origin: string,
	mode: HillshadeMode = hillshade
): { sources: StyleSpecification['sources']; hillshadeSource: string } {
	if (!m.terrain) return { sources: {}, hillshadeSource: TERRAIN_SOURCE };
	const dem = {
		type: 'raster-dem' as const,
		url: pmtilesUrl(origin, m.terrain.file),
		encoding: m.terrain.encoding,
		tileSize: m.terrain.tileSize,
		attribution: m.terrain.attribution
	};
	if (mode === 'capped') {
		return {
			sources: { [TERRAIN_SOURCE]: dem, [HILLSHADE_SOURCE]: { ...dem, maxzoom: HILLSHADE_CAP_ZOOM } },
			hillshadeSource: HILLSHADE_SOURCE
		};
	}
	return { sources: { [TERRAIN_SOURCE]: dem }, hillshadeSource: TERRAIN_SOURCE };
}

/** The parts of a MapLibre map the style helpers use (so tests can pass a fake). */
export type MapLike = Pick<
	GlMap,
	'getLayer' | 'getSource' | 'addSource' | 'addLayer' | 'getLayersOrder' | 'setLayoutProperty' | 'setPaintProperty'
>;

/**
 * Add the aerial imagery to a running map the first time Aerial is wanted
 * (docs/14 §14.8: imagery sources only in Aerial). Its layers go right after
 * `aerialAfter(m)`, hidden. Once added they stay; turning Aerial off only
 * hides them. Returns false when the manifest has no imagery.
 */
export function addAerial(map: MapLike, m: BasemapManifest, origin: string): boolean {
	if (!m.imagery) return false;
	if (map.getLayer(IMAGERY_LAYERS[0])) return true;
	const { sources, layers: imageryLayers } = imagery(m, origin, false, flavorKit().photoSaturation(map));
	for (const [id, src] of Object.entries(sources)) if (!map.getSource(id)) map.addSource(id, src);
	const order = map.getLayersOrder();
	const i = order.indexOf(aerialAfter(m));
	const before = i === -1 ? order[0] : order[i + 1];
	for (const l of imageryLayers) map.addLayer(l, before);
	return true;
}

/**
 * Show or hide the aerial imagery (adding it first when needed), with the
 * buildings' opacity to match (and the flavor's: see `#lib/map/flavors`).
 * Returns whether Aerial is now on.
 */
export function setAerial(map: MapLike, m: BasemapManifest, origin: string, on: boolean): boolean {
	if (on && !addAerial(map, m, origin)) return false;
	for (const id of IMAGERY_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
	const opacity = buildingOpacity(on, flavorKit().appliedFlavor(map));
	for (const id of BUILDINGS_LAYERS) if (map.getLayer(id)) map.setPaintProperty(id, 'fill-extrusion-opacity', opacity);
	return on;
}

/** The basemap's first label layer: data layers drawn under the labels go before it. */
export function firstBasemapLabel(map: Pick<GlMap, 'getLayer' | 'getLayersOrder'>): string | undefined {
	return map.getLayersOrder().find((id) => {
		const l = map.getLayer(id);
		return l?.type === 'symbol' && l.source === 'protomaps';
	});
}

/** What `buildStyle` can also be told. */
export interface StyleOptions {
	/** /api/meta, when the caller has it (a toggled layer's tiles need a version). */
	meta?: DataMeta | null;
	/** The base contributions to build in (the registry's by default). */
	contributions?: readonly BaseContribution[];
}

/**
 * The style. MapLibre needs absolute URLs for glyphs and sprites, so the page
 * origin is passed in. The imagery is part of it only when `aerial` is on at
 * creation; otherwise `addAerial` adds it the first time it's wanted.
 *
 * It's built in one base flavor (docs/14 §14.5), Valley unless asked; the
 * layer manager switches flavors on the running map with `flavorDiff`.
 */
export function buildStyle(
	m: BasemapManifest,
	origin: string,
	aerial = false,
	flavor: FlavorName = 'valley',
	opts: StyleOptions = {}
): StyleSpecification {
	const { head, land, water, rest, labels } = basemapLayers(m, flavor);

	const style: StyleSpecification = {
		version: 8,
		glyphs: `${origin}${TILES_PATH}/${m.glyphs}`,
		sprite: `${origin}${TILES_PATH}/${m.sprite}`,
		sources: {
			protomaps: {
				type: 'vector',
				url: pmtilesUrl(origin, m.basemap.file),
				attribution: m.basemap.attribution
			}
		},
		layers: [],
		// Warm haze toward the horizon when the map is tilted.
		sky: {
			'sky-color': '#9fc9e8',
			'horizon-color': '#f3e6d3',
			'fog-color': '#efe6d8',
			'sky-horizon-blend': 0.6,
			'horizon-fog-blend': 0.6,
			'fog-ground-blend': 0.85
		}
	};
	// Under the draped data slots: hillshade and imagery. Over them: the 3D buildings.
	const middle: LayerSpecification[] = [];
	const over: LayerSpecification[] = [];

	if (m.terrain) {
		const t = terrainSources(m, origin);
		Object.assign(style.sources, t.sources);
		style.terrain = { source: TERRAIN_SOURCE, exaggeration: m.terrain.exaggeration };
		middle.push({
			id: HILLSHADE_LAYER,
			type: 'hillshade',
			source: t.hillshadeSource,
			paint: { ...flavorKit().HILLSHADE_PAINT[flavor] }
		});
	}

	if (aerial) {
		const img = imagery(m, origin, true, flavorKit().AERIAL_SATURATION[flavor]);
		Object.assign(style.sources, img.sources);
		middle.push(...img.layers);
	}

	if (m.buildings) {
		style.sources.buildings = {
			type: 'vector',
			url: pmtilesUrl(origin, m.buildings.file),
			attribution: m.buildings.attribution
		};
		// Measured heights, then estimated ones in a lighter tone (#lib/map/buildings: no height in the
		// data stands at an estimate, and every building at least 3 m). Two layers rather than one
		// data-driven color: a constant color crossfades between flavors, while a data-driven one
		// would snap at the end of the fade and lay the building tiles out again.
		const kit = flavorKit();
		const opacity = buildingOpacity(aerial && Boolean(m.imagery), flavor);
		for (const [id, filter, color] of [
			[BUILDINGS_LAYER, MEASURED_FILTER, kit.BUILDINGS_PAINT[flavor].color],
			[BUILDINGS_ESTIMATED_LAYER, ESTIMATED_FILTER, kit.ESTIMATED_BUILDINGS_PAINT[flavor].color]
		] as const) {
			over.push({
				id,
				type: 'fill-extrusion',
				source: 'buildings',
				'source-layer': m.buildings.sourceLayer,
				minzoom: m.buildings.minzoom,
				filter,
				paint: {
					'fill-extrusion-height': BUILDING_HEIGHT,
					'fill-extrusion-base': BUILDING_BASE,
					'fill-extrusion-color': color,
					'fill-extrusion-vertical-gradient': true,
					'fill-extrusion-opacity': opacity
				}
			});
		}
	}

	// The slot anchors (docs/14 §14.8 "Layer order", #lib/map/order.ts): modules
	// insert before their slot's anchor, so the draped slots (base through
	// routes) stay one contiguous run whatever loads first.
	style.layers = [
		...head,
		anchorLayer('ground'),
		...land,
		anchorLayer('areas'),
		...water,
		anchorLayer('water'),
		anchorLayer('surfaces'),
		...rest,
		anchorLayer('base'),
		...middle,
		anchorLayer('land'),
		anchorLayer('streets'),
		anchorLayer('lanes'),
		anchorLayer('footprints'),
		anchorLayer('routes'),
		...over,
		anchorLayer('scene'),
		anchorLayer('points'),
		...labels,
		anchorLayer('labels'),
		anchorLayer('overlay')
	];
	// The base contributions (S3a): the built ones whose tiles the style can name now. The painted ground
	// and a toggled layer's tiles are added on the running map (`syncContributions`).
	const state: BaseState = { flavor, aerial, layers: new Set() };
	const ranks = {};
	const kit = flavorKit();
	for (const c of opts.contributions ?? BASE_CONTRIBUTIONS) {
		if (c.source.kind !== 'landscape' || !kit.contributionStatus(c, m, opts.meta).built) continue;
		Object.assign(style.sources, kit.contributionSources(c, m, origin, opts.meta));
		for (const l of c.layers) style.layers = insertSlotted(style.layers, [{ slot: l.slot, layer: kit.contributionLayer(c, l, state) }], l.rank, ranks);
	}
	return style;
}

/**
 * Every layer a flavor restyles, in style order: the style built in that
 * flavor (without Aerial), with the imagery layers where `addAerial` puts
 * them, so their saturation is part of the diff.
 */
export function flavorLayers(m: BasemapManifest, flavor: FlavorName): LayerSpecification[] {
	const layers = buildStyle(m, '', false, flavor).layers;
	const img = imagery(m, '', false, flavorKit().AERIAL_SATURATION[flavor]).layers;
	if (!img.length) return layers;
	const at = layers.findIndex((l) => l.id === aerialAfter(m));
	return [...layers.slice(0, at + 1), ...img, ...layers.slice(at + 1)];
}

const diffs = new WeakMap<BasemapManifest, PaintChange[]>();

/** The paint properties that differ between Valley and Clay for this manifest (computed once). */
export function flavorDiff(m: BasemapManifest): PaintChange[] {
	let d = diffs.get(m);
	if (!d) diffs.set(m, (d = flavorKit().clayPaintDiff(flavorLayers(m, 'valley'), flavorLayers(m, 'clay'))));
	return d;
}
