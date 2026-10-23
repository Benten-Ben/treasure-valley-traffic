<script lang="ts">
	import type { CardProps } from '../types.js';
	import type { PavingCard } from '#lib/server/roads/paving.js';
	import type { LanesModule } from './index.svelte.js';
	import { CardError, claimText, lanesPhrase, metresFeet, NOTE_WORD, pieceTitle, WAY_WORDS, type LanesSelectionData, type PieceAnswer } from './lanes.js';

	/**
	 * The Lanes cards (landscape sprint plan v3 §4.2 P9, the UI v2 card pattern): a road piece (its lanes, each count
	 * with its source, a ▲ where the sources disagree, its width and how it is known, its material), a junction or an
	 * island (no lane counts), and paving (a parking lot or a way). What the click already told us shows at once; the
	 * rest comes from /api/roads/piece (asked with the build the map's tiles are from, so a road is never another
	 * build's) and /api/roads/paving. Estimates say so, with a warning sign; the values rest on ACHD's and ITD's internal data,
	 * and the card says they are shown on this map only.
	 */
	let { selection, module }: CardProps = $props();
	const lanes = $derived(module as unknown as LanesModule);
	const data = $derived(selection.data as LanesSelectionData);

	let answer = $state.raw<PieceAnswer | PavingCard | null>(null);
	let loading = $state(false);
	let problem = $state<string | null>(null);
	let behind = $state(false);

	$effect(() => {
		const d = data;
		answer = null;
		problem = null;
		behind = false;
		loading = true;
		let live = true;
		const asked = d.type === 'piece' ? lanes.piece(d) : lanes.paving(d);
		asked.then(
			(got) => {
				if (!live) return;
				answer = got;
				loading = false;
			},
			(e) => {
				if (!live) return;
				loading = false;
				if (e instanceof CardError && e.status === 409) {
					behind = true;
					problem = e.message;
				} else if (e instanceof CardError && e.status === 404) problem = d.type === 'piece' ? 'This is no longer in the roads build.' : 'This is no longer in the paving data.';
				else problem = `Couldn't load its details: ${e instanceof Error ? e.message : e}`;
			}
		);
		return () => {
			live = false;
		};
	});

	const piece = $derived(answer?.kind === 'piece' ? answer : null);
	const junction = $derived(answer?.kind === 'junction' ? answer : null);
	const lot = $derived(answer?.kind === 'lot' ? answer : null);
	const way = $derived(answer?.kind === 'way' ? answer : null);

	const acres = (n: number) => `${n} acre${n === 1 ? '' : 's'}`;
	/** A text warning sign (U+FE0E keeps it from drawing as a color emoji, which the project doesn't use). */
	const WARN = '\u26A0\uFE0E';
</script>

{#if piece}
	<h2>{pieceTitle(piece)}</h2>
	<p class="meta">
		{piece.class_word}{piece.ref && piece.name ? ` · ${piece.ref}` : ''}{piece.bridge ? ' · bridge' : ''}{piece.tunnel ? ' · tunnel' : ''}{piece.roundabout ? ' · roundabout' : ''}{piece.county ? ` · ${piece.county} County` : ''}
	</p>
	<dl class="facts">
		<dt>Lanes</dt>
		<dd>
			<span class="num">{lanesPhrase(piece.lanes, piece.oneway)}</span>
			<span class="how">{piece.lanes.source_label}</span>
			{#if piece.lanes.assumed}
				<span class="how">{WARN} estimated: no source gives this road's lanes</span>
			{/if}
			{#if piece.lanes.split_estimated}
				<span class="how block">{WARN} estimated: the way gives only a total, so the split between the directions is ours</span>
			{/if}
		</dd>
		<dt>Width</dt>
		<dd>
			<span class="num">{metresFeet(piece.width.total_m)}</span>
			<span class="how">{piece.width.tier_word} · {piece.width.source_word}</span>
			{#if piece.width.estimated}
				<span class="how block">{WARN} estimated: drawn with a soft edge on the map</span>
			{/if}
		</dd>
		<dt>Material</dt>
		<dd>
			{piece.material.value}
			{#if piece.material.estimated}<span class="how">{WARN} estimated</span>{/if}
		</dd>
		<dt>Markings</dt>
		<dd>{piece.lanes.markings ? 'Lane lines drawn' : 'No lane lines drawn: a source has to give the lane count first'}</dd>
	</dl>
	{#if piece.conflict}
		<section class="conflict" aria-label="The sources disagree">
			<h3>▲ The sources disagree on the lanes</h3>
			{#if piece.conflict.osm || piece.conflict.other}
				<ul>
					{#if piece.conflict.osm}<li class="num">{claimText(piece.conflict.osm)}</li>{/if}
					{#if piece.conflict.other}<li class="num">{claimText(piece.conflict.other)}</li>{/if}
				</ul>
			{:else if piece.conflict.rule_disagrees}
				<p class="how">The sources ACHD's rule draws on disagree with each other.</p>
			{:else}
				<p class="how">They differ by more than a lane; the two counts aren't on file for this piece.</p>
			{/if}
			<p class="how">The count shown above is the one the map draws: {piece.lanes.source_label}.</p>
		</section>
	{/if}
	{#each piece.notes as n (n)}
		<p class="how">{NOTE_WORD[n]}</p>
	{/each}
	<p class="credit">{piece.credit}</p>
{:else if junction}
	<h2>{junction.title}</h2>
	<p class="meta">{junction.pieces ? `${junction.pieces} road pieces meet here` : 'Road surface with no lane count of its own'}</p>
	<p class="how">A junction or an island has no lanes of its own, so no lane counts are shown. Click a road leading into it for its lanes.</p>
	<p class="credit">{junction.credit}</p>
{:else if lot}
	<h2>{lot.name ?? 'Parking lot'}</h2>
	<p class="meta">Parking lot{lot.operator ? ` · ${lot.operator}` : ''}</p>
	<dl class="facts">
		<dt>Size</dt>
		<dd><span class="num">{acres(lot.acres)}</span> <span class="how">({lot.area_m2.toLocaleString('en-US')} m²)</span></dd>
		<dt>Stalls</dt>
		<dd>
			{#if lot.capacity !== null}<span class="num">{lot.capacity}</span> <span class="how">tagged in OpenStreetMap</span>
			{:else if lot.stalls_estimated !== null}<span class="num">about {lot.stalls_estimated}</span> <span class="how">{WARN} estimated from the area</span>
			{:else}<span class="how">not known</span>{/if}
		</dd>
		<dt>Surface</dt>
		<dd>{lot.material} {#if lot.material_estimated}<span class="how">{WARN} estimated</span>{/if}</dd>
		{#if lot.access}<dt>Access</dt><dd>{lot.access}</dd>{/if}
		{#if lot.fee}<dt>Fee</dt><dd>{lot.fee}</dd>{/if}
	</dl>
	<p class="credit">{lot.credit}</p>
{:else if way}
	<h2>{WAY_WORDS[way.way_kind] ?? 'Paving'}</h2>
	<p class="meta">Paving</p>
	<dl class="facts">
		<dt>Surface</dt>
		<dd>{way.surface ?? 'not tagged'} {#if way.surface_estimated}<span class="how">{WARN} estimated</span>{/if}</dd>
		<dt>Width</dt>
		<dd><span class="num">{metresFeet(way.width_m)}</span> {#if way.width_estimated}<span class="how">{WARN} estimated</span>{/if}</dd>
		<dt>Length</dt>
		<dd class="num">{metresFeet(way.length_m)}</dd>
	</dl>
	<p class="credit">{way.credit}</p>
{:else}
	<h2>{selection.title}</h2>
	{#if selection.fact}<p class="meta">{selection.fact}</p>{/if}
	{#if loading}
		<p class="meta" role="status">Loading what we know…</p>
	{:else if problem}
		<p class="meta" role="alert">▲ {problem}</p>
		{#if behind}
			<button class="pill" type="button" onclick={() => location.reload()}>Reload the map</button>
		{/if}
	{/if}
{/if}

<style>
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
	.block {
		display: block;
	}
	h3 {
		margin: 0 0 4px;
		font: 600 14px var(--font-display);
	}
	.conflict {
		margin: 0 0 8px;
		padding: 6px 8px;
		border: 1px solid var(--ink-soft);
		border-radius: 6px;
	}
	.conflict ul {
		margin: 0 0 4px;
		padding-left: 18px;
		font-size: 13px;
	}
</style>
