<script lang="ts">
	import type { Map } from 'maplibre-gl';
	import ValleyMap from '#lib/components/ValleyMap.svelte';
	import { onDestroy } from 'svelte';
	import { addCameraLayer, CAMERA_LAYERS, type CameraCounts, type CameraProps } from '#lib/map/cameras.js';
	import { ageText, isStale, stopText, TransitLayer, UNKNOWN_COLOR, type Vehicle } from '#lib/map/transit.js';
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

	// Lenses (docs/13 §13.5): what the map is about right now. Hotkeys follow the design's numbering.
	type Lens = 'transit' | 'cameras';
	const LENSES: { id: Lens; name: string; icon: string; key: string }[] = [
		{ id: 'transit', name: 'Transit', icon: '🚌', key: '4' },
		{ id: 'cameras', name: 'Cameras', icon: '📷', key: '7' }
	];
	const CAMERA_EXTRA = ['cameras-calibrated-check', 'cones-fill', 'cones-line'];
	let lens = $state<Lens>('cameras');
	let transit = $state.raw<TransitLayer | undefined>();
	let transitReady = $state(false);
	let transitProblem = $state<string | null>(null);
	let vehicles = $state<Vehicle[]>([]);
	let feedNow = $state(0);
	let busId = $state<string | null>(null);
	let spot = $state<string | null>(null);
	const bus = $derived(vehicles.find((v) => v.vehicleId === busId) ?? null);
	const live = $derived(vehicles.filter((v) => !isStale(v, feedNow)));
	const liveByRoute = $derived(
		live.reduce<Record<string, number>>((n, v) => ((n[v.routeId ?? '?'] = (n[v.routeId ?? '?'] ?? 0) + 1), n), {})
	);

	function setLens(next: Lens) {
		lens = next;
		try {
			localStorage.setItem('tvt-lens', next);
		} catch {
			/* per-viewer convenience only */
		}
		const map = theMap;
		if (!map) return;
		for (const id of [...CAMERA_LAYERS, ...CAMERA_EXTRA])
			if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', next === 'cameras' ? 'visible' : 'none');
		for (const c of calibrations)
			if (map.getLayer(`drape-${c.calibrationId}`))
				map.setLayoutProperty(`drape-${c.calibrationId}`, 'visibility', next === 'cameras' && showImages ? 'visible' : 'none');
		transit?.setVisible(next === 'transit');
		if (next !== 'cameras') selected = null;
		if (next !== 'transit') busId = null;
	}

	function onKey(e: KeyboardEvent) {
		if (e.target instanceof HTMLInputElement || e.metaKey || e.ctrlKey || e.altKey) return;
		const l = LENSES.find((x) => x.key === e.key);
		if (l) setLens(l.id);
	}

	function spotlight(routeId: string | null) {
		spot = routeId;
		transit?.spotlight(routeId);
	}

	async function addTransit(map: Map) {
		transit = new TransitLayer(map, {
			onSelect: (v) => (busId = v?.vehicleId ?? null),
			onUpdate: (vs, now) => {
				vehicles = vs;
				feedNow = now;
			},
			onError: (m) => (transitProblem = m)
		});
		transitReady = await transit.load();
	}

	onDestroy(() => transit?.destroy());

	async function ready(map: Map) {
		theMap = map;
		await addTransit(map);
		let saved: string | null = null;
		try {
			saved = localStorage.getItem('tvt-lens');
		} catch {
			/* ignore */
		}
		const r = await addCameraLayer(map, (c) => (selected = c));
		if ('error' in r) {
			cameraProblem = r.error;
			if (saved === 'transit') setLens('transit');
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
		if (saved === 'transit') setLens('transit');
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

<svelte:window onkeydown={onKey} />

<main>
	<ValleyMap onready={ready} />

	<header class="card">
		<h1>Treasure Valley</h1>
		{#if lens === 'transit'}
			<p class="num">
				{live.length} buses live · {Object.keys(liveByRoute).filter((r) => r !== '?').length} routes
				{#if live.length}· positions {ageText(feedNow - Math.max(...live.map((v) => v.ts)))}{/if}
			</p>
		{:else if counts}
			<p class="num">
				{counts.calibrated + counts.uncalibrated + counts.no_image} cameras · {counts.calibrated} calibrated
			</p>
		{/if}
	</header>

	<nav class="lenses" aria-label="Map lenses">
		{#each LENSES as l (l.id)}
			<button
				class="lens"
				class:active={lens === l.id}
				aria-pressed={lens === l.id}
				disabled={l.id === 'transit' && !transitReady}
				title="{l.name} (key {l.key})"
				onclick={() => setLens(l.id)}
			>
				<span aria-hidden="true">{l.icon}</span><span class="lens-name">{l.name}</span>
			</button>
		{/each}
	</nav>

	{#if lens === 'transit' && transit}
		<aside class="legend transit-legend card" aria-label="Bus routes">
			<p class="legend-title">Routes <span class="num">· live buses</span></p>
			<ul>
				{#each transit.routes as r (r.route_id)}
					<li>
						<button
							class="route"
							class:spot={spot === r.route_id}
							class:idle={!liveByRoute[r.route_id]}
							aria-pressed={spot === r.route_id}
							onclick={() => spotlight(spot === r.route_id ? null : r.route_id)}
						>
							<span class="badge" style="background:{r.color};color:{r.text_color}">{r.short_name}</span>
							<span class="route-name">{r.long_name}</span>
							<span class="num count">{liveByRoute[r.route_id] ?? ''}</span>
						</button>
					</li>
				{/each}
				{#if liveByRoute['?']}
					<li class="unknown">
						<span class="badge" style="background:{UNKNOWN_COLOR};color:#fffbf4">?</span>
						<span class="route-name">Route not reported</span>
						<span class="num count">{liveByRoute['?']}</span>
					</li>
				{/if}
			</ul>
			<p class="credit">Live positions: Valley Regional Transit (CC BY 3.0)</p>
		</aside>
	{/if}

	{#if lens === 'transit' && transitProblem}
		<p class="notice card" role="alert">{transitProblem}</p>
	{/if}

	{#if bus}
		<section class="camera card" aria-label="Selected bus">
			<button class="close" aria-label="Close" onclick={() => (busId = null)}>×</button>
			<h2>
				<span class="badge big" style="background:{bus.color ?? UNKNOWN_COLOR};color:{bus.textColor ?? '#fffbf4'}"
					>{bus.shortName ?? '?'}</span
				>
				{bus.longName ?? 'Route not reported'}
			</h2>
			<p class="meta">
				Bus <span class="num">{bus.label ?? bus.vehicleId}</span> · updated {ageText(feedNow - bus.ts)}
				{#if isStale(bus, feedNow)}<strong> · not reporting</strong>{/if}
			</p>
			{#if stopText(bus)}<p class="meta">{stopText(bus)}</p>{/if}
		</section>
	{/if}

	{#if counts && lens === 'cameras'}
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

	{#if cameraProblem && lens === 'cameras'}
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
	.lenses {
		position: absolute;
		top: 76px;
		left: 10px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.lens {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 46px;
		height: 46px;
		padding: 0 0 0 11px;
		overflow: hidden;
		border: 2px solid var(--panel-edge);
		border-radius: 999px;
		background: var(--panel);
		box-shadow: 0 3px 0 rgb(60 45 20 / 0.14);
		font: 600 14px var(--font-body);
		color: var(--ink);
		white-space: nowrap;
		cursor: pointer;
		transition: width 0.15s;
	}
	.lens span[aria-hidden] {
		font-size: 19px;
	}
	.lens:hover,
	.lens:focus-visible {
		width: 128px;
	}
	.lens.active {
		background: var(--ink);
		border-color: var(--ink);
		color: var(--panel);
	}
	.lens:disabled {
		opacity: 0.45;
		cursor: default;
	}
	.transit-legend {
		max-height: calc(100% - 210px);
		overflow-y: auto;
		gap: 2px;
		min-width: 230px;
	}
	.legend-title {
		margin: 0 0 4px;
		font: 600 14px var(--font-display);
	}
	.transit-legend ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.route,
	.unknown {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		padding: 2px 4px;
		border: 0;
		border-radius: 8px;
		background: none;
		font: 13px var(--font-body);
		color: var(--ink);
		text-align: left;
		cursor: pointer;
	}
	.route:hover,
	.route.spot {
		background: rgb(43 42 51 / 0.08);
	}
	.route.idle {
		opacity: 0.55;
	}
	.route-name {
		flex: 1;
	}
	.count {
		font-size: 12px;
		color: var(--ink-soft);
	}
	.badge {
		display: inline-block;
		min-width: 26px;
		padding: 1px 6px;
		border-radius: 999px;
		font: 600 12px var(--font-body);
		text-align: center;
		box-shadow: 0 0 0 1.5px var(--panel), 0 0 0 2.5px rgb(43 42 51 / 0.35);
	}
	.badge.big {
		font-size: 15px;
		margin-right: 4px;
		vertical-align: 2px;
	}
	.credit {
		margin: 6px 0 0;
		font-size: 11px;
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
