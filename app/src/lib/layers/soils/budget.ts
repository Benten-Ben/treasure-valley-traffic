/**
 * The Soils layer's tile budget (owner, Oct 22, decision on #32 Q1) and what was measured against it.
 *
 * The budget, per layer: the busiest tile of any zoom band at most 150 KB gzip, and the layer's first toggle at
 * the default view at most 1 MB gzip. A layer over either stops and is reported: simplifying the data
 * (`SIMPLIFY_Z8_M`, plugins/soils/ingest/load.py) is a data change for its own issue.
 *
 * **z8 was over, so the wash starts at z9** (a tiling choice inside the app, as for the crop fields): the busiest
 * z8 tile with every map unit in it was 250,560 B gzip (337,066 raw, 8/45/93; plugins/soils/README.md measured
 * 319 KB raw for the geometry alone), so z8 tiles carry the survey bounds only (`WASH_FROM` in `./tiles.ts` and
 * the server's `tiles.ts`). Everything else is under: z9 at 140,571 and z10 at 140,891 are the busiest, 6 to 7%
 * short of the bar, so a SSURGO refresh that adds map units near Boise and Nampa may need the same treatment
 * (start the wash at z10, or a coarser `geom_z8`): re-measure after each October refresh.
 *
 * The numbers are the real tiles of the scratch database's soils build `20261011T1228Z-3dc4b3` (1,038 map
 * units, 21,999 polygons), cut by the SQL `#lib/server/soils/tiles.ts` makes and gzipped at level 9, as the tile
 * server does (Oct 23, 2026). Candidate tiles were every tile over the polygons' extent; the busiest by raw size
 * is the one listed.
 */
export const BUDGET = {
	/** The busiest tile of any zoom band, gzip. */
	busiestTileBytes: 150_000,
	/** All the tiles the first toggle fetches at the default view, gzip. */
	firstToggleBytes: 1_000_000
} as const;

export interface BandMeasure {
	band: string;
	/** The busiest tile: `z/x/y`. */
	tile: string;
	raw: number;
	gzip: number;
}

/** The busiest tile of each zoom (what the server serves: survey only at z8, then the wash, then polygons and labels). */
export const BANDS: readonly BandMeasure[] = [
	{ band: 'z8 (survey bounds)', tile: '8/44/93', raw: 11_479, gzip: 7_361 },
	{ band: 'z9', tile: '9/90/187', raw: 172_724, gzip: 140_571 },
	{ band: 'z10', tile: '10/180/373', raw: 172_634, gzip: 140_891 },
	{ band: 'z11', tile: '11/360/746', raw: 71_896, gzip: 62_362 },
	{ band: 'z12', tile: '12/720/1492', raw: 59_640, gzip: 44_290 },
	{ band: 'z13', tile: '13/1445/2984', raw: 21_131, gzip: 15_754 },
	{ band: 'z14 (polygons and labels)', tile: '14/2889/5967', raw: 16_398, gzip: 12_715 }
];

/** What z8 would have cost with the wash in it (not served): over the budget, which is why it isn't. */
export const Z8_WITH_WASH: BandMeasure = { band: 'z8 with the wash (not served)', tile: '8/45/93', raw: 337_066, gzip: 250_560 };

/**
 * The first toggle at the default view (the manifest's centre -116.4, 43.6, z10, pitch 45; defaultView() in
 * `#lib/state/view.svelte.ts`): the 25 z10 tiles around the centre tile 10/180/373 (an upper bound on what a
 * 1280 x 800 view asks for), all non-empty, and the 9 nearest to it. Gzip bytes. (At pitch, distant tiles may
 * load a zoom lower: the z9 tiles are a little smaller each, so this stays an upper bound.)
 */
export const FIRST_TOGGLE = { tiles: 25, raw: 1_156_480, gzip: 942_082, nearest9: { tiles: 9, gzip: 727_713 } } as const;

/** What is over the budget, in words (empty when nothing is). */
export function overBudget(bands: readonly Pick<BandMeasure, 'band' | 'gzip'>[] = BANDS, first: number = FIRST_TOGGLE.gzip): string[] {
	const out: string[] = [];
	for (const b of bands) if (b.gzip > BUDGET.busiestTileBytes) out.push(`${b.band}: busiest tile ${b.gzip} B gzip is over ${BUDGET.busiestTileBytes}`);
	if (first > BUDGET.firstToggleBytes) out.push(`first toggle ${first} B gzip is over ${BUDGET.firstToggleBytes}`);
	return out;
}
