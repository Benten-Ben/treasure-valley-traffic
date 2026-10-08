<script lang="ts">
	import type { CardProps } from '../types.js';
	import type { TreesModule } from './index.svelte.js';
	import {
		CATALOGUE_NAME,
		credits,
		dateText,
		DISC_EDGE,
		eventDetail,
		eventName,
		howWeKnow,
		KIND_WORD,
		kindText,
		lidarYear,
		metresFeet,
		treeColor,
		treeTitle,
		trunkIn,
		TYPE_NAME,
		type TreeDetail,
		type TreeRow
	} from './trees.js';

	/**
	 * The tree panel (docs/19 §19.6, the UI v2 card pattern): the species'
	 * common name (or the type), the kind in plain words, its sizes (estimated
	 * ones say so), the catalogue's trunk diameter, planting date, last
	 * verification and condition when known, how we know, the log (newest
	 * first) and the credits for its kind.
	 */
	let { selection, module }: CardProps = $props();
	const trees = $derived(module as unknown as TreesModule);
	const row = $derived(selection.data as TreeRow);

	let detail = $state<TreeDetail | null>(null);
	let loading = $state(true);
	let problem = $state<string | null>(null);

	$effect(() => {
		const id = selection.id;
		let live = true;
		loading = true;
		problem = null;
		detail = null;
		trees.detail(id).then(
			(d) => {
				if (!live) return;
				detail = d;
				loading = false;
				if (!d) problem = 'This tree is no longer in the build.';
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

	const kind = $derived(detail?.kind ?? row.kind);
	const type = $derived(detail?.type ?? row.type);
	const height = $derived(detail?.height_m ?? row.h);
	const crown = $derived(2 * (detail?.crown_radius_m ?? row.r));
	const catalogueName = $derived(detail?.catalogue ? (CATALOGUE_NAME[detail.catalogue.catalogue] ?? detail.catalogue.catalogue) : 'City of Boise');
	const title = $derived(detail ? treeTitle(detail) : TYPE_NAME[row.type]);
	const year = $derived(detail ? lidarYear(detail) : '2023');
	const trunk = $derived(detail ? trunkIn(detail) : null);
	const cat = $derived(detail?.catalogue ?? null);
	const species = $derived(cat && (cat.genus || cat.species) ? [cat.genus, cat.species].filter(Boolean).join(' ') : null);
	/** Which sizes are estimates, in words (docs/14: estimated things say so). */
	const heightNote = $derived(kind === 'estimated' ? 'estimated from its species and trunk' : `measured by the ${year} lidar`);
	const crownNote = $derived(
		kind === 'estimated' ? 'estimated from its species and trunk' : kind === 'placed' ? 'estimated by placement' : 'from its species, checked against the lidar'
	);
</script>

<h2>{title}</h2>
<p class="meta kind-line">
	<svg viewBox="0 0 14 14" width="13" height="13" aria-hidden="true">
		<circle cx="7" cy="7" r="5.5" fill={treeColor(row.id, type, kind)} stroke={DISC_EDGE} stroke-width="1" />
	</svg>
	<span><b>{KIND_WORD[kind]}</b> · {TYPE_NAME[type].replace(' tree', '').toLowerCase()}</span>
</p>
<p class="explain">{kindText(kind, year, catalogueName)}.</p>
<dl class="facts">
	<dt>Height</dt>
	<dd><span class="num">{metresFeet(height)}</span> <span class="how">{heightNote}</span></dd>
	<dt>Crown width</dt>
	<dd><span class="num">{metresFeet(crown)}</span> <span class="how">{crownNote}</span></dd>
	{#if trunk !== null}
		<dt>Trunk</dt>
		<dd><span class="num">{Math.round(trunk)} in · {Math.round(trunk * 2.54)} cm</span> <span class="how">diameter, from the inventory</span></dd>
	{/if}
	{#if species}
		<dt>Species</dt>
		<dd><i>{species}</i></dd>
	{/if}
	{#if cat?.installed}
		<dt>Planted</dt>
		<dd class="num">{dateText(cat.installed)}</dd>
	{/if}
	{#if cat?.last_verified}
		<dt>Last verified</dt>
		<dd class="num">{dateText(cat.last_verified)}</dd>
	{/if}
	{#if cat?.condition}
		<dt>Condition</dt>
		<dd>{cat.condition}</dd>
	{/if}
	{#if cat?.site_type}
		<dt>Site</dt>
		<dd>{cat.site_type}</dd>
	{/if}
</dl>
{#if loading}
	<p class="meta" role="status">Loading what we know…</p>
{:else if problem}
	<p class="meta" role="alert">▲ {problem}</p>
{/if}
{#if detail}
	<h3>How we know</h3>
	<ul class="know">
		{#each howWeKnow(detail) as line, i (i)}
			<li>{line}</li>
		{/each}
	</ul>
	{#if detail.log.length}
		<h3>Log</h3>
		<ol class="log" aria-label="Log, newest first">
			{#each detail.log as e, i (i)}
				<li>
					<span class="num when">{dateText(e.at)}</span>
					<span><b>{eventName(e.event)}</b>{#if eventDetail(e)}{': '}{eventDetail(e)}{/if}</span>
				</li>
			{/each}
		</ol>
	{/if}
{/if}
<p class="credit">{credits(kind, detail?.catalogue?.catalogue ?? (kind === 'placed' ? null : 'boise'), year).join(' · ')}</p>

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
	.log {
		margin: 0;
		padding: 0;
		list-style: none;
		font-size: 12px;
	}
	.log li {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 8px;
	}
	.log li + li {
		margin-top: 3px;
	}
	.when {
		color: var(--ink-soft);
		white-space: nowrap;
	}
</style>
