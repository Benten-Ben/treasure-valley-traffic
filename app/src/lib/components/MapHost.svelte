<script lang="ts">
	import 'maplibre-gl/dist/maplibre-gl.css';
	import type { Map } from 'maplibre-gl';
	import { onMount } from 'svelte';
	import type { App } from '#lib/app/app.svelte.js';
	import * as boot from '#lib/app/boot.js';
	import { createMap, MapUnavailable } from '#lib/map/create.js';

	/**
	 * The one map (docs/14 §14.8). The `(map)` layout mounts this once, so the
	 * map is created once per visit and survives every page change inside the
	 * layout: calibrating and coming back finds the same map, its tiles and
	 * its exact view. It opens at the view module's first view (URL, then
	 * saved, then the manifest's default) and hands the map to the app
	 * context.
	 */
	let { app }: { app: App } = $props();

	let container: HTMLDivElement;
	const hasImagery = $derived(Boolean(app.manifest?.imagery));

	// Entering a mode (look-through, calibrate) folds the open credits card back to its (i),
	// as MapLibre does on the first drag: the mode's banner takes the bottom of the screen,
	// and the card would sit under it (WP15's review). The (i) still opens it.
	$effect(() => {
		if (app.modes.current === 'explore') return;
		container?.querySelector('.maplibregl-ctrl-attrib.maplibregl-compact-show')?.classList.remove('maplibregl-compact-show');
	});

	onMount(() => {
		let gone = false;
		let map: Map | undefined;
		(async () => {
			const result = await boot.manifest;
			if (gone) return;
			if (!result.ok) return app.unavailable(result.reason);
			const first = app.view.initial(result.manifest);
			try {
				const made = await createMap(container, {
					manifest: result.manifest,
					center: first.view.center,
					zoom: first.view.zoom,
					bearing: first.view.bearing,
					pitch: first.view.pitch
				});
				if (gone) return made.map.remove();
				map = made.map;
				app.attach(map, made.manifest);
				// An old `#z/lat/lng/…` link: rewrite it once, in the new form.
				if (first.legacy) void app.styleReady.then(() => app.view.writeNow());
			} catch (e) {
				app.unavailable(e instanceof MapUnavailable ? e.message : `The map failed to start: ${e}`, 'error');
			}
		})();
		return () => {
			gone = true;
			app.detach();
			map?.remove();
		};
	});
</script>

<div class="map" bind:this={container}></div>

{#if hasImagery}
	<div class="views card" class:in-mode={app.modes.current !== 'explore'} role="group" aria-label="Map view">
		<button aria-pressed={!app.aerial} onclick={() => app.setAerial(false)}>Map</button>
		<button aria-pressed={app.aerial} onclick={() => app.setAerial(true)}>Aerial</button>
	</div>
{/if}

{#if app.problem}
	<div class="problem card" role="alert">{app.problem}</div>
{/if}

{#if app.paused}
	<div class="problem card" role="alert">
		<p><strong>Map paused.</strong> The browser took back the map's graphics memory. It usually resumes by itself.</p>
		<button class="pill" onclick={() => location.reload()}>Reload</button>
	</div>
{/if}

<style>
	.map {
		position: absolute;
		inset: 0;
	}
	.views {
		position: absolute;
		top: 10px;
		right: 52px;
		z-index: 40;
		display: flex;
		gap: 2px;
		padding: 3px;
		border-radius: 12px;
	}
	.views button {
		border: 0;
		border-radius: 9px;
		padding: 5px 12px;
		background: transparent;
		color: var(--ink);
		font: 600 13px var(--font-body);
		cursor: pointer;
	}
	.views button[aria-pressed='true'] {
		background: var(--ink);
		color: var(--panel);
	}
	/* On narrow screens a mode's panel takes the top of the screen. */
	@media (max-width: 899px) {
		.views.in-mode {
			display: none;
		}
	}
	.problem {
		position: absolute;
		top: 50%;
		left: 50%;
		z-index: 60;
		transform: translate(-50%, -50%);
		box-sizing: border-box;
		width: max-content;
		max-width: min(32rem, calc(100% - 2rem));
		padding: 1rem 1.25rem;
	}
	.problem p {
		margin: 0 0 10px;
	}
</style>
