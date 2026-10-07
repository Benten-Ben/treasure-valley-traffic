import type { FeatureCollection } from 'geojson';
import type { SlottedLayer } from '#lib/map/order.js';
import { inBounds, stationFact, type Bounds, type RoadWeatherStation } from './model.js';

/**
 * The Road weather layer's map parts (docs/14 §14.6 "Road weather", §14.8
 * "Layer order": road-weather badges sit in the `labels` slot, above the
 * base labels). Pure, so they're unit-tested.
 *
 * Each station is a cream rounded-square badge with the thermometer-and-road
 * icon, in ink and cream only: no data hue (§14.3, "The color budget": road
 * weather uses form, icons and ink/cream). A station whose views all show
 * 511's "no live feed" picture is drawn hollow. From z11 its name sits under
 * it, when there's room.
 */
export const SOURCE = 'roadweather';
export const BADGE_LAYER = 'roadweather-badges';
export const ALL_LAYERS = [BADGE_LAYER];
export const SOLID_IMAGE = 'roadweather-badge';
export const HOLLOW_IMAGE = 'roadweather-badge-hollow';

export const INK = '#2b2a33';
export const INK_SOFT = '#5d5a66';
export const CREAM = '#fffbf4';

/** Badge size, CSS px (the images are drawn at 2× for sharp edges). */
export const BADGE_PX = 26;

/** GeoJSON for the stations inside the base map (the rest are loaded but not drawn). */
export function stationFeatures(stations: readonly RoadWeatherStation[], bounds: Bounds | null | undefined): FeatureCollection {
	return {
		type: 'FeatureCollection',
		features: stations
			.filter((s) => inBounds(s, bounds))
			.map((s) => ({
				type: 'Feature',
				id: s.id,
				geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
				properties: { id: s.id, name: s.name, provider: s.provider, hollow: s.hollow, views: s.views.length, fact: stationFact(s) }
			}))
	};
}

/** The layers, each with its slot. They start hidden. */
export function roadWeatherLayers(): SlottedLayer[] {
	const num = (v: unknown) => v as number;
	return [
		{
			slot: 'labels',
			layer: {
				id: BADGE_LAYER,
				type: 'symbol',
				source: SOURCE,
				layout: {
					visibility: 'none',
					'icon-image': ['case', ['boolean', ['get', 'hollow'], false], HOLLOW_IMAGE, SOLID_IMAGE],
					'icon-size': num(['interpolate', ['linear'], ['zoom'], 7, 0.7, 11, 0.85, 15, 1]),
					'icon-allow-overlap': true,
					'icon-ignore-placement': true,
					'text-field': ['step', ['zoom'], '', 11, ['get', 'name']],
					'text-font': ['Noto Sans Medium'],
					'text-size': 11,
					'text-anchor': 'top',
					'text-offset': [0, 1.35],
					'text-max-width': 9,
					'text-optional': true
				},
				paint: { 'text-color': INK, 'text-halo-color': CREAM, 'text-halo-width': 1.5 }
			}
		}
	];
}
