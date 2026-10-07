import { prefetch } from '../prefetch.js';
import type { LayerDef } from '../types.js';
import RoadWeatherIcon from './RoadWeatherIcon.svelte';

/** The station list with each view's newest picture (no-store: the ages change). */
export const DATA_URL = '/api/roadweather';

/**
 * Road weather (docs/14 §14.6, WP16): ITD's road-weather station cameras and
 * Oregon DOT's in the regional ring, one window per station with a tab per
 * view. Key 9, reserved for it in §14.3's keymap.
 */
const def: LayerDef = {
	id: 'weather',
	title: 'Road weather',
	icon: RoadWeatherIcon,
	key: '9',
	order: 40,
	blurb: 'Road-weather station cameras: a picture per direction, about every 15 minutes',
	source: 'ITD 511 road weather (RWIS) · Oregon DOT',
	loadingText: 'Loading road-weather stations…',
	// Always offered when the map has a database: an empty list says why in the legend.
	available: () => true,
	prefetch: () => void prefetch(DATA_URL),
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
