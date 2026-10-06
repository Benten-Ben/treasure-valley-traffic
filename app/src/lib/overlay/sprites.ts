import type { SpriteDef } from '#lib/gl/atlas.js';

/**
 * Canvas-drawn sprites for the overlay (docs/14 §14.8): discs and number
 * plates following the badge rule (§14.3): numerals at least 14 px bold in
 * the badge's text color; where that color doesn't reach 4.5:1 on the plate,
 * the numerals get a 2 px halo in the opposite tone (ink around white, cream
 * around ink), and the halo is what they're measured against.
 */
export const INK = '#2b2a33';
export const CREAM = '#fffbf4';

function channel(c: number): number {
	const s = c / 255;
	return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

/** WCAG relative luminance of a #rrggbb color. */
export function luminance(hex: string): number {
	const h = hex.replace('#', '');
	const full = h.length === 3 ? [...h].map((c) => c + c).join('') : h;
	const n = parseInt(full, 16);
	return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}

/** WCAG contrast ratio of two #rrggbb colors. */
export function contrast(a: string, b: string): number {
	const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
	return (x + 0.05) / (y + 0.05);
}

/** Whether numerals in `text` on `plate` need the halo (under 4.5:1). */
export function needsHalo(plate: string, text: string): boolean {
	return contrast(plate, text) < 4.5;
}

/** The halo color for a text color: ink around light numerals, cream around dark ones. */
export function haloFor(text: string): string {
	return luminance(text) > 0.4 ? INK : CREAM;
}

export interface DiscOptions {
	key: string;
	text: string;
	color: string;
	textColor: string;
	/** Hollow: a cream disc with a ring in the color (stale). */
	hollow?: boolean;
	/** Diameter, CSS px. */
	size?: number;
	/** Force the halo (else decided by contrast). */
	halo?: boolean;
}

/** A disc with a number: bus discs at far zoom. Numerals 14 px bold, per the badge rule. */
export function discSprite(o: DiscOptions): SpriteDef {
	const size = o.size ?? 26;
	const pad = 3;
	const box = size + pad * 2;
	return {
		key: o.key,
		width: box,
		height: box,
		draw(g) {
			const c = box / 2;
			const r = size / 2;
			g.beginPath();
			g.arc(c, c + 1.5, r, 0, Math.PI * 2);
			g.fillStyle = 'rgba(60,45,20,0.25)';
			g.fill();
			g.beginPath();
			g.arc(c, c, r, 0, Math.PI * 2);
			g.fillStyle = o.hollow ? CREAM : o.color;
			g.fill();
			g.lineWidth = o.hollow ? 3 : 2;
			g.strokeStyle = o.hollow ? o.color : CREAM;
			g.stroke();
			const fg = o.hollow ? INK : o.textColor;
			const bg = o.hollow ? CREAM : o.color;
			const label = o.text.length > 3 ? o.text.slice(0, 3) : o.text;
			const px = label.length >= 3 ? 12 : 14;
			g.font = `700 ${px}px Overpass, system-ui, sans-serif`;
			g.textAlign = 'center';
			g.textBaseline = 'middle';
			if (o.halo ?? needsHalo(bg, fg)) {
				g.lineJoin = 'round';
				g.lineWidth = 4;
				g.strokeStyle = haloFor(fg);
				g.strokeText(label, c, c + 1);
			}
			g.fillStyle = fg;
			g.fillText(label, c, c + 1);
		}
	};
}

/** A heading arrow: ink with a cream outline, pointing up (north) before rotation. */
export function arrowSprite(key = 'arrow'): SpriteDef {
	const s = 16;
	return {
		key,
		width: s,
		height: s,
		draw(g) {
			g.beginPath();
			g.moveTo(s / 2, 1.5);
			g.lineTo(s - 3, s - 3.5);
			g.lineTo(s / 2, s - 6);
			g.lineTo(3, s - 3.5);
			g.closePath();
			g.lineJoin = 'round';
			g.lineWidth = 2.5;
			g.strokeStyle = CREAM;
			g.stroke();
			g.fillStyle = INK;
			g.fill();
		}
	};
}

/** A selection ring: 2 px ink inside a 3 px cream halo (§14.3: selection never relies on amber). */
export function ringSprite(key = 'ring', size = 40): SpriteDef {
	return {
		key,
		width: size,
		height: size,
		draw(g) {
			const c = size / 2;
			g.beginPath();
			g.arc(c, c, c - 4, 0, Math.PI * 2);
			g.lineWidth = 6;
			g.strokeStyle = CREAM;
			g.stroke();
			g.lineWidth = 2;
			g.strokeStyle = INK;
			g.stroke();
		}
	};
}
