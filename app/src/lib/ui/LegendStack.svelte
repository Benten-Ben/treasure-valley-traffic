<script lang="ts">
	import { layerIcon } from '#lib/layers/icons.js';
	import type { AppCtx } from '#lib/app/context.js';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import type { LayerDef, LayerId } from '#lib/layers/types.js';
	import Icon from './Icon.svelte';
	import { CARET_DOWN } from './chrome-icons.js';
	import { inTray, LANDSCAPE } from './LandscapeTray.svelte';
	import { slots } from './slots.svelte.js';

	/**
	 * The legend stack (docs/14 §14.3): one legend per layer that's on. The most
	 * recently turned-on layer's is expanded; the others collapse to one-line
	 * rows that expand on click. A loading layer says so ("Loading routes…");
	 * a failed one says why and offers Retry. Each legend is its own panel
	 * boundary.
	 *
	 * The Landscape tray's layers that are on share one "Landscape" card (S3b): a section per layer, each
	 * its module's own legend, with the section of the most recently turned-on layer open.
	 */
	let { app, collapsed = false }: { app: AppCtx; collapsed?: boolean } = $props();
	const manager = $derived(app.layers);
	/** A row the viewer opened (or, with id null, closed), until another layer is turned on. */
	let override = $state<{ id: LayerId | 'landscape' | null; focus: LayerId | null } | null>(null);
	const focus = $derived(manager.focus);
	const expanded = $derived(override && override.focus === focus ? override.id : collapsed ? null : focus);
	const shown = $derived(manager.defs.filter((d) => manager.isOn(d.id) && !inTray(d)));
	const landscape = $derived(manager.defs.filter((d) => manager.isOn(d.id) && inTray(d)));
	/** The card is open when the most recently turned-on layer is in it (or the viewer opened it). */
	const landscapeOpen = $derived(expanded === 'landscape' || (expanded !== null && landscape.some((d) => d.id === expanded)));
	/** The section open inside the card: the viewer's pick, else the most recently turned-on tray layer. */
	let section = $state<{ id: LayerId | null; focus: LayerId | null } | null>(null);
	const sectionOpen = $derived(
		section && section.focus === focus ? (section.id !== null && landscape.some((d) => d.id === section!.id) ? section.id : null) : (landscape.find((d) => d.id === focus)?.id ?? landscape.at(-1)?.id ?? null)
	);

	function expand(id: LayerId) {
		override = { id: expanded === id ? null : id, focus };
	}
	function expandLandscape() {
		override = { id: landscapeOpen ? null : 'landscape', focus };
	}
	function openSection(id: LayerId) {
		section = { id: sectionOpen === id ? null : id, focus };
	}
</script>

{#snippet legendOf(d: LayerDef)}
	{@const mod = manager.modules[d.id]}
	{#if mod?.Legend}
		{#if manager.status(d.id) === 'stale' && manager.error(d.id)}
			<p class="stale" role="alert">▲ {manager.error(d.id)} <button class="pill small" onclick={() => manager.retry(d.id)}>Retry</button></p>
		{/if}
		<PanelBoundary name="{d.title} legend">
			<mod.Legend module={mod} />
		</PanelBoundary>
	{/if}
{/snippet}

{#if shown.length || landscape.length || slots.items('legend').length}
	<div class="stack" aria-label="Legends">
		{#each shown as d (d.id)}
			{@const status = manager.status(d.id)}
			{@const mod = manager.modules[d.id]}
			{@const open = expanded === d.id}
			<section class="legend card" class:open aria-label="{d.title} legend">
				<button class="row" aria-expanded={open} onclick={() => expand(d.id)}>
					<Icon icon={layerIcon(d)} size={18} />
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
					<div class="body">{@render legendOf(d)}</div>
				{/if}
			</section>
		{/each}
		{#if landscape.length}
			<section class="legend card" class:open={landscapeOpen} aria-label="Landscape legend" data-legend="landscape">
				<button class="row" aria-expanded={landscapeOpen} onclick={expandLandscape}>
					<Icon icon={LANDSCAPE} size={18} />
					<span class="name">Landscape</span>
					<span class="state">{landscape.length} on</span>
					<span class="caret" class:up={landscapeOpen} aria-hidden="true"><Icon icon={CARET_DOWN} size={14} /></span>
				</button>
				{#if landscapeOpen}
					<div class="body sections">
						{#each landscape as d (d.id)}
							{@const status = manager.status(d.id)}
							{@const mod = manager.modules[d.id]}
							{@const open = sectionOpen === d.id}
							<section class="part" class:open aria-label="{d.title} legend" data-legend={d.id}>
								<button class="part-row" aria-expanded={open} onclick={() => openSection(d.id)}>
									<Icon icon={layerIcon(d)} size={16} />
									<span class="name">{d.title}</span>
									{#if status === 'loading' || status === 'idle'}
										<span class="state" role="status"><span class="spin" aria-hidden="true"></span>{d.loadingText ?? 'Loading…'}</span>
									{:else if status === 'error'}
										<span class="state bad">▲ Failed</span>
									{:else if status === 'stale'}
										<span class="state bad">▲ Stale</span>
									{/if}
									<span class="caret" class:up={open} aria-hidden="true"><Icon icon={CARET_DOWN} size={12} /></span>
								</button>
								{#if status === 'error'}
									<div class="problem" role="alert">
										<p>{manager.error(d.id) ?? `${d.title} failed to load.`}</p>
										<button class="pill" onclick={() => manager.retry(d.id)}>Retry</button>
									</div>
								{:else if open && mod?.Legend && (status === 'ready' || status === 'stale')}
									{@render legendOf(d)}
								{/if}
							</section>
						{/each}
					</div>
				{/if}
			</section>
		{/if}
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
		/* Scroll shadows: an ink shadow at an edge with more to scroll to. The panel-colored covers
		   scroll with the content and hide the shadow once an end is reached (no script needed). */
		background:
			linear-gradient(var(--panel) 40%, transparent) top / 100% 32px no-repeat local,
			linear-gradient(transparent, var(--panel) 60%) bottom / 100% 32px no-repeat local,
			radial-gradient(farthest-side at 50% 0, rgb(43 42 51 / 0.24), transparent) top / 100% 12px no-repeat scroll,
			radial-gradient(farthest-side at 50% 100%, rgb(43 42 51 / 0.24), transparent) bottom / 100% 12px no-repeat scroll,
			var(--panel);
	}
	.sections {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.part {
		border-top: 2px solid var(--panel-edge);
	}
	.part:first-child {
		border-top: 0;
	}
	.part-row {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		padding: 6px 0;
		border: 0;
		background: none;
		color: var(--ink);
		font: 600 13px var(--font-display);
		text-align: left;
		cursor: pointer;
	}
	.part-row:focus-visible {
		outline: 2px solid var(--ink);
		outline-offset: 2px;
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
