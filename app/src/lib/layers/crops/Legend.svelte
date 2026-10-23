<script lang="ts">
	import type { LegendProps } from '../types.js';
	import type { CropsModule } from './index.svelte.js';
	import { METHOD_FROM, METHOD_NOTE } from './model.js';
	import { FILL, GROUP_NAME, GROUPS, PATTERN_INK } from './palette.js';
	import { GROWTH_KEYS, PATTERNS, svgMarks, type GrowthKey, type PatternKey } from './patterns.js';

	/**
	 * The Crop fields legend (plan §3.4; P3-app): the seven groups, each drawn as the map draws it (colour and
	 * pattern, named: never colour alone), the year switcher, the toggles for built over, being built and
	 * approved plats, the notes that these are estimated outlines and that 2024-25 maps use a new USDA method,
	 * and the credit.
	 */
	let { module }: LegendProps = $props();
	const crops = $derived(module as unknown as CropsModule);

	const GROWTH_TEXT: Record<GrowthKey, string> = {
		built_over: 'Built over (farmed early, developed by 2024)',
		being_built: 'Being built (developed, with new-construction permits)',
		plat: 'Under an approved plat (still farmed)'
	};
	const swatchFill = (key: PatternKey) => (key in FILL ? FILL[key as keyof typeof FILL] : '#fffbf4');
</script>

<p class="legend-title">Crop fields</p>
<ul class="keys">
	{#each GROUPS as g (g)}
		<li data-group={g}>
			{@render swatch(g)}
			<span><b>{GROUP_NAME[g]}</b> <span class="look">({PATTERNS[g].look})</span></span>
		</li>
	{/each}
</ul>

{#snippet swatch(key: PatternKey)}
	<svg viewBox="0 0 16 16" width="22" height="22" aria-hidden="true" class="swatch">
		<clipPath id="legend-clip-{key}"><rect width="16" height="16" rx="3" /></clipPath>
		<rect width="16" height="16" rx="3" fill={swatchFill(key)} stroke="#6a6455" stroke-width="1" />
		<g clip-path="url(#legend-clip-{key})" stroke={PATTERN_INK} fill={PATTERN_INK} stroke-width={PATTERNS[key].width * 0.8} opacity="0.7">
			{#each svgMarks(PATTERNS[key]) as m, i (i)}
				{#if m.tag === 'line'}<line {...m.attrs} />{:else}<circle {...m.attrs} fill={m.fill ? PATTERN_INK : 'none'} />{/if}
			{/each}
		</g>
	</svg>
{/snippet}

<p class="sub">Year</p>
<div class="chips" role="group" aria-label="Crop year">
	{#each crops.years as y (y)}
		<button class="pill small" data-year={y} aria-pressed={crops.year === y} onclick={() => crops.setYear(y)}>
			{y}{#if y === crops.current}{' '}<span class="newest">newest</span>{/if}
		</button>
	{/each}
</div>
{#if crops.year !== crops.current}
	<p class="hint">Showing {crops.year}.{#if !crops.hasLowZoom(crops.year)}{' '}This year's map shows from zoom 11.{/if} Click a field for its rotation.</p>
{:else}
	<p class="hint">{crops.info?.label ?? "USDA's newest map"}. Zoom in to see each field; click one for its card.</p>
{/if}

<p class="sub">Show</p>
<ul class="toggles">
	{#each GROWTH_KEYS as k (k)}
		<li>
			<label>
				<input type="checkbox" checked={crops.growth[k]} onchange={(e) => crops.setGrowth(k, e.currentTarget.checked)} data-growth={k} />
				{@render swatch(k)}
				<span>{GROWTH_TEXT[k]} <span class="look">({PATTERNS[k].look})</span></span>
			</label>
		</li>
	{/each}
</ul>

<p class="note">These are <b>estimated field outlines</b>: modelled from 30 m satellite pixels, edges can be off by a few metres. They fade out near z15 into a dashed estimated edge.</p>
{#if crops.year >= METHOD_FROM || crops.current >= METHOD_FROM}
	<p class="note">{METHOD_NOTE}: don't read 2023 to 2024 changes as real.</p>
{/if}
<p class="credit">
	{crops.credit ?? 'USDA NASS Crop Sequence Boundaries and Cropland Data Layer; Contains modified Copernicus Sentinel data 2025; COMPASS (permits and plats)'}.
</p>

<style>
	li {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		font-size: 12px;
	}
	.keys,
	.toggles {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.keys li + li,
	.toggles li + li {
		margin-top: 3px;
	}
	.toggles label {
		display: flex;
		align-items: flex-start;
		gap: 6px;
		cursor: pointer;
	}
	.swatch {
		flex: none;
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
	.newest {
		font-size: 10px;
		color: var(--ink-soft);
	}
	.hint,
	.note {
		margin: 6px 0 0;
		font-size: 12px;
	}
	.hint {
		color: var(--ink-soft);
	}
</style>
