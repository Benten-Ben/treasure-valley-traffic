<script lang="ts">
	import type { AppCtx } from '#lib/app/context.js';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import type { LayerId } from '#lib/layers/types.js';
	import Icon from './Icon.svelte';
	import { CARET_DOWN } from './chrome-icons.js';
	import { slots } from './slots.svelte.js';

	/**
	 * The legend stack (docs/14 §14.3): one legend per layer that's on. The most
	 * recently turned-on layer's is expanded; the others collapse to one-line
	 * rows that expand on click. A loading layer says so ("Loading routes…");
	 * a failed one says why and offers Retry. Each legend is its own panel
	 * boundary.
	 */
	let { app, collapsed = false }: { app: AppCtx; collapsed?: boolean } = $props();
	const manager = $derived(app.layers);
	/** A row the viewer opened (or, with id null, closed), until another layer is turned on. */
	let override = $state<{ id: LayerId | null; focus: LayerId | null } | null>(null);
	const focus = $derived(manager.focus);
	const expanded = $derived(override && override.focus === focus ? override.id : collapsed ? null : focus);
	const shown = $derived(manager.defs.filter((d) => manager.isOn(d.id)));

	function expand(id: LayerId) {
		override = { id: expanded === id ? null : id, focus };
	}
</script>

{#if shown.length || slots.items('legend').length}
	<div class="stack" aria-label="Legends">
		{#each shown as d (d.id)}
			{@const status = manager.status(d.id)}
			{@const mod = manager.modules[d.id]}
			{@const open = expanded === d.id}
			<section class="legend card" class:open aria-label="{d.title} legend">
				<button class="row" aria-expanded={open} onclick={() => expand(d.id)}>
					<Icon icon={d.icon} size={18} />
					<span class="name">{d.title}</span>
					{#if status === 'loading' || status === 'idle'}
						<span class="state" role="status"><span class="spin" aria-hidden="true"></span>{d.loadingText ?? 'Loading…'}</span>
					{:else if status === 'error'}
						<span class="state bad">▲ Failed</span>
					{:else if status === 'stale'}
						<span class="state bad">▲ Stale</span>
					{/if}
					<span class="caret" class:up={open} aria-hidden="true"><Icon icon={CARET_DOWN} size={14} /></span>
				</button>
				{#if status === 'error'}
					<div class="problem" role="alert">
						<p>{manager.error(d.id) ?? `${d.title} failed to load.`}</p>
						<button class="pill" onclick={() => manager.retry(d.id)}>Retry</button>
					</div>
				{:else if open && mod?.Legend && (status === 'ready' || status === 'stale')}
					<div class="body">
						{#if status === 'stale' && manager.error(d.id)}
							<p class="stale" role="alert">▲ {manager.error(d.id)} <button class="pill small" onclick={() => manager.retry(d.id)}>Retry</button></p>
						{/if}
						<PanelBoundary name="{d.title} legend">
							<mod.Legend module={mod} />
						</PanelBoundary>
					</div>
				{/if}
			</section>
		{/each}
		{#each slots.items('legend') as it (it.id)}
			<PanelBoundary name={it.id}><it.component {...it.props} /></PanelBoundary>
		{/each}
	</div>
{/if}

<style>
	.stack {
		display: flex;
		flex-direction: column;
		gap: 8px;
		max-height: 100%;
		overflow-y: auto;
		padding: 2px 4px 6px 2px;
	}
	.legend {
		flex: none;
		padding: 0;
		overflow: hidden;
		font-size: 13px;
	}
	.legend.open {
		flex: 0 1 auto;
		min-height: 0;
		display: flex;
		flex-direction: column;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		padding: 8px 12px;
		border: 0;
		background: none;
		color: var(--ink);
		font: 600 14px var(--font-display);
		text-align: left;
		cursor: pointer;
	}
	.row:focus-visible {
		outline: 2px solid var(--ink);
		outline-offset: -4px;
	}
	.name {
		flex: 1;
	}
	.state {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font: 12px var(--font-body);
		color: var(--ink-soft);
	}
	.state.bad {
		color: var(--ink);
	}
	.spin {
		width: 10px;
		height: 10px;
		border: 2px solid var(--panel-edge);
		border-top-color: var(--accent-2);
		border-radius: 50%;
		animation: spin 0.9s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.spin {
			border-style: dashed;
		}
	}
	.caret {
		display: inline-flex;
		transition: transform 120ms;
	}
	.caret.up {
		transform: rotate(180deg);
	}
	.body {
		padding: 0 12px 10px;
		overflow-y: auto;
		min-height: 0;
	}
	.problem {
		padding: 0 12px 10px;
	}
	.problem p,
	.stale {
		margin: 0 0 8px;
		font-size: 12px;
	}
	.small {
		padding: 2px 10px;
		font-size: 12px;
	}
</style>
