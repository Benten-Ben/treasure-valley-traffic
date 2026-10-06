<script lang="ts">
	import { onDestroy, type Component } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import type { LayerDef } from '#lib/layers/types.js';
	import { STACK } from './chrome-icons.js';
	import { ESC, onEscape } from './keys.js';
	import LayerButton from './LayerButton.svelte';

	/**
	 * The toolbar (docs/14 §14.3, "Layers and the toolbar"): the Base button at
	 * the left end, then a button per layer that exists. When it has focus,
	 * ← and → move between its buttons (roving tabindex). The Base popover
	 * loads the first time it opens.
	 */
	let { app, compact = false }: { app: AppCtx; compact?: boolean } = $props();
	const manager = $derived(app.layers);

	let buttons: HTMLButtonElement[] = $state([]);
	let current = $state(0);
	let baseOpen = $state(false);
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let Popover = $state<Component<any> | null>(null);

	async function toggleBase() {
		if (!Popover) Popover = (await import('./BasePopover.svelte')).default;
		baseOpen = !baseOpen;
	}

	const stopEsc = onEscape(ESC.popover, () => {
		if (!baseOpen) return false;
		baseOpen = false;
		buttons[0]?.focus();
		return true;
	});
	onDestroy(stopEsc);

	function roving(e: KeyboardEvent) {
		if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft' && e.key !== 'Home' && e.key !== 'End') return;
		e.preventDefault();
		e.stopPropagation();
		const n = buttons.filter(Boolean).length;
		if (!n) return;
		if (e.key === 'Home') current = 0;
		else if (e.key === 'End') current = n - 1;
		else current = (current + (e.key === 'ArrowRight' ? 1 : -1) + n) % n;
		buttons[current]?.focus();
	}

	function tipLines(d: LayerDef): string[] {
		const lines = [d.blurb];
		const m = manager.modules[d.id];
		const at = m?.updatedAt;
		lines.push(at ? `${d.source} · updated ${new Date(at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}` : d.source);
		return lines;
	}

	function outside(e: PointerEvent) {
		if (!baseOpen) return;
		const t = e.target as Element | null;
		if (t?.closest('.base-popover') || t?.closest('.base-button')) return;
		baseOpen = false;
	}
</script>

<svelte:window onpointerdown={outside} />

<div class="toolbar card" class:compact role="toolbar" aria-label="Map layers" tabindex="-1" onkeydown={roving}>
	<div class="base-button">
		<LayerButton
			bind:element={buttons[0]}
			label="Base"
			icon={STACK}
			expanded={baseOpen}
			controls="base-popover"
			tabindex={current === 0 ? 0 : -1}
			onfocus={() => (current = 0)}
			tip={{ title: 'Base', lines: ['Map look, aerial photos, buildings, terrain and labels'] }}
			onclick={toggleBase}
		/>
	</div>
	<span class="divider" aria-hidden="true"></span>
	{#each manager.defs as d, i (d.id)}
		{@const status = manager.status(d.id)}
		{@const why = manager.available(d.id)}
		<LayerButton
			bind:element={buttons[i + 1]}
			label={d.title}
			icon={d.icon}
			pressed={manager.isOn(d.id)}
			busy={manager.isOn(d.id) && status === 'loading'}
			problem={status === 'error' || status === 'stale' ? manager.error(d.id) ?? 'Something went wrong' : null}
			disabled={why === true ? null : why}
			tabindex={current === i + 1 ? 0 : -1}
			onfocus={() => (current = i + 1)}
			tip={{ title: d.key ? `${d.title} · key ${d.key}` : d.title, lines: tipLines(d) }}
			onclick={() => manager.toggle(d.id)}
		/>
	{/each}
	{#if baseOpen && Popover}
		<Popover {app} onclose={() => (baseOpen = false)} />
	{/if}
</div>

<style>
	.toolbar {
		position: relative;
		display: flex;
		align-items: flex-start;
		gap: 4px;
		padding: 10px 12px 6px;
		border-radius: 24px;
		min-height: 72px;
		box-sizing: border-box;
	}
	.toolbar:focus {
		outline: none;
	}
	.divider {
		align-self: center;
		width: 2px;
		height: 36px;
		margin: 0 4px 16px;
		border-radius: 1px;
		background: var(--panel-edge);
	}
	.compact :global(.label) {
		display: none;
	}
	.compact {
		min-height: 0;
		padding-bottom: 10px;
	}
</style>
