import { describe, expect, it } from 'vitest';
import { contrast } from '#lib/overlay/sprites.js';
import { numeralLook, PLATE_BODY_H, PLATE_FONT_PX, PLATE_PAD, PLATE_POINTER_H, plateKey, plateLabel, plateOffset, plateSize, plateSprite } from './plates.js';

const INK = '#2b2a33';
const WHITE = '#ffffff';
const CREAM = '#fffbf4';

/** §14.4's 13 palette slots: color, badge text color and whether the table marks a halo; and the unknown gray. */
const SLOTS: [name: string, color: string, text: string, halo: boolean][] = [
	['blue', '#2a78d6', WHITE, true],
	['orange', '#eb6834', INK, true],
	['aqua', '#1baf7a', INK, false],
	['yellow', '#eda100', INK, false],
	['pink', '#e87ba4', INK, false],
	['green', '#008300', WHITE, false],
	['violet', '#4a3aa7', WHITE, false],
	['red', '#e34948', WHITE, true],
	['wine', '#99095c', WHITE, false],
	['lavender', '#a791fa', INK, false],
	['brown', '#7f4315', WHITE, false],
	['plum', '#9059af', WHITE, false],
	['lime', '#8cc63f', INK, false],
	['unknown', '#8a857c', INK, true]
];

/** A canvas context that records what's drawn (no canvas in unit tests). */
function recorder() {
	const calls: { op: string; args: unknown[]; font: string; fillStyle: unknown; strokeStyle: unknown; lineWidth: number }[] = [];
	const g: Record<string, unknown> = { font: '', fillStyle: '', strokeStyle: '', lineWidth: 1, lineJoin: 'miter', textAlign: 'start', textBaseline: 'alphabetic' };
	for (const op of ['beginPath', 'moveTo', 'lineTo', 'arcTo', 'arc', 'closePath', 'fill', 'stroke', 'fillText', 'strokeText'])
		g[op] = (...args: unknown[]) => calls.push({ op, args, font: g.font as string, fillStyle: g.fillStyle, strokeStyle: g.strokeStyle, lineWidth: g.lineWidth as number });
	return { g: g as unknown as CanvasRenderingContext2D, calls };
}

describe('bus plates: the badge rule (§14.3)', () => {
	it('every palette slot reaches 4.5:1, with the halo exactly where the table says', () => {
		for (const [name, color, text, halo] of SLOTS) {
			const look = numeralLook({ color, textColor: text, halo });
			expect(look.fontPx, name).toBeGreaterThanOrEqual(14);
			expect(look.bold).toBe(true);
			expect(look.ratio, `${name}: numerals against ${look.halo ? 'their halo' : 'the plate'}`).toBeGreaterThanOrEqual(4.5);
			expect(Boolean(look.halo), `${name} halo`).toBe(halo);
			// Where there's a halo, the plain pair is the one that fell short.
			if (halo) expect(contrast(text, color), name).toBeLessThan(4.5);
			// The halo is the opposite tone: ink around white, cream around ink.
			if (look.halo) expect(look.halo).toBe(text === WHITE ? INK : CREAM);
		}
	});

	it('decides the halo by contrast when the API does not say', () => {
		expect(numeralLook({ color: '#2a78d6', textColor: WHITE }).halo).toBe(INK);
		expect(numeralLook({ color: '#4a3aa7', textColor: WHITE }).halo).toBeNull();
	});

	it('a stale (hollow) plate is ink on cream', () => {
		for (const [name, color, text, halo] of SLOTS) {
			const look = numeralLook({ color, textColor: text, halo, look: 'hollow' });
			expect(look.plate).toBe(CREAM);
			expect(look.numerals).toBe(INK);
			expect(look.halo).toBeNull();
			expect(look.ratio, name).toBeGreaterThanOrEqual(4.5);
		}
	});

	it('draws 15 px bold numerals in the text color, with a 2 px halo where needed', () => {
		const { g, calls } = recorder();
		plateSprite({ key: 'k', text: '9', color: '#2a78d6', textColor: WHITE, halo: true }).draw(g);
		const fill = calls.find((c) => c.op === 'fillText')!;
		const stroke = calls.find((c) => c.op === 'strokeText')!;
		expect(fill.args[0]).toBe('9');
		expect(fill.font).toMatch(new RegExp(`^700 ${PLATE_FONT_PX}px Overpass`));
		expect(fill.fillStyle).toBe(WHITE);
		expect(stroke.strokeStyle).toBe(INK);
		expect(stroke.lineWidth).toBe(4);
		// No halo: no stroked text.
		const plain = recorder();
		plateSprite({ key: 'k', text: '45', color: '#4a3aa7', textColor: WHITE, halo: false }).draw(plain.g);
		expect(plain.calls.some((c) => c.op === 'strokeText')).toBe(false);
	});

	it('a selected plate gets a 2 px ink line in a 3 px cream halo', () => {
		const { g, calls } = recorder();
		plateSprite({ key: 'k', text: '9', color: '#2a78d6', textColor: WHITE, halo: true, selected: true }).draw(g);
		const strokes = calls.filter((c) => c.op === 'stroke');
		expect(strokes[0]).toMatchObject({ strokeStyle: CREAM, lineWidth: 6 });
		expect(strokes[1]).toMatchObject({ strokeStyle: INK, lineWidth: 2 });
	});

	it('never shrinks numerals for longer labels: the plate widens', () => {
		expect(plateLabel('R1')).toBe('R1');
		expect(plateLabel('1234')).toBe('123');
		expect(plateSize('101').width).toBeGreaterThan(plateSize('10').width);
		expect(plateSize('10').width).toBeGreaterThan(plateSize('5').width - 1);
		// Wide enough for the numerals (about 0.6 em each) plus padding.
		expect(plateSize('101').width - 2 * PLATE_PAD).toBeGreaterThanOrEqual(3 * 0.6 * PLATE_FONT_PX + 8);
	});

	it('the offset puts the pointer tip on the anchor', () => {
		const { height } = plateSize('9');
		const tip = PLATE_PAD + PLATE_BODY_H + PLATE_POINTER_H;
		const [, dy] = plateOffset();
		// The sprite is drawn centred on anchor + offset: its tip lands at anchor + dy + (tip − height/2).
		expect(dy + (tip - height / 2)).toBeCloseTo(0, 9);
		expect(plateOffset(10)[1]).toBeCloseTo(dy - 10, 9);
	});

	it('keys each route, look and selection apart', () => {
		const b = { text: '9', color: '#2a78d6', textColor: WHITE, halo: true };
		const keys = new Set([plateKey(b, 'solid'), plateKey(b, 'hollow'), plateKey(b, 'solid', true), plateKey(b, 'hollow', true), plateKey({ ...b, text: '8' }, 'solid')]);
		expect(keys.size).toBe(5);
	});
});
