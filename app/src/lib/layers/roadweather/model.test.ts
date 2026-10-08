import { describe, expect, it } from 'vitest';
import { THRESHOLDS } from '../cameras/freshness.js';
import {
	ageAt,
	creditOf,
	feedOf,
	footOf,
	inBounds,
	isHollow,
	isNoFeed,
	NO_FEED_AFTER_S,
	REFRESH_TEXT,
	shortAge,
	stationFact,
	summarize,
	viewLabel,
	viewStatus,
	type RoadWeatherStation,
	type RoadWeatherView
} from './model.js';

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
	it('"no live feed" after 4 of 511’s 15-minute refreshes, the same as the stale threshold', () => {
		expect(NO_FEED_AFTER_S).toBe(60 * 60);
		expect(NO_FEED_AFTER_S).toBe(THRESHOLDS.road_weather.late);
	});

	it('a recent picture is live; none for an hour while capture runs is no live feed', () => {
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

describe('road weather: one vocabulary for the window and the card', () => {
	const words = (v: RoadWeatherView, age: number | null) => {
		const s = viewStatus(v, age);
		return `${s.shape} ${s.word}`;
	};

	it('live within 30 min, late within 60, stale after, by the picture’s age', () => {
		expect(words(view(), 8 * 60)).toBe('● live');
		expect(words(view(), 30 * 60)).toBe('● live');
		expect(words(view(), 34 * 60)).toBe('▲ late');
		expect(words(view(), 60 * 60)).toBe('▲ late');
		// Over an hour while capture runs: stale, and 511 probably shows "no live feed" (the window's note).
		expect(words(view({ feed: 'no_feed' }), 70 * 60)).toBe('■ stale');
		expect(words(view({ feed: 'unknown', capturing: false }), 70 * 60)).toBe('■ stale');
	});

	it('no live feed when 511 lists the view as disabled, or nothing was recorded while capture runs', () => {
		expect(words(view({ disabled: true }), null)).toBe('■ no live feed');
		expect(words(view({ disabled: true, feed: 'no_feed' }), 4 * 60)).toBe('■ no live feed');
		expect(words(view({ feed: 'no_feed' }), null)).toBe('■ no live feed');
		expect(isNoFeed(viewStatus(view({ feed: 'no_feed' }), null))).toBe(true);
		expect(isNoFeed(viewStatus(view(), 60))).toBe(false);
	});

	it('no picture yet when none was recorded and we can’t tell why', () => {
		expect(words(view({ feed: 'unknown', capturing: false }), null)).toBe('◌ no picture yet');
	});

	it('says 511 updates the pictures about every 15 minutes (not our 10-minute capture)', () => {
		expect(REFRESH_TEXT).toBe('511 updates these pictures about every 15 minutes');
		expect(footOf(4 * 60 + 5)).toBe('seen 4:05 ago · 511 updates these pictures about every 15 minutes');
		expect(footOf(70 * 60)).toBe('seen 1 h 10 min ago · 511 updates these pictures about every 15 minutes');
		expect(footOf(null)).toBe('no picture yet · 511 updates these pictures about every 15 minutes');
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
		const a = station([view({ feed: 'live', ageS: 300 }), view({ feed: 'live', ageS: 40 * 60 }), view({ feed: 'no_feed' })]);
		const b = station([view({ feed: 'no_feed' }), view({ feed: 'no_feed' })], { id: 8 });
		expect(summarize([a, b])).toEqual({ stations: 2, views: 5, live: 1, hollow: 1 });
	});

	it('says how many views are live (a picture within 30 min, as the window says), or that none has a feed', () => {
		const views = [view({ ageS: 300 }), view({ feed: 'no_feed' }), view({ ageS: 1000 }), view({ ageS: 34 * 60 })];
		expect(stationFact(station(views))).toBe('2 of 4 views live');
		expect(stationFact(station([view({ feed: 'no_feed' }), view({ feed: 'no_feed' })]))).toBe('No live feed on any of 2 views');
		expect(stationFact(station([view({ feed: 'unknown' }), view({ feed: 'unknown' })]))).toBe('2 views');
		// At a later clock, from when each picture was seen: 300 s + 26 min is past 30 min.
		const seen = [view({ seenAt: 10_000, ageS: 300 }), view({ seenAt: 9_000, ageS: 1300 })];
		expect(stationFact(station(seen))).toBe('2 of 2 views live');
		expect(stationFact(station(seen), 10_300 + 26 * 60)).toBe('0 of 2 views live');
	});

	it('gives a picture’s age from the answer, or from when it was seen at a later clock', () => {
		expect(ageAt({ seenAt: 1000, ageS: 60 })).toBe(60);
		expect(ageAt({ seenAt: 1000, ageS: 60 }, 1600)).toBe(600);
		expect(ageAt({ seenAt: 1000, ageS: 60 }, 900)).toBe(0);
		expect(ageAt({ seenAt: null, ageS: null }, 1600)).toBeNull();
	});

	it('short ages for the tabs and the card', () => {
		expect(shortAge(30)).toBe('<1 min');
		expect(shortAge(34 * 60 + 5)).toBe('34 min');
		expect(shortAge(70 * 60)).toBe('1 h');
		expect(shortAge(2 * 86_400)).toBe('2 d');
	});

	it('credits ITD, or Oregon DOT through ITD’s 511', () => {
		expect(creditOf('ITD RWIS')).toBe('ITD 511 road weather');
		expect(creditOf('ODOT')).toBe('Oregon DOT via ITD 511');
	});
});
