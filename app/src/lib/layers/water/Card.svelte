<script lang="ts">
	import type { CardProps } from '../types.js';
	import type { Details, WaterModule, WaterSelectionData } from './index.svelte.js';
	import {
		ageText,
		areaText,
		BODY_WORD,
		bodyTitle,
		canalSourceWords,
		CANAL_KIND_WORD,
		CREDITS,
		dayText,
		ECOLI_NOTE,
		ecoliResultText,
		evidenceWords,
		FLOW_WORD,
		floodWords,
		geometryWords,
		HAZARD_NOTE,
		HAZARD_STATUS_WORD,
		HAZARD_WORD,
		KIND_WORD,
		lengthText,
		measuresWords,
		metresFeet,
		nameWords,
		outlineWords,
		readingText,
		reachTitle,
		SERVICE_AREA_NOTE,
		serviceAreasWords,
		SOURCE_NAME,
		STRUCTURE_WORD,
		widthHow,
		type GaugeSummary
	} from './water.js';

	/**
	 * The water cards (landscape sprint plan v3 §4.2 P4-app, the UI v2 card pattern): a reach or canal, an
	 * area, a gauge, a structure, a river hazard or an E. coli site. Details come from /api/water/…, what the
	 * click already told us shows at once. Each card says where its facts came from and how we know; widths and
	 * flows say when they are estimates; the canal's card names the irrigation service areas it runs through;
	 * the City's notices are in its own words and we make no swim call.
	 */
	let { selection, module }: CardProps = $props();
	const water = $derived(module as unknown as WaterModule);
	const data = $derived(selection.data as WaterSelectionData);

	type Fetched = Details[keyof Details];
	let detail = $state<Fetched | null>(null);
	let loading = $state(false);
	let problem = $state<string | null>(null);

	$effect(() => {
		const d = data;
		detail = null;
		problem = null;
		if (d.type !== 'reach' && d.type !== 'body' && d.type !== 'gauge' && d.type !== 'structure') {
			loading = false;
			return;
		}
		const id = d.type === 'gauge' ? d.lid : d.id;
		let live = true;
		loading = true;
		water.detail(d.type, id).then(
			(got) => {
				if (!live) return;
				detail = got as Fetched | null;
				loading = false;
				if (!got) problem = 'This is no longer in the water build.';
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

	const reach = $derived(data.type === 'reach' ? (detail as Details['reach'] | null) : null);
	const body = $derived(data.type === 'body' ? (detail as Details['body'] | null) : null);
	const gauge = $derived(data.type === 'gauge' ? (detail as Details['gauge'] | null) : null);
	const structure = $derived(data.type === 'structure' ? (detail as Details['structure'] | null) : null);
	const hazard = $derived(data.type === 'hazard' ? water.hazard(data.id) : undefined);
	const sample = $derived(data.type === 'ecoli' ? water.sample(data.id) : undefined);

	const widthM = $derived(reach?.width_m ?? (data.type === 'reach' ? data.width_m : 0));
	const piped = $derived(reach?.piped ?? (data.type === 'reach' ? data.piped : false));
	const kindWord = $derived(data.type === 'reach' ? KIND_WORD[reach?.kind ?? data.kind] : '');
	const flow = $derived(reach?.flow ?? (data.type === 'reach' ? (data.intermittent ? 'intermittent' : 'unknown') : 'unknown'));
	const canal = $derived(reach?.canal ?? null);
	const nhdOnly = $derived(data.type === 'reach' || data.type === 'body' ? data.nhd_only : false);
</script>

{#snippet reading(g: GaugeSummary)}
	<dt>Gauge</dt>
	<dd>
		<b>{g.lid}</b> · {g.name}
		{#if g.reading}
			<br /><span class="num">{readingText(g.reading)}</span> <span class="how">observed {ageText(g.reading.at)}</span>
		{:else}
			<br /><span class="how">No reading yet.</span>
		{/if}
		<br /><span class="how">{floodWords(g.flood)}</span>
	</dd>
{/snippet}

{#if data.type === 'reach'}
	<h2>{reachTitle(reach?.kind ?? data.kind, reach?.name ?? data.name, piped)}</h2>
	<p class="meta">
		{kindWord}{#if canal} · {CANAL_KIND_WORD[canal.kind].toLowerCase()}{/if}{#if piped} · piped (culvert or siphon){/if}
	</p>
	<dl class="facts">
		<dt>Flow</dt>
		<dd>{FLOW_WORD[flow]}{#if !reach} <span class="how">(from the map)</span>{/if}</dd>
		<dt>Width</dt>
		<dd>
			<span class="num">about {metresFeet(widthM)}</span>
			<span class="how">{reach ? widthHow(reach.width_from) : 'an estimate'}; widths are estimates until measured</span>
		</dd>
		{#if reach}
			<dt>Length</dt>
			<dd class="num">{lengthText(reach.length_m)}</dd>
			{#if nameWords(reach.name_from)}
				<dt>Name</dt>
				<dd><span class="how">{nameWords(reach.name_from)}</span></dd>
			{/if}
		{/if}
	</dl>
	{#if reach}
		<p class="explain">{geometryWords(reach.geometry_from, reach.confirmed)}</p>
		{#if canal}
			<h3>{canal.name}</h3>
			<dl class="facts">
				<dt>Kind</dt>
				<dd>{CANAL_KIND_WORD[canal.kind]}{#if canal.kind === 'main_canal'} <span class="how">(20 km or longer)</span>{/if}</dd>
				<dt>Length</dt>
				<dd class="num">
					{lengthText(canal.length_m)}
					{#if canal.piped_m > 0}<span class="how">, {lengthText(canal.piped_m)} of it piped</span>{/if}
				</dd>
				{#if canalSourceWords(canal.source)}
					<dt>Water from</dt>
					<dd>{canalSourceWords(canal.source)}</dd>
				{/if}
				{#if canal.head_structure}
					<dt>Head</dt>
					<dd>{canal.head_structure.name ?? STRUCTURE_WORD[canal.head_structure.kind]} <span class="how">({STRUCTURE_WORD[canal.head_structure.kind].toLowerCase()})</span></dd>
				{/if}
				{#if canal.gauge}{@render reading(canal.gauge)}{/if}
			</dl>
			{#if canal.service_areas.length}
				<p class="explain" data-service-areas>{serviceAreasWords(canal.service_areas)}</p>
				<p class="how">{SERVICE_AREA_NOTE}</p>
			{/if}
		{:else if reach.gauge}
			<dl class="facts">{@render reading(reach.gauge)}</dl>
		{/if}
		{#if reach.evidence.length}
			<h3>How we know</h3>
			<ul class="know">
				{#each reach.evidence as e, i (i)}
					<li>{evidenceWords(e)}</li>
				{/each}
			</ul>
		{/if}
	{/if}
{:else if data.type === 'body'}
	<h2>{bodyTitle(body?.kind ?? data.kind, body?.name ?? data.name)}</h2>
	<p class="meta">{BODY_WORD[body?.kind ?? data.kind]}{#if body?.intermittent ?? data.intermittent} · dries up part of the year{/if}</p>
	{#if body}
		<dl class="facts">
			<dt>Size</dt>
			<dd class="num">{areaText(body.area_m2)}</dd>
			{#if body.osm}
				<dt>OpenStreetMap</dt>
				<dd class="num">{body.osm}</dd>
			{/if}
			{#if body.gauge}{@render reading(body.gauge)}{/if}
		</dl>
		<p class="explain">{outlineWords(body.geometry_from, body.confirmed)}</p>
		{#if body.kind === 'wetland'}
			<p class="how">Not a legal (regulatory) wetland boundary.</p>
		{/if}
	{/if}
{:else if data.type === 'gauge'}
	<h2>{gauge?.name ?? selection.title}</h2>
	<p class="meta">Gauge {data.lid}{#if gauge?.measures} · measures {measuresWords(gauge.measures)}{/if}</p>
	{#if gauge}
		<dl class="facts">
			<dt>Latest</dt>
			<dd>
				{#if gauge.reading}
					<span class="num">{readingText(gauge.reading)}</span> <span class="how">observed {ageText(gauge.reading.at)}</span>
				{:else}
					<span class="how">No reading yet.</span>
				{/if}
			</dd>
			<dt>Flood</dt>
			<dd>{floodWords(gauge.flood)}</dd>
			{#if gauge.method === 'nearest' && gauge.distance_m !== null}
				<dt>Matched</dt>
				<dd><span class="how">to the nearest waterway, {Math.round(gauge.distance_m)} m away</span></dd>
			{/if}
		</dl>
		<p class="how">Readings and categories are NWPS's, shown as published; this isn't a forecast.</p>
	{/if}
{:else if data.type === 'structure'}
	<h2>{selection.title}</h2>
	<p class="meta">{STRUCTURE_WORD[structure?.kind ?? 'dam']}</p>
	{#if structure}
		<dl class="facts">
			{#if structure.reach}
				<dt>On</dt>
				<dd>{reachTitle(structure.reach.kind, structure.reach.name)}</dd>
			{/if}
			{#if structure.head_of.length}
				<dt>Head of</dt>
				<dd>{structure.head_of.map((c) => c.name).join(', ')}</dd>
			{/if}
			<dt>From</dt>
			<dd><span class="how">{SOURCE_NAME[structure.source]}</span></dd>
			{#if structure.gauge}{@render reading(structure.gauge)}{/if}
		</dl>
	{/if}
{:else if data.type === 'hazard'}
	{#if hazard}
		<h2>{hazard.name ?? 'River hazard'}</h2>
		<p class="meta">{HAZARD_WORD[hazard.kind]} · {HAZARD_STATUS_WORD[hazard.status].toLowerCase()}{#if hazard.mile_marker} · mile {hazard.mile_marker}{/if}</p>
		{#if hazard.description}<p class="explain" data-city-words>{hazard.description}</p>{/if}
		<dl class="facts">
			{#if hazard.since}
				<dt>Since</dt>
				<dd class="num">{dayText(hazard.since)}</dd>
			{/if}
			{#if hazard.edited}
				<dt>Edited</dt>
				<dd class="num">{dayText(hazard.edited)}</dd>
			{/if}
		</dl>
		<p class="how">{HAZARD_NOTE}</p>
	{:else}
		<h2>{selection.title}</h2>
		<p class="meta" role="alert">▲ This hazard is no longer listed.</p>
	{/if}
{:else if data.type === 'ecoli'}
	{#if sample}
		<h2>{sample.site ?? sample.id}</h2>
		<p class="meta">E. coli sampling site</p>
		<dl class="facts">
			<dt>Latest</dt>
			<dd><span class="num">{ecoliResultText(sample)}</span> <span class="how">sampled {dayText(sample.sampled)}</span></dd>
		</dl>
		{#if sample.history.length}
			<h3>Earlier results</h3>
			<ol class="log" aria-label="Earlier results, newest first">
				{#each sample.history as h, i (i)}
					<li><span class="num when">{dayText(h.sampled)}</span> <span class="num">{ecoliResultText(h)}</span></li>
				{/each}
			</ol>
		{/if}
		<p class="how">{ECOLI_NOTE}</p>
	{:else}
		<h2>{selection.title}</h2>
		<p class="meta" role="alert">▲ This site is no longer listed.</p>
	{/if}
{/if}
{#if loading}
	<p class="meta" role="status">Loading what we know…</p>
{:else if problem}
	<p class="meta" role="alert">▲ {problem}</p>
{/if}
<p class="credit">
	{#if reach}{reach.credit.join(' · ')}
	{:else if body}{body.credit.join(' · ')}
	{:else if structure}{structure.credit.join(' · ')}
	{:else if gauge}{gauge.credit.join(' · ')}
	{:else if data.type === 'hazard'}{CREDITS.boiseHazards}
	{:else if data.type === 'ecoli'}{CREDITS.boiseEcoli}
	{:else}{nhdOnly ? CREDITS.nhd : `${CREDITS.osm} · ${CREDITS.nhd}`}
	{/if}
</p>

<style>
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
	.log {
		margin: 0 0 8px;
		padding: 0;
		list-style: none;
		font-size: 12px;
	}
	.log li {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 8px;
	}
	.when {
		color: var(--ink-soft);
		white-space: nowrap;
	}
</style>
