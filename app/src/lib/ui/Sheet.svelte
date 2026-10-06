<script lang="ts">
	import type { Snippet } from 'svelte';
	import { slots } from './slots.svelte.js';

	/**
	 * Stub (WP2): the phone bottom sheet (docs/14 §14.3, under 600 px) that
	 * holds the legends and the inspect card. WP3 replaces this file with the
	 * real sheet (snap points 25%, 55%, 90%; camera tabs); this stub is a
	 * panel above the tab bar that opens and closes.
	 */
	let { children, label = 'Details' }: { children: Snippet; label?: string } = $props();
	let open = $state(true);
</script>

<section class="sheet card" class:open aria-label={label}>
	<button class="handle" aria-expanded={open} onclick={() => (open = !open)}>
		<span class="bar" aria-hidden="true"></span>
		<span class="sr">{open ? 'Hide details' : 'Show details'}</span>
	</button>
	{#if open}
		<div class="content">
			{@render children()}
			{#each slots.items('sheet') as it (it.id)}<it.component {...it.props} />{/each}
		</div>
	{/if}
</section>

<style>
	.sheet {
		display: flex;
		flex-direction: column;
		max-height: 32vh;
		border-radius: 20px 20px 16px 16px;
		overflow: hidden;
	}
	.handle {
		display: grid;
		place-items: center;
		min-height: 28px;
		border: 0;
		background: none;
		cursor: pointer;
	}
	.bar {
		width: 40px;
		height: 5px;
		border-radius: 3px;
		background: var(--panel-edge);
	}
	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}
	.content {
		overflow-y: auto;
		padding: 0 8px 8px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
</style>
