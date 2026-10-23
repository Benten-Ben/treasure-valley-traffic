import type { LayerDef } from '../types.js';

/**
 * Lanes (landscape sprint plan v3 §4.2 P9; key 8): the roads' lane counts, turn arrows and markings on the roads at
 * real width the base map draws (`#lib/base/roads`). While it is on:
 *
 * - the base markings show in Clay (ink at 60%) and under Aerial (they read the layer set through the base's `show`);
 * - a ▲ marks every piece where OpenStreetMap's lane count and ACHD's rule differ by more than a lane, and turn
 *   arrows draw from z17.5;
 * - road surfaces, decks, edges, markings and piece lines open a card with the lanes, their source and any
 *   disagreement, the width and how it is known; paving (lots, driveways, service ways, sidewalks) opens its own.
 *
 * It keeps the Valley look in Auto (plan §3.6) and is a main-bar layer, not a Landscape tray one. The roads rest on
 * ACHD's and ITD's internal data, so its credit says so.
 */
const def: LayerDef = {
	id: 'lanes',
	title: 'Lanes',
	key: '8',
	order: 35,
	keepsValley: true,
	blurb: 'Lane counts and turn lanes at real road width, each count with its source and the places the sources disagree',
	source: '© OpenStreetMap contributors · ACHD and ITD (internal: this map only)',
	loadingText: 'Loading lanes…',
	// Offered once the landscape file holds roads (the tiles' manifest says so in /api/meta; null: not baked yet).
	available: (meta) => (meta && meta.database === 'ok' && meta.tiles?.landscape === null ? 'Roads at real width are not built yet' : true),
	load: () => import('./index.svelte.js').then((m) => m.create())
};

export default def;
