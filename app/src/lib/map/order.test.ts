import { beforeAll, describe, expect, it } from 'vitest';
import type { LayerSpecification } from 'maplibre-gl';
import { cameraLayers } from '#lib/layers/cameras/cameras.js';
import { streetLayers } from '#lib/layers/streets/streets.js';
import { fallbackBusLayers, transitLayers } from '#lib/layers/transit/transit.js';
import { ANCHORS, drapedRuns, insertSlotted, ordered, rttStacks, type SlottedLayer } from './order.js';
import { addAerial, basemapReady, BUILDINGS_LAYERS, buildStyle, type BasemapManifest } from './style.js';

beforeAll(() => basemapReady);

const manifest: BasemapManifest = {
	bounds: [-117.05, 43, -115.95, 43.85],
	center: [-116.4, 43.6],
	zoom: 10,
	basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
	glyphs: 'fonts/{fontstack}/{range}.pbf',
	sprite: 'sprites/v4/light',
	terrain: { file: 'terrain.pmtiles', encoding: 'mapbox', tileSize: 512, exaggeration: 1.3, attribution: 'USGS 3DEP', built: '2026-10-05' },
	buildings: { file: 'buildings.pmtiles', sourceLayer: 'buildings', minzoom: 14, attribution: 'Overture', built: '2026-10-05' },
	imagery: { file: 'imagery.pmtiles', tileSize: 512, maxzoom: 14, attribution: 'USDA NAIP', built: '2026-10-05', detail: { file: 'd.pmtiles', minzoom: 15, maxzoom: 17, points: 1, radius: 1 } }
};

/** The temporary wash the manager adds before anchor:base. */
const wash: SlottedLayer = { slot: 'base', layer: { id: 'base-wash', type: 'fill', source: 'base-wash', paint: {} } };
/** A stand-in for the overlay custom layer (not draped). */
const overlay = { id: 'overlay', type: 'custom' } as unknown as LayerSpecification;

const ALL_LAYERS: Record<string, string[]> = {
	streets: streetLayers().map((s) => s.layer.id),
	transit: transitLayers().map((s) => s.layer.id),
	cameras: cameraLayers().map((s) => s.layer.id)
};

/** The style with every module's layers inserted the way they are at run time, in a given load order. */
function assembled(loadOrder: string[], o: { aerial: boolean }): LayerSpecification[] {
	const style = buildStyle(manifest, 'http://x');
	let layers = style.layers;
	const mods: Record<string, SlottedLayer[]> = {
		streets: streetLayers(),
		transit: [...transitLayers(), ...fallbackBusLayers()],
		cameras: cameraLayers()
	};
	// Each module's rank is its def's order (streets 10, transit 20, cameras 30).
	const rank: Record<string, number> = { streets: 10, transit: 20, cameras: 30 };
	const ranks = {};
	layers = insertSlotted(layers, [wash], 0, ranks);
	for (const id of loadOrder) layers = insertSlotted(layers, mods[id], rank[id], ranks);
	layers = insertSlotted(layers, [{ slot: 'overlay', layer: overlay }], 100, ranks);
	if (o.aerial) {
		const map = {
			layers,
			getLayer: (id: string) => map.layers.find((l) => l.id === id),
			getSource: () => undefined,
			addSource: () => {},
			addLayer: (l: LayerSpecification, before?: string) => {
				const i = before ? map.layers.findIndex((x) => x.id === before) : -1;
				if (i === -1) map.layers.push(l);
				else map.layers.splice(i, 0, l);
			},
			getLayersOrder: () => map.layers.map((l) => l.id),
			setLayoutProperty: () => {},
			setPaintProperty: () => {}
		};
		addAerial(map as never, manifest, 'http://x');
		layers = map.layers;
	}
	return layers;
}

const subsets = <T>(xs: T[]): T[][] => xs.reduce<T[][]>((acc, x) => [...acc, ...acc.map((s) => [...s, x])], [[]]);

describe('rttStacks', () => {
	it('counts contiguous draped runs among the layers that draw', () => {
		const L = (id: string, type: string, visible = true) => ({ id, type, visible });
		expect(rttStacks([])).toBe(0);
		expect(rttStacks([L('a', 'fill'), L('b', 'line'), L('c', 'raster')])).toBe(1);
		expect(rttStacks([L('a', 'fill'), L('s', 'symbol'), L('b', 'line')])).toBe(2);
		// Hidden layers neither draw nor break a run.
		expect(rttStacks([L('a', 'fill'), L('s', 'symbol', false), L('b', 'line')])).toBe(1);
		expect(rttStacks([L('a', 'fill'), L('x', 'fill-extrusion'), L('b', 'line', false)])).toBe(1);
		// Zoom ranges count too (MapLibre's isHidden).
		const z = [{ id: 'a', type: 'fill' }, { id: 'x', type: 'fill-extrusion', minzoom: 14 }, { id: 'b', type: 'line' }];
		expect(rttStacks(z, 12)).toBe(1);
		expect(rttStacks(z, 15)).toBe(2);
		expect(drapedRuns(z, 15)).toEqual([['a'], ['b']]);
	});

	it('is at most 1 for every combination of layers, Aerial and load order, at every zoom', () => {
		const ids = Object.keys(ALL_LAYERS);
		for (const aerial of [false, true]) {
			for (const order of [ids, [...ids].reverse(), ['transit', 'streets', 'cameras']]) {
				const layers = assembled(order, { aerial });
				for (const on of subsets(ids)) {
					for (const buildings of [true, false]) {
						const shown = new Set(on.flatMap((id) => ALL_LAYERS[id]));
						const list = layers.map((l) => {
							const o = ordered(l);
							if (Object.values(ALL_LAYERS).flat().includes(l.id)) o.visible = shown.has(l.id);
							if (l.id === 'base-wash') o.visible = on.length > 0;
							if (l.id === 'aerial' || l.id === 'aerial-detail') o.visible = aerial;
							if (BUILDINGS_LAYERS.includes(l.id)) o.visible = buildings;
							return o;
						});
						for (const zoom of [8, 10, 12, 14, 15.5, 17, 19]) {
							const runs = drapedRuns(list, zoom);
							expect(runs.length, `on=[${on}] aerial=${aerial} buildings=${buildings} z${zoom}: ${JSON.stringify(runs)}`).toBeLessThanOrEqual(1);
						}
					}
				}
			}
		}
	});

	it('puts each module’s layers in its slot whatever loads first', () => {
		const a = assembled(['streets', 'transit', 'cameras'], { aerial: false }).map((l) => l.id);
		const b = assembled(['cameras', 'transit', 'streets'], { aerial: false }).map((l) => l.id);
		expect(a).toEqual(b);
		const at = (id: string) => a.indexOf(id);
		expect(at('streets-speed')).toBeLessThan(at(ANCHORS.streets));
		expect(at('cones-fill')).toBeGreaterThan(at(ANCHORS.lanes));
		expect(at('transit-routes')).toBeGreaterThan(at(ANCHORS.footprints));
		expect(at('transit-routes')).toBeLessThan(at(ANCHORS.routes));
		expect(at('cameras-calibrated')).toBeGreaterThan(at(ANCHORS.scene));
		expect(at('cameras-calibrated')).toBeLessThan(at(ANCHORS.points));
		// Labels below the buses: every symbol layer sits under the overlay and the fallback bus layers.
		const lastSymbol = a.findLastIndex((id) => id === 'streets-speed-labels' || id === 'transit-route-labels' || id === 'places_locality');
		expect(lastSymbol).toBeLessThan(at('transit-buses'));
		expect(at('transit-buses')).toBeLessThan(at('overlay'));
	});
});
