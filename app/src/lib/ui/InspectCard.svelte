<script lang="ts">
	import { onDestroy } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import type { LayerId, Selection } from '#lib/layers/types.js';
	import Badge from './Badge.svelte';
	import { ESC, onEscape } from './keys.js';
	import { slots } from './slots.svelte.js';

	/**
	 * The docked inspect card (docs/14 §14.3): bus, stop, road, route and camera
	 * cards share it, each drawn by its layer's Card. Where several routes share
	 * the street, it lists them ("3 routes here: 7 · 8 · 9"), each opening its
	 * own card. Esc closes it (after help, popovers, windows and modes).
	 */
	let { app }: { app: AppCtx } = $props();
	const sel = $derived(app.selection.current);
	const mod = $derived(sel ? app.layers.modules[sel.layer as LayerId] : undefined);

	const LABEL: Record<string, string> = {
		bus: 'Selected bus',
		camera: 'Selected camera',
		street: 'Selected road',
		route: 'Selected route',
		routes: 'Routes here',
		stop: 'Selected stop',
		hub: 'Selected station',
		lane: 'Selected lane',
		weather: 'Selected station',
		tree: 'Selected tree',
		sprite: 'Selected marker'
	};

	const stop = onEscape(ESC.inspect, () => {
		if (!app.selection.current) return false;
		app.selection.clear();
		return true;
	});
	onDestroy(stop);

	function open(s: Selection) {
		app.selection.select(s);
	}
</script>

{#if sel}
	<section class="inspect card" aria-label={LABEL[sel.kind] ?? 'Selected'}>
		<button class="close" aria-label="Close" onclick={() => app.selection.clear()}>×</button>
		<PanelBoundary name="Card">
			{#if sel.kind === 'routes' && sel.items}
				<h2>{sel.items.length} routes here</h2>
				<p class="meta">They share this street. Pick one:</p>
				<ul class="many">
					{#each sel.items as it (it.layer + it.id)}
						<li>
							<button class="pick" onclick={() => open(it)}>
								{#if it.badge}<Badge badge={it.badge} />{/if}
								<span>{it.title}</span>
							</button>
						</li>
					{/each}
				</ul>
			{:else if mod?.Card}
				<mod.Card selection={sel} module={mod} />
			{:else}
				<h2>{sel.title}</h2>
				{#if sel.fact}<p class="meta">{sel.fact}</p>{/if}
				{#if sel.source}<p class="credit">{sel.source}</p>{/if}
			{/if}
		</PanelBoundary>
		{#each slots.items('inspect') as it (it.id)}
			<it.component {...it.props} selection={sel} />
		{/each}
	</section>
{/if}

<style>
	.inspect {
		position: relative;
		box-sizing: border-box;
		width: 100%;
		max-height: 100%;
		overflow-y: auto;
		padding: 14px 16px;
	}
	.close {
		position: absolute;
		top: 6px;
		right: 8px;
		width: 32px;
		height: 32px;
		border: 0;
		border-radius: 50%;
		background: none;
		font-size: 22px;
		line-height: 1;
		cursor: pointer;
		color: var(--ink-soft);
	}
	.close:hover {
		background: rgb(43 42 51 / 0.08);
	}
	.many {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.pick {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		padding: 4px 6px;
		border: 0;
		border-radius: 8px;
		background: none;
		font: 14px var(--font-body);
		color: var(--ink);
		text-align: left;
		cursor: pointer;
	}
	.pick:hover {
		background: rgb(43 42 51 / 0.08);
	}
</style>
