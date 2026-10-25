import { PRIORITY } from '../types.js';
import { SCENE_CAP, SCENE_CAP_PHONE } from './trees.js';

/**
 * The scene options of the trees group, exactly as production passes them to `scene.set`. The trees layer
 * hands the scene at most SCENE_CAP (the tallest in view), and the scene keeps the nearest SCENE_CAP of them
 * (SCENE_CAP_PHONE on a phone). Trees are not `scenery`: the scene reads the ground under every tree whenever
 * MapLibre's drawn ground changes.
 * The scene budget case (scene/test-scene.ts) imports this constant for its tree group, so it measures
 * production's trees and cannot drift from them.
 */
export const TREES_SCENE = { priority: PRIORITY.tree, cap: SCENE_CAP, capPhone: SCENE_CAP_PHONE } as const;
