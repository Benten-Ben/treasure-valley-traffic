import type { BaseContribution } from '../types.js';

/**
 * The painted ground (landscape sprint plan v3 §4.2 G1a; basemap/ground/README.md, "Switching in").
 *
 * Valley's base: each soil type in its own colour, from the manifest's `ground` entry. Two rasters:
 * the valley-wide file (z8 to z15, overzoomed above) and, from z17, the sharper detail file around the
 * ten class boxes. Both sit in `anchor:ground` under every other fill, and hide under Aerial.
 *
 * - **Valley only.** The ground loads on the first use of Valley, through the manager's lazy add
 *   (`syncContributions`): a Clay first visit makes no ground request (owner, Oct 22, #32 Q2).
 * - **It covers the map box**, so while it is painted every Protomaps landcover and landuse fill
 *   (aerodromes, industrial, schools and hospitals included) is hidden: the `landcover` group
 *   (plan §3.2 b3). Burn scars sit on it at rank 20 in `anchor:areas`.
 * - **Flat or missing:** a `flat` entry adds nothing, and the Base menu row shows its reason
 *   (`contributionStatus`); no entry says it hasn't been built. No other source stands in for it.
 */

const GROUND_PAINT = { 'raster-opacity': 1, 'raster-fade-duration': 0 };

const ground: BaseContribution = {
	id: 'ground.paint',
	title: 'Painted ground',
	blurb: 'The soil under the Valley, each type in its own colour. Valley look only.',
	source: { kind: 'ground' },
	looks: 'valley',
	layers: [
		// The valley-wide file: z8 to its maxzoom 15, overzoomed above (z16 included).
		{ id: 'ground-paint', type: 'raster', slot: 'ground', rank: 0, valley: GROUND_PAINT, aerial: 'hide' },
		// The sharper file around the ten boxes, from `detail.minzoom` (17 today; basemap/ground/spec.json).
		{ id: 'ground-detail', type: 'raster', slot: 'ground', rank: 5, detail: true, minzoom: 17, valley: GROUND_PAINT, aerial: 'hide' }
	],
	suppresses: { groups: ['landcover'] },
	credit: 'Ground: USDA NRCS soils and NAIP; © OpenStreetMap contributors'
};

export default ground;
