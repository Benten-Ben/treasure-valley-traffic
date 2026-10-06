/**
 * GET /api/transit/network?v=<build>: routes, side-by-side corridor segments,
 * stops, hubs and dormant routes (docs/14 §14.4, "Route colors", "Side-by-side
 * ribbons", "Running and not-running routes"; §14.8 "APIs"). Built by WP6,
 * drawn by WP8.
 *
 * - Immutable for the current build (the URL carries it); at most about
 *   60 KB gzip.
 * - Until the first ribbon build exists (`build: 'none'`), the server sends
 *   each route's plain shapes as unbundled segments with one route each
 *   (`bundled: false`), so Transit never goes blank.
 * - The client expands each segment into one feature per route, with `rid`
 *   (the source's promoteId), `slot` (its index in `routes`) and
 *   `n` (= `routes.length`), and offsets it by slot (§14.4 "Drawing").
 *
 * Frozen contract (§14.10): only the wave integrator changes it.
 */
export const NETWORK_CONTRACT = 1;

export interface NetworkRoute {
	/** VRT's GTFS route_id. */
	id: string;
	/** Numeric route index within this build: the feature-state key (promoteId). */
	rid: number;
	shortName: string;
	longName: string | null;
	/** One of the 13 palette slots (§14.4), e.g. '#2a78d6'. */
	color: string;
	/** The pale ghost of `color` on clay, drawn when the route isn't running. */
	ghost: string;
	/** Badge numeral color on `color`: white '#ffffff' or ink '#2b2a33'. */
	textColor: string;
	/** The badge rule (§14.3): numerals need a 2 px halo in the opposite tone. */
	halo: boolean;
	sortOrder: number | null;
}

export interface NetworkSegment {
	id: number;
	/** Flat lon,lat,… (6 decimals) in the segment's digitized direction; shared by every route on it. */
	coords: number[];
	/**
	 * Route ids from left to right, looking along `coords`. Dormant routes
	 * take no slot. Positive line offsets are to the right of the direction.
	 */
	routes: string[];
	/** Midpoint within 300 m of a stop served by 6 or more routes. */
	hub: boolean;
	lengthM: number;
}

export interface NetworkStop {
	id: string;
	name: string | null;
	lon: number;
	lat: number;
	/** Routes serving the stop (from stop_times). */
	routes: string[];
	/** The segment the stop capsule lies across; null when it's on none. */
	segment: number | null;
	/** That segment's bundle size, so the capsule spans the whole bundle (1 when unbundled). */
	n: number;
	/** Bearing of the segment at the stop, degrees clockwise from north, to turn the capsule. */
	bearing: number | null;
}

export interface NetworkHub {
	id: string;
	/** e.g. 'Main Street Station'. */
	name: string;
	lon: number;
	lat: number;
	routes: string[];
}

export interface DormantRoute {
	routeId: string;
	/** Newest fix of any bus on the route (epoch s), or null if none was ever recorded. */
	lastFix: number | null;
}

export interface TransitNetwork {
	contract: typeof NETWORK_CONTRACT;
	/** Ribbon build hash, or 'none' (plain shapes). */
	build: string;
	/** false: plain shapes, one route per segment. */
	bundled: boolean;
	feedVersion: string | null;
	routes: NetworkRoute[];
	segments: NetworkSegment[];
	stops: NetworkStop[];
	hubs: NetworkHub[];
	/** Routes with no bus in 7 days: listed in the legend, no slot in any bundle. */
	dormant: DormantRoute[];
}
