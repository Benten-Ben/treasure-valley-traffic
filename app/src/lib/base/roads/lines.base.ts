import type { BaseContribution } from '../types.js';
import { ASPHALT, CONCRETE, UNPAVED } from '#lib/map/materials.js';
import { LINE_START, ZOOM, metres } from './palette.js';

/**
 * Roads' piece lines (P9; plan v3 §3.2 row b7, §3.4 K11, §3.5).
 *
 * From z14 the pieces' centrelines draw `w` metres wide (shifted by `off`, where a sidewalk cut one side),
 * white at z14 and asphalt by z15.5, and take over from Protomaps' road lines: once the layer is built the
 * `roads` group is hidden from z14 (below z14 Protomaps' lines stay). They sit in `anchor:base`, above the
 * surfaces (`anchor:surfaces`), and fade out over z15.5-16 while the opaque surfaces come in under them.
 * K11: the lower layer (the surfaces) stays opaque and only this upper one fades, so no ground shows through
 * (two layers fading at t and 1-t would leave a quarter of it showing).
 */

const tone = (asphalt: string, concrete: string): unknown => ['match', ['get', 'material'], 'concrete', concrete, asphalt];

/** Gravel and dirt have no asphalt tone: their lines are the same tint the surface lays over the ground. */
const unpavedFilter: unknown = ['in', ['get', 'material'], ['literal', ['gravel', 'dirt']]];
const unpavedColor: unknown = ['match', ['get', 'material'], 'gravel', UNPAVED.gravel.color, UNPAVED.dirt.color];
const unpavedOpacity: unknown = ['match', ['get', 'material'], 'gravel', UNPAVED.gravel.opacity, UNPAVED.dirt.opacity];

/** A tunnel's line is drawn faint (it isn't on the surface). */
const strength = (full: number): unknown => ['case', ['==', ['get', 'tunnel'], true], full * 0.45, full];

const common = {
	'line-width': metres(['get', 'w'], ZOOM.linesFrom, ZOOM.fadeTo),
	'line-offset': metres(['coalesce', ['get', 'off'], 0], ZOOM.linesFrom, ZOOM.fadeTo),
	'line-opacity': ['interpolate', ['linear'], ['zoom'], ZOOM.fadeFrom, strength(1), ZOOM.fadeTo, 0]
};

const lines: BaseContribution = {
	id: 'roads.lines',
	title: 'Road lines at real width',
	blurb: 'Roads at real width: surfaces measured where crisp, estimated where soft (OpenStreetMap, ACHD, ITD; internal)',
	source: { kind: 'landscape', sourceLayers: ['roads.lines'] },
	looks: 'both',
	suppresses: { groups: ['roads'], fromZoom: ZOOM.linesFrom },
	layers: [
		{
			// Gravel and dirt: the surface's own tint from z14, so there is nothing to pop at the K11 handover (the
			// surface tint is translucent, so a line fading over it would double the tint). Gone at z15.5.
			id: 'roads.lines.unpaved',
			type: 'line',
			slot: 'base',
			rank: 10,
			sourceLayer: 'roads.lines',
			filter: unpavedFilter,
			minzoom: ZOOM.linesFrom,
			maxzoom: ZOOM.fadeFrom,
			valley: {
				'line-width': common['line-width'],
				'line-offset': common['line-offset'],
				'line-color': unpavedColor,
				'line-opacity': unpavedOpacity
			}
		},
		{
			id: 'roads.lines.line',
			type: 'line',
			slot: 'base',
			rank: 10,
			sourceLayer: 'roads.lines',
			filter: ['!', unpavedFilter],
			minzoom: ZOOM.linesFrom,
			maxzoom: ZOOM.fadeTo,
			valley: {
				...common,
				'line-color': [
					'interpolate',
					['linear'],
					['zoom'],
					ZOOM.linesFrom,
					LINE_START,
					ZOOM.toneBy,
					tone(ASPHALT.valley, CONCRETE.valley)
				]
			},
			clay: {
				...common,
				'line-color': [
					'interpolate',
					['linear'],
					['zoom'],
					ZOOM.linesFrom,
					LINE_START,
					ZOOM.toneBy,
					tone(ASPHALT.clay, CONCRETE.clay)
				]
			}
		}
	],
	credit: '© OpenStreetMap contributors, Ada County Highway District, Idaho Transportation Department'
};

export default lines;
