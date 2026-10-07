import { barPx, type ImageSize, type LngLatZ, type Pair, type Pixel } from '#lib/calibration/solver.js';
import type { LiveFrame, SaveFrameRequest } from '#lib/contracts/live.js';
import { readStored, removeStored, writeStored } from '#lib/state/persisted.svelte.js';

/**
 * The calibrator's working state, kept pure (docs/14 §14.6, "Calibrating on
 * the map"; WP14):
 *
 * - **Pairs:** each is an image point and a ground point, clicked in either
 *   order. Only the last pair may be unfinished (the "pending" one): the next
 *   click on the other side completes it, a click on the same side moves it.
 *   Every edit returns a new list (undo keeps the old ones).
 * - **Drafts** are saved per view in localStorage, `tvt:v2:calib-draft:<viewId>`,
 *   on every change, so a reload (or Back, or Esc) resumes where it was. A
 *   draft is removed once it's saved or discarded, or when it's back to what
 *   it started from.
 * - **The reference frame** is the frozen picture the pairs were clicked on.
 *   "Use this frame" freezes the live picture shown in the inset: the client
 *   posts its identity (an archive frame's image, day and stamp, or an
 *   on-demand frame's sha), never "whatever is newest".
 */

export interface DraftPair {
	pixel?: Pixel;
	ground?: LngLatZ;
}

/** A reference frame kept in FRAMES_DIR (what POST /api/views/[id]/frame answers). */
export interface RefFrame {
	/** Relative to FRAMES_DIR, stored as the calibration's reference_frame. */
	frame: string;
	/** /frames/<frame> */
	url: string;
	width: number;
	height: number;
	/** ISO time it was kept, when known. */
	capturedAt?: string | null;
}

export interface Draft {
	v: 1;
	cameraId: number;
	viewId: number;
	frame: RefFrame | null;
	pairs: DraftPair[];
	/** The saved calibration it started from (null: a new one). */
	base: number | null;
	/** When it was last changed, epoch ms. */
	savedAt: number;
}

export const draftKey = (viewId: number) => `calib-draft:${viewId}`;

const isNum = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
const isPixel = (x: unknown): x is Pixel => Array.isArray(x) && x.length === 2 && x.every(isNum);
const isGround = (x: unknown): x is LngLatZ => Array.isArray(x) && x.length === 3 && x.every(isNum);

function isFrame(x: unknown): x is RefFrame {
	const f = x as RefFrame;
	return !!f && typeof f.frame === 'string' && typeof f.url === 'string' && isNum(f.width) && isNum(f.height) && f.width > 0 && f.height > 0;
}

export function isDraft(x: unknown): x is Draft {
	const d = x as Draft;
	return (
		!!d &&
		d.v === 1 &&
		Number.isInteger(d.cameraId) &&
		Number.isInteger(d.viewId) &&
		(d.frame === null || isFrame(d.frame)) &&
		Array.isArray(d.pairs) &&
		d.pairs.every((p) => !!p && (p.pixel === undefined || isPixel(p.pixel)) && (p.ground === undefined || isGround(p.ground)) && (p.pixel || p.ground)) &&
		(d.base === null || Number.isInteger(d.base)) &&
		isNum(d.savedAt)
	);
}

/** The view's saved draft, or null (none, unreadable, or another camera's). */
export function readDraft(viewId: number, cameraId?: number): Draft | null {
	const d = readStored(draftKey(viewId), isDraft);
	if (!d || d.viewId !== viewId || (cameraId !== undefined && d.cameraId !== cameraId)) return null;
	return d;
}

export function writeDraft(d: Draft): boolean {
	return writeStored(draftKey(d.viewId), d);
}

export function clearDraft(viewId: number): void {
	removeStored(draftKey(viewId));
}

// --- pairs ---------------------------------------------------------------------------

/** The finished pairs, in order. */
export function complete(pairs: readonly DraftPair[]): Pair[] {
	return pairs.filter((p): p is Pair => !!p.pixel && !!p.ground);
}

/** The unfinished pair's index (only the last may be), or -1. */
export function pendingIndex(pairs: readonly DraftPair[]): number {
	const last = pairs.at(-1);
	return last && !(last.pixel && last.ground) ? pairs.length - 1 : -1;
}

/** What the next click should be: the other half of the pending pair, or a new pair. */
export function nextStep(pairs: readonly DraftPair[]): 'image' | 'map' | 'either' {
	const i = pendingIndex(pairs);
	if (i === -1) return 'either';
	return pairs[i].pixel ? 'map' : 'image';
}

export interface Placed {
	pairs: DraftPair[];
	/** The pair the click went to. */
	index: number;
}

/** A click in the picture: completes (or moves) the pending pair's image point, or starts a pair. */
export function placePixel(pairs: readonly DraftPair[], px: Pixel): Placed {
	const i = pendingIndex(pairs);
	if (i === -1) return { pairs: [...pairs, { pixel: px }], index: pairs.length };
	return { pairs: pairs.with(i, { ...pairs[i], pixel: px }), index: i };
}

/** A click on the map: completes (or moves) the pending pair's ground point, or starts a pair. */
export function placeGround(pairs: readonly DraftPair[], g: LngLatZ): Placed {
	const i = pendingIndex(pairs);
	if (i === -1) return { pairs: [...pairs, { ground: g }], index: pairs.length };
	return { pairs: pairs.with(i, { ...pairs[i], ground: g }), index: i };
}

export function removePair(pairs: readonly DraftPair[], i: number): DraftPair[] {
	return i < 0 || i >= pairs.length ? [...pairs] : pairs.filter((_, k) => k !== i);
}

/** Move one pair's image point (dragging its marker). */
export function movePixel(pairs: readonly DraftPair[], i: number, px: Pixel): DraftPair[] {
	return i < 0 || i >= pairs.length ? [...pairs] : pairs.with(i, { ...pairs[i], pixel: px });
}

/** Move one pair's ground point (dragging its marker on the map). */
export function moveGround(pairs: readonly DraftPair[], i: number, g: LngLatZ): DraftPair[] {
	return i < 0 || i >= pairs.length ? [...pairs] : pairs.with(i, { ...pairs[i], ground: g });
}

/** The pair whose image point is within `radius` (image px) of `px`, nearest first; -1 for none. */
export function pairNear(pairs: readonly DraftPair[], px: Pixel, radius: number): number {
	let best = -1;
	let bestD = radius;
	pairs.forEach((p, i) => {
		if (!p.pixel) return;
		const d = Math.hypot(p.pixel[0] - px[0], p.pixel[1] - px[1]);
		if (d <= bestD) {
			best = i;
			bestD = d;
		}
	});
	return best;
}

/** Same pairs and frame (what decides whether there's anything to keep as a draft). */
export function sameWork(a: { pairs: readonly DraftPair[]; frame: RefFrame | null }, b: { pairs: readonly DraftPair[]; frame: RefFrame | null }): boolean {
	if ((a.frame?.frame ?? null) !== (b.frame?.frame ?? null)) return false;
	if (a.pairs.length !== b.pairs.length) return false;
	const eq = (x?: readonly number[], y?: readonly number[]) => (!x && !y) || (!!x && !!y && x.length === y.length && x.every((v, k) => v === y[k]));
	return a.pairs.every((p, i) => eq(p.pixel, b.pairs[i].pixel) && eq(p.ground, b.pairs[i].ground));
}

/**
 * Image points carried to a reference frame of another size: scaled by the
 * width ratio, when both pictures above their 511 bar have the same shape
 * (the 768×466 and 1920×1166 frames are both 16:9 over their bar). Null when
 * they don't, so the points can't carry over.
 */
export function rescalePairs(pairs: readonly DraftPair[], from: ImageSize, to: ImageSize): DraftPair[] | null {
	if (from.width === to.width && from.height === to.height) return [...pairs];
	const a = from.width / (from.height - barPx(from.width, from.height));
	const b = to.width / (to.height - barPx(to.width, to.height));
	if (Math.abs(a - b) > 0.01 * a) return null;
	const k = to.width / from.width;
	return pairs.map((p) => (p.pixel ? { ...p, pixel: [p.pixel[0] * k, p.pixel[1] * k] as Pixel } : { ...p }));
}

// --- frames --------------------------------------------------------------------------

/** "Use this frame": the identity of the live picture shown, as POST /api/views/[id]/frame wants it. */
export function frameChoice(f: Pick<LiveFrame, 'sha' | 'archive'>): Exclude<SaveFrameRequest, Record<string, never>> {
	if (f.archive) return { image: f.archive.image, day: f.archive.day, stamp: f.archive.stamp };
	return { sha: f.sha };
}

// --- ground heights --------------------------------------------------------------------

/**
 * A true ground height from the drawn one: the map draws terrain multiplied
 * by its *current* exaggeration (not the manifest's), so a height picked at
 * 1.3 and one picked at 1.0 agree.
 */
export function trueHeight(drawn: number, exaggeration: number): number {
	return exaggeration > 0 ? drawn / exaggeration : drawn;
}

// --- undo ------------------------------------------------------------------------------

/** A bounded undo stack of whole states. */
export class Undo<T> {
	#stack: T[] = [];
	constructor(readonly limit = 100) {}

	push(state: T): void {
		this.#stack.push(state);
		if (this.#stack.length > this.limit) this.#stack.shift();
	}

	pop(): T | undefined {
		return this.#stack.pop();
	}

	clear(): void {
		this.#stack = [];
	}

	get size(): number {
		return this.#stack.length;
	}
}

// --- the solve card ----------------------------------------------------------------------

/** The fit, in words (the same thresholds as the old calibrator). */
export function quality(rms: number): { word: 'great' | 'good' | 'rough' | 'poor'; text: string } {
	if (rms < 1.5) return { word: 'great', text: 'great' };
	if (rms < 3) return { word: 'good', text: 'good' };
	if (rms < 6) return { word: 'rough', text: 'rough: check the pairs with the biggest errors' };
	return { word: 'poor', text: 'poor: some pairs probably don’t match' };
}

/** A pair's error as a shape and a class (never color alone): ● under 2 px, ▲ under 5, ■ beyond. */
export function residualMark(r: number): { shape: '●' | '▲' | '■'; cls: 'good' | 'fair' | 'bad' } {
	if (r < 2) return { shape: '●', cls: 'good' };
	if (r < 5) return { shape: '▲', cls: 'fair' };
	return { shape: '■', cls: 'bad' };
}

export const compass = (h: number) => ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round((((h % 360) + 360) % 360) / 45) % 8];
