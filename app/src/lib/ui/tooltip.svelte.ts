/**
 * The one tooltip (docs/14 §14.3): toolbar buttons and chips show theirs
 * after 400 ms, then instantly when moving between them within 1 s; the map
 * shows the hovered thing's after 200 ms, 12 px from the cursor, flipping at
 * the edges.
 */
export interface Tip {
	/** Anchor point in viewport px. */
	x: number;
	y: number;
	/** Above an element (toolbar) or beside the cursor (map). */
	placement: 'above' | 'below' | 'cursor';
	title: string;
	lines: string[];
}

export const TOOLBAR_DELAY = 400;
export const MAP_DELAY = 200;
export const GRACE = 1000;

class TooltipState {
	current = $state.raw<Tip | null>(null);
	#timer: ReturnType<typeof setTimeout> | undefined;
	#hiddenAt = -Infinity;

	/** Show after `delay`, or at once when another tip was showing within the last second. */
	show(tip: Tip, delay = TOOLBAR_DELAY): void {
		clearTimeout(this.#timer);
		if (this.current || performance.now() - this.#hiddenAt < GRACE) {
			this.current = tip;
			return;
		}
		this.#timer = setTimeout(() => (this.current = tip), delay);
	}

	/** Move a showing tip (the cursor moved over the same thing). */
	move(tip: Tip): void {
		if (this.current) this.current = tip;
	}

	hide(): void {
		clearTimeout(this.#timer);
		if (this.current) this.#hiddenAt = performance.now();
		this.current = null;
	}
}

export const tooltip = new TooltipState();

/** Where an element's tip goes: centred above it (or below, near the top of the screen). */
export function tipFor(el: Element, title: string, lines: string[]): Tip {
	const r = el.getBoundingClientRect();
	const above = r.top > 120;
	return { x: r.left + r.width / 2, y: above ? r.top : r.bottom, placement: above ? 'above' : 'below', title, lines };
}
