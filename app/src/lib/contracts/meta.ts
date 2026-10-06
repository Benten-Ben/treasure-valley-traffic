/**
 * GET /api/meta: data versions (docs/14 §14.8, "Boot" and "APIs").
 *
 * The boot fetches this (preloaded from app.html) before any layer data, and
 * every data URL carries the matching version as `?v=`, so a response can be
 * cached for as long as its version stands. Memoized 15 s on the server and
 * sent with `Cache-Control: no-cache`.
 *
 * It works before and after migrations 0006 and 0007: tables that don't
 * exist yet read as "none" or null rather than failing the request. When the
 * database is down or unconfigured it still answers (200), with `database`
 * saying so and every database version null, so the map can boot without it.
 *
 * Frozen contract (§14.10): only the wave integrator changes it. Adding an
 * optional field is compatible; renaming or removing one is not.
 */
export const META_CONTRACT = 1;

/** Opaque, short version strings for `?v=`. null: no such data (yet). */
export interface DataVersions {
	/** VRT's static GTFS feed version (core.transit_route.feed_version). */
	gtfs: string | null;
	/**
	 * Ribbon build hash (core.transit_ribbon.build), or 'none' before the first
	 * build or migration 0006. Its form is described on TransitNetwork.build.
	 */
	ribbons: string;
	/** Road segments (ACHD centerlines): changes when segments are added, retired or re-seen. */
	roads: string | null;
	/**
	 * Cameras and views, including each camera's calibration status, since
	 * /api/cameras reports it: changes with the calibrations version too.
	 */
	cameras: string | null;
	/** Current calibrations: changes whenever one is saved or closed. */
	calibrations: string | null;
	/** The basemap build (manifest dates), when the server can see the manifest. */
	tiles: string | null;
}

export interface DataMeta {
	contract: typeof META_CONTRACT;
	/** When the server computed this answer (epoch s); it may be up to 15 s old. */
	generatedAt: number;
	/** 'ok'; 'unconfigured' (no DATABASE_URL); 'error' (the database didn't answer). */
	database: 'ok' | 'unconfigured' | 'error';
	versions: DataVersions;
	gtfs: { feedVersion: string; routes: number; updatedAt: number } | null;
	/** null until migration 0006 exists and a build has run. */
	ribbons: { build: string; segments: number } | null;
	/** obs.vehicle_progress (migration 0007) exists: playback can use matched steps. */
	progress: { available: boolean };
	roads: { segments: number; lastSeen: number | null } | null;
	cameras: { cameras: number; views: number; withImage: number } | null;
	calibrations: { current: number; latestId: number | null; latestAt: number | null } | null;
	/** Build dates (YYYY-MM-DD) from /tiles/manifest.json; null when the server can't read it. */
	tiles: { basemap: string | null; terrain: string | null; imagery: string | null; buildings: string | null } | null;
}
