<script lang="ts">
	import type { SoilCard } from '#lib/server/soils/units.js';
	import type { CardProps } from '../types.js';
	import type { SoilsModule } from './index.svelte.js';
	import { groupText, hydricText, NOT_SURVEYED, REGULATORY, restrictionText, surveyText, waterText } from './model.js';
	import { css } from './patterns.js';
	import { PATTERN_INK, STEPS } from './palette.js';

	/**
	 * The soil card (landscape sprint plan v3 §3.4, P1-app; the UI v2 card pattern): the map unit's name, the
	 * dominant soil and what else is in it, texture, drainage, the shallowest restriction, water held in the top
	 * metre, farmland class, runoff group (hatched when it is a dual group), the hydric rating as a row, the
	 * survey area and its version, then the credit. It is mapped soil, never a site test: the card says so at
	 * the top, and "not surveyed" over the part of the box NRCS has no data for.
	 */
	let { selection, module }: CardProps = $props();
	const soils = $derived(module as unknown as SoilsModule);

	let detail = $state<SoilCard | null>(null);
	let loading = $state(true);
	let problem = $state<string | null>(null);

	$effect(() => {
		const id = selection.id;
		let live = true;
		loading = true;
		problem = null;
		detail = null;
		soils.detail(id).then(
			(d) => {
				if (!live) return;
				detail = d;
				loading = false;
				if (!d) problem = 'This map unit is no longer in the build.';
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

	const heading = $derived(detail && !detail.surveyed ? 'Not surveyed' : (detail?.name ?? selection.title));
	const water = $derived(detail ? waterText(detail) : null);
	const group = $derived(detail ? groupText(detail) : null);
	const hydric = $derived(detail ? hydricText(detail) : null);
	const survey = $derived(detail ? surveyText(detail.survey) : null);
	const acres = $derived(detail?.area_ha ? Math.round(detail.area_ha * 2.47105).toLocaleString('en-US') : null);
	const hatch = css('hatch', PATTERN_INK, STEPS[1]);
</script>

<h2>{heading}</h2>
<p class="meta">{detail?.symbol ?? selection.fact ?? ''}{#if detail?.survey}{' · '}{detail.survey.name}{/if}</p>
<p class="regulatory">{REGULATORY}.</p>
{#if loading}
	<p class="meta" role="status">Loading what we know…</p>
{:else if problem}
	<p class="meta" role="alert">▲ {problem}</p>
{/if}
{#if detail && !detail.surveyed}
	<p class="explain">{NOT_SURVEYED}</p>
{:else if detail}
	<dl class="facts">
		{#if detail.dominant}
			<dt>Main soil</dt>
			<dd>
				<b>{detail.dominant.name}</b>{#if detail.dominant.texture}{', '}{detail.dominant.texture.toLowerCase()}{/if}{#if detail.dominant_share !== null}{' '}<span class="how">({detail.dominant_share}% of the map unit)</span>{/if}
			</dd>
		{/if}
		{#if detail.mix}
			<dt>Made up of</dt>
			<dd>{detail.mix}</dd>
		{/if}
		{#if detail.drainage}
			<dt>Drainage</dt>
			<dd>{detail.drainage}</dd>
		{/if}
		<dt>Hardpan or bedrock</dt>
		<dd>{restrictionText(detail.restriction)}</dd>
		{#if water}
			<dt>Water held</dt>
			<dd>{water} <span class="how">our scaling of NRCS's 150 cm classes to the top metre</span></dd>
		{/if}
		{#if detail.farmland}
			<dt>Farmland</dt>
			<dd>{detail.farmland}</dd>
		{/if}
		{#if group}
			<dt>Runoff group</dt>
			<dd>
				{group}
				{#if detail.hydrologic_dual}<span class="swatch" style:background={hatch} role="img" aria-label="Shown hatched on the map: a dual hydrologic group"></span>{/if}
			</dd>
		{/if}
		{#if hydric}
			<dt>Hydric soil</dt>
			<dd>{hydric}</dd>
		{/if}
		{#if detail.slope_percent !== null}
			<dt>Slope</dt>
			<dd>{detail.slope_percent}% (dominant component)</dd>
		{/if}
		{#if acres}
			<dt>Size here</dt>
			<dd>{acres} acres of this map unit in the Treasure Valley</dd>
		{/if}
	</dl>
	{#if survey}<p class="survey"><b>Survey:</b> {survey}</p>{/if}
{/if}
<p class="credit">{detail?.credit ?? 'Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)'}.</p>

<style>
	.regulatory {
		margin: 0 0 8px;
		font-size: 12px;
		font-weight: 600;
	}
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
	.survey {
		margin: 6px 0 0;
		font-size: 12px;
	}
	.swatch {
		display: inline-block;
		width: 22px;
		height: 12px;
		margin-left: 6px;
		vertical-align: -1px;
		border: 1px solid var(--ink-soft);
		border-radius: 3px;
	}
</style>
