<script lang="ts">
	import type { LegendProps } from '../types.js';
	import type { SoilsModule } from './index.svelte.js';
	import { CREDIT, NOT_SURVEYED, REGULATORY, SHOW_BY, SHOW_BY_DEFS } from './model.js';
	import { PATTERN_INK, STEPS } from './palette.js';
	import { css, LOOK } from './patterns.js';

	/**
	 * The Soils legend (landscape sprint plan v3 §3.4, P1-app): "Show by" (one property at a time), that
	 * property's gray ramp with every step named (never colour alone), the patterns it carries (each named with
	 * what it looks like), the notes that this is mapped soil and not surveyed in part of Malheur County, and the credit.
	 */
	let { module }: LegendProps = $props();
	const soils = $derived(module as unknown as SoilsModule);
	const def = $derived(SHOW_BY_DEFS[soils.by]);
</script>

<p class="legend-title">Soils</p>
<p class="sub">Show by</p>
<div class="chips" role="group" aria-label="Show soils by">
	{#each SHOW_BY as k (k)}
		<button class="pill small" data-by={k} aria-pressed={soils.by === k} onclick={() => soils.setBy(k)}>{SHOW_BY_DEFS[k].short}</button>
	{/each}
</div>
<p class="sub">{def.title}</p>
<ul class="keys">
	{#each def.levels as level, code (code)}
		<li data-step={code}>
			<span class="swatch" style:background={STEPS[def.steps[code]]} aria-hidden="true"></span>
			<span>{level}</span>
		</li>
	{/each}
	<li data-step="none">
		<span class="swatch none" aria-hidden="true"></span>
		<span>Not rated (no fill)</span>
	</li>
</ul>
{#if def.patterns.length}
	<ul class="keys patterns">
		{#each def.patterns as p (p.key)}
			<li data-pattern={p.key}>
				<span class="swatch" style:background={css(p.key, PATTERN_INK, STEPS[1])} aria-hidden="true"></span>
				<span>{p.text} <span class="look">({LOOK[p.key]})</span></span>
			</li>
		{/each}
	</ul>
{/if}
{#if def.note}<p class="note">{def.note}</p>{/if}
<p class="note"><b>{REGULATORY}.</b></p>
<p class="note">Gray steps run from palest to darkest. The wash shows from zoom 9, hatches and dots from 11, outlines from 12, map-unit symbols from 14 and names from 16. {NOT_SURVEYED}</p>
<p class="credit">{soils.credit ?? CREDIT}.</p>

<style>
	li {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
	}
	.keys {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.keys li + li {
		margin-top: 3px;
	}
	.patterns {
		margin-top: 6px;
	}
	.swatch {
		flex: none;
		width: 22px;
		height: 14px;
		border: 1px solid var(--ink-soft);
		border-radius: 3px;
	}
	.swatch.none {
		border-style: dashed;
		background: none;
	}
	.look {
		color: var(--ink-soft);
	}
	.sub {
		margin: 8px 0 4px;
		font: 600 12px var(--font-display);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
	}
	.small {
		padding: 2px 8px;
		font-size: 12px;
	}
	.note {
		margin: 6px 0 0;
		font-size: 12px;
	}
</style>
