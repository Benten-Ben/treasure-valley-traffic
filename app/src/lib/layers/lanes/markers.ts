import { ARROW_PREFIX, TURN_CODES, arrowsOfImage, type Turn } from './lanes.js';
import { IMAGE } from './layers.js';

/**
 * The Lanes layer's two kinds of mark, painted once on a canvas for map.addImage (landscape sprint plan v3 §3.2,
 * points and labels slots). Both are told by **shape** in ink and cream, never by colour (docs/14 §14.3):
 *
 * - **the ▲ conflict mark:** a cream triangle with an ink edge holding two bars of different heights (two sources,
 *   two counts). It is the shape of a warning, but not Water's magenta hazard triangle: ink on cream, no "!";
 * - **a turn arrow:** a cream arrow with an ink edge, pointing up, for a lane's turns (left, through, right, U-turn
 *   and the combinations a lane carries). It is rotated to the way the lane runs by the layer (`icon-rotate`).
 *
 * Browser only (canvas). `ARROW_IMAGES` lists every arrow image id the layer adds.
 */

export const MARKER_PX = 32;
const INK = '#2b2a33';
const CREAM = '#fffbf4';

const SETS: readonly Turn[][] = (() => {
	const order: Turn[] = ['left', 'through', 'right', 'uturn'];
	const out: Turn[][] = [];
	for (let mask = 1; mask < 16; mask++) out.push(order.filter((_, i) => mask & (1 << i)));
	return out;
})();

/** Every arrow image id: the 15 non-empty combinations of left, through, right and U-turn. */
export const ARROW_IMAGES: readonly string[] = SETS.map((s) => `${ARROW_PREFIX}${s.map((t) => TURN_CODES[t]).join('')}`);
/** A lane whose turns draw nothing (`none`): a transparent pixel, so the map doesn't ask for an image that isn't there. */
export const EMPTY_ARROW = ARROW_PREFIX;

type Ctx = CanvasRenderingContext2D;

function canvas(ratio: number, px = MARKER_PX): { g: Ctx; px: number } | null {
	if (typeof document === 'undefined') return null;
	const size = px * ratio;
	const c = document.createElement('canvas');
	c.width = c.height = size;
	const g = c.getContext('2d');
	return g ? { g, px: size } : null;
}

/** The ▲ mark's pixels at a ratio (2 by default), or null outside a browser. */
export function conflictImage(ratio = 2): ImageData | null {
	const made = canvas(ratio);
	if (!made) return null;
	const { g, px } = made;
	const u = ratio;
	const c = px / 2;
	g.beginPath();
	g.moveTo(c, 3 * u);
	g.lineTo(px - 2.5 * u, px - 5 * u);
	g.lineTo(2.5 * u, px - 5 * u);
	g.closePath();
	g.fillStyle = CREAM;
	g.fill();
	g.lineJoin = 'round';
	g.strokeStyle = INK;
	g.lineWidth = 2 * u;
	g.stroke();
	// Two bars of different heights: two sources, two counts.
	g.fillStyle = INK;
	g.beginPath();
	g.roundRect(c - 5 * u, 12 * u, 3.4 * u, 10 * u, 1 * u);
	g.fill();
	g.beginPath();
	g.roundRect(c + 1.6 * u, 16 * u, 3.4 * u, 6 * u, 1 * u);
	g.fill();
	return g.getImageData(0, 0, px, px);
}

/** An arrow's pixels (the lane's arrows named by its image id), pointing up; null outside a browser or for none. */
export function arrowImage(id: string, ratio = 2): ImageData | null {
	if (id === EMPTY_ARROW) {
		const made = canvas(ratio, 1);
		return made ? made.g.getImageData(0, 0, made.px, made.px) : null;
	}
	const turns = arrowsOfImage(id);
	if (!turns.length) return null;
	const made = canvas(ratio);
	if (!made) return null;
	const { g, px } = made;
	const u = ratio;
	g.scale(u, u);
	g.lineJoin = 'round';
	g.lineCap = 'butt';
	const has = (t: Turn) => turns.includes(t);
	const x = 16;
	const base = 29;
	// Where the shaft ends: at the tip for a through arrow, at the bend for a turn, below the arc for a U-turn.
	const tip = has('through') ? 10 : has('left') || has('right') ? 19 : 14;
	const shaft = (x0: number, y0: number, x1: number, y1: number) => {
		g.beginPath();
		g.moveTo(x0, y0);
		g.lineTo(x1, y1);
		g.strokeStyle = INK;
		g.lineWidth = 5.4;
		g.stroke();
		g.strokeStyle = CREAM;
		g.lineWidth = 3;
		g.stroke();
	};
	const head = (pts: [number, number][]) => {
		g.beginPath();
		g.moveTo(...pts[0]);
		for (const p of pts.slice(1)) g.lineTo(...p);
		g.closePath();
		g.fillStyle = CREAM;
		g.fill();
		g.strokeStyle = INK;
		g.lineWidth = 1.6;
		g.stroke();
	};
	if (has('uturn') && !has('through')) {
		// Up the lane's right, over, and back down on the left, head pointing down.
		const ux = 21;
		g.beginPath();
		g.moveTo(ux, base);
		g.lineTo(ux, 13);
		g.arc(ux - 5.5, 13, 5.5, 0, Math.PI, true);
		g.lineTo(ux - 11, 21);
		g.strokeStyle = INK;
		g.lineWidth = 5.4;
		g.stroke();
		g.strokeStyle = CREAM;
		g.lineWidth = 3;
		g.stroke();
		head([
			[ux - 11 - 4.6, 20],
			[ux - 11 + 4.6, 20],
			[ux - 11, 27]
		]);
		if (has('left') || has('right')) {
			// A U-turn lane that also turns: the turn branches off the shaft.
			const d = has('left') ? -1 : 1;
			shaft(ux, 21, ux + d * 9, 21);
			head([
				[ux + d * 14, 21],
				[ux + d * 7, 16.4],
				[ux + d * 7, 25.6]
			]);
		}
		return g.getImageData(0, 0, px, px);
	}
	shaft(x, base, x, tip);
	if (has('through')) head([[x, 3], [x - 6.5, 11.5], [x + 6.5, 11.5]]);
	for (const side of [-1, 1] as const) {
		if (!(side === -1 ? has('left') : has('right'))) continue;
		const y = has('through') ? 20 : 19;
		shaft(x, y, x + side * 8.5, y);
		head([
			[x + side * 14.5, y],
			[x + side * 7.5, y - 5.6],
			[x + side * 7.5, y + 5.6]
		]);
	}
	if (has('uturn')) {
		// A through lane that also allows a U-turn: a short hook on the left of the shaft.
		shaft(x, 24, x - 7, 24);
		head([
			[x - 12.5, 24],
			[x - 6.5, 19.5],
			[x - 6.5, 28.5]
		]);
	}
	return g.getImageData(0, 0, px, px);
}

/** Every image the layer adds, by style image id. */
export function allImages(ratio = 2): { id: string; image: ImageData; ratio: number }[] {
	const out: { id: string; image: ImageData; ratio: number }[] = [];
	const conflict = conflictImage(ratio);
	if (conflict) out.push({ id: IMAGE.conflict, image: conflict, ratio });
	for (const id of [...ARROW_IMAGES, EMPTY_ARROW]) {
		const image = arrowImage(id, ratio);
		if (image) out.push({ id, image, ratio: id === EMPTY_ARROW ? 1 : ratio });
	}
	return out;
}
