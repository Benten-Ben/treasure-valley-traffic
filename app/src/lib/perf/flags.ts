/**
 * Performance flags (docs/14 §14.9, fixes 1 and 8; "How we measure"), read
 * once from the page's query string by the boot (`#lib/app/boot`):
 *
 * - `?hillshade=terrain|capped`: where the hillshade gets its elevations.
 *   `terrain` (the default, owner's Q7 answer) draws it from the 3D terrain's
 *   own source, so each DEM tile downloads once; `capped` keeps a second
 *   source for it, capped at `HILLSHADE_CAP_ZOOM`, for the side-by-side check.
 * - `?workers=N`: MapLibre's worker count (1–8), for A/B runs. MapLibre's
 *   own default in Chrome is 1.
 * - `?lod=M,R`: `map.setSourceTileLodParams(M, R)` on the terrain source
 *   (fewer, coarser DEM tiles toward the horizon at high pitch). MapLibre's
 *   defaults are 9.314 and 3.
 * - `?perf`: the HUD (fps, heap, tiles, bytes, setData calls, textures).
 *
 * Anything unrecognised reads as the default, so a typo never breaks the map.
 */

export type HillshadeMode = 'terrain' | 'capped';

export const HILLSHADE_MODES: readonly HillshadeMode[] = ['terrain', 'capped'];

/** The default until the owner decides otherwise from the screenshots (Q7). */
export const DEFAULT_HILLSHADE: HillshadeMode = 'terrain';

export interface PerfFlags {
	hillshade: HillshadeMode;
	/** MapLibre's worker count, or null for its default. */
	workers: number | null;
	/** Terrain tile LOD parameters [maxZoomLevelsOnScreen, tileCountMaxMinRatio], or null for MapLibre's. */
	lod: [number, number] | null;
	/** Show the `?perf` HUD. */
	hud: boolean;
}

export const DEFAULT_FLAGS: Readonly<PerfFlags> = Object.freeze({ hillshade: DEFAULT_HILLSHADE, workers: null, lod: null, hud: false });

const MAX_WORKERS = 8;

function parseLod(v: string | null): [number, number] | null {
	if (!v) return null;
	const parts = v.split(',').map((s) => Number(s.trim()));
	if (parts.length !== 2 || !parts.every((n) => Number.isFinite(n) && n >= 1 && n <= 32)) return null;
	return [parts[0], parts[1]];
}

/** The flags in a query string (`location.search`, with or without the `?`). */
export function parsePerfFlags(search: string | URLSearchParams): PerfFlags {
	const q = typeof search === 'string' ? new URLSearchParams(search) : search;
	const hs = q.get('hillshade');
	const w = Number(q.get('workers'));
	return {
		hillshade: (HILLSHADE_MODES as readonly string[]).includes(hs ?? '') ? (hs as HillshadeMode) : DEFAULT_HILLSHADE,
		workers: q.has('workers') && Number.isInteger(w) && w >= 1 && w <= MAX_WORKERS ? w : null,
		lod: parseLod(q.get('lod')),
		hud: q.has('perf') && q.get('perf') !== '0'
	};
}
