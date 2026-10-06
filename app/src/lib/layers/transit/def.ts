import { BUS } from '#lib/ui/icons.js';
import type { LayerDef } from '../types.js';

const def: LayerDef = {
	id: 'transit',
	title: 'Transit',
	icon: BUS,
	key: '4',
	order: 20,
	blurb: 'Bus routes, stops and live buses',
	source: 'Valley Regional Transit (CC BY 3.0)',
	loadingText: 'Loading routes…',
	available: (meta) => (meta && meta.database === 'ok' && !meta.gtfs ? 'No transit feed loaded yet' : true),
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
