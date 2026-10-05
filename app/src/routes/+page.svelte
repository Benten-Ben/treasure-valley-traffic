<script lang="ts">
	import type { Map } from 'maplibre-gl';
	import ValleyMap from '#lib/components/ValleyMap.svelte';
	import { addCameraLayer, type CameraCounts, type CameraProps } from '#lib/map/cameras.js';
	import { drape, imageData } from '#lib/calibration/drape.js';
	import { footprint, type ImageSize, type Pose } from '#lib/calibration/solver.js';

	type Calibration = { calibrationId: number; pose: Pose; size: ImageSize; groundZ: number; frame: string };

	let selected = $state<CameraProps | null>(null);
	let counts = $state<CameraCounts | null>(null);
	let cameraProblem = $state<string | null>(null);
	let calibrations = $state<Calibration[]>([]);
	let showImages = $state(false);
	let draped = false;
	let theMap: Map | undefined;

	async function ready(map: Map) {
		theMap = map;
		const r = await addCameraLayer(map, (c) => (selected = c));
		if ('error' in r) {
			cameraProblem = r.error;
			return;
		}
		counts = r.counts;
		// View cones for calibrated cameras, under the camera nodes.
		const res = await fetch('/api/calibrations');
		if (!res.ok) return;
		const cones = await res.json();
		calibrations = cones.features.map((f: { properties: Calibration }) => f.properties);
		map.addSource('cones', { type: 'geojson', data: cones });
		map.addLayer({ id: 'cones-fill', type: 'fill', source: 'cones',
			paint: { 'fill-color': '#2c8c99', 'fill-opacity': 0.14 } }, 'cameras-no-image');
		map.addLayer({ id: 'cones-line', type: 'line', source: 'cones',
			paint: { 'line-color': '#2c8c99', 'line-width': 1.5, 'line-opacity': 0.8 } }, 'cameras-no-image');
	}

	/** Drape each calibrated camera's reference frame onto the ground under its cone. */
	async function toggleImages() {
		const map = theMap;
		if (!map) return;
		if (!draped && showImages) {
			draped = true;
			for (const c of calibrations) {
				const pixels = await imageData(`/frames/${c.frame}`);
				const d = drape(c.pose, c.size, pixels, c.groundZ, footprint(c.pose, c.size, c.groundZ, 200));
				if (!d) continue;
				map.addSource(`drape-${c.calibrationId}`, { type: 'image', url: d.url, coordinates: d.coordinates });
				map.addLayer({ id: `drape-${c.calibrationId}`, type: 'raster', source: `drape-${c.calibrationId}`,
					paint: { 'raster-fade-duration': 0 } }, 'cones-fill');
			}
		}
		for (const c of calibrations)
			if (map.getLayer(`drape-${c.calibrationId}`))
				map.setLayoutProperty(`drape-${c.calibrationId}`, 'visibility', showImages ? 'visible' : 'none');
	}

	const statusText = {
		calibrated: 'Calibrated',
		uncalibrated: 'Needs calibration',
		no_image: 'No camera image linked yet'
	};
</script>

<svelte:head>
	<title>Treasure Valley Traffic</title>
</svelte:head>

<main>
	<ValleyMap onready={ready} />

	<header class="card">
		<h1>Treasure Valley</h1>
		{#if counts}
			<p class="num">
				{counts.calibrated + counts.uncalibrated + counts.no_image} cameras · {counts.calibrated} calibrated
			</p>
		{/if}
	</header>

	{#if counts}
		<aside class="legend card" aria-label="Camera legend">
			<span><i class="dot calibrated"></i>Calibrated</span>
			<span><i class="dot uncalibrated"></i>Needs calibration</span>
			<span><i class="dot no-image"></i>No image yet</span>
			{#if calibrations.length}
				<span><i class="cone"></i>View cone (calibrated)</span>
				<label><input type="checkbox" bind:checked={showImages} onchange={toggleImages} /> Camera images on the map</label>
			{/if}
		</aside>
	{/if}

	{#if cameraProblem}
		<p class="notice card" role="alert">{cameraProblem}</p>
	{/if}

	{#if selected}
		<section class="camera card" aria-label="Selected camera">
			<button class="close" aria-label="Close" onclick={() => (selected = null)}>×</button>
			<h2>{selected.name}</h2>
			<p class="meta">
				<i class="dot {selected.status.replace('_', '-')}"></i>{statusText[selected.status]}
				{#if selected.achdCamId}<span class="num"> · ACHD #{selected.achdCamId}</span>{/if}
			</p>
			{#if selected.status !== 'no_image'}
				<a class="pill primary" href={`/calibrate/${selected.id}`}>
					{selected.status === 'calibrated' ? 'Review calibration' : 'Calibrate'}
				</a>
			{/if}
		</section>
	{/if}
</main>

<style>
	main {
		position: fixed;
		inset: 0;
	}
	header {
		position: absolute;
		top: 10px;
		left: 10px;
		padding: 8px 14px;
	}
	h1 {
		margin: 0;
		font: 600 20px var(--font-display);
	}
	header p {
		margin: 0;
		font-size: 12px;
		color: var(--ink-soft);
	}
	.legend {
		position: absolute;
		left: 10px;
		bottom: 36px;
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 8px 12px;
		font-size: 13px;
	}
	.dot {
		display: inline-block;
		width: 10px;
		height: 10px;
		border-radius: 50%;
		margin-right: 8px;
		vertical-align: -1px;
	}
	.dot.calibrated {
		background: var(--accent-2);
		box-shadow: 0 0 0 2px var(--panel), 0 0 0 3px var(--accent-2);
	}
	.dot.uncalibrated {
		background: var(--panel);
		box-shadow: inset 0 0 0 2.5px var(--accent);
	}
	.cone {
		display: inline-block;
		width: 0;
		height: 0;
		margin-right: 6px;
		border-left: 6px solid transparent;
		border-right: 6px solid transparent;
		border-bottom: 11px solid rgb(44 140 153 / 0.45);
		vertical-align: -1px;
	}
	.legend label {
		font-size: 12px;
		margin-top: 4px;
	}
	.dot.no-image {
		width: 7px;
		height: 7px;
		background: #9a958c;
	}
	.notice {
		position: absolute;
		top: 70px;
		left: 10px;
		margin: 0;
		padding: 8px 12px;
	}
	.camera {
		position: absolute;
		right: 10px;
		bottom: 36px;
		width: min(320px, calc(100% - 20px));
		padding: 14px 16px;
	}
	.camera h2 {
		margin: 0 24px 2px 0;
		font: 600 18px var(--font-display);
	}
	.meta {
		margin: 0 0 12px;
		font-size: 13px;
		color: var(--ink-soft);
	}
	.close {
		position: absolute;
		top: 6px;
		right: 8px;
		border: 0;
		background: none;
		font-size: 22px;
		cursor: pointer;
		color: var(--ink-soft);
	}
	a.pill {
		display: inline-block;
		text-decoration: none;
		border: 2px solid #d68d00;
		border-radius: 999px;
		padding: 6px 16px;
		background: var(--accent);
		color: var(--ink);
		font: 600 14px var(--font-body);
		box-shadow: 0 3px 0 rgb(60 45 20 / 0.14);
	}
</style>
