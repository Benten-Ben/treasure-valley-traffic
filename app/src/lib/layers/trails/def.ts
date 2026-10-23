import { layerVersion } from '#lib/contracts/layer-tiles.js';
import { prefetch } from '../prefetch.js';
import type { LayerDef } from '../types.js';
import { TRAILS } from './icons.js';

/** The status API (taken at boot by `prefetch`, and again by the module); here, not in trails.ts, so the always-loaded def doesn't pull that file in. */
export const STATUS_URL = '/api/trails/status';

/**
 * Trails (landscape sprint, package P6-app; plan §3.2): OpenStreetMap's paths, tracks and routes in one
 * trail umber, with Ridge to Rivers' per-trail conditions and the Greenbelt's closures and detours as
 * dashes and icons, the paved ones in the base, and a card for a way. A Landscape tray layer (S3b); it
 * hides Protomaps' footpaths while it is on, and the Auto look goes to Clay with it (plan §3.6).
 * The status comes from /api/trails/status, applied as feature-state, so it is taken early (prefetch)
 * and asked again every few minutes while the layer is on.
 */
const def: LayerDef = {
	id: 'trails',
	title: 'Trails',
	icon: TRAILS,
	order: 60,
	group: 'landscape',
	suppresses: ['paths'],
	blurb: 'Paths, tracks and routes, with Ridge to Rivers and Greenbelt status',
	source: '© OpenStreetMap contributors · City of Boise Parks & Recreation (Ridge to Rivers)',
	loadingText: 'Loading trails…',
	// Offered while the database is up and the trails tiles have a build (their versions come with /api/meta).
	available: (meta) => (meta && meta.database === 'ok' && !layerVersion(meta, 'trails', 'paths') ? 'No trails built yet' : true),
	prefetch: () => void prefetch(STATUS_URL),
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
