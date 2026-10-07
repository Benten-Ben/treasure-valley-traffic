import { SECURITY_CAMERA } from '#lib/ui/icons.js';
import { prefetch } from '../prefetch.js';
import type { LayerDef } from '../types.js';

const def: LayerDef = {
	id: 'cameras',
	title: 'Cameras',
	icon: SECURITY_CAMERA,
	key: '7',
	order: 30,
	blurb: 'Traffic cameras, their calibration and view cones',
	source: 'ITD 511 / ACHD',
	loadingText: 'Loading cameras…',
	available: (meta) => (meta && meta.database === 'ok' && !meta.cameras?.cameras ? 'No cameras loaded yet' : true),
	prefetch: (ctx) => {
		void ctx.dataUrl('/api/cameras', 'cameras').then(prefetch);
		void ctx.dataUrl('/api/calibrations', 'calibrations').then(prefetch);
		void ctx.dataUrl('/api/cameras/views', 'cameras').then(prefetch);
	},
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
