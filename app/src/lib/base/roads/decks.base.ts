import type { BaseContribution } from '../types.js';
import { ASPHALT } from '#lib/map/materials.js';
import { DECK_CASING, ZOOM } from './palette.js';

/**
 * Roads' decks (P9; plan v3 §3.2 b6 rank 25, §3.5): bridge and overpass surfaces (`kind = deck`) draped over the
 * surfaces, with an ink casing, from z15. The generalised `surfaces_z15` draws z15-16, the full detail from z16
 * (and the deck edges from `roads.edges`). 3D decks stay later; these are draped, so the draped run is unbroken.
 * Hidden under Aerial.
 */

const RANK = 25;
const isDeck: unknown = ['==', ['get', 'kind'], 'deck'];

const fill = { 'fill-color': ASPHALT.valley, 'fill-opacity': 1, 'fill-antialias': false };
const clayFill = { ...fill, 'fill-color': ASPHALT.clay };
const casing = (width: number) => ({ 'line-color': DECK_CASING, 'line-width': width });

const decks: BaseContribution = {
	id: 'roads.decks',
	title: 'Bridge decks',
	blurb: 'Roads at real width: decks drawn over what they cross, with an ink casing (OpenStreetMap, ACHD, ITD; internal)',
	source: { kind: 'landscape', sourceLayers: ['roads.surfaces_z15', 'roads.surfaces', 'roads.edges'] },
	looks: 'both',
	layers: [
		{
			id: 'roads.decks.z15.fill',
			type: 'fill',
			slot: 'surfaces',
			rank: RANK,
			sourceLayer: 'roads.surfaces_z15',
			minzoom: ZOOM.decksFrom,
			maxzoom: ZOOM.surfacesFrom,
			filter: isDeck,
			valley: fill,
			clay: clayFill,
			aerial: 'hide'
		},
		{
			id: 'roads.decks.z15.casing',
			type: 'line',
			slot: 'surfaces',
			rank: RANK,
			sourceLayer: 'roads.surfaces_z15',
			minzoom: ZOOM.decksFrom,
			maxzoom: ZOOM.surfacesFrom,
			filter: isDeck,
			valley: casing(1.2),
			clay: casing(1.2),
			aerial: 'hide'
		},
		{
			id: 'roads.decks.z16.fill',
			type: 'fill',
			slot: 'surfaces',
			rank: RANK,
			sourceLayer: 'roads.surfaces',
			minzoom: ZOOM.surfacesFrom,
			filter: isDeck,
			valley: fill,
			clay: clayFill,
			aerial: 'hide'
		},
		{
			id: 'roads.decks.z16.casing',
			type: 'line',
			slot: 'surfaces',
			rank: RANK,
			sourceLayer: 'roads.edges',
			minzoom: ZOOM.surfacesFrom,
			filter: isDeck,
			valley: casing(1.6),
			clay: casing(1.6),
			aerial: 'hide'
		}
	],
	credit: '© OpenStreetMap contributors, Ada County Highway District, Idaho Transportation Department'
};

export default decks;
