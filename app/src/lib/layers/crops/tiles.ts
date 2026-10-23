import { layerCredit, layerTilesUrl, layerVersion } from '#lib/contracts/layer-tiles.js';
import type { DataMeta } from '#lib/contracts/meta.js';

/**
 * The crop fields' tile URLs (the server side is `#lib/server/farm/tiles.ts`; a test checks this file's
 * numbers against it). The fields layer carries the build's version and credit; the year switcher's
 * earlier-year layers (`crop_year_<year>`, z8-10) take the same ones (`versionOf` on the server), so their
 * URL is made with the shared key.
 */
export const PLUGIN = 'farm';
export const FIELDS_LAYER = 'crop_fields';
/** The MVT layer in every tile (a style's `source-layer`). */
export const MVT_LAYER = 'fields';
/** Where per-field tiles start; below it the tiles are dissolves. */
export const FIELDS_FROM = 11;
/** The fields tiles' zooms: the source stops at z14 and overzooms. */
export const MIN_ZOOM = 8;
export const MAX_ZOOM = 14;
/** The earlier years' cuts stop at z10. */
export const YEAR_MAX_ZOOM = 10;
/** The earlier years that have a cut of their own. */
export const CUT_YEARS: readonly number[] = [2018, 2019, 2020, 2021, 2022, 2023, 2024];

export const yearLayer = (year: number): string => `crop_year_${year}`;

type Meta = Pick<DataMeta, 'versions' | 'layers'> | null | undefined;

/** The fields tiles' URL template, with the layer's version as `?v=`. */
export function fieldsUrl(origin: string, meta: Meta): string {
	return layerTilesUrl(origin, PLUGIN, FIELDS_LAYER, meta);
}

/** An earlier year's tiles, versioned by the fields layer's build. */
export function yearUrl(origin: string, meta: Meta, year: number): string {
	const v = layerVersion(meta, PLUGIN, FIELDS_LAYER);
	const shared = { versions: { layers: v ? { [`${PLUGIN}.${yearLayer(year)}`]: v } : {} } } as Pick<DataMeta, 'versions'>;
	return layerTilesUrl(origin, PLUGIN, yearLayer(year), shared);
}

/** The credit the fields layer's build recorded (the earlier years share it). */
export const fieldsCredit = (meta: Meta): string | null => layerCredit(meta, PLUGIN, FIELDS_LAYER);

/** Whether an earlier year has a z8-10 cut. */
export const hasCut = (year: number): boolean => CUT_YEARS.includes(year);
