import type { ExpressionSpecification, FilterSpecification } from 'maplibre-gl';

/**
 * How tall the 3D buildings are drawn: a height floor (owner, Oct 7;
 * docs/DECISIONS.md).
 *
 * The tiles (basemap/buildings.py, Overture) keep the data as it is: `height`
 * in metres where known, `num_floors` on a few, `min_height` on a handful.
 * About 18% of buildings have no `height`, and drawn flat (0 m) they looked
 * like missing blocks; about 12% of the rest are under 3 m, too low to read as
 * buildings. Only the drawing changes:
 *
 * - a building without a usable `height` (none, 0 m or less, or not a
 *   number) stands `num_floors` × FLOOR_HEIGHT_M tall when it has floors,
 *   else DEFAULT_HEIGHT_M, and is drawn in a lighter tone in a layer of its
 *   own (`ESTIMATED_BUILDINGS_PAINT` in `#lib/map/flavors`), so the map still
 *   tells measured from guessed (ch. 13 §13.8: missing data is never silently
 *   filled in);
 * - every building is drawn at least MIN_HEIGHT_M tall;
 * - `min_height` (a part that starts above the ground) is the base, never
 *   above the drawn top.
 *
 * Every value goes through `to-number` with 0 as the fallback, so a missing,
 * null or non-numeric value reads as 0: no feature falls out of both layers,
 * and none is drawn flat because an expression failed.
 *
 * Roof shapes and lidar-checked heights are to follow (the nDSM surface tiles,
 * docs/17 §17.8).
 */

/** Metres per floor, for a building with `num_floors` but no `height`. */
export const FLOOR_HEIGHT_M = 3.2;

/** Metres for a building with neither `height` nor `num_floors` (the valley's median measured height is 4.5 m). */
export const DEFAULT_HEIGHT_M = 4;

/** The lowest any building is drawn, in metres, measured or not. */
export const MIN_HEIGHT_M = 3;

/** A property as a number: 0 when it's missing, null or not a number. */
const num = (key: string): ExpressionSpecification => ['to-number', ['get', key], 0];

/** The buildings with a measured height, above 0 m (the `buildings-3d` layer). */
export const MEASURED_FILTER: FilterSpecification = ['>', num('height'), 0];

/** The buildings drawn at an estimated height, in the lighter tone: everything else (the `buildings-3d-estimated` layer). */
export const ESTIMATED_FILTER: FilterSpecification = ['!', MEASURED_FILTER];

/** The height before the floor: measured, else from the floors (above 0), else the default. */
const HEIGHT: ExpressionSpecification = [
	'case',
	['>', num('height'), 0],
	num('height'),
	['>', num('num_floors'), 0],
	['*', num('num_floors'), FLOOR_HEIGHT_M],
	DEFAULT_HEIGHT_M
];

/** `fill-extrusion-height`: the drawn top, at least MIN_HEIGHT_M. The same in both layers. */
export const BUILDING_HEIGHT: ExpressionSpecification = ['max', MIN_HEIGHT_M, HEIGHT];

/** `fill-extrusion-base`: `min_height` where the data has it (else the ground), never above the drawn top. */
export const BUILDING_BASE: ExpressionSpecification = ['min', num('min_height'), BUILDING_HEIGHT];
