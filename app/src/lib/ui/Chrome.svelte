<script lang="ts">
	import type { AppCtx } from '#lib/app/context.js';
	import type { Shell as ShellComponent, WithShellSlot } from './shell-slot.js';

	/**
	 * The chrome's loader. The chrome itself (ChromeShell: top bar, toolbar,
	 * legends, inspect card, keys) is its own chunk, so the initial
	 * JavaScript stays within its budget (docs/14 §14.9: 330 KB gzip with
	 * MapLibre's 280 and the overlay). Imported only here, it arrived after
	 * the map's first frame; src/hooks.client.ts starts loading it as the
	 * app's entry runs, alongside MapLibre's chunk (shell-slot.ts). When it
	 * has arrived, the shell mounts at once, with the layout and before the
	 * map exists, so it paints first (the `tvt:shell` mark); otherwise when
	 * it arrives (or, after a navigation from another page, when this import
	 * brings it). If it can't load, the map still works.
	 */
	let { app }: { app: AppCtx } = $props();
	const slot = (globalThis as WithShellSlot).__tvtShell;
	const ready = slot?.loaded ?? null;
	let Shell = $state.raw<ShellComponent | null>(ready);
	let failed = $state(false);
	if (!ready)
		(slot?.loading ?? import('./ChromeShell.svelte').then((m) => m.default)).then(
			(c) => (Shell = c),
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
