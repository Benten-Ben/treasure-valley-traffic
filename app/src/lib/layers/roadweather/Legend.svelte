<script lang="ts">
	import type { LegendProps } from '../types.js';
	import { partTransform, ROAD_WEATHER_ICON } from './icons.js';
	import type { RoadWeatherModule } from './index.svelte.js';
	import { CREAM, INK, INK_SOFT } from './layers.js';
	import { summarize } from './model.js';

	/**
	 * The Road weather legend (docs/14 §14.6 "Road weather"): both badges as
	 * the map draws them, with counts; how many stations are loaded and how
	 * many are inside the map; and how to open one. No data hue: there are no
	 * road-sensor readings on the map yet, only the pictures.
	 */
	let { module }: LegendProps = $props();
	const rw = $derived(module as unknown as RoadWeatherModule);
	const drawn = $derived(summarize(rw.drawn));
	const loaded = $derived(rw.data?.stations.length ?? 0);
	const outside = $derived(loaded - drawn.stations);
</script>

{#snippet badge(hollow: boolean)}
	<svg viewBox="0 0 26 26" width="22" height="22" aria-hidden="true">
		{#if hollow}
			<rect x="2" y="2" width="22" height="22" rx="7" fill="none" stroke={CREAM} stroke-width="4" />
			<rect x="2" y="2" width="22" height="22" rx="7" fill="none" stroke={INK} stroke-width="2" stroke-dasharray="3.2 2.2" />
		{:else}
			<rect x="2" y="2" width="22" height="22" rx="7" fill={CREAM} stroke={INK} stroke-width="2" />
		{/if}
		<g transform="translate(4 4) scale(0.0703)" fill={hollow ? INK_SOFT : INK}>
			{#each ROAD_WEATHER_ICON as p (p.icon.name)}
				<g transform={partTransform(p)}>{#if !hollow}<path d={p.icon.tone} opacity="0.2" />{/if}<path d={p.icon.line} /></g>
			{/each}
		</g>
	</svg>
{/snippet}

<p class="legend-title">Road weather</p>
{#if rw.data?.note}
	<p class="hint"><span aria-hidden="true">▲</span> {rw.data.note}</p>
{:else if loaded === 0}
	<p class="hint">No road-weather stations are loaded yet: they come from 511's camera list, loaded by hand.</p>
{:else}
	<ul class="keys">
		<li>{@render badge(false)} Station with pictures <span class="num">({drawn.stations - drawn.hollow})</span></li>
		<li>{@render badge(true)} No live feed on any view <span class="num">({drawn.hollow})</span></li>
	</ul>
	<p class="hint">
		<span class="num">{drawn.stations}</span> of <span class="num">{loaded}</span> stations are inside the map{#if outside > 0}; the
			other {outside} wait for a larger map area{/if}. Pictures only: no road-sensor readings yet.
	</p>
	{#if !rw.data?.images}
		<p class="hint"><span aria-hidden="true">■</span> Live camera images are off, so picture ages aren't known.</p>
	{/if}
	<p class="hint">Click a station for its cameras, one tab per direction.</p>
{/if}
<p class="credit">ITD 511 road weather (RWIS) · Oregon DOT</p>

<style>
	li {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	svg {
		flex: none;
	}
	.hint {
		margin: 6px 0 0;
		color: var(--ink-soft);
		font-size: 12px;
	}
</style>
