import { PRIORITY } from '../types.js';

/**
 * The scene options of the trees group, exactly as production passes them to `scene.set`. The trees layer
 * caps the list itself (SCENE_CAP, the tallest in view), so the scene gets no `cap` or `capPhone`, and trees
 * are not `scenery`: the scene reads the ground under every tree whenever MapLibre's drawn ground changes.
 * The scene budget case (scene/test-scene.ts) imports this constant for its tree group, so it measures
 * production's trees and cannot drift from them.
 */
export const TREES_SCENE = { priority: PRIORITY.tree } as const;
