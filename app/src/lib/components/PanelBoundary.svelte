<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * A panel's error boundary (docs/14 §14.3, "Loading, errors and honesty"):
	 * each legend, card and the calibrator sits in its own, so one failing
	 * panel shows "This panel failed: reload it" while the map and every other
	 * panel carry on.
	 */
	let { name, children }: { name: string; children: Snippet } = $props();

	function report(error: unknown) {
		console.warn(`${name} failed:`, error);
	}
</script>

<svelte:boundary onerror={report}>
	{@render children()}
	{#snippet failed(error, reset)}
		<div class="failed card" role="alert">
			<p>{name}: this panel failed.</p>
			<p class="why">{error instanceof Error ? error.message : String(error)}</p>
			<button class="pill" onclick={reset}>Reload it</button>
		</div>
	{/snippet}
</svelte:boundary>

<style>
	.failed {
		position: relative;
		z-index: 20;
		max-width: 320px;
		padding: 10px 14px;
		font-size: 13px;
	}
	.failed p {
		margin: 0 0 6px;
	}
	.why {
		color: var(--ink-soft);
		font-size: 12px;
	}
</style>
