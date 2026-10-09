/**
 * Fanning out a group's sprites that cover each other (docs/14 §14.4, "the
 * number plate is never hidden"): two buses at one stop put their plates on
 * the same spot, so one route number would be hidden at every zoom.
 *
 * Going from the last instance (drawn on top: it stays where it is) to the
 * first, a box that overlaps one already placed by more than STACK_SHARE of
 * the smaller box moves up until it clears that one by `gap` px, and again
 * past any it then covers. So the plates stand in a column over the buses,
 * each with its pointer, the last one on the buses themselves.
 *
 * A box lifted last frame stays lifted down to KEEP_SHARE, so a pair near
 * the threshold doesn't flicker between one and two rows.
 */

/** Overlap (of the smaller box's area) from which a box makes way: its numerals would be partly covered. */
export const STACK_SHARE = 0.3;
/** A box lifted last frame stays lifted until the overlap falls below this. */
export const KEEP_SHARE = 0.15;

export interface StackItem {
	id: string;
	/** The sprite's centre on screen, px; `y` is moved. */
	x: number;
	y: number;
	/** The box that must stay clear, as its reach from the centre: left, up, right and down (px). */
	l: number;
	t: number;
	r: number;
	b: number;
	/** Set by `stackUp`: how far it was moved up (px). */
	dy: number;
}

const area = (a: StackItem) => (a.l + a.r) * (a.t + a.b);

/** The area two boxes share, px². */
export function overlapArea(a: StackItem, b: StackItem): number {
	const w = Math.min(a.x + a.r, b.x + b.r) - Math.max(a.x - a.l, b.x - b.l);
	const h = Math.min(a.y + a.b, b.y + b.b) - Math.max(a.y - a.t, b.y - b.t);
	return w > 0 && h > 0 ? w * h : 0;
}

/**
 * Fan out the first `n` items in place (see above). `was` holds the ids lifted
 * last frame; the ids lifted now are written into `out` (cleared first) and
 * returned.
 */
export function stackUp(items: StackItem[], n: number, gap: number, was?: ReadonlySet<string>, out: Set<string> = new Set()): Set<string> {
	out.clear();
	for (let i = n - 1; i >= 0; i--) {
		const a = items[i];
		a.dy = 0;
		const share = was?.has(a.id) ? KEEP_SHARE : STACK_SHARE;
		// Each pass lifts it past one box; it only ever moves up, so n passes are plenty.
		for (let pass = 0; pass < n; pass++) {
			let top = Infinity;
			for (let j = i + 1; j < n; j++) {
				const b = items[j];
				const o = overlapArea(a, b);
				if (o > 0 && o > share * Math.min(area(a), area(b))) top = Math.min(top, b.y - b.t);
			}
			if (top === Infinity) break;
			const y = top - gap - a.b;
			if (y >= a.y) break;
			a.dy += a.y - y;
			a.y = y;
			out.add(a.id);
		}
	}
	return out;
}
