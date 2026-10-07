import type * as Protomaps from '@protomaps/basemaps';
import type { LayerSpecification, LineLayerSpecification, Map, StyleSpecification } from 'maplibre-gl';
import type * as Flavors from './flavors.js';
import type { FlavorName, PaintChange } from './flavors.js';
import { anchorLayer, ANCHORS } from './order.js';
import { DEFAULT_HILLSHADE, type HillshadeMode } from '#lib/perf/flags.js';

/** Where the basemap build (basemap/) publishes its output. Same origin, no third-party hosts. */
export const TILES_PATH = '/tiles';

/** Layer ids of the aerial imagery, toggled together by the Map/Aerial switch (added on first use). */
export const IMAGERY_LAYERS = ['aerial', 'aerial-detail'];

/** Layer id of the 3D buildings. */
export const BUILDINGS_LAYER = 'buildings-3d';

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
}

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

const pmtilesUrl = (origin: string, file: string) => `pmtiles://${origin}${TILES_PATH}/${file}`;

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
 * The basemap's own layers in a flavor (docs/14 §14.5: Valley or Clay over the
 * manifest's Protomaps flavor), split at the first label: fills and lines
 * below, labels above.
 */
function basemapLayers(m: BasemapManifest, flavor: FlavorName): { below: LayerSpecification[]; labels: LayerSpecification[] } {
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
	return {
		below: firstSymbol === -1 ? base : base.slice(0, firstSymbol),
		labels: firstSymbol === -1 ? [] : base.slice(firstSymbol)
	};
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
	Map,
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
	if (map.getLayer(BUILDINGS_LAYER)) map.setPaintProperty(BUILDINGS_LAYER, 'fill-extrusion-opacity', buildingOpacity(on, flavorKit().appliedFlavor(map)));
	return on;
}

/** The basemap's first label layer: data layers drawn under the labels go before it. */
export function firstBasemapLabel(map: Pick<Map, 'getLayer' | 'getLayersOrder'>): string | undefined {
	return map.getLayersOrder().find((id) => {
		const l = map.getLayer(id);
		return l?.type === 'symbol' && l.source === 'protomaps';
	});
}

/**
 * The style. MapLibre needs absolute URLs for glyphs and sprites, so the page
 * origin is passed in. The imagery is part of it only when `aerial` is on at
 * creation; otherwise `addAerial` adds it the first time it's wanted.
 *
 * It's built in one base flavor (docs/14 §14.5), Valley unless asked; the
 * layer manager switches flavors on the running map with `flavorDiff`.
 */
export function buildStyle(m: BasemapManifest, origin: string, aerial = false, flavor: FlavorName = 'valley'): StyleSpecification {
	const { below, labels } = basemapLayers(m, flavor);

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
		over.push({
			id: BUILDINGS_LAYER,
			type: 'fill-extrusion',
			source: 'buildings',
			'source-layer': m.buildings.sourceLayer,
			minzoom: m.buildings.minzoom,
			paint: {
				// Buildings without a known height stay flat rather than getting a guessed one.
				'fill-extrusion-height': ['coalesce', ['get', 'height'], 0],
				'fill-extrusion-color': flavorKit().BUILDINGS_PAINT[flavor].color,
				'fill-extrusion-vertical-gradient': true,
				'fill-extrusion-opacity': buildingOpacity(aerial && Boolean(m.imagery), flavor)
			}
		});
	}

	// The slot anchors (docs/14 §14.8 "Layer order", #lib/map/order.ts): modules
	// insert before their slot's anchor, so the draped slots (base through
	// routes) stay one contiguous run whatever loads first.
	style.layers = [
		...below,
		anchorLayer('base'),
		...middle,
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
