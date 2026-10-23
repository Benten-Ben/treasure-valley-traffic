<script lang="ts">
	import type { LegendProps } from '../types.js';
	import { LINE_FROM_ZOOM, NOT_MAPPED_NOTE, WALLS_FROM_ZOOM } from './fences.js';
	import type { FencesModule } from './index.svelte.js';
	import { ESTIMATED, HALO, POST } from './palette.js';

	/**
	 * The Fences legend (plan §4.2 P10): a wall, a solid fence and a see-through one, each drawn as the map draws it, and
	 * a height from OpenStreetMap against one we estimated (named, never told by tone alone). Only what contributors have
	 * mapped is here.
	 */
	let { module }: LegendProps = $props();
	const fences = $derived(module as unknown as FencesModule);
	const view = $derived(fences.view);
</script>

<p class="legend-title">Fences</p>
<ul class="keys">
	<li>
		<svg viewBox="0 0 32 16" width="32" height="16" aria-hidden="true">
			<rect x="1" y="2" width="30" height="12" fill={POST} stroke={HALO} stroke-width="1" />
		</svg>
		<span><b>Wall</b>: a thick, solid bar (retaining walls too)</span>
	</li>
	<li>
		<svg viewBox="0 0 32 16" width="32" height="16" aria-hidden="true">
			<rect x="1" y="5" width="30" height="6" fill={POST} stroke={HALO} stroke-width="1" />
		</svg>
		<span><b>Solid fence</b>: you can't see through it</span>
	</li>
	<li>
		<svg viewBox="0 0 32 16" width="32" height="16" aria-hidden="true">
			<rect x="1" y="4" width="30" height="2" fill={POST} />
			<rect x="1" y="2" width="2" height="12" fill={POST} />
			<rect x="15" y="2" width="2" height="12" fill={POST} />
			<rect x="29" y="2" width="2" height="12" fill={POST} />
		</svg>
		<span><b>See-through fence</b>: posts and rails, or a chain link</span>
	</li>
</ul>
<ul class="keys heights" aria-label="Height">
	<li>
		<svg viewBox="0 0 32 16" width="32" height="16" aria-hidden="true">
			<rect x="1" y="3" width="30" height="10" fill={POST} />
		</svg>
		<span><b>Measured height</b>: tagged in OpenStreetMap (darker)</span>
	</li>
	<li>
		<svg viewBox="0 0 32 16" width="32" height="16" aria-hidden="true">
			<rect x="1" y="3" width="30" height="10" fill={ESTIMATED} stroke={POST} stroke-width="1" stroke-dasharray="3 2" />
		</svg>
		<span><b>Estimated height</b>: guessed from the type (paler, dashed edge)</span>
	</li>
</ul>
{#if view.phone}
	<p class="hint">3D walls are off on this screen; the line shows from z{LINE_FROM_ZOOM}.</p>
{:else}
	<p class="hint">A line from z{LINE_FROM_ZOOM}, low 3D walls from z{WALLS_FROM_ZOOM}. Click one for what we know about it.</p>
{/if}
{#if view.fences === 0}
	<p class="note">No mapped fences are loaded yet.</p>
{/if}
<p class="where">{NOT_MAPPED_NOTE}.</p>
<p class="credit">© OpenStreetMap contributors (ODbL)</p>

<style>
	li {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
	}
	svg {
		flex: none;
	}
	.heights {
		margin-top: 6px;
	}
	.note,
	.where {
		margin: 6px 0 0;
		font-size: 12px;
		color: var(--ink);
	}
</style>
