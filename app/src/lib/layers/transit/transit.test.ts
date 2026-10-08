import { describe, expect, it } from 'vitest';
import { ageText, busNumber, ease, isStale, lerp, stopText, towardText, trailSegments, TRAIL_S, UNKNOWN_COLOR, type Vehicle } from './transit.js';

const bus = (over: Partial<Vehicle> = {}): Vehicle => ({
	vehicleId: '706',
	label: '706',
	routeId: '9',
	routeMatched: false,
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

describe('the bus card', () => {
	it('numbers a bus by its vehicle ID, never the feed label (the run)', () => {
		// Oct 7: vehicle 3505 reported the label "05:41:00-4", 708 "NIS"; a few IDs carry a trailing space.
		expect(busNumber('3505')).toBe('3505');
		expect(busNumber('722 ')).toBe('722');
		expect(busNumber('N701 ')).toBe('N701');
	});

	it('says every headsign VRT uses once, as "toward …" or as it is', () => {
		// Every headsign in the Oct 7 schedule (core.transit_trip), with its number of trips.
		const real: [string, string][] = [
			['Towards Main Street Station', 'toward Main Street Station'], // 1,581
			['Toward Towne Square Mall', 'toward Towne Square Mall'], // 1,235
			['Toward Boise Airport', 'toward Boise Airport'],
			['Toward Gary & State', 'toward Gary & State'],
			['Inbound', 'Inbound'], // 333
			['Toward 36th & Shasta', 'toward 36th & Shasta'],
			['Toward Parkhill & Bogus Basin', 'toward Parkhill & Bogus Basin'],
			['Outbound', 'Outbound'], // 130
			['Toward Pro Tech & Salt Creek', 'toward Pro Tech & Salt Creek'],
			['Toward Millspur Way', 'toward Millspur Way'],
			['Toward Happy Day Transit Center', 'toward Happy Day Transit Center'],
			['Toward Records & Village', 'toward Records & Village'],
			['Toward University & Joyce', 'toward University & Joyce'],
			['Toward Wayfinder & Vanguard', 'toward Wayfinder & Vanguard'],
			['Toward Discovery & Chinden', 'toward Discovery & Chinden'],
			['Toward The College of Western Idaho', 'toward The College of Western Idaho'],
			['Toward River Valley & Records', 'toward River Valley & Records'],
			['Toward Blaine & 24th', 'toward Blaine & 24th'],
			['Toward State & Ellens Ferry', 'toward State & Ellens Ferry']
		];
		for (const [headsign, said] of real) expect(towardText(headsign)).toBe(said);
	});

	it('adds "toward" to a bare place, and keeps words that only start like it', () => {
		expect(towardText('Towne Square Mall')).toBe('toward Towne Square Mall');
		expect(towardText('  TOWARDS  Main Street Station ')).toBe('toward Main Street Station');
		expect(towardText('inbound')).toBe('Inbound');
		expect(towardText('Inbound Express')).toBe('toward Inbound Express');
	});
});
