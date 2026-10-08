import { prefetch } from '../prefetch.js';
import type { LayerDef } from '../types.js';
import { TREE } from './icons.js';

/** Where trees are built (small; the legend says where, and the map waits for no tree). */
export const AREAS_URL = '/api/trees/areas';

/**
 * Trees (docs/19 §19.6): every tree in the lidar, catalogued trees first;
 * low-poly 3D trees from z15, crown discs farther out; a click opens the
 * tree panel. No toggle key yet (2, 4, 7 and 9 are taken; 3, 5, 6 and 8 are
 * kept for Signals, Roadwork, Safety and Lanes).
 */
const def: LayerDef = {
	id: 'trees',
	title: 'Trees',
	icon: TREE,
	order: 50,
	blurb: 'Every tree in the lidar: 3D trees from z15, crown discs farther out',
	source: 'USGS 3DEP lidar · City of Boise · US Forest Service',
	loadingText: 'Loading trees…',
	// Always offered when the map has a database: the legend says where trees are built so far.
	available: () => true,
	prefetch: () => void prefetch(AREAS_URL),
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
