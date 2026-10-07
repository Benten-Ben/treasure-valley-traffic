import { BUS } from '#lib/ui/icons.js';
import { prefetch } from '../prefetch.js';
import type { LayerDef } from '../types.js';

const def: LayerDef = {
	id: 'transit',
	title: 'Transit',
	icon: BUS,
	key: '4',
	order: 20,
	blurb: 'Bus routes side by side, stops, and buses played back a little behind live',
	source: 'Valley Regional Transit (CC BY 3.0)',
	loadingText: 'Loading routes…',
	available: (meta) => (meta && meta.database === 'ok' && !meta.gtfs ? 'No transit feed loaded yet' : true),
	prefetch: (ctx) => void ctx.dataUrl('/api/transit/network', 'ribbons').then(prefetch),
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
