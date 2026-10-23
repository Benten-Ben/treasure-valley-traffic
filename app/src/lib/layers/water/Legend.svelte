<script lang="ts">
	import { DASH, NHD_FINER, TONES } from '#lib/base/water/palette.js';
	import type { LegendProps } from '../types.js';
	import type { WaterModule } from './index.svelte.js';
	import { ageText, CREDITS, STRUCTURE_WORD } from './water.js';

	/**
	 * The Water legend (landscape sprint plan v3 §3.5, §4.2 P4-app): every kind by its form, never by colour
	 * alone: widths for kinds, dashes for flow and source, dots for piped water, and a shape for each badge.
	 * It says what is estimated, when the water network isn't baked yet, and where each fact comes from.
	 */
	let { module }: LegendProps = $props();
	const water = $derived(module as unknown as WaterModule);
	const t = $derived(TONES[water.flavor]);
	const points = $derived(water.points);
	const notices = $derived(water.notices);

	/** A sample line: width px, a dash (in widths), finer for NHD-only. */
	const rows = $derived([
		{ id: 'river', word: 'River or creek', note: 'the widest line', w: 3.4, nhd: false, dash: null as readonly number[] | null },
		{ id: 'canal', word: 'Canal', note: 'main canals from z10, named canals from z11', w: 2.4, nhd: false, dash: null },
		{ id: 'lateral', word: 'Lateral, drain or ditch', note: 'laterals and drains from z12, ditches from z13', w: 1.3, nhd: false, dash: null },
		{ id: 'intermittent', word: 'Dashes: dries up part of the year', note: 'intermittent', w: 1.6, nhd: false, dash: DASH.intermittent },
		{ id: 'nhd', word: 'Fine long dashes, lighter: the federal map only', note: 'USGS NHD has it, OpenStreetMap does not', w: 1.6 * NHD_FINER, nhd: true, dash: DASH.nhd },
		{ id: 'nhd-i', word: 'Fine short dashes, lighter: federal map only, and dries up', note: 'a desert wash', w: 1.6 * NHD_FINER, nhd: true, dash: DASH.nhdIntermittent },
		{ id: 'piped', word: 'Dots: piped (culvert or siphon)', note: 'from z16', w: 2.2, nhd: false, dash: DASH.piped }
	]);
	const dashed = (w: number, d: readonly number[] | null) => (d ? d.map((x) => Math.round(x * w * 10) / 10).join(' ') : undefined);

	const credits = $derived(
		water.bakedCredit.length ? water.bakedCredit : ['© OpenStreetMap contributors', 'U.S. Geological Survey, National Hydrography Dataset']
	);
</script>

<p class="legend-title">Water</p>
{#if !water.baked}
	<p class="note" role="status" data-not-baked>The water network isn’t baked into the map yet, so the basemap’s water and names show. Gauges, hazards and structures are on top.</p>
{/if}
<ul class="keys" aria-label="Lines">
	{#each rows as r (r.id)}
		<li>
			<svg viewBox="0 0 40 12" width="40" height="12" aria-hidden="true">
				<line x1="1" y1="6" x2="39" y2="6" stroke={r.nhd ? t.lineNhd : t.line} stroke-width={r.w} stroke-dasharray={dashed(r.w, r.dash)} />
			</svg>
			<span><b>{r.word}</b> <span class="how">({r.note})</span></span>
		</li>
	{/each}
	<li>
		<svg viewBox="0 0 40 12" width="40" height="12" aria-hidden="true">
			<rect x="3" y="1" width="34" height="10" rx="4" fill={t.fill} />
		</svg>
		<span><b>Lake, pond, reservoir</b> <span class="how">(a paler wash for wetlands, a dashed rim when it dries up)</span></span>
	</li>
</ul>
<p class="hint">True width from z15 (widths are estimates until measured). Lines never carry a dark edge, so they sit quietly under the streets.</p>
<ul class="shapes" aria-label="Badges">
	<li>
		<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
			<circle cx="10" cy="10" r="8" fill="#fffbf4" stroke="#2b2a33" stroke-width="1.5" />
			<path d="M7 5v10M7 7h2M7 10h2M7 13h2M4.5 11q2-2 4 0t4 0" fill="none" stroke="#2b2a33" stroke-width="1.2" stroke-linecap="round" />
		</svg>
		Gauge{#if points}<span class="num"> ({points.gauges.length})</span>{/if}
	</li>
	<li>
		<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
			<path d="M10 1.5 18.5 10 10 18.5 1.5 10Z" fill="#fffbf4" stroke="#2b2a33" stroke-width="1.5" stroke-linejoin="round" />
			<path d="M6 10h8" stroke="#2b2a33" stroke-width="2.4" stroke-linecap="round" />
		</svg>
		Dam, weir, gate, waterfall or spring{#if points}<span class="num"> ({points.structures.length})</span>{/if}
	</li>
	<li>
		<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
			<path d="M10 2 18 16.5H2Z" fill="#d9467a" stroke="#2b2a33" stroke-width="1.5" stroke-linejoin="round" />
			<path d="M10 7v5" stroke="#fffbf4" stroke-width="1.8" stroke-linecap="round" />
			<circle cx="10" cy="14.2" r="1" fill="#fffbf4" />
		</svg>
		River hazard{#if notices}<span class="num"> ({notices.hazards.length})</span>{/if}
	</li>
	<li>
		<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
			<rect x="2" y="2" width="16" height="16" rx="4.5" fill="#fffbf4" stroke="#2b2a33" stroke-width="1.5" />
			<path d="M10 5q4 4.5 4 7.2a4 4 0 0 1-8 0Q6 9.5 10 5Z" fill="#2b2a33" fill-opacity="0.25" stroke="#2b2a33" stroke-width="1.2" stroke-linejoin="round" />
		</svg>
		E. coli site{#if notices}<span class="num"> ({notices.ecoli.length})</span>{/if}
	</li>
</ul>
<p class="hint">Names are in italics. A gauge in flood has a magenta ring and a triangle, and its label names the category. Click any line, area or badge for its card.</p>
{#if water.noticesProblem}
	<p class="note" role="alert">▲ {water.noticesProblem}</p>
{/if}
{#if notices}
	<p class="hint">
		Hazards and E. coli results are the City of Boise’s, in its words; we make no swim call.
		{#if notices.polled.boise_river_hazards}Hazards checked {ageText(notices.polled.boise_river_hazards)}.{/if}
		{#if notices.polled.boise_ecoli}E. coli results checked {ageText(notices.polled.boise_ecoli)}.{/if}
	</p>
{/if}
<p class="credit">{credits.join(' · ')} · {CREDITS.nwps}; {STRUCTURE_WORD.gauge.toLowerCase()} observations courtesy of USGS where NWPS names a USGS site · {CREDITS.boiseHazards}; {CREDITS.boiseEcoli}</p>

<style>
	li {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
	}
	svg {
		flex: none;
	}
	.how {
		color: var(--ink-soft);
	}
	.shapes {
		display: flex;
		flex-direction: column;
		gap: 4px;
		margin: 6px 0 0;
		padding: 0;
		list-style: none;
	}
	.note {
		margin: 6px 0 0;
		font-size: 12px;
		color: var(--ink);
	}
</style>
