import type { Map, PaddingOptions } from 'maplibre-gl';
import { LEFT_COLUMN, MARGIN, RIGHT_COLUMN, SAFE_BOTTOM, SAFE_TOP, type Layout } from '#lib/state/windows.svelte.js';

/**
 * The map's padding in Explore (docs/14 §14.3, "Regions": `setPadding`
 * follows the open columns, so fly-tos centre in the visible area). The map's
 * centre is drawn in the middle of what the padding leaves, so H, O, Back,
 * a camera's fly and `fitBounds` all land between the bars and columns.
 *
 * - Desktop and tablet: below the top bar and above the toolbar; right of
 *   the legend column; left of the camera widget, or of the inspect card
 *   while it's open.
 * - Phone: below the nameplate and chips, above the sheet at its smallest
 *   (25%) and the tab bar.
 *
 * The values mirror the chrome's CSS (ChromeShell, TopBar, Sheet), the same
 * way the window manager's safe area does. The padding is part of every view
 * snapshot, so the modes put it back as they found it.
 */

/** The camera widget's column, right of the map: 16 + 40 + 16 px. */
export const WIDGET_COLUMN = MARGIN + 40 + MARGIN;
/** The right column with the inspect card open on a tablet: 16 + 320 + 16 px. */
export const TABLET_RIGHT_COLUMN = MARGIN + 320 + MARGIN;
/** Phone: the nameplate pill and the row of chips under it (8 + 40 + 6 + 44 + 8 px). */
export const PHONE_TOP = 106;
/** Phone: the tab bar and its gaps (64 + 8 + 8 px), under the sheet. */
export const PHONE_BELOW = 80;
/** The sheet's smallest snap point, a share of the screen's height. */
export const PHONE_SHEET = 0.25;
/** Map left between the paddings, at the least, across and down: a small screen shrinks the padding instead. */
export const MIN_VISIBLE = 200;

export type Padding = Required<PaddingOptions>;

export interface ChromeLayout {
	layout: Layout;
	/** The map's size (the viewport). */
	width: number;
	height: number;
	/** The inspect card is open (desktop and tablet; a phone's is in the sheet). */
	inspect: boolean;
}

/** Shrink two opposite paddings in proportion so at least MIN_VISIBLE px stay between them. */
function fit(a: number, b: number, size: number): [number, number] {
	const room = size - MIN_VISIBLE;
	if (a + b <= room) return [a, b];
	if (room <= 0) return [0, 0];
	const k = room / (a + b);
	return [Math.floor(a * k), Math.floor(b * k)];
}

/** The padding for the chrome as laid out now. */
export function chromePadding(c: ChromeLayout): Padding {
	let top: number;
	let bottom: number;
	let left: number;
	let right: number;
	if (c.layout === 'phone') {
		top = PHONE_TOP;
		bottom = PHONE_BELOW + Math.round(PHONE_SHEET * c.height) + 8;
		left = 0;
		right = 0;
	} else {
		top = SAFE_TOP;
		bottom = SAFE_BOTTOM;
		left = LEFT_COLUMN;
		right = c.inspect ? (c.layout === 'tablet' ? TABLET_RIGHT_COLUMN : RIGHT_COLUMN) : WIDGET_COLUMN;
	}
	[left, right] = fit(left, right, c.width);
	[top, bottom] = fit(top, bottom, c.height);
	return { top, right, bottom, left };
}

export function samePadding(a: PaddingOptions, b: PaddingOptions): boolean {
	return (
		Math.abs((a.top ?? 0) - (b.top ?? 0)) < 0.5 &&
		Math.abs((a.right ?? 0) - (b.right ?? 0)) < 0.5 &&
		Math.abs((a.bottom ?? 0) - (b.bottom ?? 0)) < 0.5 &&
		Math.abs((a.left ?? 0) - (b.left ?? 0)) < 0.5
	);
}

/** Where the map's centre is drawn with a padding, in the map's own pixels. */
export function paddedCentre(width: number, height: number, p: PaddingOptions): [number, number] {
	const { top = 0, right = 0, bottom = 0, left = 0 } = p;
	return [left + (width - left - right) / 2, top + (height - top - bottom) / 2];
}

const padded = new WeakSet<Map>();

/**
 * Give the map a padding.
 *
 * - The first time for a map, the centre stays the same place: a link's or
 *   a saved view's centre lands in the middle of the visible area, and the
 *   hash reads the same after a reload.
 * - After that the picture stays still (opening the inspect card, or
 *   stepping out of look-through where it is, doesn't shove the map
 *   sideways): the centre becomes the place now drawn where the new
 *   padding's centre is.
 *
 * Returns whether the padding changed.
 */
export function applyPadding(map: Map, p: Padding): boolean {
	const first = !padded.has(map);
	padded.add(map);
	const from = map.getPadding();
	if (samePadding(from, p)) return false;
	if (first) {
		map.setPadding(p);
		return true;
	}
	const el = map.getContainer();
	const [x, y] = paddedCentre(el.clientWidth, el.clientHeight, p);
	const at = map.unproject([x, y]);
	if (!Number.isFinite(at.lng) || !Number.isFinite(at.lat)) map.setPadding(p);
	else map.jumpTo({ center: at, padding: p });
	return true;
}
