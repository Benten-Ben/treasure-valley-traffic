import type { SpriteDef } from '#lib/gl/atlas.js';
import { contrast, CREAM, haloFor, INK, needsHalo } from '#lib/overlay/sprites.js';
import type { Badge } from '../types.js';

/**
 * Bus number plates over the 3D models (docs/14 §14.4 "Buses and stops";
 * WP10). From about z15 a bus is a 3D model in the scene layer, and its route
 * number rides above it on a plate drawn by the always-loaded overlay: the
 * plate stays above the model at every zoom and is never hidden by it (the
 * overlay is the top of the map).
 *
 * - **The badge rule** (§14.3): numerals at least 14 px bold (15 px here) in
 *   the route's badge text color. Where that color is under 4.5:1 on the
 *   plate (blue, orange, red and the unknown gray), the numerals get a 2 px
 *   halo in the opposite tone, and the halo is what they're measured
 *   against.
 * - **Looks:** solid (the route color with a cream rim), hollow for a stale
 *   bus (cream with a rim in the route color, ink numerals, as the stale
 *   disc), and selected (a 2 px ink line with a 3 px cream halo around it,
 *   §14.3 "Selection").
 * - A short pointer under the plate marks the bus: the sprite is anchored at
 *   its centre, so `plateOffset` moves it up until the pointer's tip sits on
 *   the anchor (the model's roof, lifted by `altitude`).
 *
 * Sprites are drawn on a canvas once per route and look, as the discs are.
 */

/** Numeral size (CSS px, bold): at least 14 px (§14.3). */
export const PLATE_FONT_PX = 15;
export const PLATE_FONT = `700 ${PLATE_FONT_PX}px Overpass, system-ui, sans-serif`;
/** The plate's body height and the pointer under it (CSS px). */
export const PLATE_BODY_H = 21;
export const PLATE_POINTER_H = 6;
/** Room around the body for the rim, the shadow and the selection ring (CSS px). */
export const PLATE_PAD = 6;
/** The halo around numerals that need one: 2 px on each side (a 4 px stroke). */
export const HALO_PX = 2;

export type PlateLook = 'solid' | 'hollow';

export interface PlateOptions {
	key: string;
	text: string;
	color: string;
	textColor: string;
	/** Force the halo (the API's flag); else decided by contrast. */
	halo?: boolean;
	look?: PlateLook;
	selected?: boolean;
}

/** The label as drawn (at most 3 characters, never shrunk below the rule's size). */
export const plateLabel = (text: string) => (text.length > 3 ? text.slice(0, 3) : text);

/** The body's width for a label (CSS px): the numerals plus padding, never narrower than tall. */
export function plateBodyWidth(text: string): number {
	const n = plateLabel(text).length;
	return Math.max(PLATE_BODY_H + 7, Math.round(14 + n * 0.62 * PLATE_FONT_PX));
}

/** The whole sprite's size (CSS px). */
export function plateSize(text: string): { width: number; height: number } {
	return { width: plateBodyWidth(text) + 2 * PLATE_PAD, height: PLATE_BODY_H + PLATE_POINTER_H + 2 * PLATE_PAD };
}

/** Screen offset (px) that puts the pointer's tip on the anchor, raised `clearance` px more. */
export function plateOffset(clearance = 0): [number, number] {
	const { height } = plateSize('0');
	return [0, -(height / 2 - PLATE_PAD) - clearance];
}

/** Which colors the numerals are drawn in, and the pair the badge rule measures. */
export interface NumeralLook {
	/** Plate fill and numeral color. */
	plate: string;
	numerals: string;
	/** The halo color, or null without one. */
	halo: string | null;
	/** The measured pair's contrast: numerals on the halo when there is one, else on the plate. */
	ratio: number;
	fontPx: number;
	bold: boolean;
}

export function numeralLook(o: Pick<PlateOptions, 'color' | 'textColor' | 'halo' | 'look'>): NumeralLook {
	const hollow = o.look === 'hollow';
	const plate = hollow ? CREAM : o.color;
	const numerals = hollow ? INK : o.textColor;
	const halo = !hollow && (o.halo ?? needsHalo(plate, numerals)) ? haloFor(numerals) : null;
	return { plate, numerals, halo, ratio: contrast(numerals, halo ?? plate), fontPx: PLATE_FONT_PX, bold: true };
}

/** A plate's sprite key: one per route color, numerals, look and selection. */
export function plateKey(b: Badge, look: PlateLook, selected = false): string {
	return `plate:${b.color}:${b.textColor}:${b.text}:${b.halo ? 1 : 0}:${look}${selected ? ':sel' : ''}`;
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
	g.beginPath();
	g.moveTo(x + r, y);
	g.lineTo(x + w - r, y);
	g.arcTo(x + w, y, x + w, y + r, r);
	g.lineTo(x + w, y + h - r);
	g.arcTo(x + w, y + h, x + w - r, y + h, r);
	g.lineTo(x + r, y + h);
	g.arcTo(x, y + h, x, y + h - r, r);
	g.lineTo(x, y + r);
	g.arcTo(x, y, x + r, y, r);
	g.closePath();
}

/** The plate's outline: a rounded body with a pointer below its middle. */
function platePath(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, pointer: number) {
	const r = 6;
	const cx = x + w / 2;
	const half = 5;
	g.beginPath();
	g.moveTo(x + r, y);
	g.lineTo(x + w - r, y);
	g.arcTo(x + w, y, x + w, y + r, r);
	g.lineTo(x + w, y + h - r);
	g.arcTo(x + w, y + h, x + w - r, y + h, r);
	g.lineTo(cx + half, y + h);
	g.lineTo(cx, y + h + pointer);
	g.lineTo(cx - half, y + h);
	g.lineTo(x + r, y + h);
	g.arcTo(x, y + h, x, y + h - r, r);
	g.lineTo(x, y + r);
	g.arcTo(x, y, x + r, y, r);
	g.closePath();
}

/** A bus's number plate (§14.4), following the badge rule. */
export function plateSprite(o: PlateOptions): SpriteDef {
	const { width, height } = plateSize(o.text);
	const bw = plateBodyWidth(o.text);
	const look = numeralLook(o);
	const hollow = o.look === 'hollow';
	const label = plateLabel(o.text);
	return {
		key: o.key,
		width,
		height,
		draw(g) {
			const x = PLATE_PAD;
			const y = PLATE_PAD;
			if (o.selected) {
				// A 2 px ink line with a 3 px cream halo, around the plate (§14.3 "Selection").
				roundRect(g, x - 3.5, y - 3.5, bw + 7, PLATE_BODY_H + 7, 9);
				g.lineWidth = 6;
				g.strokeStyle = CREAM;
				g.stroke();
				g.lineWidth = 2;
				g.strokeStyle = INK;
				g.stroke();
			}
			// A soft shadow, then the body and pointer with their rim.
			platePath(g, x, y + 1.5, bw, PLATE_BODY_H, PLATE_POINTER_H);
			g.fillStyle = 'rgba(60,45,20,0.25)';
			g.fill();
			platePath(g, x, y, bw, PLATE_BODY_H, PLATE_POINTER_H);
			g.fillStyle = look.plate;
			g.fill();
			g.lineJoin = 'round';
			g.lineWidth = hollow ? 3 : 2;
			g.strokeStyle = hollow ? o.color : CREAM;
			g.stroke();
			g.font = PLATE_FONT;
			g.textAlign = 'center';
			g.textBaseline = 'middle';
			const tx = x + bw / 2;
			const ty = y + PLATE_BODY_H / 2 + 1;
			if (look.halo) {
				g.lineJoin = 'round';
				g.lineWidth = 2 * HALO_PX;
				g.strokeStyle = look.halo;
				g.strokeText(label, tx, ty);
			}
			g.fillStyle = look.numerals;
			g.fillText(label, tx, ty);
		}
	};
}

/** Draw plates with the app's own font once it's loaded (sprites drawn before then keep the fallback). */
export function loadPlateFont(): void {
	try {
		void (globalThis.document as Document | undefined)?.fonts?.load(PLATE_FONT).catch(() => {});
	} catch {
		/* no font loading API */
	}
}
