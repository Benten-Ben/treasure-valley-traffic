import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { deltaE, ghostColor, mixLab, oklch } from '#lib/map/color.js';
import {
	LEGEND_RANGE,
	LEGEND_TICKS,
	legendGradient,
	legendPosition,
	RAMP_ALONE,
	RAMP_UNDER,
	rampStops,
	SPEED_STOPS,
	speedColor,
	speedExpression,
	UNDER_WIDTH
} from './ramp.js';

const DOC = readFileSync(new URL('../../../../../docs/14-ui-v2.md', import.meta.url), 'utf8');

/** A row of §14.5's ramp table, by its first cell. */
function rampRow(first: string): string[] {
	const line = DOC.split('\n').find((l) => l.startsWith(`| ${first} |`));
	expect(line, `the "${first}" row of the ramp table`).toBeTruthy();
	return line!
		.split('|')
		.slice(2, -1)
		.map((c) => c.trim().replace(/`/g, ''));
}

/** The 13 route colors (§14.4). */
const PALETTE = [...DOC.matchAll(/^\| \d+ \| \w+ \| `(#[0-9a-f]{6})` \|/gm)].map((m) => m[1]);

describe('speed ramp', () => {
	it('matches the stops in docs/14 §14.5', () => {
		expect(rampRow('mph')).toEqual(['≤ 20', ...SPEED_STOPS.slice(1).map(String)]);
		expect(rampRow('Alone')).toEqual([...RAMP_ALONE]);
		expect(rampRow('Under Transit')).toEqual([...RAMP_UNDER]);
		expect(rampStops('alone')[0]).toEqual([20, '#9fc2f0']);
		expect(rampStops('under').at(-1)).toEqual([75, '#657284']);
		expect(DOC).toContain('ticks at 20,\n  25, 35, 45, 55, 65 and 75');
		expect([...LEGEND_TICKS]).toEqual([20, 25, 35, 45, 55, 65, 75]);
	});

	it('is one hue, light to dark, with even steps to 55 mph and compressed above', () => {
		const L = RAMP_ALONE.map((c) => oklch(c).L);
		for (const c of RAMP_ALONE) expect(Math.abs(oklch(c).h - 255), c).toBeLessThan(1.5);
		for (const c of RAMP_UNDER) expect(Math.abs(oklch(c).h - 255), c).toBeLessThan(2);
		for (let i = 1; i < L.length; i++) expect(L[i], `step ${SPEED_STOPS[i]}`).toBeLessThan(L[i - 1]);
		// 20 → 55 mph: lightness falls about 0.062 per 5 mph.
		for (let i = 1; i <= SPEED_STOPS.indexOf(55); i++) expect(L[i - 1] - L[i], `${SPEED_STOPS[i]} mph`).toBeCloseTo(0.062, 2);
		// 60, 65, 75 (freeway classes, already drawn wide): smaller steps.
		for (let i = SPEED_STOPS.indexOf(60); i < L.length; i++) expect(L[i - 1] - L[i]).toBeLessThan(0.04);
	});

	it('under Transit: the same order in low-chroma slate, ΔE 3.6–4.0 apart to 55 mph and 1–2 above', () => {
		for (let i = 0; i < RAMP_UNDER.length; i++) {
			expect(oklch(RAMP_UNDER[i]).C).toBeLessThan(0.06);
			expect(oklch(RAMP_UNDER[i]).C).toBeLessThan(oklch(RAMP_ALONE[i]).C);
		}
		for (let i = 1; i < RAMP_UNDER.length; i++) {
			// The doc quotes one decimal.
			const d = Math.round(deltaE(RAMP_UNDER[i - 1], RAMP_UNDER[i]) * 10) / 10;
			const [lo, hi] = SPEED_STOPS[i] <= 55 ? [3.6, 4.0] : [1.0, 2.0];
			expect(d, `${SPEED_STOPS[i]} mph`).toBeGreaterThanOrEqual(lo);
			expect(d, `${SPEED_STOPS[i]} mph`).toBeLessThanOrEqual(hi);
		}
		expect(UNDER_WIDTH).toBe(0.7);
	});

	it('keeps every route color at least ΔE 11 from every street shade under Transit (15 or more for 9 of the 13)', () => {
		expect(PALETTE).toHaveLength(13);
		const nearest = PALETTE.map((p) => Math.min(...RAMP_UNDER.map((u) => deltaE(p, u))));
		for (let i = 0; i < PALETTE.length; i++) expect(nearest[i], PALETTE[i]).toBeGreaterThanOrEqual(11);
		expect(nearest.filter((d) => d >= 15).length).toBeGreaterThanOrEqual(9);
		// The reason for the slate ramp: route blue sits too close to the blue ramp.
		expect(Math.min(...RAMP_ALONE.map((u) => deltaE('#2a78d6', u)))).toBeLessThan(6);
	});

	it('reports the ghost-vs-street distances §14.3 quotes (form, not color, tells them apart)', () => {
		const near = (ghostOf: string) => Math.min(...RAMP_UNDER.map((u) => deltaE(ghostColor(ghostOf), u)));
		expect(near('#2a78d6')).toBeCloseTo(1.0, 0); // blue
		expect(near('#4a3aa7')).toBeCloseTo(3.1, 0); // violet
		expect(near('#9059af')).toBeCloseTo(4.6, 0); // plum
		expect(near('#a791fa')).toBeCloseTo(5.1, 0); // lavender
		expect(deltaE(ghostColor('#2a78d6'), RAMP_UNDER[1]), 'ghost blue vs slate 25 mph').toBeCloseTo(1.0, 0);
	});

	it('draws with interpolate-lab on the speed, clamped at 20 and 75', () => {
		const e = speedExpression('alone') as unknown[];
		expect(e.slice(0, 3)).toEqual(['interpolate-lab', ['linear'], ['coalesce', ['get', 'speed'], 0]]);
		expect(e.slice(3)).toEqual(rampStops('alone').flat());
		expect(speedColor(1)).toBe(RAMP_ALONE[0]);
		expect(speedColor(15)).toBe(RAMP_ALONE[0]);
		expect(speedColor(90)).toBe(RAMP_ALONE[10]);
		// No road is posted at 70; if one were, it would sit halfway between 65 and 75 in Lab.
		expect(speedColor(70)).toBe(mixLab(RAMP_ALONE[9], RAMP_ALONE[10], 0.5));
		for (let i = 0; i < SPEED_STOPS.length; i++) expect(speedColor(SPEED_STOPS[i], 'under')).toBe(RAMP_UNDER[i]);
	});

	it('the legend bar shows the 11 shades in hard steps across 160 px, ticks where the speeds are', () => {
		for (const name of ['alone', 'under'] as const) {
			const g = legendGradient(name);
			expect(g.startsWith('linear-gradient(to right, ')).toBe(true);
			const parts = [...g.matchAll(/(#[0-9a-f]{6}) ([\d.]+)% ([\d.]+)%/g)].map((m) => [m[1], Number(m[2]), Number(m[3])] as const);
			expect(parts.map((p) => p[0])).toEqual([...(name === 'alone' ? RAMP_ALONE : RAMP_UNDER)]);
			expect(parts[0][1]).toBe(0);
			expect(parts.at(-1)![2]).toBe(100);
			for (let i = 1; i < parts.length; i++) expect(parts[i][1]).toBe(parts[i - 1][2]);
			// Each tick lands inside its own shade.
			for (const t of LEGEND_TICKS) {
				const i = SPEED_STOPS.indexOf(t as (typeof SPEED_STOPS)[number]);
				const x = legendPosition(t) * 100;
				expect(x).toBeGreaterThan(parts[i][1]);
				expect(x).toBeLessThan(parts[i][2]);
			}
		}
		expect(legendPosition(LEGEND_RANGE[0])).toBe(0);
		expect(legendPosition(LEGEND_RANGE[1])).toBe(1);
	});
});
