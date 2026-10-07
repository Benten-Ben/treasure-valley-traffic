import type { NetworkRoute } from '#lib/contracts/network.js';
import { haloFor, needsHalo } from '#lib/overlay/sprites.js';
import { capsuleLength, CREAM, INK } from './network.js';

/**
 * Canvas-made map images for the Transit layer (docs/14 §14.4): route
 * shields (badges in slot order, ghosts for routes not running), stop
 * capsules and the hub pill. Drawn at twice the CSS size, the first time
 * MapLibre asks for one (`styleimagemissing`).
 *
 * Badges follow the badge rule (§14.3): numerals 14 px bold in the slot's
 * text color, with a 2 px halo in the opposite tone where the route is
 * flagged. A ghost badge (route not running) is its pale ghost plate with
 * ink numerals and a dashed edge, so "not running" is a shape, not a color.
 */
export const RATIO = 2;
const BADGE_H = 20;
const BADGE_MIN_W = 26;
const BADGE_GAP = 2;
const FONT = '700 14px Overpass, system-ui, sans-serif';

export interface MapImage {
	data: ImageData;
	options: { pixelRatio: number; stretchX?: [number, number][]; stretchY?: [number, number][]; content?: [number, number, number, number] };
}

function canvas(w: number, h: number): CanvasRenderingContext2D {
	const c = document.createElement('canvas');
	c.width = Math.max(1, Math.ceil(w * RATIO));
	c.height = Math.max(1, Math.ceil(h * RATIO));
	const g = c.getContext('2d')!;
	g.scale(RATIO, RATIO);
	return g;
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
	g.beginPath();
	g.moveTo(x + r, y);
	g.arcTo(x + w, y, x + w, y + h, r);
	g.arcTo(x + w, y + h, x, y + h, r);
	g.arcTo(x, y + h, x, y, r);
	g.arcTo(x, y, x + w, y, r);
	g.closePath();
}

const measure = (() => {
	let g: CanvasRenderingContext2D | null = null;
	return (text: string) => {
		g ??= document.createElement('canvas').getContext('2d')!;
		g.font = FONT;
		return g.measureText(text).width;
	};
})();

const badgeWidth = (text: string) => Math.max(BADGE_MIN_W, Math.ceil(measure(text)) + 12);

/** A strip of route badges, left to right (running ones in their color, the rest as ghosts). */
export function shieldImage(routes: readonly NetworkRoute[], running: readonly boolean[]): MapImage {
	const pad = 2;
	const widths = routes.map((r) => badgeWidth(r.shortName));
	const W = widths.reduce((a, b) => a + b, 0) + BADGE_GAP * Math.max(0, routes.length - 1) + pad * 2;
	const H = BADGE_H + pad * 2;
	const g = canvas(W, H);
	let x = pad;
	routes.forEach((r, i) => {
		const w = widths[i];
		const on = running[i];
		const plate = on ? r.color : r.ghost;
		const text = on ? r.textColor : INK;
		const y = pad;
		// A cream ring, then the plate.
		roundRect(g, x - 1.5, y - 1.5, w + 3, BADGE_H + 3, (BADGE_H + 3) / 2);
		g.fillStyle = CREAM;
		g.fill();
		roundRect(g, x, y, w, BADGE_H, BADGE_H / 2);
		g.fillStyle = plate;
		g.fill();
		g.lineWidth = 1;
		g.strokeStyle = 'rgba(43,42,51,0.45)';
		if (!on) g.setLineDash([2.5, 2]);
		g.stroke();
		g.setLineDash([]);
		g.font = FONT;
		g.textAlign = 'center';
		g.textBaseline = 'middle';
		const cx = x + w / 2;
		const cy = y + BADGE_H / 2 + 1;
		if (on ? r.halo || needsHalo(plate, text) : needsHalo(plate, text)) {
			g.lineJoin = 'round';
			g.lineWidth = 4;
			g.strokeStyle = haloFor(text);
			g.strokeText(r.shortName, cx, cy);
		}
		g.fillStyle = text;
		g.fillText(r.shortName, cx, cy);
		x += w + BADGE_GAP;
	});
	return { data: g.getImageData(0, 0, g.canvas.width, g.canvas.height), options: { pixelRatio: RATIO } };
}

/** A cream capsule with a 1.25 px ink outline, as long as a bundle of n at z15, drawn along x (turned to the street by icon-rotate). */
export function capsuleImage(n: number): MapImage {
	const len = capsuleLength(n);
	const h = 7;
	const g = canvas(len + 2, h + 2);
	roundRect(g, 1, 1, len, h, h / 2);
	g.fillStyle = CREAM;
	g.fill();
	g.lineWidth = 1.25;
	g.strokeStyle = INK;
	g.stroke();
	return { data: g.getImageData(0, 0, g.canvas.width, g.canvas.height), options: { pixelRatio: RATIO } };
}

/** The hub's station pill: a stretchable cream capsule with an ink edge (icon-text-fit). */
export function pillImage(): MapImage {
	const w = 40;
	const h = 24;
	const g = canvas(w, h);
	roundRect(g, 1, 1, w - 2, h - 2, (h - 2) / 2);
	g.fillStyle = CREAM;
	g.fill();
	g.lineWidth = 2;
	g.strokeStyle = INK;
	g.stroke();
	const r = RATIO;
	return {
		data: g.getImageData(0, 0, g.canvas.width, g.canvas.height),
		options: { pixelRatio: r, stretchX: [[14 * r, 26 * r]], stretchY: [[11 * r, 13 * r]], content: [8 * r, 4 * r, 32 * r, 20 * r] }
	};
}
