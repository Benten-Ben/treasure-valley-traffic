import { ROAD_HORIZON } from '#lib/ui/icons.js';
import type { LayerDef } from '../types.js';

const def: LayerDef = {
	id: 'streets',
	title: 'Streets',
	icon: ROAD_HORIZON,
	key: '2',
	order: 10,
	blurb: 'Posted speeds and road classes',
	source: 'ACHD road centerlines',
	loadingText: 'Loading roads…',
	available: (meta) => (meta && meta.database === 'ok' && !meta.roads?.segments ? 'No road data loaded yet' : true),
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
