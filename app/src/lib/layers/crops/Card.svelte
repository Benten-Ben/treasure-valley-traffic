<script lang="ts">
	import type { CardProps } from '../types.js';
	import type { CropsModule } from './index.svelte.js';
	import { cropNow, growthText, howSure, julyText, methodNote, platText, rotationText, subtitle, type FieldCard } from './model.js';
	import { FILL, GROUP_SHORT, isCrop, PATTERN_INK, type TileGroup } from './palette.js';
	import { PATTERNS, svgMarks } from './patterns.js';

	/**
	 * The field card (landscape sprint plan §3.4, P3-app; the UI v2 card pattern): "Estimated field · 24 acres ·
	 * Canyon County", this year's crop ("USDA's newest map"), a chip per year with the rotation, how sure
	 * USDA's map is (the CDL agreement), the July state, and the growth and plat flags as stored by
	 * `farm-derive`; then the credits. The outline is a model of 30 m pixels, never a survey.
	 */
	let { selection, module }: CardProps = $props();
	const crops = $derived(module as unknown as CropsModule);

	let detail = $state<FieldCard | null>(null);
	let loading = $state(true);
	let problem = $state<string | null>(null);

	$effect(() => {
		const id = selection.id;
		let live = true;
		loading = true;
		problem = null;
		detail = null;
		crops.detail(id).then(
			(d) => {
				if (!live) return;
				detail = d;
				loading = false;
				if (!d) problem = 'This field is no longer in the build.';
			},
			(e) => {
				if (!live) return;
				loading = false;
				problem = `Couldn't load its details: ${e instanceof Error ? e.message : e}`;
			}
		);
		return () => {
			live = false;
		};
	});

	const now = $derived(detail ? cropNow(detail) : null);
	const sure = $derived(detail ? howSure(detail.agree) : null);
	const growth = $derived(detail ? growthText(detail) : null);
	const plat = $derived(detail ? platText(detail.plat) : null);
	const july = $derived(detail ? julyText(detail.july) : null);
	const label = $derived(crops.info?.label ?? "USDA's newest map");
	const heading = $derived(detail ? subtitle(detail.acres, detail.county) : subtitle(null, null));
	const paint = (g: string): string | null => (isCrop(g) ? FILL[g] : null);
	const short = (g: string) => GROUP_SHORT[g as TileGroup] ?? 'Other';
</script>

<h2>Estimated field</h2>
<p class="meta">{detail ? heading.replace('Estimated field · ', '') : (selection.fact ?? '')}</p>
<p class="explain">The outline is modelled from 30 m satellite pixels, so edges can be off by a few metres and some fields are split or merged.</p>
{#if loading}
	<p class="meta" role="status">Loading what we know…</p>
{:else if problem}
	<p class="meta" role="alert">▲ {problem}</p>
{/if}
{#if detail && now}
	<dl class="facts">
		<dt>{now.year} crop</dt>
		<dd>
			<b>{now.name}</b>
			<span class="how">{label}{#if now.year === crops.current}{''}{/if}</span>
		</dd>
		{#if sure}
			<dt>How sure</dt>
			<dd>{sure.text}</dd>
		{/if}
		{#if july}
			<dt>Green in July</dt>
			<dd>{july} <span class="how">from Sentinel-2</span></dd>
		{/if}
		{#if growth}
			<dt>Growth</dt>
			<dd>{growth}</dd>
		{/if}
		{#if plat}
			<dt>Plats</dt>
			<dd>{plat}</dd>
		{/if}
	</dl>
	<h3>Eight years</h3>
	<ol class="years" aria-label="Crop in each year, oldest first">
		{#each detail.years as y (y.year)}
			<li>
				<svg viewBox="0 0 16 16" width="22" height="22" aria-hidden="true" class="swatch">
					<rect width="16" height="16" rx="3" fill={paint(y.group) ?? 'none'} stroke="#6a6455" stroke-width="1" stroke-dasharray={paint(y.group) ? undefined : '2 2'} />
					{#if isCrop(y.group)}
						<clipPath id="clip-{y.year}"><rect width="16" height="16" rx="3" /></clipPath>
						<g clip-path="url(#clip-{y.year})" stroke={PATTERN_INK} fill={PATTERN_INK} stroke-width={PATTERNS[y.group].width * 0.8} opacity="0.7">
							{#each svgMarks(PATTERNS[y.group]) as m, i (i)}
								{#if m.tag === 'line'}<line {...m.attrs} />{:else}<circle {...m.attrs} fill={m.fill ? PATTERN_INK : 'none'} />{/if}
							{/each}
						</g>
					{/if}
				</svg>
				<span class="num">{y.year}</span>
				<span>{y.name ?? short(y.group)}</span>
			</li>
		{/each}
	</ol>
	<p class="rotation"><b>Rotation:</b> {rotationText(detail.years)}.</p>
	{#if methodNote(now.year)}
		<p class="hint">{methodNote(now.year)}: 2024 and 2025 can't be compared with earlier years as real changes (hay moves into grass and pasture, developed land moves up).</p>
	{/if}
{/if}
<p class="credit">
	{detail?.credit ?? 'USDA NASS Crop Sequence Boundaries and Cropland Data Layer; Contains modified Copernicus Sentinel data 2025; COMPASS (permits and plats)'}. Fields are estimates, never joined to parcels or owners.
</p>

<style>
	.explain {
		margin: 0 0 8px;
		font-size: 12px;
		color: var(--ink-soft);
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
	.years {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 3px 10px;
		margin: 0;
		padding: 0;
		list-style: none;
		font-size: 12px;
	}
	.years li {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.swatch {
		flex: none;
	}
	.rotation,
	.hint {
		margin: 6px 0 0;
		font-size: 12px;
	}
	.hint {
		color: var(--ink-soft);
	}
</style>
