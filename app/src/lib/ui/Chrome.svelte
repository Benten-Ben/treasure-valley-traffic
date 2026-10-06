<script lang="ts">
	import type { Component } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';

	/**
	 * The chrome's loader. The chrome itself (ChromeShell: top bar, toolbar,
	 * legends, inspect card, keys) is its own chunk, imported at once: it
	 * arrives while the manifest, the style and the first tiles are still on
	 * their way, so the shell still paints before the map, and the initial
	 * JavaScript stays within its budget (docs/14 §14.9: 330 KB gzip with
	 * MapLibre's 280 and the overlay). If it can't load, the map still works.
	 */
	let { app }: { app: AppCtx } = $props();
	let Shell = $state.raw<Component<{ app: AppCtx }> | null>(null);
	let failed = $state(false);
	import('./ChromeShell.svelte').then(
		(m) => (Shell = m.default),
		(e) => {
			console.error('The map chrome failed to load', e);
			failed = true;
		}
	);
</script>

{#if Shell}
	<Shell {app} />
{:else if failed}
	<p class="failed card" role="alert">The map's controls failed to load. <button class="pill" onclick={() => location.reload()}>Reload</button></p>
{/if}

<style>
	.failed {
		position: absolute;
		left: 50%;
		bottom: 16px;
		z-index: 70;
		transform: translateX(-50%);
		margin: 0;
		padding: 8px 12px;
	}
</style>
