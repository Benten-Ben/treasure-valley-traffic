<script lang="ts">
	import type { CardProps } from '../types.js';
	import type { RoadWeatherModule } from './index.svelte.js';
	import { creditOf, stationFact, type RoadWeatherStation } from './model.js';

	/**
	 * The selected station's inspect card: name, provider, how many views are
	 * live (shape and word), each view in 511's order, and a way to its window
	 * (a click on the station has already opened one; this brings it back).
	 */
	let { selection, module }: CardProps = $props();
	const rw = $derived(module as unknown as RoadWeatherModule);
	const s = $derived(selection.data as RoadWeatherStation);
	const SHAPE = { live: '●', no_feed: '■', unknown: '◌' } as const;
	const WORD = { live: 'live', no_feed: 'no live feed', unknown: 'not known' } as const;
</script>

<h2>{s.name}</h2>
<p class="meta">
	<span aria-hidden="true">{s.hollow ? '■' : '●'}</span>
	{stationFact(s)} · {s.provider}
</p>
<ul class="views">
	{#each s.views as v (v.id)}
		<li><span aria-hidden="true">{SHAPE[v.feed]}</span> {v.label}: {WORD[v.feed]}</li>
	{/each}
</ul>
<div class="row">
	<button class="pill" onclick={() => rw.open(s.id)}>{rw.windowOf(s.id) === null ? 'Open its window' : 'Show its window'}</button>
</div>
<p class="credit">{creditOf(s.provider)}</p>

<style>
	.views {
		margin: 4px 0 8px;
		padding: 0;
		list-style: none;
		font-size: 13px;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
</style>
