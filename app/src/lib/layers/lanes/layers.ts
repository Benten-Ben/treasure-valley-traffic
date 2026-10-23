import type { LayerSpecification } from 'maplibre-gl';
import decks from '#lib/base/roads/decks.base.js';
import lines from '#lib/base/roads/lines.base.js';
import markings from '#lib/base/roads/markings.base.js';
import paving from '#lib/base/roads/paving.base.js';
import surfaces from '#lib/base/roads/surfaces.base.js';
import type { BaseContribution } from '#lib/base/types.js';
import type { SlottedLayer } from '#lib/map/order.js';
import { ARROW_PREFIX, TURN_CODES } from './lanes.js';

/**
 * The Lanes layer's map parts (landscape sprint plan v3 §4.2 P9, §3.2 slots 10-13). Pure, so they're unit-tested.
 * The base contributions draw the roads (`#lib/base/roads`: surfaces, decks, piece lines, markings and paving);
 * this layer adds, from the same landscape file:
 *
 * - `points`: a ▲ at the middle of every piece line the build flagged (`conflict`: OpenStreetMap and ACHD's rule
 *   disagree by more than a lane), from z14;
 * - `labels`: the turn arrows (`roads.arrows`: `turns`, `bearing`), from z17.5, turned to the way the lane runs;
 *
 * and it makes the contributions' own layers clickable while it is on (`pickableRoadLayers`, `pickablePavingLayers`).
 */
export const LANDSCAPE_SOURCE = 'landscape';
export const LINES = 'roads.lines';
export const ARROWS = 'roads.arrows';
export const CONFLICT_LAYER = 'lanes-conflict';
export const ARROW_LAYER = 'lanes-arrows';
/** The arrows come in from here (plan §3.2). */
export const ARROWS_FROM_ZOOM = 17.5;
/** The ▲ marks come in with the piece lines. */
export const CONFLICT_FROM_ZOOM = 14;

/** The style images (see `markers.ts`). */
export const IMAGE = { conflict: 'lanes-conflict' } as const;

/** The layers this module adds, in the order it adds them. They draw from the landscape file, so only once it is baked. */
export const OWN_LAYERS = [CONFLICT_LAYER, ARROW_LAYER] as const;

/** Every style layer a contribution adds. */
function idsOf(c: BaseContribution, keep: (id: string) => boolean = () => true): string[] {
	return c.layers.map((l) => l.id).filter(keep);
}

/**
 * The road layers a click opens a card from (`PRIORITY.lane`): the surfaces and their edges and island outlines, the
 * decks, the markings and the piece lines, and the ▲ marks. All of them are the contributions' own style layer ids.
 */
export function pickableRoadLayers(): string[] {
	return [...idsOf(surfaces), ...idsOf(decks), ...idsOf(markings), ...idsOf(lines), CONFLICT_LAYER];
}

/** The paving layers a click opens a card from (`PRIORITY.paving`): lots and ways. Mapped stalls have no card. */
export function pickablePavingLayers(): string[] {
	return idsOf(paving, (id) => id !== 'roads.paving_stalls');
}

// -- the turn arrows' image name, as a style expression ------------------------------------------------------------

/**
 * `icon-image` for an arrow: `lanes-arrow:` and the letters of the arrows its `turns` ('left;through') carry, in
 * the order L, T, R, U. The same choice as `turnArrows` in `lanes.ts` (a test holds them together): a word match,
 * a merging lane draws no left or right arrow.
 */
export function arrowImageExpression(): unknown {
	const turns: unknown = ['to-string', ['coalesce', ['get', 'turns'], '']];
	const has = (word: string): unknown => ['in', word, turns];
	const noMerge: unknown = ['!', has('merge')];
	const code = (c: string, test: unknown): unknown => ['case', test, c, ''];
	return [
		'concat',
		ARROW_PREFIX,
		code(TURN_CODES.left, ['all', has('left'), noMerge]),
		code(TURN_CODES.through, has('through')),
		code(TURN_CODES.right, ['all', has('right'), noMerge]),
		code(TURN_CODES.uturn, has('reverse'))
	];
}

// -- the layers ---------------------------------------------------------------------------------------------------------------

/**
 * The layer's own style layers, hidden until the layer is on. Symbols never go below `anchor:routes`, so none is
 * draped. They read the shared landscape source; a layer is only listed when its source-layer is in the bake.
 */
export function ownLayers(built: { lines: boolean; arrows: boolean }): SlottedLayer[] {
	const out: SlottedLayer[] = [];
	if (built.lines) {
		out.push({
			slot: 'points',
			layer: {
				id: CONFLICT_LAYER,
				type: 'symbol',
				source: LANDSCAPE_SOURCE,
				'source-layer': LINES,
				minzoom: CONFLICT_FROM_ZOOM,
				filter: ['==', ['get', 'conflict'], true],
				layout: {
					visibility: 'none',
					'symbol-placement': 'line-center',
					// Upright, not turned along its line (a line-placed icon follows the line by default).
					'icon-rotation-alignment': 'viewport',
					'icon-image': IMAGE.conflict,
					'icon-size': ['interpolate', ['linear'], ['zoom'], CONFLICT_FROM_ZOOM, 0.55, 17, 0.9],
					'icon-allow-overlap': true,
					'icon-ignore-placement': true
				}
			} as unknown as LayerSpecification
		});
	}
	if (built.arrows) {
		out.push({
			slot: 'labels',
			layer: {
				id: ARROW_LAYER,
				type: 'symbol',
				source: LANDSCAPE_SOURCE,
				'source-layer': ARROWS,
				minzoom: ARROWS_FROM_ZOOM,
				layout: {
					visibility: 'none',
					'icon-image': arrowImageExpression(),
					'icon-rotate': ['get', 'bearing'],
					'icon-rotation-alignment': 'map',
					'icon-pitch-alignment': 'map',
					'icon-size': ['interpolate', ['linear'], ['zoom'], ARROWS_FROM_ZOOM, 0.4, 20, 1],
					'icon-allow-overlap': true,
					'icon-ignore-placement': true
				}
			} as unknown as LayerSpecification
		});
	}
	return out;
}
