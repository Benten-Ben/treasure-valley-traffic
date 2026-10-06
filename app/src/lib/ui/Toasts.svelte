<script lang="ts">
	import { updated } from '$app/state';
	import type { AppCtx } from '#lib/app/context.js';
	import { slots } from './slots.svelte.js';

	/**
	 * Stub (WP2): toasts (band 70). WP3 replaces this file with its toast API;
	 * until then it shows the new-version toast (SvelteKit's version polling,
	 * docs/14 §14.3) and anything registered in the `toasts` slot.
	 */
	let props: { app: AppCtx } = $props();
	let dismissed = $state(false);
</script>

<div class="toasts">
	{#if updated.current && !dismissed}
		<div class="toast card" role="status">
			<span>New version: reload when convenient.</span>
			<button class="pill" onclick={() => location.reload()}>Reload</button>
			<button class="close" aria-label="Dismiss" onclick={() => (dismissed = true)}>×</button>
		</div>
	{/if}
	{#each slots.items('toasts') as it (it.id)}<it.component {...it.props} />{/each}
</div>

<style>
	.toasts {
		position: absolute;
		left: 50%;
		bottom: 104px;
		z-index: 70;
		transform: translateX(-50%);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
		pointer-events: none;
	}
	.toast {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 10px 8px 16px;
		font-size: 14px;
		white-space: nowrap;
		pointer-events: auto;
	}
	.close {
		border: 0;
		background: none;
		font-size: 20px;
		cursor: pointer;
		color: var(--ink-soft);
	}
</style>
