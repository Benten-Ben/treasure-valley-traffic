import type { ExpressionSpecification } from 'maplibre-gl';
import { interpolateLab } from '#lib/map/color.js';

/**
 * The speed ramp (docs/14 §14.5, "Speed ramp"; §14.3 "The color budget").
 *
 * One hue (255), light to dark as the posted speed rises, with a stop every
 * 5 mph from 20 to 65 plus 75 for I-84 (no road is posted at 70). Roads carry
 * one speed each, so the shade changes crisply where the posted speed
 * changes: 11 distinct shades (the stepped ramp the owner approved in Q2).
 * Values of 20 and under, including stray 1, 5, 10 and 15, share the lightest
 * shade; MapLibre's `interpolate-lab` would mix a value between stops in Lab.
 *
 * - **Alone:** the blue ramp, while Transit is off.
 * - **Under Transit:** a pale slate version (same order, low chroma, 70%
 *   width), so categorical hue stays Transit's: every route color sits at
 *   least ΔE 11 from every slate shade. The slate steps above 55 mph are only
 *   ΔE 1–2 apart, so the legend says "speeds approximate" and the card gives
 *   the exact speed.
 */

export type RampName = 'alone' | 'under';

/** The stops, in mph. */
export const SPEED_STOPS = [20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 75] as const;

/** §14.5's table, row "Alone". */
export const RAMP_ALONE = ['#9fc2f0', '#7baff0', '#5b9beb', '#3c86e0', '#1e72d1', '#0560ba', '#034f9b', '#003e7e', '#013974', '#033469', '#062d59'] as const;
/** §14.5's table, row "Under Transit". */
export const RAMP_UNDER = ['#c3cfdf', '#b2c4db', '#a2b8d5', '#94adcd', '#87a1c3', '#7d96b6', '#748aa7', '#6d7f97', '#6a7b91', '#68788c', '#657284'] as const;

export const RAMPS: Record<RampName, readonly string[]> = { alone: RAMP_ALONE, under: RAMP_UNDER };

/** Line width under Transit, as a share of the road-class width. */
export const UNDER_WIDTH = 0.7;

/** Legend ticks (§14.5). */
export const LEGEND_TICKS = [20, 25, 35, 45, 55, 65, 75] as const;

export function rampStops(name: RampName): [number, string][] {
	return SPEED_STOPS.map((mph, i) => [mph, RAMPS[name][i]]);
}

/** The color a road of this posted speed is drawn in (what the map's expression gives). */
export function speedColor(mph: number | null | undefined, name: RampName = 'alone'): string {
	return interpolateLab(rampStops(name), mph ?? 0);
}

/** The line-color expression: `interpolate-lab` over the stops on the road's `speed` (no speed counts as ≤ 20). */
export function speedExpression(name: RampName): ExpressionSpecification {
	return [
		'interpolate-lab',
		['linear'],
		['coalesce', ['get', 'speed'], 0],
		...rampStops(name).flat()
	] as unknown as ExpressionSpecification;
}

/** The speed scale the legend bar spans: half a step beyond each end stop. */
export const LEGEND_RANGE: readonly [number, number] = [17.5, 77.5];

/** Where a speed sits along the legend bar, 0–1. */
export function legendPosition(mph: number): number {
	const [lo, hi] = LEGEND_RANGE;
	return (mph - lo) / (hi - lo);
}

/**
 * The legend bar as a CSS gradient with hard stops: each shade owns the
 * stretch between the midpoints to its neighbors, so the bar shows the same
 * 11 distinct shades the map draws (65 ends, and 75 begins, at 70).
 */
export function legendGradient(name: RampName): string {
	const colors = RAMPS[name];
	const pct = (mph: number) => `${(legendPosition(mph) * 100).toFixed(2)}%`;
	const parts = SPEED_STOPS.map((mph, i) => {
		const from = i === 0 ? LEGEND_RANGE[0] : (SPEED_STOPS[i - 1] + mph) / 2;
		const to = i === SPEED_STOPS.length - 1 ? LEGEND_RANGE[1] : (mph + SPEED_STOPS[i + 1]) / 2;
		return `${colors[i]} ${pct(from)} ${pct(to)}`;
	});
	return `linear-gradient(to right, ${parts.join(', ')})`;
}
