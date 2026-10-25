<script lang="ts">
	import type { LegendProps } from '../types.js';
	import type { TreesModule } from './index.svelte.js';
	import { LOOKS, LOOK_ABOUT, LOOK_NAME, SHRUB_CREDIT, SHRUB_EDGE, SHRUB_COLORS, SHRUB_LIMIT, SHRUBS_ZOOM, shrubsBuiltText } from './shrubs.js';
	import {
		areaName,
		builtText,
		DISC_EDGE,
		fmtCount,
		KIND_WORD,
		legendFor,
		TREE_GREENS,
		TREE_TONES,
		type TreeKind
	} from './trees.js';

	/**
	 * The Trees legend (docs/19 §19.6): the kinds in view, each drawn as the map
	 * draws it (by tone, with the discs' dark edge) and named, never told by
	 * color alone; the three
	 * shapes; when the view's trees were cut to the tallest; and where trees are
	 * built so far, with a way there when the view has none.
	 */
	let { module }: LegendProps = $props();
	const trees = $derived(module as unknown as TreesModule);
	const view = $derived(trees.view);
	const areas = $derived(trees.areas);

	const ABOUT: Record<TreeKind, string> = {
		catalogued: "in the City's inventory, measured by lidar",
		placed: 'found in the lidar; crown placed'
	};
	const LOOK: Record<TreeKind, string> = { catalogued: 'full green', placed: 'lighter' };
	/**
	 * The map's boxes send every tree as placed; only a tree's card says it is catalogued. So when the catalogue
	 * flag alone lists the entry (no catalogued tree in view), it says how to find one, with no tone and no count.
	 */
	const inView = (k: TreeKind) => k !== 'catalogued' || view.kinds.catalogued > 0;
	/** Catalogued shows once the catalogue answered (the API's flag) or a catalogued tree is in view. */
	const legend = $derived(legendFor(view.kinds, view.catalogue));
	const kinds = $derived(legend.kinds);
	const shrubs = $derived(view.shrubs);
	const shrubAreas = $derived(trees.shrubAreas);
	const shrubCount = (look: 'bush' | 'sage') => (look === 'bush' ? shrubs.bush : shrubs.sage);
</script>

<p class="legend-title">Trees</p>
<ul class="keys">
	{#each kinds as k (k)}
		<li>
			<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
				{#if inView(k)}
					<circle cx="10" cy="10" r="7.5" fill={TREE_TONES.broadleaf[k][1]} stroke={DISC_EDGE} stroke-width="1" />
				{:else}
					<!-- Listed by the catalogue flag alone: the map draws no tree in this tone, so no fill. -->
					<circle class="unfilled" cx="10" cy="10" r="7.5" fill="none" stroke={DISC_EDGE} stroke-width="1" stroke-dasharray="2 2" />
				{/if}
			</svg>
			{#if inView(k)}
				<span><b>{KIND_WORD[k]}</b> ({LOOK[k]}): {ABOUT[k]}{#if view.shown}{' '}<span class="num">({fmtCount(view.kinds[k])})</span>{/if}</span>
			{:else}
				<span><b>{KIND_WORD[k]}</b>: in the City's inventory, measured by lidar; a tree's card says when it is one</span>
			{/if}
		</li>
	{/each}
</ul>
<ul class="shapes" aria-label="Tree shapes">
	<li>
		<svg viewBox="0 0 20 22" width="16" height="18" aria-hidden="true">
			<rect x="9" y="12" width="2" height="9" fill="#785a3d" />
			<path d="M10 2 16.5 5.5 18 11 14 15.5H6L2 11 3.5 5.5Z" fill={TREE_GREENS.broadleaf[1]} />
		</svg>
		Broadleaf
	</li>
	<li>
		<svg viewBox="0 0 20 22" width="16" height="18" aria-hidden="true">
			<rect x="9" y="17" width="2" height="4" fill="#785a3d" />
			<path d="M10 1 15 9H5Z M10 5 17 13H3Z M10 9 19 18H1Z" fill={TREE_GREENS.conifer[1]} />
		</svg>
		Conifer
	</li>
	<li>
		<svg viewBox="0 0 20 22" width="16" height="18" aria-hidden="true">
			<rect x="9" y="16" width="2" height="5" fill="#785a3d" />
			<path d="M10 1 14 5 14.5 12 12 17H8L5.5 12 6 5Z" fill={TREE_GREENS.narrow[1]} />
		</svg>
		Narrow
	</li>
</ul>
{#if view.mode === 'far'}
	<p class="hint">Zoom in to see trees: crown discs from z13, 3D trees from z15.</p>
{:else}
	<p class="hint">3D trees from z15, crown discs farther out. Click a tree for what we know about it.</p>
{/if}
{#if view.problem}
	<p class="note" role="alert">▲ {view.problem}</p>
{/if}
{#if view.capped || view.truncated}
	<p class="note" data-capped={view.capped} data-truncated={view.truncated}>
		Showing the tallest {fmtCount(view.capped ? Math.min(view.cap, view.shown) : view.shown)} trees in view{view.capped ? ' in 3D (a cap that keeps the map smooth)' : ''}.
	</p>
{/if}
<p class="where" class:empty={!view.here}>
	{#if !view.here && areas.length}No trees here yet.{' '}{/if}{builtText(areas)}
</p>
{#if !view.here && areas.length}
	<div class="go">
		{#each areas as a (a.area)}
			<button class="pill small" onclick={() => trees.goTo(a)}>Go to {areaName(a.area)}</button>
		{/each}
	</div>
{/if}
<p class="legend-title shrubs-title">Shrubs</p>
<ul class="keys" aria-label="Shrubs">
	{#each LOOKS as look (look)}
		<li data-look={look}>
			<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
				{#if look === 'bush'}
					<path d="M2 16 C2 8 6 5 10 5 C14 5 18 8 18 16Z" fill={SHRUB_COLORS[look]} stroke={SHRUB_EDGE} stroke-width="1" />
				{:else}
					<path d="M1 16 C2 11 5 9 8 10 C9 7 13 7 14 10 C17 10 19 12 19 16Z" fill={SHRUB_COLORS[look]} stroke={SHRUB_EDGE} stroke-width="1" />
				{/if}
			</svg>
			<span><b>{LOOK_NAME[look]}</b>: {LOOK_ABOUT[look]}{#if shrubs.drawn}{' '}<span class="num">({fmtCount(shrubCount(look))})</span>{/if}</span>
		</li>
	{/each}
</ul>
{#if shrubs.phone}
	<p class="hint">Shrubs are off on phones.</p>
{:else}
	<p class="hint">Shrubs stand in 3D from z{SHRUBS_ZOOM}, the nearest {fmtCount(SHRUB_LIMIT)} to the middle of the map.</p>
{/if}
{#if shrubs.truncated}
	<p class="note" data-shrubs-truncated="true">Showing the {fmtCount(SHRUB_LIMIT)} shrubs nearest the middle of the map.</p>
{/if}
<p class="where">{shrubsBuiltText(shrubAreas, areaName)}</p>
<p class="credit">{legend.credit}</p>
<p class="credit">Shrubs: {SHRUB_CREDIT}.</p>

<style>
	li {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		font-size: 12px;
	}
	svg {
		flex: none;
		margin-top: 1px;
	}
	.shapes {
		display: flex;
		gap: 12px;
		margin: 6px 0 0;
		padding: 0;
		list-style: none;
	}
	.shapes li {
		align-items: center;
		gap: 4px;
	}
	.note,
	.where {
		margin: 6px 0 0;
		font-size: 12px;
		color: var(--ink);
	}
	.shrubs-title {
		margin-top: 10px;
	}
	.where.empty {
		font-weight: 600;
	}
	.go {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-top: 6px;
	}
	.small {
		padding: 2px 10px;
		font-size: 12px;
	}
</style>
