/**
 * GET /api/transit/tracks?window=120[&at=<ISO time>]: playback steps
 * (docs/14 §14.4, "Playback"). Built by WP7, played by WP8.
 *
 * - `window` is in seconds, at most 900. A past `at` pins the window's end
 *   for replay and tests.
 * - `Cache-Control: no-store`, with a 5 s server micro-cache.
 * - A bus's newest fix arrives as a step with `t1 = null`; a later poll
 *   replaces it (steps are keyed by vehicle id and `t0`).
 * - Fixes with no progress row yet come through as 'straight' steps between
 *   fixes, so playback never goes blank. About 4–8 KB gzip per poll.
 *
 * Frozen contract (§14.10): only the wave integrator changes it.
 */
export const TRACKS_CONTRACT = 1;

/**
 * - along: constant speed along `path` between t0 and t1;
 * - still: at the fix;
 * - straight: linear between the fixes (off every shape, or no progress row yet);
 * - gap: more than 150 s to the next fix: hold, then a short fade-jump.
 * null for a bus's newest fix (no next fix yet).
 */
export type StepKind = 'along' | 'still' | 'straight' | 'gap';

/** How a bus's route is known: the feed's own route, its trip ID, trip_route_match, or a provisional path match. */
export type RouteSource = 'feed' | 'trip' | 'matched' | 'path';

export interface TrackVehicle {
	label: string | null;
	routeId: string | null;
	routeSource: RouteSource | null;
	shortName: string | null;
	color: string | null;
	textColor: string | null;
	/** The badge rule (§14.3); true for unknown-route gray. */
	halo: boolean;
	headsign: string | null;
}

/** One step from a fix to the next; positions are WGS84 degrees, times epoch seconds. */
export type TrackStep = [
	vid: string,
	t0: number,
	t1: number | null,
	kind: StepKind | null,
	lon0: number,
	lat0: number,
	/** Feed bearing at the fix, degrees. */
	bearing: number | null,
	/** m/s over the step: Δm/dt for along, chord/dt for straight, 0 for still. */
	speed: number | null,
	/** 'along' only: flat lon,lat,… along the shape, endpoints included. */
	path: number[] | null
];

export interface Tracks {
	contract: typeof TRACKS_CONTRACT;
	/** Server time, epoch s (the client's clock offset comes from it). */
	now: number;
	vehicles: Record<string, TrackVehicle>;
	steps: TrackStep[];
	/**
	 * Per route, spans of fixes over the last 75 min, split where two
	 * consecutive fixes are more than 15 min apart. A route is running at T
	 * iff some span has start ≤ T and end ≥ T − 900.
	 */
	routeRuns: Record<string, [start: number, end: number][]>;
	/** Newest fix of any bus, any age (for "No buses reporting · last fix …"). */
	lastFix: number | null;
}
