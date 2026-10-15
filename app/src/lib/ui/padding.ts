import type { Map, PaddingOptions } from 'maplibre-gl';
import { LEFT_COLUMN, MARGIN, RIGHT_COLUMN, SAFE_BOTTOM, SAFE_TOP, type Layout, type Point } from '#lib/state/windows.svelte.js';

/**
 * The map's padding in Explore (docs/14 §14.3, "Regions"). The map's centre
 * is drawn in the middle of what the padding leaves, so the app's own camera
 * moves land between the bars and columns. The padding follows only the
 * fixed chrome:
 *
 * - Desktop and tablet: below the top bar and above the toolbar; right of
 *   the legend column; left of the camera widget.
 * - Phone: below the nameplate and chips, above the sheet at its smallest
 *   (25%) and the tab bar.
 *
 * The inspect card doesn't change it (the owner's option 1, Oct 15): on a
 * tilted map a new padding moves the perspective's vanishing point, so the
 * 3D scene would skew each time the card opened or closed. Instead a move
 * the app starts while the card is open (H, O, Back, a fly to a camera or a
 * station, the trees' Go there, Follow) lands in the area the card leaves,
 * by the card's padding for that move only (`cardLanding`): an `offset` for
 * a fly or an ease, extra padding for `cameraForBounds`. The map's own
 * padding never takes it, so view snapshots and the URL hash don't either.
 * A click that selects something the card would cover pans it clear
 * (`revealTarget`, `revealPan`), a plain pan with no skew.
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
	/**
	 * Take the inspect card's column too (desktop and tablet; a phone's card is
	 * in the sheet): the padding a move lands in while the card is open, never
	 * the map's own.
	 */
	inspect?: boolean;
}

/** Shrink two opposite paddings in proportion so at least MIN_VISIBLE px stay between them. */
function fit(a: number, b: number, size: number): [number, number] {
	const room = size - MIN_VISIBLE;
	if (a + b <= room) return [a, b];
	if (room <= 0) return [0, 0];
	const k = room / (a + b);
	return [Math.floor(a * k), Math.floor(b * k)];
}

/** The padding for the chrome as laid out now (with `inspect`, the open card's column too). */
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
 * Event data on the padding's own camera moves. MapLibre's `jumpTo` fires
 * `movestart` and `moveend` even when the picture doesn't change, so a
 * listener that lets something go when the view moves (Streets' keeper)
 * checks for it and ignores these. A layer checks `tvtPadding` through this
 * type (`import type`), so its chunk takes no code from the chrome's.
 */
export type PaddingMove = { readonly tvtPadding: true };
export const PADDING_MOVE: PaddingMove = Object.freeze({ tvtPadding: true });

/** Whether a map movement event came from `applyPadding`. */
export function isPaddingMove(e: unknown): e is PaddingMove {
	return typeof e === 'object' && e !== null && (e as Partial<PaddingMove>).tvtPadding === true;
}

/**
 * Give the map a padding.
 *
 * - The first time for a map, the centre stays the same place: a link's or
 *   a saved view's centre lands in the middle of the visible area, and the
 *   hash reads the same after a reload.
 * - After that the picture stays still (a resize into another layout
 *   doesn't shove the map sideways): the centre becomes the place now drawn
 *   where the new padding's centre is. On a tilted map that's exact only at
 *   the centre (the perspective moves with the padding), which is why the
 *   inspect card no longer changes it.
 *
 * Its moves carry PADDING_MOVE, so a listener can tell them from real
 * ones (Streets' keeper). Returns whether the padding changed.
 */
export function applyPadding(map: Map, p: Padding): boolean {
	const first = !padded.has(map);
	padded.add(map);
	const from = map.getPadding();
	if (samePadding(from, p)) return false;
	if (first) {
		map.setPadding(p, PADDING_MOVE);
		return true;
	}
	const el = map.getContainer();
	const [x, y] = paddedCentre(el.clientWidth, el.clientHeight, p);
	const at = map.unproject([x, y]);
	if (!Number.isFinite(at.lng) || !Number.isFinite(at.lat)) map.setPadding(p, PADDING_MOVE);
	else map.jumpTo({ center: at, padding: p }, PADDING_MOVE);
	return true;
}

// --- the app's own moves while the inspect card is open -------------------------------------------

/** Where a move lands instead of the middle of the map's own padding. */
export interface Landing {
	/** The padding it lands in: the chrome's with the open card's column. */
	padding: Padding;
	/** From the map's padded centre to the middle of that padding, px: a fly's or an ease's `offset`. */
	offset: [number, number];
	/** That padding less the map's own, side by side (negative where it's less): more padding for `cameraForBounds`. */
	extra: Padding;
}

/** A move that lands in the middle of `move` while the map keeps its own padding `stored`. Pure. */
export function landingFor(stored: PaddingOptions, move: Padding): Landing {
	const { top = 0, right = 0, bottom = 0, left = 0 } = stored;
	return {
		padding: move,
		offset: [(move.left - move.right - (left - right)) / 2, (move.top - move.bottom - (top - bottom)) / 2],
		extra: { top: move.top - top, right: move.right - right, bottom: move.bottom - bottom, left: move.left - left }
	};
}

/** The landing while the inspect card is open: in the area left of its column. None on a phone (its card is in the sheet). */
export function cardLanding(c: Omit<ChromeLayout, 'inspect'> & { stored: PaddingOptions }): Landing | null {
	if (c.layout === 'phone') return null;
	return landingFor(c.stored, chromePadding({ layout: c.layout, width: c.width, height: c.height, inspect: true }));
}

/** `cameraForBounds`' padding: `px` on every side, plus a landing's extra. */
export function fitPadding(px: number, landing?: Landing | null): Padding {
	const e = landing?.extra;
	return { top: px + (e?.top ?? 0), right: px + (e?.right ?? 0), bottom: px + (e?.bottom ?? 0), left: px + (e?.left ?? 0) };
}

/** A clicked selection this close to the inspect card (px), or under it, is covered... */
export const REVEAL_NEAR_PX = 16;
/** ...and pans to this far left of the card. */
export const REVEAL_CLEAR_PX = 40;
export const REVEAL_MS = 450;

/**
 * The open inspect card's column, in the map's px: its left edge, the card's
 * top, and the column's foot above the toolbar (the card grows down to it as
 * its content loads).
 */
export interface CardArea {
	left: number;
	top: number;
	bottom: number;
}

/**
 * Where a clicked selection goes so the inspect card leaves it in view (the
 * map's px), or null when it's clear already and nothing moves. Under the
 * card's column, or within REVEAL_NEAR_PX of it, it goes REVEAL_CLEAR_PX left
 * of the card at the same height: just far enough, sideways. Pure.
 */
export function revealTarget(p: Point, card: CardArea): Point | null {
	const covered = p.x >= card.left - REVEAL_NEAR_PX && p.y >= card.top - REVEAL_NEAR_PX && p.y <= card.bottom + REVEAL_NEAR_PX;
	return covered ? { x: card.left - REVEAL_CLEAR_PX, y: p.y } : null;
}

/**
 * Pan the map so the ground point `at` is drawn at `to` (the map's px): an
 * ease with an offset, at the same zoom, pitch, bearing and padding, so on a
 * tilted map the picture moves without skewing (a jump under reduced motion).
 * Not a fly: the view history keeps nothing.
 */
export function revealPan(map: Map, at: { lng: number; lat: number }, to: Point, reduced: boolean): void {
	const el = map.getContainer();
	const [x, y] = paddedCentre(el.clientWidth, el.clientHeight, map.getPadding());
	map.easeTo({ center: [at.lng, at.lat], offset: [to.x - x, to.y - y], ...(reduced ? { animate: false } : { duration: REVEAL_MS }) });
}

declare module '#lib/app/context.js' {
	interface AppCtx {
		/**
		 * Where a camera move the app starts now lands (§14.3 "Regions"): the
		 * inspect card's landing while it's open in Explore on a desktop or a
		 * tablet, else null (the middle of the map's own padding). The chrome
		 * sets it; a layer reads it here, so its chunk takes no code from the
		 * chrome's.
		 */
		readonly landing?: () => Landing | null;
	}
}
