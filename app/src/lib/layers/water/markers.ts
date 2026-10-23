import { DROP } from './icons.js';
import { IMAGE } from './layers.js';

/**
 * The Water layer's badges, painted once on a canvas for map.addImage (landscape sprint plan v3 §3.2, points
 * slot). Each kind has its own **shape**, in ink and cream, so none is told by colour alone (docs/14 §14.3,
 * the colour budget; magenta, the problem colour, is only ever beside an icon):
 *
 * - **gauge:** a cream disc with a measuring staff and a water line; **in flood** the same with a magenta ring
 *   and a corner triangle, and its label says the category in words;
 * - **structure** (dam, weir, gate, waterfall, spring): a cream diamond with a bar across it, a dam in profile;
 * - **river hazard:** a magenta triangle with an ink edge and a cream "!";
 * - **E. coli site:** a cream rounded square with Phosphor's Drop (MIT), duotone.
 *
 * Browser only (canvas); `MARKERS` lists what is drawn, for the legend and the tests.
 */

export const MARKER_PX = 30;
const INK = '#2b2a33';
const CREAM = '#fffbf4';
const ALERT = '#d9467a';

export interface MarkerInfo {
	image: string;
	/** The shape in words, for the legend. */
	shape: string;
	/** What it marks. */
	marks: string;
}

export const MARKERS: readonly MarkerInfo[] = [
	{ image: IMAGE.gauge, shape: 'disc with a staff', marks: 'Gauge: river, creek, canal or reservoir level' },
	{ image: IMAGE.gaugeFlood, shape: 'disc with a staff, a magenta ring and a triangle', marks: 'Gauge at action stage or above' },
	{ image: IMAGE.structure, shape: 'diamond with a bar', marks: 'Dam, weir, gate, waterfall or spring' },
	{ image: IMAGE.hazard, shape: 'triangle with an exclamation mark', marks: 'River hazard (the City of Boise)' },
	{ image: IMAGE.ecoli, shape: 'rounded square with a drop', marks: 'E. coli sampling site (the City of Boise)' }
];

type Ctx = CanvasRenderingContext2D;

function stroke(g: Ctx, width: number, color = INK) {
	g.lineJoin = 'round';
	g.lineCap = 'round';
	g.strokeStyle = color;
	g.lineWidth = width;
	g.stroke();
}

function disc(g: Ctx, c: number, r: number, ratio: number, ring?: string) {
	g.beginPath();
	g.arc(c, c, r, 0, Math.PI * 2);
	g.fillStyle = CREAM;
	g.fill();
	if (ring) {
		stroke(g, 4.2 * ratio, ring);
		g.beginPath();
		g.arc(c, c, r - 1.6 * ratio, 0, Math.PI * 2);
	}
	stroke(g, 2 * ratio);
}

function staff(g: Ctx, c: number, ratio: number) {
	const u = ratio;
	g.beginPath();
	// The staff and its three ticks.
	g.moveTo(c - 4 * u, c - 8 * u);
	g.lineTo(c - 4 * u, c + 8 * u);
	for (const dy of [-5, 0, 5]) {
		g.moveTo(c - 4 * u, c + dy * u);
		g.lineTo(c - 1 * u, c + dy * u);
	}
	stroke(g, 1.6 * u);
	// The water line across it.
	g.beginPath();
	g.moveTo(c - 6 * u, c + 2 * u);
	g.quadraticCurveTo(c - 3 * u, c - 1 * u, c, c + 2 * u);
	g.quadraticCurveTo(c + 3 * u, c + 5 * u, c + 6 * u, c + 2 * u);
	stroke(g, 1.8 * u);
}

function paint(image: string, ratio: number): ImageData | null {
	if (typeof document === 'undefined') return null;
	const px = MARKER_PX * ratio;
	const canvas = document.createElement('canvas');
	canvas.width = canvas.height = px;
	const g = canvas.getContext('2d');
	if (!g) return null;
	const c = px / 2;
	const u = ratio;
	switch (image) {
		case IMAGE.gauge:
		case IMAGE.gaugeFlood: {
			const flood = image === IMAGE.gaugeFlood;
			disc(g, c, 12.5 * u, u, flood ? ALERT : undefined);
			staff(g, c, u);
			if (flood) {
				// A corner triangle: the same shape as a hazard, small.
				g.beginPath();
				g.moveTo(px - 11 * u, 2.5 * u);
				g.lineTo(px - 2.5 * u, 2.5 * u);
				g.lineTo(px - 6.75 * u, 10 * u);
				g.closePath();
				g.fillStyle = ALERT;
				g.fill();
				stroke(g, 1.4 * u);
			}
			break;
		}
		case IMAGE.structure: {
			const r = 12.5 * u;
			g.beginPath();
			g.moveTo(c, c - r);
			g.lineTo(c + r, c);
			g.lineTo(c, c + r);
			g.lineTo(c - r, c);
			g.closePath();
			g.fillStyle = CREAM;
			g.fill();
			stroke(g, 2 * u);
			g.beginPath();
			g.moveTo(c - 6 * u, c);
			g.lineTo(c + 6 * u, c);
			stroke(g, 3.4 * u);
			break;
		}
		case IMAGE.hazard: {
			g.beginPath();
			g.moveTo(c, 3 * u);
			g.lineTo(px - 2.5 * u, px - 5 * u);
			g.lineTo(2.5 * u, px - 5 * u);
			g.closePath();
			g.fillStyle = ALERT;
			g.fill();
			stroke(g, 2 * u);
			g.fillStyle = CREAM;
			g.beginPath();
			g.roundRect(c - 1.6 * u, 11 * u, 3.2 * u, 8 * u, 1.4 * u);
			g.fill();
			g.beginPath();
			g.arc(c, 22.4 * u, 1.9 * u, 0, Math.PI * 2);
			g.fill();
			break;
		}
		case IMAGE.ecoli: {
			const inset = 2 * u;
			g.beginPath();
			g.roundRect(inset, inset, px - 2 * inset, px - 2 * inset, 7 * u);
			g.fillStyle = CREAM;
			g.fill();
			stroke(g, 2 * u);
			const icon = 19 * u;
			g.save();
			g.translate((px - icon) / 2, (px - icon) / 2);
			g.scale(icon / 256, icon / 256);
			g.globalAlpha = 0.2;
			g.fillStyle = INK;
			g.fill(new Path2D(DROP.tone));
			g.globalAlpha = 1;
			// Phosphor's lines are drawn for 24 px and up; on a map badge they are thickened a little.
			g.fillStyle = INK;
			g.strokeStyle = INK;
			g.lineWidth = 9;
			g.lineJoin = 'round';
			const line = new Path2D(DROP.line);
			g.fill(line);
			g.stroke(line);
			g.restore();
			break;
		}
		default:
			return null;
	}
	return g.getImageData(0, 0, px, px);
}

/** One badge's pixels at a ratio (2 by default), or null outside a browser. */
export function markerImage(image: string, ratio = 2): ImageData | null {
	return paint(image, ratio);
}
