import type { TileLayerDef } from '#lib/server/mvt.js';

/**
 * The burn scars the map draws (landscape sprint plan C15, package P13; the ground's overlay in
 * `#lib/base/hazards/burn-scars.base.ts`). Read from the view `hazards.burn_scar_shown` (migration
 * 0001): the simplified outlines (`geom_lo`) at z8–12, the full ones from z13, and z14 overzooms
 * the last band. The version is `hazards.burn_scars` in core.layer_version (written by the build).
 */
const COLUMNS = ['fire_id', 'kind', 'burned_on', 'seasons', 'fade'] as const;

const burnScars: TileLayerDef = {
	plugin: 'hazards',
	layer: 'burn_scars',
	minzoom: 8,
	maxzoom: 14,
	parts: [
		{
			name: 'scars',
			sources: [
				{ minzoom: 8, maxzoom: 12, table: 'hazards.burn_scar_shown', geom: 'geom_lo', columns: COLUMNS },
				{ minzoom: 13, maxzoom: 14, table: 'hazards.burn_scar_shown', geom: 'geom', columns: COLUMNS }
			]
		}
	]
};

export default burnScars;
