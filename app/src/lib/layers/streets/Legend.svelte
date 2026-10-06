<script lang="ts">
	import type { LegendProps } from '../types.js';
	import type { StreetsModule } from './index.svelte.js';
	import { LEGEND_TICKS, legendGradient, legendPosition } from './ramp.js';

	/**
	 * The Streets legend (docs/14 §14.5): the ramp that's drawn as a 160 × 10 px
	 * bar of its 11 shades, ticks at 20, 25, 35, 45, 55, 65 and 75 mph, and
	 * what width and the arrows mean. Under Transit it shows the slate ramp
	 * and says it's dimmed, with speeds approximate.
	 */
	let { module }: LegendProps = $props();
	const ramp = $derived((module as Partial<StreetsModule>).ramp ?? 'alone');
</script>

<p class="legend-title">Posted speed <span class="unit">mph</span></p>
{#if ramp === 'under'}
	<p class="dimmed" data-ramp="under">Dimmed while Transit is on; speeds approximate</p>
{/if}
<div class="ramp" role="img" aria-label="Posted speed, light at 20 mph and under to dark at 75 mph{ramp === 'under' ? ', dimmed' : ''}" data-ramp={ramp}>
	<div class="bar" style:background={legendGradient(ramp)}></div>
	<div class="ticks" aria-hidden="true">
		{#each LEGEND_TICKS as t, i (t)}
			<span class="tick" class:first={i === 0} class:second={i === 1} style:left="{(legendPosition(t) * 100).toFixed(2)}%">{t}</span>
		{/each}
	</div>
</div>
<ul class="notes">
	<li>≤ 20 includes local streets, where 20 is likely a default</li>
	<li>Width = road class</li>
	<li><b class="arrows" aria-hidden="true">››</b> = one-way</li>
</ul>
<p class="credit">Ada County: ACHD road centerlines. Canyon County isn't covered yet. The card gives each road's exact speed.</p>

<style>
	.unit {
		font: 500 12px var(--font-body);
		color: var(--ink-soft);
	}
	.dimmed {
		margin: 0 0 6px;
		font-size: 12px;
		color: var(--ink);
	}
	.ramp {
		position: relative;
		width: 160px;
		margin: 4px 0 2px;
	}
	.bar {
		width: 160px;
		height: 10px;
		border-radius: 3px;
		box-shadow: inset 0 0 0 1px rgb(43 42 51 / 0.12);
	}
	.ticks {
		position: relative;
		height: 18px;
	}
	.tick {
		position: absolute;
		top: 0;
		padding-top: 4px;
		transform: translateX(-50%);
		font: 500 10px var(--font-mono);
		color: var(--ink-soft);
	}
	.tick::before {
		content: '';
		position: absolute;
		top: 0;
		left: 50%;
		width: 1px;
		height: 3px;
		background: var(--ink-soft);
	}
	/* 20 and 25 are only 13 px apart: "20" starts at the bar's start and "25" leans right. */
	.tick.first {
		transform: translateX(-6.67px);
	}
	.tick.first::before {
		left: 6.67px;
	}
	.tick.second {
		transform: translateX(-30%);
	}
	.tick.second::before {
		left: 30%;
	}
	.notes {
		margin: 4px 0 0;
		padding: 0;
		list-style: none;
		font-size: 12px;
		color: var(--ink-soft);
	}
	.notes li + li {
		margin-top: 2px;
	}
	.arrows {
		color: var(--ink);
	}
</style>
