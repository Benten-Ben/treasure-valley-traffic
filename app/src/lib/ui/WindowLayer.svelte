<script lang="ts">
	import type { AppCtx } from '#lib/app/context.js';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import { slots } from './slots.svelte.js';

	/**
	 * Stub (WP2): the floating-window layer (band 30–39, kept inside the safe
	 * area below the top bar and above the toolbar). WP3 replaces this file
	 * with the window manager; until then it renders whatever is registered in
	 * the `windows` slot.
	 */
	let props: { app: AppCtx } = $props();
</script>

{#if slots.items('windows').length}
	<div class="windows">
		{#each slots.items('windows') as it (it.id)}
			<PanelBoundary name={it.id}><it.component {...it.props} /></PanelBoundary>
		{/each}
	</div>
{/if}

<style>
	.windows {
		position: absolute;
		top: 76px;
		left: 312px;
		right: 392px;
		bottom: 104px;
		z-index: 30;
		display: flex;
		flex-wrap: wrap;
		align-content: flex-start;
		gap: 12px;
		pointer-events: none;
	}
</style>
