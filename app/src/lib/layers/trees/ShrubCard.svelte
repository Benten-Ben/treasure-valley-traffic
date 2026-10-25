<script lang="ts">
	import type { CardProps } from '../types.js';
	import { LOOK_ABOUT, LOOK_NAME, SHRUB_COLORS, SHRUB_CREDIT, SHRUB_EDGE, shrubHowWeKnow, type ShrubRow } from './shrubs.js';
	import { metresFeet } from './trees.js';

	/**
	 * The shrub card (docs/19 §19.8): the look in words, its height (measured by the lidar), its width (from the
	 * test areas' model, not measured), how we know and the credits. Everything is in the click's own row: no fetch.
	 */
	let { selection }: CardProps = $props();
	const row = $derived(selection.data as ShrubRow);
</script>

<h2>{LOOK_NAME[row.look]}</h2>
<p class="meta kind-line">
	<svg viewBox="0 0 14 14" width="13" height="13" aria-hidden="true">
		<circle cx="7" cy="7" r="5.5" fill={SHRUB_COLORS[row.look]} stroke={SHRUB_EDGE} stroke-width="1" />
	</svg>
	<span><b>Shrub</b> · found in the lidar</span>
</p>
<p class="explain">{LOOK_NAME[row.look]}: {LOOK_ABOUT[row.look]}.</p>
<dl class="facts">
	<dt>Height</dt>
	<dd><span class="num">{metresFeet(row.h)}</span> <span class="how">measured by the lidar</span></dd>
	<dt>Width</dt>
	<dd><span class="num">{metresFeet(row.w)}</span> <span class="how">from the height, by the test areas' model</span></dd>
</dl>
<h3>How we know</h3>
<ul class="know">
	{#each shrubHowWeKnow(row) as line, i (i)}
		<li>{line}</li>
	{/each}
</ul>
<p class="credit">{SHRUB_CREDIT}</p>

<style>
	.kind-line {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-bottom: 4px;
		color: var(--ink);
	}
	.explain {
		margin: 0 0 8px;
		font-size: 13px;
	}
	.facts {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 2px 10px;
		margin: 0 0 8px;
		font-size: 13px;
	}
	dt {
		color: var(--ink-soft);
	}
	dd {
		margin: 0;
	}
	.how {
		color: var(--ink-soft);
		font-size: 12px;
	}
	h3 {
		margin: 8px 0 4px;
		font: 600 14px var(--font-display);
	}
	.know {
		margin: 0;
		padding-left: 18px;
		font-size: 12px;
	}
</style>
