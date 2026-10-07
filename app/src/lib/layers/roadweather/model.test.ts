import { describe, expect, it } from 'vitest';
import { THRESHOLDS } from '../cameras/freshness.js';
import { creditOf, feedOf, inBounds, isHollow, NO_FEED_AFTER_S, stationFact, summarize, viewLabel, type RoadWeatherStation, type RoadWeatherView } from './model.js';

const view = (o: Partial<RoadWeatherView> = {}): RoadWeatherView => ({
	id: 1,
	imageId: 990011,
	label: 'View 1',
	sortOrder: 0,
	disabled: false,
	seenAt: null,
	ageS: null,
	capturing: true,
	feed: 'live',
	...o
});

const station = (views: RoadWeatherView[], o: Partial<RoadWeatherStation> = {}): RoadWeatherStation => ({
	id: 7,
	name: 'Example Grade (synthetic)',
	provider: 'ITD RWIS',
	lon: -116.24,
	lat: 43.56,
	views,
	hollow: isHollow(views),
	...o
});

describe('road weather: what a view shows', () => {
	it('"no live feed" after 3 of 511’s 15-minute refreshes, the same as the stale threshold', () => {
		expect(NO_FEED_AFTER_S).toBe(45 * 60);
		expect(NO_FEED_AFTER_S).toBe(THRESHOLDS.road_weather.late);
	});

	it('a recent picture is live; none for 45 min while capture runs is no live feed', () => {
		expect(feedOf({ disabled: false, ageS: 300, capturing: true }, true)).toBe('live');
		expect(feedOf({ disabled: false, ageS: NO_FEED_AFTER_S, capturing: true }, true)).toBe('live');
		expect(feedOf({ disabled: false, ageS: NO_FEED_AFTER_S + 1, capturing: true }, true)).toBe('no_feed');
		expect(feedOf({ disabled: false, ageS: null, capturing: true }, true)).toBe('no_feed');
	});

	it('511 listing the view as disabled is no live feed, whatever the archive says', () => {
		expect(feedOf({ disabled: true, ageS: 60, capturing: true }, true)).toBe('no_feed');
		expect(feedOf({ disabled: true, ageS: null, capturing: false }, false)).toBe('no_feed');
	});

	it("can't tell with live images off or capture not running for the view", () => {
		expect(feedOf({ disabled: false, ageS: null, capturing: false }, true)).toBe('unknown');
		expect(feedOf({ disabled: false, ageS: 4000, capturing: false }, true)).toBe('unknown');
		expect(feedOf({ disabled: false, ageS: null, capturing: true }, false)).toBe('unknown');
	});

	it('a station is hollow only when every view shows no live feed', () => {
		expect(isHollow([view({ feed: 'no_feed' }), view({ feed: 'no_feed' })])).toBe(true);
		expect(isHollow([view({ feed: 'no_feed' }), view({ feed: 'live' })])).toBe(false);
		expect(isHollow([view({ feed: 'no_feed' }), view({ feed: 'unknown' })])).toBe(false);
		expect(isHollow([])).toBe(false);
	});
});

describe('road weather: labels, bounds and counts', () => {
	it('labels a view by its direction, else "View n" in 511’s order', () => {
		expect(viewLabel('Looking East', 0)).toBe('Looking East');
		expect(viewLabel('  ', 1)).toBe('View 2');
		expect(viewLabel(null, 2)).toBe('View 3');
	});

	it('draws only stations inside the base map; without bounds, all', () => {
		const valley = [-117.05, 43.0, -115.95, 43.85] as const;
		expect(inBounds({ lon: -116.24, lat: 43.56 }, valley)).toBe(true);
		expect(inBounds({ lon: -116.9, lat: 44.2 }, valley)).toBe(false);
		expect(inBounds({ lon: -112, lat: 47 }, null)).toBe(true);
	});

	it('counts stations, views, live views and hollow stations', () => {
		const a = station([view({ feed: 'live' }), view({ feed: 'no_feed' })]);
		const b = station([view({ feed: 'no_feed' }), view({ feed: 'no_feed' })], { id: 8 });
		expect(summarize([a, b])).toEqual({ stations: 2, views: 4, live: 1, hollow: 1 });
	});

	it('says how many views are live, or that none has a feed', () => {
		expect(stationFact(station([view({ feed: 'live' }), view({ feed: 'no_feed' }), view({ feed: 'live' })]))).toBe('2 of 3 views live');
		expect(stationFact(station([view({ feed: 'no_feed' }), view({ feed: 'no_feed' })]))).toBe('No live feed on any of 2 views');
		expect(stationFact(station([view({ feed: 'unknown' }), view({ feed: 'unknown' })]))).toBe('2 views');
	});

	it('credits ITD, or Oregon DOT through ITD’s 511', () => {
		expect(creditOf('ITD RWIS')).toBe('ITD 511 road weather');
		expect(creditOf('ODOT')).toBe('Oregon DOT via ITD 511');
	});
});
