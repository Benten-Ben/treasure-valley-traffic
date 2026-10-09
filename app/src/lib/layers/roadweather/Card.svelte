<script lang="ts">
	import { onDestroy } from 'svelte';
	import type { CardProps } from '../types.js';
	import type { RoadWeatherModule } from './index.svelte.js';
	import { ageAt, creditOf, shortAge, stationFact, viewStatus, type RoadWeatherStation } from './model.js';

	/**
	 * The selected station's inspect card: name, provider, how many views are
	 * live, each view in 511's order with its status (shape and word, the
	 * window's own: live, late, stale, no live feed, no picture yet; model.ts
	 * `viewStatus`) and its picture's age, and a way to its window (a click on
	 * the station has already opened one; this brings it back).
	 */
	let { selection, module }: CardProps = $props();
	const rw = $derived(module as unknown as RoadWeatherModule);
	const s = $derived(selection.data as RoadWeatherStation);

	// Ages move with the clock between the list's refreshes (every 5 min); a status changes at most once a minute or so.
	let now = $state(Date.now());
	const tick = setInterval(() => (now = Date.now()), 15_000);
	onDestroy(() => clearInterval(tick));
	const nowS = $derived((now + rw.skew) / 1000);
	// Each age is written " · 6 min" as one expression: Svelte trims a space at the start of an element's text.
	const views = $derived(
		s.views.map((v) => {
			const age = v.disabled ? null : ageAt(v, nowS);
			return { v, age, st: viewStatus(v, age) };
		})
	);
</script>

<h2>{s.name}</h2>
<p class="meta">
	<span aria-hidden="true">{s.hollow ? '■' : '●'}</span>
	{stationFact(s, nowS)} · {s.provider}
</p>
<ul class="views">
	{#each views as { v, age, st } (v.id)}
		<li data-view-id={v.id} data-state={st.kind} title={st.detail}>
			<!-- Ink shapes: amber alone on cream is 2.05:1, below the 3:1 a status shape needs (docs/13). -->
			<span class="shape" aria-hidden="true">{st.shape}</span>
			{v.label}: {st.word}{#if age !== null}<span class="age num">{` · ${shortAge(age)}`}</span>{/if}
		</li>
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
	.shape {
		font-size: 11px;
	}
	.age {
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 12px;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
</style>
