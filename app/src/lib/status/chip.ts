import type { StatusLevel } from './summary.js';

/**
 * The pure parts of the status chip (landscape sprint, M1): how often it
 * asks /api/meta again, when a focus may ask again, and when its live region
 * should speak. The chip's component only wires these to the page.
 */

/** Minutes-long polling: the chip refetches /api/meta this often while the page is visible (ms). */
export const POLL_MS = 5 * 60_000;

/** A focus refetches only when the last answer is at least this old (ms), so tabbing about doesn't hammer the server. */
export const FOCUS_GAP_MS = 60_000;

/** Whether a focus should refetch: never fetched, or the last answer is older than the gap. */
export function refetchOnFocus(lastAt: number | null, now: number, gap = FOCUS_GAP_MS): boolean {
	return lastAt === null || now - lastAt >= gap;
}

/**
 * Whether the live region speaks: only when the level moves from one known
 * level to another. The first answer is not a change, so a page load is silent.
 */
export function levelChanged(prev: StatusLevel | null, next: StatusLevel): boolean {
	return prev !== null && prev !== next;
}
