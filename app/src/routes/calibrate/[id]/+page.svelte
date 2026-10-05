<script lang="ts">
	import { Marker, type GeoJSONSource, type ImageSource, type Map } from 'maplibre-gl';
	import ValleyMap from '#lib/components/ValleyMap.svelte';
	import type { BasemapManifest } from '#lib/map/style.js';
	import { MIN_PAIRS, footprint, groundHeight, project, solve, type Pair, type Pixel } from '#lib/calibration/solver.js';
	import { drape, imageData } from '#lib/calibration/drape.js';

	let { data } = $props();
	const camera = $derived(data.camera);

	type Draft = { pixel?: Pixel; ground?: [number, number, number] };
	type Frame = { frame: string; url: string; width: number; height: number };

	let viewIdx = $state(0);
	const view = $derived(camera.views[viewIdx]);
	let frame = $state<Frame | null>(null);
	let pairs = $state<Draft[]>([]);
	let busy = $state<string | null>(null);
	let message = $state<{ kind: 'ok' | 'problem'; text: string } | null>(null);
	let map = $state<Map | null>(null);
	let terrainReady = $state(false);
	let exaggeration = 1;
	let showDrape = $state(true);
	let framePixels: { url: string; data: ImageData } | null = null;

	const complete = $derived(pairs.filter((p): p is Pair => !!p.pixel && !!p.ground));
	const size = $derived(frame ? { width: frame.width, height: frame.height } : null);
	const solution = $derived(size && complete.length >= MIN_PAIRS ? solve(complete, size, camera.pole) : null);
	const pending = $derived(pairs.length && !(pairs.at(-1)!.pixel && pairs.at(-1)!.ground) ? pairs.at(-1)! : null);
	const quality = $derived(
		!solution ? null : solution.rms < 1.5 ? 'great' : solution.rms < 3 ? 'good' : solution.rms < 6 ? 'rough: check the pairs with the biggest errors' : 'poor: some pairs probably don’t match'
	);

	// Start from the current calibration if there is one, otherwise capture a fresh frame.
	$effect(() => {
		const cal = view.calibration;
		message = null;
		if (cal) {
			frame = { frame: cal.frame, url: `/frames/${cal.frame}`, width: cal.imageWidth, height: cal.imageHeight };
			pairs = cal.pairs.map((p: Pair) => ({ pixel: p.pixel, ground: p.ground }));
		} else {
			pairs = [];
			captureFrame();
		}
	});

	async function captureFrame() {
		busy = 'Fetching the camera’s current image…';
		try {
			const res = await fetch(`/api/views/${view.id}/frame`, { method: 'POST' });
			if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
			frame = await res.json();
		} catch (e) {
			message = { kind: 'problem', text: `Couldn’t get an image: ${(e as Error).message}` };
		} finally {
			busy = null;
		}
	}

	function onImageClick(e: MouseEvent) {
		if (!frame) return;
		const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
		const px: Pixel = [((e.clientX - r.left) / r.width) * frame.width, ((e.clientY - r.top) / r.height) * frame.height];
		// An unfinished pair takes (or moves) its image point; otherwise start a new pair.
		if (pending) pending.pixel = px;
		else pairs.push({ pixel: px });
		message = null;
	}

	function onMapClick(lng: number, lat: number) {
		if (!map) return;
		const z = map.queryTerrainElevation([lng, lat]);
		if (z === null) {
			message = { kind: 'problem', text: 'No ground height here yet (terrain still loading). Try again in a moment.' };
			return;
		}
		const ground: [number, number, number] = [lng, lat, z / exaggeration];
		if (pending) pending.ground = ground;
		else pairs.push({ ground });
		message = null;
	}

	function remove(i: number) {
		pairs.splice(i, 1);
	}

	async function save() {
		if (!solution || !frame) return;
		busy = 'Saving…';
		try {
			const res = await fetch(`/api/views/${view.id}/calibrations`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ pose: solution.pose, pairs: complete, imageWidth: frame.width,
					imageHeight: frame.height, frame: frame.frame })
			});
			const body = await res.json();
			if (!res.ok) throw new Error(body?.message ?? `HTTP ${res.status}`);
			message = { kind: 'ok', text: `Saved (fit error ${body.rms.toFixed(2)} px). This camera now shows as calibrated.` };
		} catch (e) {
			message = { kind: 'problem', text: `Not saved: ${(e as Error).message}` };
		} finally {
			busy = null;
		}
	}

	// --- map side -------------------------------------------------------------
	let markers: Marker[] = [];

	function ready(m: Map, manifest: BasemapManifest) {
		map = m;
		exaggeration = manifest.terrain?.exaggeration ?? 1;
		terrainReady = Boolean(manifest.terrain);
		const pole = document.createElement('div');
		pole.className = 'pole-marker';
		pole.title = 'Camera pole (ACHD location)';
		new Marker({ element: pole }).setLngLat(camera.pole).addTo(m);
		m.addSource('cone', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
		m.addLayer({ id: 'cone-fill', type: 'fill', source: 'cone', paint: { 'fill-color': '#f2a20c', 'fill-opacity': 0.18 } });
		m.addLayer({ id: 'cone-line', type: 'line', source: 'cone', paint: { 'line-color': '#d68d00', 'line-width': 2 } });
		m.on('click', (e) => onMapClick(e.lngLat.lng, e.lngLat.lat));
		m.getCanvas().style.cursor = 'crosshair';
	}

	// Keep the map's numbered markers and view cone in step with the pairs and solution.
	$effect(() => {
		if (!map) return;
		for (const mk of markers) mk.remove();
		markers = [];
		pairs.forEach((p, i) => {
			if (!p.ground) return;
			const el = document.createElement('div');
			el.className = 'pair-marker';
			el.textContent = String(i + 1);
			markers.push(new Marker({ element: el }).setLngLat([p.ground[0], p.ground[1]]).addTo(map!));
		});
		const src = map.getSource('cone') as GeoJSONSource | undefined;
		if (!src) return;
		if (!solution || !size) {
			src.setData({ type: 'FeatureCollection', features: [] });
			return;
		}
		const ring = footprint(solution.pose, size, groundHeight(complete));
		src.setData({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } });
	});

	// Project the frame onto the ground under the cone: a live check that the fit is right.
	let drapeTimer: ReturnType<typeof setTimeout> | undefined;
	$effect(() => {
		const m = map, sol = solution, f = frame, sz = size, on = showDrape, pts = complete;
		clearTimeout(drapeTimer);
		if (!m) return;
		if (!on || !sol || !f || !sz) {
			if (m.getLayer('drape')) m.setLayoutProperty('drape', 'visibility', 'none');
			return;
		}
		drapeTimer = setTimeout(async () => {
			if (framePixels?.url !== f.url) framePixels = { url: f.url, data: await imageData(f.url) };
			const gz = groundHeight(pts);
			const d = drape(sol.pose, sz, framePixels.data, gz, footprint(sol.pose, sz, gz, 200));
			if (!d) return;
			const src = m.getSource('drape') as ImageSource | undefined;
			if (src) src.updateImage({ url: d.url, coordinates: d.coordinates });
			else {
				m.addSource('drape', { type: 'image', url: d.url, coordinates: d.coordinates });
				m.addLayer({ id: 'drape', type: 'raster', source: 'drape', paint: { 'raster-fade-duration': 0 } }, 'cone-fill');
			}
			m.setLayoutProperty('drape', 'visibility', 'visible');
		}, 250);
	});

	const compass = (h: number) => ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(h / 45) % 8];
	const residualClass = (r: number) => (r < 2 ? 'good' : r < 5 ? 'fair' : 'bad');
</script>

<svelte:head>
	<title>Calibrate {camera.name} · Treasure Valley Traffic</title>
</svelte:head>

<div class="page">
	<header class="card">
		<a class="back" href="/">← Map</a>
		<h1>{camera.name}</h1>
		{#if camera.views.length > 1}
			<select bind:value={viewIdx} aria-label="Camera view">
				{#each camera.views as v, i (v.id)}<option value={i}>View {i + 1}</option>{/each}
			</select>
		{/if}
		<span class="sub num">ACHD #{camera.achdCamId} · 511 image {view.imageId}</span>
	</header>

	<section class="frame-pane card">
		{#if frame}
			<div class="frame" style:aspect-ratio="{frame.width} / {frame.height}">
				<img src={frame.url} alt="Camera view used for calibration" draggable="false" />
				<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
				<svg viewBox="0 0 {frame.width} {frame.height}" preserveAspectRatio="none" onclick={onImageClick}>
					{#each pairs as p, i (i)}
						{#if p.pixel}
							{#if solution && p.ground && size}
								{@const q = project(solution.pose, size, p.ground)}
								{#if q}
									<line x1={p.pixel[0]} y1={p.pixel[1]} x2={q[0]} y2={q[1]} class="err {residualClass(solution.residuals[complete.indexOf(p as Pair)] ?? 99)}" />
									<path d="M{q[0] - 5} {q[1]}h10M{q[0]} {q[1] - 5}v10" class="proj" />
								{/if}
							{/if}
							<circle cx={p.pixel[0]} cy={p.pixel[1]} r="9" class="pt" class:waiting={!p.ground} />
							<text x={p.pixel[0]} y={p.pixel[1] + 4} class="pt-label">{i + 1}</text>
						{/if}
					{/each}
				</svg>
			</div>
			<p class="hint">
				{#if pending && pending.pixel && !pending.ground}
					Now click <b>the same spot on the map</b> →
				{:else if pending && pending.ground && !pending.pixel}
					← Now click <b>the same spot in the camera image</b>
				{:else}
					Click a sharp ground feature in the image (stop-bar end, lane-line corner, crosswalk corner), then the same spot on the map.
				{/if}
			</p>
		{:else if busy}
			<p class="hint">{busy}</p>
		{/if}
	</section>

	<section class="map-pane card">
		<ValleyMap options={{ aerial: true, center: camera.pole, zoom: 19, pitch: 0, hash: false, pad: 0.15 }} onready={ready} />
		{#if map && !terrainReady}
			<p class="warn">Terrain isn’t built yet, so ground heights aren’t available.</p>
		{/if}
	</section>

	<section class="panel card">
		<h2>Point pairs <span class="num">{complete.length}</span></h2>
		{#if pairs.length === 0}
			<p class="muted">Aim for 6 or more, spread across the image: near and far, left and right.</p>
		{/if}
		<ol class="pairs">
			{#each pairs as p, i (i)}
				<li>
					<span class="n">{i + 1}</span>
					<span class="num">{p.pixel ? `${p.pixel[0].toFixed(0)}, ${p.pixel[1].toFixed(0)}` : 'image…'}</span>
					<span class="num">{p.ground ? `${p.ground[2].toFixed(1)} m` : 'map…'}</span>
					{#if solution && p.pixel && p.ground}
						{@const r = solution.residuals[complete.indexOf(p as Pair)]}
						<span class="res {residualClass(r)} num">{r < 2 ? '●' : r < 5 ? '▲' : '■'} {r.toFixed(1)} px</span>
					{/if}
					<button class="x" aria-label="Remove pair {i + 1}" onclick={() => remove(i)}>×</button>
				</li>
			{/each}
		</ol>

		<h2>Camera</h2>
		{#if solution}
			<dl class="pose num">
				<dt>Height</dt><dd>{solution.heightAboveGround.toFixed(1)} m above the road</dd>
				<dt>Facing</dt><dd>{solution.pose.heading.toFixed(1)}° ({compass(solution.pose.heading)})</dd>
				<dt>Tilt</dt><dd>{solution.pose.tilt.toFixed(1)}° down{Math.abs(solution.pose.roll) > 0.5 ? `, roll ${solution.pose.roll.toFixed(1)}°` : ''}</dd>
				<dt>View</dt><dd>{solution.hfov.toFixed(0)}° × {solution.pose.vfov.toFixed(0)}°</dd>
				<dt>Fit</dt><dd class="q {quality?.split(':')[0]}">{solution.rms.toFixed(2)} px, {quality}</dd>
			</dl>
		{:else}
			<p class="muted">Solves automatically once there are {MIN_PAIRS} complete pairs ({Math.max(0, MIN_PAIRS - complete.length)} to go).</p>
		{/if}

		<label class="toggle"><input type="checkbox" bind:checked={showDrape} /> Project the image onto the map</label>
		<div class="actions">
			<button class="pill" onclick={captureFrame} disabled={!!busy}>New frame</button>
			<button class="pill primary" onclick={save} disabled={!solution || !!busy}>Save calibration</button>
		</div>
		{#if message}
			<p class="msg {message.kind}" role="status">{message.text}</p>
		{/if}
		{#if busy && frame}<p class="muted">{busy}</p>{/if}
	</section>
</div>

<style>
	.page {
		position: fixed;
		inset: 0;
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		grid-template-rows: auto minmax(0, 1fr) auto;
		grid-template-areas: 'head head' 'frame map' 'panel map';
		gap: 10px;
		padding: 10px;
		box-sizing: border-box;
	}
	header {
		grid-area: head;
		display: flex;
		align-items: baseline;
		gap: 14px;
		padding: 8px 14px;
	}
	.back {
		color: var(--ink);
		font-weight: 600;
		text-decoration: none;
	}
	h1 {
		margin: 0;
		font: 600 20px var(--font-display);
	}
	.sub {
		color: var(--ink-soft);
		font-size: 12px;
	}
	.frame-pane {
		grid-area: frame;
		padding: 10px;
		display: flex;
		flex-direction: column;
		min-height: 0;
	}
	.frame {
		position: relative;
		max-width: 100%;
		max-height: calc(100% - 40px);
		margin: 0 auto;
		width: 100%;
	}
	.frame img,
	.frame svg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		user-select: none;
	}
	.frame img {
		border-radius: 8px;
		image-rendering: auto;
	}
	.frame svg {
		cursor: crosshair;
	}
	.pt {
		fill: rgb(242 162 12 / 0.35);
		stroke: #fff;
		stroke-width: 2;
	}
	.pt.waiting {
		fill: rgb(242 162 12 / 0.9);
	}
	.pt-label {
		font: 700 11px var(--font-body);
		fill: #fff;
		text-anchor: middle;
		pointer-events: none;
		paint-order: stroke;
		stroke: rgb(0 0 0 / 0.6);
		stroke-width: 2px;
	}
	.proj {
		stroke: #fff;
		stroke-width: 2;
	}
	.err {
		stroke-width: 2;
	}
	.err.good, .res.good { stroke: var(--accent-2); color: var(--accent-2); }
	.err.fair, .res.fair { stroke: var(--accent); color: #b07400; }
	.err.bad, .res.bad { stroke: var(--alert); color: var(--alert); }
	.hint {
		margin: 8px 0 0;
		font-size: 14px;
	}
	.map-pane {
		grid-area: map;
		position: relative;
		overflow: hidden;
	}
	.warn {
		position: absolute;
		left: 10px;
		top: 10px;
		margin: 0;
		padding: 6px 10px;
		border-radius: 8px;
		background: var(--panel);
		border: 2px solid var(--alert);
	}
	.panel {
		grid-area: panel;
		padding: 10px 14px;
		max-height: 40vh;
		overflow: auto;
	}
	h2 {
		margin: 6px 0;
		font: 600 16px var(--font-display);
	}
	.muted {
		color: var(--ink-soft);
		margin: 4px 0;
		font-size: 13px;
	}
	.pairs {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 2px;
	}
	.pairs li {
		display: grid;
		grid-template-columns: 26px 90px 70px 1fr 24px;
		align-items: center;
		gap: 8px;
		font-size: 13px;
	}
	.n {
		display: inline-grid;
		place-items: center;
		width: 20px;
		height: 20px;
		border-radius: 50%;
		background: var(--accent);
		font: 700 11px var(--font-body);
	}
	.x {
		border: 0;
		background: none;
		cursor: pointer;
		font-size: 18px;
		color: var(--ink-soft);
	}
	.pose {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 2px 12px;
		margin: 0;
		font-size: 13px;
	}
	.pose dt {
		color: var(--ink-soft);
		font-family: var(--font-body);
	}
	.pose dd {
		margin: 0;
	}
	.q.great, .q.good { color: var(--accent-2); }
	.q.rough { color: #b07400; }
	.q.poor { color: var(--alert); }
	.toggle {
		display: block;
		margin-top: 8px;
		font-size: 13px;
	}
	.actions {
		display: flex;
		gap: 8px;
		margin-top: 10px;
	}
	.msg {
		margin: 8px 0 0;
		font-size: 13px;
	}
	.msg.ok { color: var(--accent-2); }
	.msg.problem { color: var(--alert); }
	:global(.pair-marker) {
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: var(--accent);
		border: 2px solid #fff;
		display: grid;
		place-items: center;
		font: 700 11px var(--font-body);
		color: var(--ink);
		box-shadow: 0 1px 4px rgb(0 0 0 / 0.4);
		pointer-events: none;
	}
	:global(.pole-marker) {
		width: 14px;
		height: 14px;
		border-radius: 3px;
		background: var(--ink);
		border: 2px solid #fff;
		box-shadow: 0 1px 4px rgb(0 0 0 / 0.4);
	}
</style>
