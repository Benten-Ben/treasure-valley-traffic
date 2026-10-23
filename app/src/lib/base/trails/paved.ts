/**
 * The paved-path base contribution's names, shared by it (`paved-paths.base.ts`) and the Trails layer (whose
 * module makes these layers clickable while it is on). Plain constants: this file imports nothing.
 */
export const PAVED_ID = 'trails.paved_paths';
/** The source-layers of the landscape file (basemap/landscape; `trails-export` writes them). */
export const PAVED_SOURCE_LAYERS = { paths: 'trails.paved_paths', areas: 'trails.paved_areas' } as const;
/** The style layers. */
export const PAVED_LAYER = { areas: 'trails.paved_paths.areas', treads: 'trails.paved_paths.treads' } as const;
/** The first zoom the treads show at (plan C9: z15.5; the export bakes them from z15). */
export const PAVED_FROM_ZOOM = 15.5;
/** The slot rank: path treads between the baked paving (10) and the road surfaces (20). */
export const PAVED_RANK = 15;

/** Metres per pixel at the latitude of the valley (43.6 N) at zoom z, for 512 px tiles: what a width in metres is on the screen. */
export const metresPerPx = (z: number): number => (40_075_016.686 * Math.cos((43.6 * Math.PI) / 180)) / (512 * 2 ** z);
