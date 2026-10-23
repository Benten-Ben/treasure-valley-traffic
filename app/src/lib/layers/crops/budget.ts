/**
 * The Crop fields layer's tile budget (owner, Oct 22, decision on #32 Q1) and what was measured against it.
 *
 * The budget, per layer: the busiest tile of any zoom band at most 150 KB gzip, and the layer's first toggle at
 * the default view at most 1 MB gzip. A layer over either stops and is reported: simplifying the data is a
 * data change for its own issue. (The coordinator's rule for this layer: if z11 had been over, per-field tiles
 * would start at z12 with z10's dissolves overzoomed, a tiling choice inside the app. It is not over.)
 *
 * The numbers are the real tiles of the scratch database's build `20261011T1306Z-1d7b99` (21,460 fields),
 * cut by the SQL `#lib/server/farm/tiles.ts` makes and gzipped at level 9, as the tile server does (Oct 23, 2026).
 * Re-measure when a new CSB edition is loaded: the fields grow with it.
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

/** The busiest tile of each band of the fields layer (raw MVT and gzip bytes). */
export const FIELDS_BANDS: readonly BandMeasure[] = [
	{ band: 'z8', tile: '8/45/93', raw: 41_404, gzip: 31_143 },
	{ band: 'z9', tile: '9/89/186', raw: 44_926, gzip: 35_556 },
	{ band: 'z10', tile: '10/179/373', raw: 74_287, gzip: 60_403 },
	{ band: 'z11', tile: '11/359/747', raw: 194_077, gzip: 106_699 },
	{ band: 'z12', tile: '12/719/1495', raw: 57_160, gzip: 33_219 },
	{ band: 'z13', tile: '13/1442/2994', raw: 18_481, gzip: 10_839 },
	{ band: 'z14', tile: '14/2884/5989', raw: 6_511, gzip: 3_959 }
];

/** The busiest z10 tile of each earlier year's dissolves (the year switcher's cuts), gzip, and how long its cut took. */
export const YEAR_CUTS: readonly { year: number; tile: string; raw: number; gzip: number }[] = [
	{ year: 2018, tile: '10/179/373', raw: 80_581, gzip: 65_368 },
	{ year: 2019, tile: '10/179/373', raw: 79_159, gzip: 64_285 },
	{ year: 2020, tile: '10/179/373', raw: 79_266, gzip: 64_321 },
	{ year: 2021, tile: '10/179/373', raw: 79_225, gzip: 64_241 },
	{ year: 2022, tile: '10/179/373', raw: 79_762, gzip: 64_735 },
	{ year: 2023, tile: '10/179/373', raw: 77_361, gzip: 62_712 },
	{ year: 2024, tile: '10/179/373', raw: 79_136, gzip: 64_180 }
];

/** Database time to cut a year's tile (EXPLAIN ANALYZE, scratch, two runs each): the busiest z10 tile, ms; the 3 s statement timeout is far off. */
export const YEAR_CUT_MS = { z8: [54, 84], z9: [73, 83], z10: [129, 143] } as const;

/**
 * The first toggle at the default view (the manifest's centre, z10, pitch 45): the 25 z10 tiles around the
 * centre tile 10/180/373 (an upper bound on what the view asks for), of which 15 are not empty. Gzip bytes.
 */
export const FIRST_TOGGLE = { tiles: 25, nonEmpty: 15, raw: 236_548, gzip: 191_840 } as const;

/** What is over the budget, in words (empty when nothing is). */
export function overBudget(
	bands: readonly Pick<BandMeasure, 'band' | 'gzip'>[] = FIELDS_BANDS,
	years: readonly { year: number; gzip: number }[] = YEAR_CUTS,
	first: number = FIRST_TOGGLE.gzip
): string[] {
	const out: string[] = [];
	for (const b of bands) if (b.gzip > BUDGET.busiestTileBytes) out.push(`${b.band}: busiest tile ${b.gzip} B gzip is over ${BUDGET.busiestTileBytes}`);
	for (const y of years) if (y.gzip > BUDGET.busiestTileBytes) out.push(`${y.year}: busiest tile ${y.gzip} B gzip is over ${BUDGET.busiestTileBytes}`);
	if (first > BUDGET.firstToggleBytes) out.push(`first toggle ${first} B gzip is over ${BUDGET.firstToggleBytes}`);
	return out;
}
