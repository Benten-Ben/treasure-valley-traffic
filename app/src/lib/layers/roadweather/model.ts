/**
 * Road weather (docs/14 §14.6, "Road weather"; WP16): what `GET
 * /api/roadweather` answers, and the pure rules the server and the layer
 * share.
 *
 * ITD's road-weather stations (RWIS) carry 2 to 4 cameras each, one per
 * direction; a few Oregon DOT cameras in the regional ring come with them.
 * The capture service records every view about every 10 minutes, and 511
 * refreshes its copies about every 15. A station is one `core.camera`
 * (provider `ITD RWIS` or `ODOT`, migration cameras/0001), each view a
 * `core.camera_view` with its 511 image id (loaded by hand from the private
 * list: `idaho511_rwis_sites_oneoff`).
 *
 * **"No live feed":** when a camera is down, 511 serves its "No live camera
 * feed at this time" picture, a PNG the capture service never saves (docs/11).
 * So a view whose capture is running but which has had no new picture for 3
 * of 511's refreshes (45 minutes) is showing that placeholder, and so is one
 * that 511's list marks disabled or blocked. A station whose views all show it
 * is drawn hollow. With live images off, or no capture running for a view,
 * we can't tell, and say so ('unknown'): such a station is drawn as usual.
 */
export const ROADWEATHER_CONTRACT = 1;

export type Provider = 'ITD RWIS' | 'ODOT';
/** The providers the Road weather layer shows; the Cameras layer shows ACHD's. */
export const PROVIDERS: readonly Provider[] = ['ITD RWIS', 'ODOT'];

/** 511 refreshes road-weather pictures about every 15 minutes. */
export const REFRESH_S = 15 * 60;
/** No new picture for 3 refreshes: 511 is showing its "no live feed" picture. */
export const NO_FEED_AFTER_S = 3 * REFRESH_S;

/** live: a new picture within 45 min; no_feed: 511 shows its "no live feed" picture; unknown: can't tell. */
export type Feed = 'live' | 'no_feed' | 'unknown';

export interface RoadWeatherView {
	/** core.camera_view id (what /api/cameras/live takes). */
	id: number;
	imageId: number | null;
	/** Its direction from 511's list ("Looking East"), else "View n". */
	label: string;
	sortOrder: number;
	/** 511's list marks the image disabled or blocked. */
	disabled: boolean;
	/** When our capture first got its newest picture, epoch s; null for none today or yesterday (or images off). */
	seenAt: number | null;
	/** That picture's age at the answer's `now`, s. */
	ageS: number | null;
	/** The capture service records it and is running. */
	capturing: boolean;
	feed: Feed;
}

export interface RoadWeatherStation {
	/** core.camera id. */
	id: number;
	name: string;
	provider: Provider;
	lon: number;
	lat: number;
	views: RoadWeatherView[];
	/** Every view shows 511's "no live feed" picture: the badge is drawn hollow. */
	hollow: boolean;
}

export interface RoadWeather {
	contract: typeof ROADWEATHER_CONTRACT;
	/** Server time, epoch s. */
	now: number;
	/** CAMERA_IMAGES_ENABLED: without it no ages are known. */
	images: boolean;
	/** Why there are no stations, when the database can't have any yet (the migration isn't applied). */
	note?: string;
	stations: RoadWeatherStation[];
}

/** What a view shows, from 511's list and our capture (see the header). */
export function feedOf(v: { disabled: boolean; ageS: number | null; capturing: boolean }, images: boolean): Feed {
	if (v.disabled) return 'no_feed';
	if (v.ageS !== null && v.ageS <= NO_FEED_AFTER_S) return 'live';
	if (!images) return 'unknown';
	return v.capturing ? 'no_feed' : 'unknown';
}

/** Drawn hollow: it has views, and every one shows "no live feed". */
export const isHollow = (views: readonly Pick<RoadWeatherView, 'feed'>[]) => views.length > 0 && views.every((v) => v.feed === 'no_feed');

/** A view's tab label: its direction from 511's list, else "View n" (n from 1, in 511's order). */
export function viewLabel(direction: string | null | undefined, i: number): string {
	return direction?.trim() || `View ${i + 1}`;
}

/** The credit line for a station's pictures. */
export function creditOf(provider: Provider): string {
	return provider === 'ODOT' ? 'Oregon DOT via ITD 511' : 'ITD 511 road weather';
}

/** [west, south, east, north] */
export type Bounds = readonly [number, number, number, number];

/**
 * Stations drawn on the map: those inside the base map's bounds. The rest are
 * loaded but not drawn until the study area grows (§14.6; DECISIONS, pending).
 */
export function inBounds(s: Pick<RoadWeatherStation, 'lon' | 'lat'>, b: Bounds | null | undefined): boolean {
	return !b || (s.lon >= b[0] && s.lon <= b[2] && s.lat >= b[1] && s.lat <= b[3]);
}

/** Counts for the legend and the inspect card. */
export function summarize(stations: readonly RoadWeatherStation[]) {
	let views = 0;
	let live = 0;
	let hollow = 0;
	for (const s of stations) {
		views += s.views.length;
		live += s.views.filter((v) => v.feed === 'live').length;
		if (s.hollow) hollow++;
	}
	return { stations: stations.length, views, live, hollow };
}

/** "3 of 4 views live", "no live feed", "2 views". */
export function stationFact(s: Pick<RoadWeatherStation, 'views' | 'hollow'>): string {
	const n = s.views.length;
	if (s.hollow) return n === 1 ? 'No live feed' : `No live feed on any of ${n} views`;
	const live = s.views.filter((v) => v.feed === 'live').length;
	const known = s.views.some((v) => v.feed !== 'unknown');
	return known ? `${live} of ${n} view${n === 1 ? '' : 's'} live` : `${n} view${n === 1 ? '' : 's'}`;
}
