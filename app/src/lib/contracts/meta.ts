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
	/**
	 * Toggled layers' tile versions, `'<plugin>.<layer>'` → version: each
	 * layer's newest row in `core.layer_version` (migration 0020), for
	 * `/api/<plugin>/tiles/<layer>/{z}/{x}/{y}?v=` (#lib/contracts/layer-tiles).
	 * A layer with no build yet isn't listed (and serves no tiles). Optional
	 * (added in the landscape sprint, so the contract stays 1): absent from
	 * older servers, empty before migration 0020 or without the database.
	 */
	layers?: Record<string, string>;
}

/** What a toggled layer's current build recorded beside its version (core.layer_version; plan C3). */
export interface LayerBuild {
	/** When the build wrote its row (epoch s). */
	builtAt: number;
	/** Licence class: the strictest of the build's inputs ('ODbL', 'public domain', ...). */
	license: string;
	/** Whether its tiles may be republished, in the plugin manifests' terms (docs/15 §15.2). */
	republish: 'yes' | 'aggregates' | 'internal' | 'no';
	/** The credit to show while the layer is on: its source's MapLibre `attribution`. */
	credit: string;
}

/**
 * A scheduled source against its schedule (ops.source_status, migration
 * 0021), in docs/14's words: ● fresh, ▲ late, ■ stale, ◌ never (no good
 * fetch yet). Fresh is a last good fetch less than a schedule plus a grace
 * old (a quarter of the schedule, at least 15 min); late is up to two more
 * schedules past that; stale is later still.
 */
export type SourceState = 'fresh' | 'late' | 'stale' | 'never';

/**
 * A build (ops.build_status), by its newest run first: `running`; `failed`
 * (its newest run failed, or was killed before it could say so; it may still
 * be marked: `pendingSince`); `pending` (a source marked it out of date and no
 * run has covered that yet); `built`. Builds run by hand, never inside the
 * scheduled collector loop.
 */
export type BuildState = 'built' | 'pending' | 'running' | 'failed';

export interface SourceStatus {
	/** The source's name (ops.source.name), e.g. 'awc_metar'. */
	source: string;
	state: SourceState;
	/** Its last good fetch (epoch s); null: none yet. */
	lastOkAt: number | null;
	/** Its schedule (s); for a stream, its stale_after (s), the longest age that still reads fresh. */
	everyS: number;
	/** Finished attempts that failed since its last good fetch (0: its newest attempt was good). */
	failures: number;
}

export interface BuildStatus {
	/** The build's name: the command that runs it, e.g. 'roads-build', 'landscape-bake'. */
	build: string;
	state: BuildState;
	/** When its last good run finished (epoch s); null: never built. */
	lastOkAt: number | null;
	/** Its oldest mark no run has covered (epoch s); null: not marked. A failed build can be marked too. */
	pendingSince: number | null;
	/** When its newest run started (epoch s); null: never run. For a running build, how long it has gone. */
	lastRunAt: number | null;
}

/**
 * Scheduled work at a glance, for a status chip (landscape sprint, M1): the
 * scheduled sources by state, the ones that need a look, and every build.
 * Names only: no error text or reasons (`bin/status` on the server has those).
 */
export interface DataStatus {
	/** Scheduled sources by state; `failing`: those whose newest finished attempt failed, whatever their state. */
	sources: Record<SourceState, number> & { failing: number };
	/** The sources that aren't fresh or are failing, worst first (stale, never, late, then failing; oldest first), at most 20. */
	attention: SourceStatus[];
	/** Builds that have run or are marked: failed, running, pending (oldest mark first), then built; at most 40. */
	builds: BuildStatus[];
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
	tiles: {
		basemap: string | null;
		terrain: string | null;
		imagery: string | null;
		buildings: string | null;
		/** The landscape base file's build date; null when it is `empty` or not built. Optional: absent from older servers (the contract stays 1). */
		landscape?: string | null;
		/** The painted ground's build date; null when it is `flat` or not built. Optional, like `landscape`. */
		ground?: string | null;
	} | null;
	/**
	 * Toggled layers' current builds, by `'<plugin>.<layer>'` as in
	 * `versions.layers`: their credit, licence and `republish`, so the credit
	 * a layer shows is the one its build recorded. Optional, like
	 * `versions.layers` (the contract stays 1).
	 */
	layers?: Record<string, LayerBuild>;
	/**
	 * Scheduled sources' freshness and builds' states (migration 0021), for a
	 * status chip (`#lib/status/summary`). null before migration 0021, without
	 * the database, or when the views didn't answer. Optional (added in the
	 * landscape sprint, so the contract stays 1): absent from older servers.
	 */
	status?: DataStatus | null;
}
