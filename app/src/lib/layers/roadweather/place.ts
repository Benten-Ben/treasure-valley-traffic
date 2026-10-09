import { LEFT_COLUMN, RIGHT_COLUMN, SAFE_BOTTOM, SAFE_TOP, type Layout, type Point } from '#lib/state/windows.svelte.js';
import { landing } from '../cameras/place.js';

/**
 * Where a clicked road-weather station goes on screen (docs/14 §14.6 "Road
 * weather"), so the inspect card and its window leave it in view. Cameras fly
 * to a landing point in the free middle (WP12); a station pans there, and
 * only when something would cover it, keeping the zoom unless the map's
 * bounds would stop the pan short (`zoomToLand`). Pure.
 */

/** Room kept between a station's centre and the edge of the free middle, px (the badge is 30 px). */
export const CLEAR_PX = 32;
/** On a phone, a window lifts the sheet to 55% of the screen: a station below this share of it is covered. */
export const PHONE_CLEAR_SHARE = 0.45;
/** A tablet's right column: the 320 px inspect card and its margins (ChromeShell). */
export const TABLET_RIGHT_COLUMN = 352;

type Box = { left: number; top: number; width: number; height: number };

/**
 * Where a clicked station should land (viewport px), or null when it's clear
 * already and the map stays put:
 *
 * - on a desktop, when it's under the legend or the inspect column, the top
 *   bar or the toolbar: the cameras' landing point in the free middle (far
 *   enough left that its window fits beside it), else the middle of the map;
 * - on a tablet, when it's under the narrower inspect column or the bars:
 *   the middle of the map left of that column;
 * - on a phone, when the sheet a window lifts would cover it (or the top bar
 *   does): the middle of the map left above the sheet.
 *
 * `p` is the station on screen (viewport px), `box` the map's box.
 */
export function stationLanding(p: Point, box: Box, windowWidth: number, layout: Layout): Point | null {
	const top = box.top + SAFE_TOP;
	if (layout === 'phone') {
		const clear = p.y >= top && p.y <= box.top + PHONE_CLEAR_SHARE * box.height && p.x >= box.left && p.x <= box.left + box.width;
		return clear ? null : landing(box, windowWidth, layout);
	}
	const tablet = layout === 'tablet';
	const left = box.left + (tablet ? 0 : LEFT_COLUMN) + CLEAR_PX;
	const right = box.left + box.width - (tablet ? TABLET_RIGHT_COLUMN : RIGHT_COLUMN) - CLEAR_PX;
	const bottom = box.top + box.height - SAFE_BOTTOM - CLEAR_PX;
	const clear = p.x >= left && p.x <= right && p.y >= top + CLEAR_PX && p.y <= bottom;
	if (clear) return null;
	const midY = Math.round(box.top + box.height / 2);
	if (tablet) return { x: Math.round(box.left + (box.width - TABLET_RIGHT_COLUMN) / 2), y: midY };
	return landing(box, windowWidth, layout) ?? { x: Math.round(box.left + box.width / 2), y: midY };
}

/** The deepest a click on a station zooms in, so the map's bounds let it reach its landing point. */
export const MAX_LAND_ZOOM = 14;
/** MapLibre's world is 512 px across at zoom 0. */
const TILE_PX = 512;
const mercX = (lon: number) => (lon + 180) / 360;
const mercY = (lat: number) => (1 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / Math.PI) / 2;

/**
 * The zoom at which the map can put a station at `land`. MapLibre keeps the
 * view inside the map's bounds (maxBounds), so at low zooms, where the view
 * spans them, and near their edge, a pan alone stops short and leaves the
 * station under the inspect card. The current zoom when it's enough, else
 * just enough more; null when even `maxZoom` isn't, or the station is
 * outside the bounds (the map then stays put).
 *
 * `at` is the station (lon, lat), `land` where it should go (px in the map's
 * box), `size` the map's box and `bounds` [[west, south], [east, north]]. For
 * a flat view; MapLibre bounds the centre the same way when the map is
 * tilted, so it's close then too.
 */
export function zoomToLand(
	at: [number, number],
	land: Point,
	size: { width: number; height: number },
	bounds: [[number, number], [number, number]],
	zoom: number,
	maxZoom = MAX_LAND_ZOOM
): number | null {
	const [[west, south], [east, north]] = bounds;
	const x = mercX(at[0]);
	const y = mercY(at[1]);
	// Room between the station and each edge of the bounds (left, right, top, bottom), as a share of the world,
	// and the screen it must fill on that side once the station is at `land`.
	const room = [x - mercX(west), mercX(east) - x, y - mercY(north), mercY(south) - y];
	const fill = [land.x, size.width - land.x, land.y, size.height - land.y];
	if (room.some((r) => r <= 0)) return null;
	const world = Math.max(...fill.map((f, i) => f / room[i]));
	// A hair more than the least (MapLibre rounds its bounds), so the station lands within a pixel or two.
	const least = Math.log2(world / TILE_PX) + 0.01;
	if (least > maxZoom) return null;
	return Math.max(zoom, least);
}
