<script lang="ts">
	import 'maplibre-gl/dist/maplibre-gl.css';
	import type { Map } from 'maplibre-gl';
	import { onMount } from 'svelte';
	import { createMap, MapUnavailable, type MapOptions } from '#lib/map/create.js';
	import {
		BUILDINGS_LAYER,
		buildingOpacity,
		IMAGERY_LAYERS,
		type BasemapManifest
	} from '#lib/map/style.js';

	let {
		options = { hash: true },
		showViewSwitch = true,
		onready
	}: {
		options?: MapOptions;
		showViewSwitch?: boolean;
		onready?: (map: Map, manifest: BasemapManifest) => void;
	} = $props();

	let container: HTMLDivElement;
	let problem = $state<string | null>(null);
	let hasImagery = $state(false);
	let aerial = $state(false);
	let map: Map | undefined;

	function setAerial(on: boolean) {
		aerial = on;
		for (const id of IMAGERY_LAYERS) {
			if (map?.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		}
		if (map?.getLayer(BUILDINGS_LAYER)) {
			map.setPaintProperty(BUILDINGS_LAYER, 'fill-extrusion-opacity', buildingOpacity(on));
		}
	}

	onMount(() => {
		let cancelled = false;
		(async () => {
			try {
				const made = await createMap(container, options);
				if (cancelled) return made.map.remove();
				map = made.map;
				hasImagery = Boolean(made.manifest.imagery);
				aerial = Boolean(options.aerial && hasImagery);
				map.once('load', () => map && onready?.(map, made.manifest));
			} catch (e) {
				problem = e instanceof MapUnavailable ? e.message : `The map failed to load: ${e}`;
			}
		})();
		return () => {
			cancelled = true;
			map?.remove();
		};
	});
</script>

<div class="map" bind:this={container}></div>
{#if hasImagery && showViewSwitch}
	<div class="views card" role="group" aria-label="Map view">
		<button aria-pressed={!aerial} onclick={() => setAerial(false)}>Map</button>
		<button aria-pressed={aerial} onclick={() => setAerial(true)}>Aerial</button>
	</div>
{/if}
{#if problem}
	<div class="problem card" role="alert">{problem}</div>
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
	.problem {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		max-width: min(32rem, calc(100% - 2rem));
		padding: 1rem 1.25rem;
	}
</style>
