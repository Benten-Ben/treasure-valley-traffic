import { layerCredit, layerTilesUrl, layerVersion } from '#lib/contracts/layer-tiles.js';
import type { DataMeta } from '#lib/contracts/meta.js';

/**
 * The Soils layer's tile URL and zooms (the server side is `#lib/server/soils/tiles.ts`; a test checks this
 * file's numbers against it). The layer carries the soils build's version and credit.
 */
export const PLUGIN = 'soils';
export const LAYER = 'units';
/** The MVT layers in every tile (a style's `source-layer`). */
export const MVT_UNITS = 'soils';
export const MVT_SURVEY = 'survey';
export const MVT_LABELS = 'soil_labels';
/** The tiles' zooms: the source stops at z14 and overzooms. */
export const MIN_ZOOM = 8;
export const MAX_ZOOM = 14;
/** The wash comes in here (z8 tiles carry the survey bounds only); the survey bounds stop below SURVEY_TO. */
export const WASH_FROM = 9;
export const SURVEY_TO = 12;
/** Outlines from here; symbols from the top zoom; names from z16. */
export const OUTLINE_FROM = 12;
export const SYMBOLS_FROM = 14;
export const NAMES_FROM = 16;

type Meta = Pick<DataMeta, 'versions' | 'layers'> | null | undefined;

/** The tiles' URL template, with the layer's version as `?v=`. */
export const unitsUrl = (origin: string, meta: Meta): string => layerTilesUrl(origin, PLUGIN, LAYER, meta);

/** The credit the soils build recorded. */
export const unitsCredit = (meta: Meta): string | null => layerCredit(meta, PLUGIN, LAYER);

/** Whether the soils build has recorded a version (the layer is offered then). */
export const built = (meta: Meta): boolean => !!layerVersion(meta, PLUGIN, LAYER);
