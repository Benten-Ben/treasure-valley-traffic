import { layerVersion } from '#lib/contracts/layer-tiles.js';
import { prefetch } from '../prefetch.js';
import type { LayerDef } from '../types.js';
import { GRAINS } from './icons.js';
import { FIELDS_LAYER, PLUGIN } from './tiles.js';

/** The crop year and the edition behind it (small; the layer needs it to build its switcher). */
export const YEAR_URL = '/api/farm/year';

/**
 * Crop fields (landscape sprint plan §3.4 K1-K2, P3-app): every farm field as an "estimated field" coloured
 * by crop group, with patterns, a year switcher for the eight years of USDA's Crop Sequence Boundaries, the
 * growth and plat hatches, and a card per field. Fills draw in Clay only and go off under Transit (one area
 * fill at a time). It reads the `farm.crop_fields` tiles, so it is offered once the farm build has recorded a
 * version of them.
 */
const def: LayerDef = {
	id: 'crops',
	title: 'Crop fields',
	icon: GRAINS,
	order: 70,
	group: 'landscape',
	offUnder: ['transit'],
	blurb: "Every farm field, by crop, for each year of USDA's maps",
	source: 'USDA NASS Crop Sequence Boundaries and Cropland Data Layer · Copernicus Sentinel-2 · COMPASS',
	loadingText: 'Loading crop fields…',
	available: (meta) => (layerVersion(meta, PLUGIN, FIELDS_LAYER) ? true : 'Crop fields are not built yet'),
	prefetch: () => void prefetch(YEAR_URL),
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
