import { layers, namedFlavor } from '@protomaps/basemaps';
import type { LayerSpecification, StyleSpecification } from 'maplibre-gl';

/** Where the basemap build (basemap/) publishes its output. Same origin, no third-party hosts. */
export const TILES_PATH = '/tiles';

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

/** Layer ids of the aerial imagery, toggled together by the map's Map/Aerial switch. */
export const IMAGERY_LAYERS = ['aerial', 'aerial-detail'];

/** Layer id of the 3D buildings. */
export const BUILDINGS_LAYER = 'buildings-3d';

/**
 * Building opacity per view. In the Aerial view the photo's own roofs show
 * through, and buildings near the edge of a tilted view don't hide the ground
 * points a calibration needs.
 */
export function buildingOpacity(aerial: boolean): number {
	return aerial ? 0.3 : 0.9;
}

export type ManifestResult =
	| { ok: true; manifest: BasemapManifest }
	| { ok: false; reason: string };

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
	return { ok: true, manifest: (await res.json()) as BasemapManifest };
}

const pmtilesUrl = (origin: string, file: string) => `pmtiles://${origin}${TILES_PATH}/${file}`;

/** MapLibre needs absolute URLs for glyphs and sprites, so the page origin is passed in. */
export function buildStyle(m: BasemapManifest, origin: string, aerial = false): StyleSpecification {
	let base = layers('protomaps', namedFlavor(m.basemap.flavor), { lang: 'en' });
	if (m.buildings) {
		// Our extruded buildings take over from the basemap's flat footprints.
		const minzoom = m.buildings.minzoom;
		base = base.map((l) => (l.id === 'buildings' ? { ...l, maxzoom: minzoom } : l));
	}
	const firstSymbol = base.findIndex((l) => l.type === 'symbol');
	const below = firstSymbol === -1 ? base : base.slice(0, firstSymbol);
	const labels = firstSymbol === -1 ? [] : base.slice(firstSymbol);

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
	const middle: LayerSpecification[] = [];

	if (m.terrain) {
		// One source for the 3D surface, a second for hillshading, as MapLibre recommends.
		const dem = {
			type: 'raster-dem' as const,
			url: pmtilesUrl(origin, m.terrain.file),
			encoding: m.terrain.encoding,
			tileSize: m.terrain.tileSize,
			attribution: m.terrain.attribution
		};
		style.sources.terrain = dem;
		style.sources.hillshade = { ...dem };
		style.terrain = { source: 'terrain', exaggeration: m.terrain.exaggeration };
		middle.push({
			id: 'hillshade',
			type: 'hillshade',
			source: 'hillshade',
			paint: { 'hillshade-exaggeration': 0.3 }
		});
	}

	if (m.imagery) {
		style.sources.imagery = {
			type: 'raster',
			url: pmtilesUrl(origin, m.imagery.file),
			tileSize: m.imagery.tileSize,
			attribution: m.imagery.attribution
		};
		// Sits above the basemap's fills and roads, below buildings and labels.
		middle.push({
			id: IMAGERY_LAYERS[0],
			type: 'raster',
			source: 'imagery',
			layout: { visibility: aerial ? 'visible' : 'none' }
		});
		// Sharper imagery around the cameras, over the valley layer: where it
		// has no tile, the valley imagery below shows through.
		const detail = m.imagery.detail;
		if (detail) {
			style.sources.imageryDetail = {
				type: 'raster',
				url: pmtilesUrl(origin, detail.file),
				tileSize: m.imagery.tileSize
			};
			middle.push({
				id: IMAGERY_LAYERS[1],
				type: 'raster',
				source: 'imageryDetail',
				minzoom: detail.minzoom,
				layout: { visibility: aerial ? 'visible' : 'none' }
			});
		}
	}

	if (m.buildings) {
		style.sources.buildings = {
			type: 'vector',
			url: pmtilesUrl(origin, m.buildings.file),
			attribution: m.buildings.attribution
		};
		middle.push({
			id: BUILDINGS_LAYER,
			type: 'fill-extrusion',
			source: 'buildings',
			'source-layer': m.buildings.sourceLayer,
			minzoom: m.buildings.minzoom,
			paint: {
				// Buildings without a known height stay flat rather than getting a guessed one.
				'fill-extrusion-height': ['coalesce', ['get', 'height'], 0],
				'fill-extrusion-color': '#f3ede2',
				'fill-extrusion-vertical-gradient': true,
				'fill-extrusion-opacity': buildingOpacity(aerial)
			}
		});
	}

	style.layers = [...below, ...middle, ...labels];
	return style;
}
