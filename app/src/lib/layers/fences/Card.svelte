<script lang="ts">
	import type { CardProps } from '../types.js';
	import { heightNote, lengthText, lookWord, MAPPED_NOTE, materialText, metresFeet, TYPE_NAME, type FenceProps } from './fences.js';
	import { ESTIMATED, POST } from './palette.js';

	/**
	 * The fence card (plan §4.2 P10, the UI v2 card pattern): the type, see-through or solid, the material, the height
	 * (tagged or estimated, in words), the length and where it was mapped. Only what contributors have mapped in
	 * OpenStreetMap is here, and a mapped fence says nothing about who owns the land on either side of it.
	 */
	let { selection }: CardProps = $props();
	const p = $derived(selection.data as FenceProps);
	const material = $derived(materialText(p));
</script>

<h2>{selection.title}</h2>
<p class="meta kind-line">
	<svg viewBox="0 0 28 14" width="28" height="14" aria-hidden="true">
		{#if p.look === 'open'}
			<rect x="1" y="4" width="26" height="2" fill={p.hs === 'tagged' ? POST : ESTIMATED} />
			<rect x="1" y="2" width="2" height="10" fill={p.hs === 'tagged' ? POST : ESTIMATED} />
			<rect x="13" y="2" width="2" height="10" fill={p.hs === 'tagged' ? POST : ESTIMATED} />
			<rect x="25" y="2" width="2" height="10" fill={p.hs === 'tagged' ? POST : ESTIMATED} />
		{:else}
			<rect x="1" y="2" width="26" height="10" fill={p.hs === 'tagged' ? POST : ESTIMATED} />
		{/if}
	</svg>
	<span><b>{lookWord(p.look)}</b> · {TYPE_NAME[p.type].toLowerCase()}</span>
</p>
<dl class="facts">
	<dt>Type</dt>
	<dd>{TYPE_NAME[p.type]}</dd>
	<dt>Look</dt>
	<dd>{lookWord(p.look)} <span class="how">{p.look === 'open' ? 'you can see through it' : 'you cannot see through it'}</span></dd>
	{#if material}
		<dt>Material</dt>
		<dd>{material}</dd>
	{/if}
	<dt>Height</dt>
	<dd><span class="num">{p.hs === 'tagged' ? '' : 'about '}{metresFeet(p.h)}</span> <span class="how">{heightNote(p.hs)}</span></dd>
	<dt>Length</dt>
	<dd class="num">{lengthText(p.len)}</dd>
	<dt>Source</dt>
	<dd>{MAPPED_NOTE}</dd>
</dl>
<p class="explain">Only what contributors have mapped is here. Most backyard fences aren't mapped yet, and a mapped fence doesn't tell you who owns the land on either side.</p>
<p class="credit">© OpenStreetMap contributors (ODbL). The look is read from the tags and the height is estimated by type where none is tagged: neither is a survey.</p>

<style>
	.kind-line {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 4px;
		color: var(--ink);
	}
	.explain {
		margin: 8px 0;
		font-size: 12px;
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
</style>
