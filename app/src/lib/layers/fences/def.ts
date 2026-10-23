import type { DataMeta } from '#lib/contracts/meta.js';
import { layerVersion } from '#lib/contracts/layer-tiles.js';
import { prefetch } from '../prefetch.js';
import type { LayerDef } from '../types.js';
import { WALL } from './icons.js';

/**
 * The data's URL, with the version /api/meta reports when it has one (immutable then). Same as `linesUrl` in
 * fences.ts (a test pins it): the def mustn't import that file (the 3D batch, the style), nor be imported by
 * the layer's module, or it is a chunk of its own in the initial bundle instead of part of the registry's.
 */
const URL_PATH = '/api/fences/lines';
function linesUrl(meta: Pick<DataMeta, 'versions'> | null | undefined): string {
	const v = layerVersion(meta, 'fences', 'lines');
	return v ? `${URL_PATH}?v=${encodeURIComponent(v)}` : URL_PATH;
}

/**
 * Fences (plan §4.2 P10): the fences, walls, retaining walls, guard rails and jersey barriers mapped in
 * OpenStreetMap. A 2D line with a cream halo from z14.5 and low 3D walls from z15.5; a click opens the card.
 * Only what contributors have mapped is here: most backyard fences aren't mapped yet. No toggle key.
 */
const def: LayerDef = {
	id: 'fences',
	title: 'Fences',
	icon: WALL,
	order: 40, // = ORDER in fences.ts
	group: 'landscape',
	keepsValley: true,
	blurb: 'Fences and walls mapped in OpenStreetMap: a line from z14.5, low 3D walls from z15.5',
	source: 'OpenStreetMap contributors',
	loadingText: 'Loading fences…',
	// Always offered: before the plugin's first load the data is an empty collection, and the legend says so.
	available: () => true,
	prefetch: (ctx) => void prefetch(linesUrl(ctx.meta)),
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
