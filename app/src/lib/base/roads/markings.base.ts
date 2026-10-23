import type { BaseContribution, BaseLayer, BaseState, PaintProps } from '../types.js';
import { INK, MARKINGS } from '#lib/map/materials.js';
import { ZOOM } from './palette.js';

/**
 * Roads' markings (P9; plan v3 §3.2 slot 5, §3.5): lane, centre, edge and bike lines, stop bars and crosswalks
 * in `anchor:lanes`, fading in over z16.5-17. Cream on asphalt, ink at 70% on concrete (read from a `material`
 * field when the export carries one; today's markings have none, so they draw cream), centre lines double.
 * Shown in Valley by default; in Clay only with Lanes on, in ink at 60%; hidden under Aerial unless Lanes is on
 * (`show`, a pure function of the state). The arrows and the ▲ marks are the Lanes layer's own.
 */

/** Lanes on, or Valley with no Aerial. */
export function markingsShown(s: BaseState): boolean {
	const lanes = s.layers.has('lanes');
	if (s.flavor === 'clay') return lanes;
	return !s.aerial || lanes;
}

const RANK = 10;
const material: unknown = ['coalesce', ['get', 'material'], 'asphalt'];
const dashIn = (d: readonly string[]): unknown => ['in', ['get', 'dash'], ['literal', d]];
const fade = (full: unknown): unknown => ['interpolate', ['linear'], ['zoom'], ZOOM.markingsFrom, 0, ZOOM.markingsFull, full];
const width = (at165: number, at19: number): unknown => ['interpolate', ['linear'], ['zoom'], ZOOM.markingsFrom, at165, 19, at19];

/** Half the double's width plus half its gap, in px: a line's width again, either side of the centre. */
const offset = (side: -1 | 1): unknown => ['interpolate', ['linear'], ['zoom'], ZOOM.markingsFrom, side * 0.8, 19, side * 2];

const valleyColor = ['match', material, 'concrete', MARKINGS.onConcrete.color, MARKINGS.onAsphalt.color];
const valleyOpacity = ['match', material, 'concrete', MARKINGS.onConcrete.opacity, MARKINGS.onAsphalt.opacity];

function line(name: string, filter: unknown, w: [number, number], extra: PaintProps = {}): BaseLayer {
	return {
		id: `roads.markings.${name}`,
		type: 'line',
		slot: 'lanes',
		rank: RANK,
		sourceLayer: 'roads.markings',
		minzoom: ZOOM.markingsFrom,
		filter,
		valley: { 'line-color': valleyColor, 'line-width': width(w[0], w[1]), 'line-opacity': fade(valleyOpacity), ...extra },
		clay: { 'line-color': MARKINGS.clay.color, 'line-width': width(w[0], w[1]), 'line-opacity': fade(MARKINGS.clay.opacity), ...extra },
		show: markingsShown
	};
}

const notStop: unknown = ['!=', ['get', 'kind'], 'stop_bar'];
const stop: unknown = ['==', ['get', 'kind'], 'stop_bar'];

const markings: BaseContribution = {
	id: 'roads.markings',
	title: 'Road markings',
	blurb: 'Roads at real width: lane lines, stop bars and crosswalks where a source gives the lanes (OpenStreetMap, ACHD, ITD; internal)',
	source: { kind: 'landscape', sourceLayers: ['roads.markings', 'roads.crosswalks'] },
	looks: 'both',
	layers: [
		{
			id: 'roads.markings.crosswalk',
			type: 'fill',
			slot: 'lanes',
			rank: RANK,
			sourceLayer: 'roads.crosswalks',
			minzoom: ZOOM.markingsFrom,
			valley: { 'fill-color': MARKINGS.onAsphalt.color, 'fill-opacity': fade(MARKINGS.onAsphalt.opacity), 'fill-antialias': false },
			clay: { 'fill-color': INK, 'fill-opacity': fade(MARKINGS.clay.opacity), 'fill-antialias': false },
			show: markingsShown
		},
		line('solid', ['all', notStop, dashIn(['solid', 'solid_dashed'])], [0.8, 2.2]),
		line('dashed', ['all', notStop, dashIn(['dashed'])], [0.8, 2.2], { 'line-dasharray': [4, 4] }),
		// A double is two thin lines offset to either side of the centre, with the road itself between them (no
		// opaque gap layer: that would paint grey over the photograph under Aerial with Lanes on, and cut stop bars).
		line('double.left', ['all', notStop, dashIn(['double'])], [0.8, 2], { 'line-offset': offset(-1) }),
		line('double.right', ['all', notStop, dashIn(['double'])], [0.8, 2], { 'line-offset': offset(1) }),
		line('stop', stop, [1.6, 4.4])
	],
	credit: '© OpenStreetMap contributors, Ada County Highway District, Idaho Transportation Department'
};

export default markings;
