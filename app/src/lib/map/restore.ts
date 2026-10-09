import type { Map } from 'maplibre-gl';

/**
 * Build the terrain afresh after a WebGL context restore (a MapLibre 6.12.0
 * workaround, docs/14 §14.8 "Robustness"). On restore MapLibre reloads its
 * style, and the new terrain replaces the old one; the old one's tiles hand
 * their render-to-texture drapes, made on the dead context, back to the new
 * painter's pool, and the new terrain draws with them: the ground comes back
 * as whatever texture is bound (the glyph atlas). Turning terrain off empties
 * that pool; on again builds new drapes and reloads the DEM tiles.
 */
export function redrapeTerrain(map: Pick<Map, 'getTerrain' | 'setTerrain'>): void {
	const t = map.getTerrain();
	if (!t) return;
	map.setTerrain(null);
	map.setTerrain({ ...t });
}
