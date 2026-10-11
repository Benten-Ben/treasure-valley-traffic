import type { DataMeta } from './meta.js';

/**
 * Toggled layers' vector tiles (landscape sprint plan C4, package S2):
 * `GET /api/<plugin>/tiles/<layer>/{z}/{x}/{y}?v=`, cut by PostGIS from the
 * definitions in `#lib/server/<plugin>/tiles.ts` (`#lib/server/mvt`).
 *
 * A layer's version is `versions.layers['<plugin>.<layer>']` in /api/meta:
 * the newest row of `core.layer_version`, which each build writes. With it as
 * `?v=` the tiles are immutable; without one (no build yet, or an old server)
 * they're served with a short cache.
 */

/** A plugin's or layer's name in the URL and in the version key: lower-case letters, digits and `_`. */
export const LAYER_NAME = /^[a-z][a-z0-9_]{0,39}$/;

/** The key of a layer's version in `versions.layers` and `core.layer_version`: `'<plugin>.<layer>'`. */
export function layerKey(plugin: string, layer: string): string {
	return `${plugin}.${layer}`;
}

/** The layer's current version from /api/meta, or null when it has none (or meta didn't answer). */
export function layerVersion(meta: Pick<DataMeta, 'versions'> | null | undefined, plugin: string, layer: string): string | null {
	return meta?.versions?.layers?.[layerKey(plugin, layer)] || null;
}

/**
 * The tile URL template for a MapLibre vector source, with the layer's
 * version as `?v=` when /api/meta has one. `origin` is `location.origin`
 * (MapLibre wants absolute tile URLs).
 */
export function layerTilesUrl(origin: string, plugin: string, layer: string, meta: Pick<DataMeta, 'versions'> | null | undefined): string {
	const url = `${origin}/api/${plugin}/tiles/${layer}/{z}/{x}/{y}`;
	const v = layerVersion(meta, plugin, layer);
	return v ? `${url}?v=${encodeURIComponent(v)}` : url;
}
