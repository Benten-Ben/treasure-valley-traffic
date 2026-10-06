<script lang="ts">
	import type { Component } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import Icon from './Icon.svelte';
	import { STACK } from './chrome-icons.js';
	import { slots } from './slots.svelte.js';

	/**
	 * Stub (WP2): the phone tab bar (docs/14 §14.3, under 600 px): a 64 px
	 * scrollable row of the layer buttons with labels, Base at its end. WP3
	 * replaces this file; this stub works, with no frills.
	 */
	let { app }: { app: AppCtx } = $props();
	const manager = $derived(app.layers);
	let baseOpen = $state(false);
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let Popover = $state<Component<any> | null>(null);

	async function toggleBase() {
		if (!Popover) Popover = (await import('./BasePopover.svelte')).default;
		baseOpen = !baseOpen;
	}
</script>

<nav class="tabbar card" aria-label="Map layers">
	{#each manager.defs as d (d.id)}
		{@const status = manager.status(d.id)}
		<button
			class="tab"
			aria-pressed={manager.isOn(d.id)}
			aria-busy={manager.isOn(d.id) && status === 'loading'}
			disabled={manager.available(d.id) !== true}
			onclick={() => manager.toggle(d.id)}
		>
			<Icon icon={d.icon} size={24} />
			<span>{d.title}{#if status === 'error'} ▲{/if}</span>
		</button>
	{/each}
	{#each slots.items('tabbar') as it (it.id)}<it.component {...it.props} />{/each}
	<button class="tab" aria-expanded={baseOpen} onclick={toggleBase}>
		<Icon icon={STACK} size={24} />
		<span>Base</span>
	</button>
	{#if baseOpen && Popover}
		<div class="pop"><Popover {app} onclose={() => (baseOpen = false)} /></div>
	{/if}
</nav>

<style>
	.tabbar {
		position: relative;
		display: flex;
		gap: 2px;
		height: 64px;
		box-sizing: border-box;
		padding: 4px;
		border-radius: 20px;
		overflow-x: auto;
		scrollbar-width: none;
	}
	.tab {
		flex: 1 0 64px;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 2px;
		min-width: 64px;
		min-height: 44px;
		border: 0;
		border-radius: 14px;
		background: none;
		color: var(--ink);
		font: 600 12px var(--font-body);
		cursor: pointer;
	}
	.tab[aria-pressed='true'] {
		background: var(--ink);
		color: var(--panel);
	}
	.tab:disabled {
		opacity: 0.45;
	}
	.pop {
		position: fixed;
		right: 8px;
		bottom: 84px;
		z-index: 50;
	}
	.pop :global(.base-popover) {
		position: static;
	}
</style>
