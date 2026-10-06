<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * Stub (WP2): a floating window's frame (docs/14 §14.6, "Camera windows").
	 * WP3 replaces this file with the real one (drag, resize, snap, dock
	 * buttons, number badge, pin). This stub is a plain non-modal card.
	 */
	let { title, onclose, children }: { title: string; onclose?: () => void; children: Snippet } = $props();
</script>

<div class="window card" role="dialog" aria-label={title}>
	<header>
		<h2>{title}</h2>
		{#if onclose}<button class="close" aria-label="Close {title}" onclick={onclose}>×</button>{/if}
	</header>
	{@render children()}
</div>

<style>
	.window {
		position: relative;
		width: 400px;
		max-width: 60vw;
		padding: 10px 14px;
		pointer-events: auto;
	}
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}
	h2 {
		margin: 0;
		font: 600 16px var(--font-display);
	}
	.close {
		border: 0;
		background: none;
		font-size: 20px;
		cursor: pointer;
		color: var(--ink-soft);
	}
</style>
