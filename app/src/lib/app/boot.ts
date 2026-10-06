import { browser } from '$app/env';
import { prewarm } from 'maplibre-gl';
import type { DataMeta, DataVersions } from '#lib/contracts/meta.js';
import { setupMapLibre } from '#lib/map/create.js';
import { loadManifest, type ManifestResult } from '#lib/map/style.js';

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
 */

if (browser) performance.mark('tvt:boot');

const never = <T>() => new Promise<T>(() => {});

/** The basemap manifest, fetched once per visit. */
export const manifest: Promise<ManifestResult> = browser
	? loadManifest().then((r) => {
			performance.mark('tvt:manifest');
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
	setupMapLibre();
	prewarm();
}

/** `path?v=<version>` once /api/meta has answered; the plain path when it has no version. */
export async function dataUrl(path: string, version?: keyof DataVersions): Promise<string> {
	const m = await meta;
	const v = version ? m?.versions?.[version] : null;
	return v ? `${path}${path.includes('?') ? '&' : '?'}v=${encodeURIComponent(v)}` : path;
}
