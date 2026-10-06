/**
 * The always-loaded 2D overlay (docs/14 §14.8). WP8 (bus discs and plates),
 * WP10 (plates over the 3D models) and WP12 (window badges) draw through it.
 */
export { Overlay, type GroupOptions, type OverlayInstance, type UpdateFn } from './overlay.svelte.js';
export { arrowSprite, contrast, discSprite, haloFor, needsHalo, ringSprite, type DiscOptions } from './sprites.js';
export type { SpriteDef } from '#lib/gl/atlas.js';
