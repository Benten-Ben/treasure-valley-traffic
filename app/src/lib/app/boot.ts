import { browser } from '$app/env';
import { prewarm, setWorkerCount } from 'maplibre-gl';
import type { DataMeta, DataVersions } from '#lib/contracts/meta.js';
import { setupMapLibre } from '#lib/map/create.js';
import { loadManifest, setHillshadeMode, type ManifestResult } from '#lib/map/style.js';
import { DEFAULT_FLAGS, parsePerfFlags, type PerfFlags } from '#lib/perf/flags.js';
import { MARK, mark } from '#lib/perf/marks.js';

/**
 * The boot (docs/14 §14.8, "Boot"). This module runs at module scope, before
 * the map exists:
 *
 * - it fetches `/tiles/manifest.json` and `/api/meta`, both preloaded from
 *   app.html, so they're already in flight while the JavaScript parses;
 * - it starts MapLibre's workers (`prewarm()`).
 *
 * Each enabled layer's data fetch starts the moment `/api/meta` resolves,
 * with the matching version as `?v=` (`dataUrl`), so data never waits for
 * the map's `load`.
 *
 * The performance flags (`#lib/perf/flags`, docs/14 §14.9) are read here,
 * once: the hillshade's source (`?hillshade=`) before any map is built, the
 * worker count (`?workers=`) before the workers start, and the `?perf` HUD
 * and `?lod=` terrain parameters, whose code loads only when asked for.
 */

if (browser) mark(MARK.boot);

const never = <T>() => new Promise<T>(() => {});

/** The performance flags in the page's URL (defaults outside the browser). */
export const flags: PerfFlags = browser ? parsePerfFlags(location.search) : DEFAULT_FLAGS;

/**
 * The `?perf` HUD and `?lod=` hook, when asked for. The HUD counts WebGL
 * textures from the first one, so the map waits for it (only then).
 */
const perfTools: Promise<unknown> =
	browser && (flags.hud || flags.lod)
		? import('#lib/perf/hud.js').then((h) => h.startPerfTools(flags)).catch((e) => console.error('perf tools failed to start', e))
		: Promise.resolve();

/** The basemap manifest, fetched once per visit. */
export const manifest: Promise<ManifestResult> = browser
	? Promise.all([loadManifest(), perfTools]).then(([r]) => {
			mark(MARK.manifest);
			return r;
		})
	: never();

/** Data versions from /api/meta; null when it didn't answer (layers then load unversioned). */
export const meta: Promise<DataMeta | null> = browser
	? fetch('/api/meta')
			.then((r) => (r.ok ? (r.json() as Promise<DataMeta>) : null))
			.catch(() => null)
	: never();

if (browser) {
	setHillshadeMode(flags.hillshade);
	setupMapLibre();
	if (flags.workers) setWorkerCount(flags.workers);
	prewarm();
}

/** `path?v=<version>` once /api/meta has answered; the plain path when it has no version. */
export async function dataUrl(path: string, version?: keyof DataVersions): Promise<string> {
	const m = await meta;
	const v = version ? m?.versions?.[version] : null;
	return v ? `${path}${path.includes('?') ? '&' : '?'}v=${encodeURIComponent(v)}` : path;
}
