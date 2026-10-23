import type { BaseContribution, BaseLayer, PaintProps } from '../types.js';
import { ASPHALT, CONCRETE, UNPAVED } from '#lib/map/materials.js';
import { CRISP_TIERS, EDGES, OTHER_MATERIALS, ZOOM } from './palette.js';

/**
 * Roads' surfaces (P9; plan v3 §3.2 b6, §3.4, §3.5).
 *
 * One fill per material in `anchor:surfaces` at rank 20, each fully opaque (K11: the lower layer never fades;
 * the piece lines above it do). Asphalt and concrete are their tokens; gravel and dirt are tints over the
 * ground, as the plan says. `roads.surfaces_z15` (generalised) draws from z15.5 to z16, `roads.surfaces` from
 * z16. Edges come from `roads.edges` by tier: a crisp curb where the width is inventoried or measured, a soft
 * one where it is counted or estimated. Islands are a curb outline over the ground, not a fill. Junctions fill
 * by their own material; the export has no per-arm edge kind, so the edges around them follow the tier of the
 * edge line itself. Decks (`kind = deck`) are `decks.base.ts`'s. Hidden under Aerial.
 */

const RANK = 20;
const FILL_KINDS = ['carriageway', 'junction', 'median'];
const kindIn = (kinds: readonly string[]): unknown => ['in', ['get', 'kind'], ['literal', kinds]];
const materialIn = (m: readonly string[]): unknown => ['in', ['get', 'material'], ['literal', m]];

interface Fill {
	name: string;
	filter: unknown;
	valley: PaintProps;
	clay: PaintProps;
}

const solid = (color: string): PaintProps => ({ 'fill-color': color, 'fill-opacity': 1, 'fill-antialias': false });
const tint = (t: { color: string; opacity: number }): PaintProps => ({ 'fill-color': t.color, 'fill-opacity': t.opacity });

const FILLS: readonly Fill[] = [
	{ name: 'asphalt', filter: ['!', materialIn(OTHER_MATERIALS)], valley: solid(ASPHALT.valley), clay: solid(ASPHALT.clay) },
	{ name: 'concrete', filter: materialIn(['concrete']), valley: solid(CONCRETE.valley), clay: solid(CONCRETE.clay) },
	{ name: 'gravel', filter: materialIn(['gravel']), valley: tint(UNPAVED.gravel), clay: tint(UNPAVED.gravel) },
	{ name: 'dirt', filter: materialIn(['dirt']), valley: tint(UNPAVED.dirt), clay: tint(UNPAVED.dirt) }
];

function fills(tag: 'z15' | 'z16'): BaseLayer[] {
	const sourceLayer = tag === 'z15' ? 'roads.surfaces_z15' : 'roads.surfaces';
	const zooms = tag === 'z15' ? { minzoom: ZOOM.surfacesZ15From, maxzoom: ZOOM.surfacesFrom } : { minzoom: ZOOM.surfacesFrom };
	return FILLS.map((f) => ({
		id: `roads.surfaces.${tag}.${f.name}`,
		type: 'fill' as const,
		slot: 'surfaces' as const,
		rank: RANK,
		sourceLayer,
		...zooms,
		filter: ['all', kindIn(FILL_KINDS), f.filter],
		valley: f.valley,
		clay: f.clay,
		aerial: 'hide' as const
	}));
}

/** The crisp/soft split of an edge, as expressions of its tier. */
const crisp: unknown = ['in', ['get', 'tier'], ['literal', CRISP_TIERS]];
const edgePaint = (color: string, crispWidth: number): PaintProps => ({
	'line-color': color,
	'line-width': ['case', crisp, crispWidth, crispWidth * 3],
	'line-blur': ['case', crisp, 0, 2],
	'line-opacity': ['case', crisp, 1, 0.7]
});

function line(id: string, sourceLayer: string, filter: unknown, valley: PaintProps, clay: PaintProps): BaseLayer {
	return { id, type: 'line', slot: 'surfaces', rank: RANK, sourceLayer, minzoom: ZOOM.surfacesFrom, filter, valley, clay, aerial: 'hide' };
}

const edges: BaseLayer[] = [
	line('roads.surfaces.edge.curb', 'roads.edges', ['==', ['get', 'kind'], 'curb'], edgePaint(EDGES.curb, 1.2), edgePaint(EDGES.clayKerb, 1.2)),
	line('roads.surfaces.edge.shoulder', 'roads.edges', ['==', ['get', 'kind'], 'shoulder'], edgePaint(EDGES.shoulder, 1), edgePaint(EDGES.clayKerb, 1)),
	// An island is the ground inside a curb: an outline, no fill.
	line(
		'roads.surfaces.island',
		'roads.surfaces',
		['==', ['get', 'kind'], 'island'],
		{ 'line-color': EDGES.curb, 'line-width': 1.2 },
		{ 'line-color': EDGES.clayKerb, 'line-width': 1.2 }
	)
];

const surfaces: BaseContribution = {
	id: 'roads.surfaces',
	title: 'Road surfaces',
	blurb: 'Roads at real width: surfaces measured where crisp, estimated where soft (OpenStreetMap, ACHD, ITD; internal)',
	source: { kind: 'landscape', sourceLayers: ['roads.surfaces_z15', 'roads.surfaces', 'roads.edges'] },
	looks: 'both',
	layers: [...fills('z15'), ...fills('z16'), ...edges],
	credit: '© OpenStreetMap contributors, Ada County Highway District, Idaho Transportation Department'
};

export default surfaces;
