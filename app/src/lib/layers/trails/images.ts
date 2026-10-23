import { CREAM, ICON_IDS, UMBER } from './trails.js';

/**
 * Canvas-made map images for the Trails layer's status marks (plan §3.2, "points"): a ▲ for caution, a ■ for
 * a trail to stay off, a ✕ for a closure, an arrowhead for a detour. Each is a shape of its own, so a state
 * is never told by color alone, and each is the same cream and ink on any ground. Drawn at twice the CSS
 * size once, when the layer mounts.
 */
export const RATIO = 2;
const SIZE = 22;
const INK = '#2b2a33';

export interface MapImage {
	data: ImageData;
	options: { pixelRatio: number };
}

function canvas(): CanvasRenderingContext2D {
	const c = document.createElement('canvas');
	c.width = SIZE * RATIO;
	c.height = SIZE * RATIO;
	const g = c.getContext('2d')!;
	g.scale(RATIO, RATIO);
	g.lineJoin = 'round';
	g.lineCap = 'round';
	return g;
}

const done = (g: CanvasRenderingContext2D): MapImage => ({ data: g.getImageData(0, 0, SIZE * RATIO, SIZE * RATIO), options: { pixelRatio: RATIO } });

function plate(g: CanvasRenderingContext2D, path: () => void) {
	path();
	g.fillStyle = CREAM;
	g.strokeStyle = INK;
	g.lineWidth = 1.8;
	g.fill();
	g.stroke();
}

function caution(): MapImage {
	const g = canvas();
	plate(g, () => {
		g.beginPath();
		g.moveTo(11, 3);
		g.lineTo(19.5, 18.5);
		g.lineTo(2.5, 18.5);
		g.closePath();
	});
	g.fillStyle = INK;
	g.fillRect(10, 8.5, 2, 5.5);
	g.fillRect(10, 15.3, 2, 2);
	return done(g);
}

function muddy(): MapImage {
	const g = canvas();
	plate(g, () => {
		g.beginPath();
		g.roundRect(3.5, 3.5, 15, 15, 3);
	});
	g.fillStyle = INK;
	g.fillRect(7.5, 7.5, 7, 7);
	return done(g);
}

function closed(): MapImage {
	const g = canvas();
	plate(g, () => {
		g.beginPath();
		g.arc(11, 11, 8, 0, Math.PI * 2);
	});
	g.strokeStyle = INK;
	g.lineWidth = 2.2;
	g.beginPath();
	g.moveTo(7.5, 7.5);
	g.lineTo(14.5, 14.5);
	g.moveTo(14.5, 7.5);
	g.lineTo(7.5, 14.5);
	g.stroke();
	return done(g);
}

/** An arrowhead pointing right (along the line), umber with a cream outline. */
function detour(): MapImage {
	const g = canvas();
	g.beginPath();
	g.moveTo(5, 4.5);
	g.lineTo(17, 11);
	g.lineTo(5, 17.5);
	g.lineTo(8.5, 11);
	g.closePath();
	g.lineWidth = 3.4;
	g.strokeStyle = CREAM;
	g.stroke();
	g.fillStyle = UMBER;
	g.fill();
	return done(g);
}

/** Every status image by id (`ICON_IDS`). */
export function statusImages(): Record<(typeof ICON_IDS)[number], MapImage> {
	return { 'trails-caution': caution(), 'trails-muddy': muddy(), 'trails-closed': closed(), 'trails-detour': detour() };
}
