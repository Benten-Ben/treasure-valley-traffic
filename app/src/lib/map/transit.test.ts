import { describe, expect, it } from 'vitest';
import { ageText, ease, isStale, lerp, stopText, trailSegments, TRAIL_S, UNKNOWN_COLOR, type Vehicle } from './transit.js';

const bus = (over: Partial<Vehicle> = {}): Vehicle => ({
	vehicleId: '706',
	label: '706',
	routeId: '9',
	shortName: '9',
	longName: 'State Street',
	color: '#2a78d6',
	textColor: '#ffffff',
	ts: 1000,
	lon: -116.2,
	lat: 43.6,
	bearing: 90,
	status: 2,
	stopName: 'State & 27th',
	trail: [],
	...over
});

describe('trailSegments', () => {
	it('fades older segments and drops points past the trail window', () => {
		const v = bus({
			trail: [
				[-116.25, 43.6, 1000 - TRAIL_S - 30], // too old: dropped
				[-116.24, 43.6, 1000 - 200],
				[-116.23, 43.6, 1000 - 100],
				[-116.22, 43.6, 1000]
			]
		});
		const segs = trailSegments(v, 1000);
		expect(segs).toHaveLength(2);
		const [older, newer] = segs.map((s) => s.properties!.opacity as number);
		expect(newer).toBeGreaterThan(older);
		expect(older).toBeGreaterThan(0);
		expect(segs[0].properties!.color).toBe('#2a78d6');
	});

	it('skips repeated positions and uses gray when the route is unknown', () => {
		const v = bus({
			color: null,
			routeId: null,
			trail: [
				[-116.2, 43.6, 900],
				[-116.2, 43.6, 930],
				[-116.21, 43.6, 960]
			]
		});
		const segs = trailSegments(v, 1000);
		expect(segs).toHaveLength(1);
		expect(segs[0].properties!.color).toBe(UNKNOWN_COLOR);
	});
});

describe('wording', () => {
	it('says how old a position is', () => {
		expect(ageText(42.4)).toBe('42 s ago');
		expect(ageText(185)).toBe('3 min ago');
		expect(ageText(3900)).toBe('1 h 5 min ago');
		expect(ageText(-3)).toBe('0 s ago');
	});

	it('describes the stop from the GTFS-realtime status', () => {
		expect(stopText(bus({ status: 1 }))).toBe('At State & 27th');
		expect(stopText(bus({ status: 0 }))).toBe('Arriving at State & 27th');
		expect(stopText(bus({ status: 2 }))).toBe('Next stop: State & 27th');
		expect(stopText(bus({ stopName: null }))).toBeNull();
	});
});

describe('motion', () => {
	it('marks a bus stale after two quiet minutes', () => {
		expect(isStale({ ts: 1000 }, 1119)).toBe(false);
		expect(isStale({ ts: 1000 }, 1121)).toBe(true);
	});

	it('glides from the old position to the new one, softly at both ends', () => {
		expect(ease(0)).toBe(0);
		expect(ease(1)).toBe(1);
		expect(ease(0.5)).toBeCloseTo(0.5);
		expect(ease(0.1)).toBeLessThan(0.1);
		expect(lerp([0, 0], [10, 20], 0.25)).toEqual([2.5, 5]);
	});
});
