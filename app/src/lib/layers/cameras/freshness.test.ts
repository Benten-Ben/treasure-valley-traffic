import { describe, expect, it } from 'vitest';
import type { LiveView } from '#lib/contracts/live.js';
import { cadenceText, footText, formatAge, freshness, ringProgress, shown, sizeChanged, THRESHOLDS } from './freshness.js';
import { lookThroughBlocked } from './hooks.svelte.js';

const frame = { url: '/camera-frames/656/2026-10-07/20261007T150000Z.jpg', firstSeenAt: 1000, width: 768, height: 466, sha: 'a'.repeat(64) };
const view = (over: Partial<LiveView> = {}): LiveView => ({
	viewId: 26,
	imageId: 656,
	source: 'archive',
	frame,
	cadence: 'key',
	cadenceS: 50,
	state: 'ok',
	...over
});

describe('freshness', () => {
	it('key and on-demand pictures: live within 3 min, late within 10, stale after', () => {
		for (const c of ['key', 'on_demand'] as const) {
			expect(freshness(0, c)).toBe('fresh');
			expect(freshness(180, c)).toBe('fresh');
			expect(freshness(181, c)).toBe('late');
			expect(freshness(600, c)).toBe('late');
			expect(freshness(601, c)).toBe('stale');
		}
	});

	it('road-weather pictures: live under 20 min, stale over 45', () => {
		expect(THRESHOLDS.road_weather).toEqual({ fresh: 1200, late: 2700 });
		expect(freshness(1199, 'road_weather')).toBe('fresh');
		expect(freshness(1200, 'road_weather')).toBe('late');
		expect(freshness(2700, 'road_weather')).toBe('late');
		expect(freshness(2701, 'road_weather')).toBe('stale');
	});

	it('formats ages as m:ss, then hours and minutes, then days', () => {
		expect(formatAge(0)).toBe('0:00');
		expect(formatAge(48.9)).toBe('0:48');
		expect(formatAge(725)).toBe('12:05');
		expect(formatAge(3599)).toBe('59:59');
		expect(formatAge(3900)).toBe('1 h 05 min');
		expect(formatAge(86_400)).toBe('1 day');
		expect(formatAge(3 * 86_400 + 5)).toBe('3 days');
		expect(formatAge(-5)).toBe('0:00');
	});

	it('says how often a view updates', () => {
		expect(cadenceText(50)).toBe('updates about every minute');
		expect(cadenceText(60, true)).toBe('updates about every minute while open');
		expect(cadenceText(600)).toBe('updates about every 10 minutes');
	});

	it('fills the ring over the cadence', () => {
		expect(ringProgress(0, 50)).toBe(0);
		expect(ringProgress(25, 50)).toBe(0.5);
		expect(ringProgress(80, 50)).toBe(1);
		expect(ringProgress(10, 0)).toBe(1);
	});

	it('gives every state a shape and a word, never color alone', () => {
		const cases: [LiveView | null, number | null, string, string, string][] = [
			[null, null, 'waiting', '◌', 'waiting'],
			[view(), 30, 'fresh', '●', 'live'],
			[view(), 300, 'late', '▲', 'late'],
			[view(), 900, 'stale', '■', 'stale'],
			[view({ frame: null, state: 'waiting' }), null, 'waiting', '◌', 'no picture yet'],
			[view({ state: 'blocked', reason: undefined, source: '511' }), 30, 'blocked', '■', 'blocked'],
			[view({ state: 'capped', reason: 'On-demand limit reached (12 cameras per 10 minutes)' }), 30, 'capped', '■', 'limit reached'],
			[view({ state: 'error', frame: null, reason: '511 image 656: not a complete JPEG' }), null, 'offline', '■', 'offline'],
			[view({ state: 'disabled', frame: null, source: 'none' }), null, 'off', '■', 'off'],
			[view({ state: 'no_image', frame: null, imageId: null }), null, 'no_image', '■', 'not on 511']
		];
		for (const [v, age, kind, shape, word] of cases) {
			const s = shown(v, age);
			expect([s.kind, s.shape, s.word], `${kind}`).toEqual([kind, shape, word]);
			expect(s.color).toMatch(/^var\(--/);
			expect(s.detail.length).toBeGreaterThan(0);
		}
		expect(shown(view({ state: 'blocked', source: '511' }), 30).detail).toBe("robots.txt doesn't allow it right now");
		expect(shown(view({ state: 'error', frame: null, reason: 'boom' }), null).detail).toBe('boom');
	});

	it('writes the footer in "seen" time', () => {
		expect(footText(view(), 48)).toBe('seen 0:48 ago · updates about every minute');
		expect(footText(view({ source: '511', cadence: 'on_demand', cadenceS: 60 }), 75)).toBe('seen 1:15 ago · updates about every minute while open');
		expect(footText(view({ frame: null, state: 'waiting' }), null)).toBe('no picture yet · updates about every minute');
		expect(footText(null, null)).toBe('no picture yet');
	});

	it('checks the live picture against the calibration’s size', () => {
		expect(sizeChanged({ width: 768, height: 466 }, { imageWidth: 768, imageHeight: 466 })).toBeNull();
		expect(sizeChanged({ width: 1920, height: 1166 }, { imageWidth: 768, imageHeight: 466 })).toBe(
			'Image size changed (768×466 → 1920×1166); recalibrate'
		);
		expect(sizeChanged(null, { imageWidth: 768, imageHeight: 466 })).toBeNull();
		expect(sizeChanged({ width: 768, height: 466 }, null)).toBeNull();
	});

	it('says why look-through is off', () => {
		expect(lookThroughBlocked({ calibrated: false, sizeChanged: null, available: true })).toMatch(/not calibrated/i);
		expect(lookThroughBlocked({ calibrated: true, sizeChanged: 'Image size changed (a → b); recalibrate', available: true })).toMatch(/^Image size changed/);
		expect(lookThroughBlocked({ calibrated: true, sizeChanged: null, available: false })).toMatch(/3D cameras/);
		expect(lookThroughBlocked({ calibrated: true, sizeChanged: null, available: true })).toBeNull();
	});
});
