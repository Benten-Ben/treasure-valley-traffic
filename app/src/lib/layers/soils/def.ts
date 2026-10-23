import { built } from './tiles.js';
import type { LayerDef } from '../types.js';
import { SHOVEL } from './icons.js';

/**
 * Soils (landscape sprint plan v3 §3.4 K6, P1-app): the NRCS soil survey as a wash of gray steps for one
 * property at a time (hardpan or bedrock, drainage, water held, farmland, runoff), with the survey areas'
 * bounds, map-unit outlines, symbols and names as you zoom in, and a soil card for the map unit under a click.
 * Off by default; an area fill, so one at a time with the crop fields; Auto goes Clay while it is on. It reads
 * the `soils` tiles, so it is offered once the soils build has recorded a version of them.
 */
const def: LayerDef = {
	id: 'soils',
	title: 'Soils',
	icon: SHOVEL,
	order: 80,
	group: 'landscape',
	blurb: "Mapped soil: hardpan, drainage, water held, farmland and runoff, from NRCS's soil survey",
	source: 'USDA NRCS Soil Survey (SSURGO)',
	loadingText: 'Loading soils…',
	available: (meta) => (built(meta) ? true : 'Soils are not built yet'),
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
