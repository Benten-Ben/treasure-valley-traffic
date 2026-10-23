import { prefetch } from '../prefetch.js';
import type { LayerDef } from '../types.js';
import { DROP } from './icons.js';

/** The water points the map draws, and the river notices (small; asked for once). */
export const POINTS_URL = '/api/water/points';
export const NOTICES_URL = '/api/water/notices';

/**
 * Water (landscape sprint plan v3 §4.2 P4-app): the gauges, river notices and structures over the valley's
 * baked water network, whose lines and areas are the base map's (`#lib/base/water`) and become clickable, with
 * cards, while this layer is on. Keeps the Valley look in Auto (plan §3.6). No toggle key yet (the Landscape
 * tray, S3b, takes the tray's keys).
 */
const def: LayerDef = {
	id: 'water',
	title: 'Water',
	icon: DROP,
	order: 60,
	group: 'landscape',
	keepsValley: true,
	blurb: 'Gauges, river hazards, E. coli sites and structures over the valley’s canals, creeks and ponds',
	source: 'OpenStreetMap · USGS NHD · NOAA NWPS · City of Boise',
	loadingText: 'Loading water…',
	available: () => true,
	prefetch: () => {
		void prefetch(POINTS_URL);
		void prefetch(NOTICES_URL);
	},
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
