<script lang="ts">
	/**
	 * The calibrator on the shared map (docs/14 §14.6, "Calibrating on the
	 * map"): a parity port of the old page (/v1/calibrate/[id]) that renders
	 * only its panel, over the same map the explore page uses.
	 *
	 * - Entering pushes a view snapshot (Calibrate mode), turns Aerial on,
	 *   puts terrain at true scale, hides the lenses and jumps (no flight) to
	 *   the camera at zoom 19, pitch 0, bearing = its solved heading.
	 * - Leaving (Back, or the Leave button) removes everything this page added
	 *   and restores the snapshot exactly, with jumpTo.
	 * - A calibration link opened fresh has no view to go back to: the map
	 *   opens at the camera (z16, pitch 50), and that's where leaving goes.
	 *
	 * WP14 rewrites this with the full design (live inset, look-through check,
	 * drafts, "Use this frame").
	 */
	import { Marker, type GeoJSONSource, type ImageSource, type MapMouseEvent } from 'maplibre-gl';
	import { afterNavigate, goto } from '$app/navigation';
	import { onMount, untrack } from 'svelte';
	import { MapScope } from '#lib/app/cleanup.js';
	import { getAppCtx } from '#lib/app/context.js';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import { drape, imageData } from '#lib/calibration/drape.js';
	import { MIN_PAIRS, footprint, groundHeight, project, solve, type Pair, type Pixel } from '#lib/calibration/solver.js';

	let { data } = $props();
	const app = getAppCtx();
	const camera = $derived(data.camera);

	type Draft = { pixel?: Pixel; ground?: [number, number, number] };
	type Frame = { frame: string; url: string; width: number; height: number };
	type View = (typeof data.camera.views)[number];

	// A deep link: open the map at this camera rather than somewhere else first.
	untrack(() => app.view.preferInitial({ center: data.camera.pole, zoom: 16, bearing: 0, pitch: 50 }));

	const startIdx = untrack(() => Math.max(0, data.camera.views.findIndex((v: View) => v.id === data.viewId)));
	let viewIdx = $state(startIdx);
	const view = $derived(camera.views[viewIdx] ?? camera.views[0]);
	let frame = $state<Frame | null>(null);
	let pairs = $state<Draft[]>([]);
	let busy = $state<string | null>(null);
	let message = $state<{ kind: 'ok' | 'problem'; text: string } | null>(null);
	let entered = $state(false);
	let showDrape = $state(true);
	let panel = $state<HTMLElement | null>(null);
	let framePixels: { url: string; data: ImageData } | null = null;
	let scope: MapScope | null = null;
	let cameFromMap = false;

	const complete = $derived(pairs.filter((p): p is Pair => !!p.pixel && !!p.ground));
	const size = $derived(frame ? { width: frame.width, height: frame.height } : null);
	const solution = $derived(size && complete.length >= MIN_PAIRS ? solve(complete, size, camera.pole) : null);
	const pending = $derived(pairs.length && !(pairs.at(-1)!.pixel && pairs.at(-1)!.ground) ? pairs.at(-1)! : null);
	const quality = $derived(
		!solution ? null : solution.rms < 1.5 ? 'great' : solution.rms < 3 ? 'good' : solution.rms < 6 ? 'rough: check the pairs with the biggest errors' : 'poor: some pairs probably don’t match'
	);

	// Leave goes Back when the entry before this one is the map; otherwise to the map.
	afterNavigate((nav) => {
		const fromMap = nav.from?.route.id === '/(map)';
		cameFromMap =
			fromMap && (nav.type === 'link' || nav.type === 'goto' || (nav.type === 'popstate' && (nav.delta ?? 0) > 0));
	});

	function leave() {
		if (cameFromMap) history.back();
		else void goto('/');
	}

	// Start from the current calibration if there is one, otherwise capture a fresh frame.
	$effect(() => {
		const cal = view.calibration;
		message = null;
		if (cal) {
			frame = { frame: cal.frame, url: `/frames/${cal.frame}`, width: cal.imageWidth, height: cal.imageHeight };
			pairs = cal.pairs.map((p: Pair) => ({ pixel: p.pixel, ground: p.ground }));
		} else {
			pairs = [];
			untrack(() => captureFrame());
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

	function onMapClick(e: MapMouseEvent) {
		const map = app.map;
		if (!map || app.modes.current !== 'calibrate') return;
		const z = map.queryTerrainElevation(e.lngLat);
		if (z === null) {
			message = { kind: 'problem', text: 'No ground height here yet (terrain still loading). Try again in a moment.' };
			return;
		}
		// Heights come back exaggerated: divide by the exaggeration in force now (true scale here, so 1).
		const ground: [number, number, number] = [e.lngLat.lng, e.lngLat.lat, z / app.exaggeration()];
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
			app.notify('cameras');
		} catch (e) {
			message = { kind: 'problem', text: `Not saved: ${(e as Error).message}` };
		} finally {
			busy = null;
		}
	}

	// --- map side -------------------------------------------------------------

	/** The map's padding: the panel's side of the screen is not map. */
	function padding() {
		const r = panel?.getBoundingClientRect();
		const none = { top: 0, right: 0, bottom: 0, left: 0 };
		if (!r) return none;
		const docked = r.height >= innerHeight * 0.8;
		return docked ? { ...none, left: Math.round(r.right) } : { ...none, top: Math.round(r.bottom) };
	}

	/**
	 * Where to look: for a calibrated view, the middle of the part of its
	 * footprint that was worked on (the pole and the pairs' ground points),
	 * facing its solved heading; else the pole, facing north. (The whole
	 * footprint runs 200 m out, more than z19 shows.)
	 */
	function target(v: View): { center: [number, number]; bearing: number } {
		const cal = v.calibration;
		if (!cal) return { center: camera.pole, bearing: 0 };
		const pts: [number, number][] = [camera.pole, ...cal.pairs.map((p: Pair) => [p.ground[0], p.ground[1]] as [number, number])];
		const xs = pts.map((p) => p[0]);
		const ys = pts.map((p) => p[1]);
		return {
			center: [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2],
			bearing: cal.pose.heading
		};
	}

	let poleMarker: Marker | null = null;
	let aimedAt = '';

	/** Jump (no flight, so no tiles load for the zooms in between) to this camera's view. */
	function aim(v: View) {
		const map = app.map;
		if (!map) return;
		aimedAt = `${camera.id}:${v.id}`;
		poleMarker?.setLngLat(camera.pole);
		const t = target(v);
		map.jumpTo({ center: t.center, zoom: 19, pitch: 0, bearing: t.bearing, padding: padding() });
	}

	/** Enter Calibrate mode on the shared map and add this page's markers and layers. */
	function enter() {
		const map = app.map;
		if (!map) return;
		app.modes.enter('calibrate');
		app.setAerial(true);
		app.setExaggeration(1);
		const s = (scope = new MapScope(map));
		const pole = document.createElement('div');
		pole.className = 'pole-marker';
		pole.title = 'Camera pole (ACHD location)';
		poleMarker = new Marker({ element: pole }).setLngLat(camera.pole).addTo(map);
		s.defer(() => {
			poleMarker?.remove();
			poleMarker = null;
		});
		s.addSource('calib-cone', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
		s.addLayer({ id: 'calib-cone-fill', type: 'fill', source: 'calib-cone', paint: { 'fill-color': '#f2a20c', 'fill-opacity': 0.18 } });
		s.addLayer({ id: 'calib-cone-line', type: 'line', source: 'calib-cone', paint: { 'line-color': '#d68d00', 'line-width': 2 } });
		s.on('click', onMapClick);
		const canvas = map.getCanvas();
		canvas.style.cursor = 'crosshair';
		s.defer(() => (canvas.style.cursor = ''));
		aim(view);
		entered = true;
	}

	onMount(() => {
		let gone = false;
		app.track(
			app.styleReady
				.then(() => {
					if (!gone) enter();
				})
				.catch(() => {})
		);
		// Keep the map's padding equal to the panel's size.
		const ro = new ResizeObserver(() => {
			if (entered && app.map) app.map.setPadding(padding());
		});
		if (panel) ro.observe(panel);
		return () => {
			gone = true;
			ro.disconnect();
			if (!entered) return;
			for (const mk of markers) mk.remove();
			markers = [];
			scope?.dispose();
			scope = null;
			entered = false;
			app.modes.leave('calibrate');
		};
	});

	// Another camera or view: aim again.
	$effect(() => {
		const v = view;
		const key = `${camera.id}:${v.id}`;
		if (entered && key !== untrack(() => aimedAt)) untrack(() => aim(v));
	});

	// Keep the map's numbered markers and view cone in step with the pairs and solution.
	let markers: Marker[] = [];
	$effect(() => {
		const map = app.map;
		if (!entered || !map) return;
		for (const mk of markers) mk.remove();
		markers = [];
		pairs.forEach((p, i) => {
			if (!p.ground) return;
			const el = document.createElement('div');
			el.className = 'pair-marker';
			el.textContent = String(i + 1);
			markers.push(new Marker({ element: el }).setLngLat([p.ground[0], p.ground[1]]).addTo(map));
		});
		const src = map.getSource('calib-cone') as GeoJSONSource | undefined;
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
		const m = app.map, sol = solution, f = frame, sz = size, on = showDrape, pts = complete, s = scope;
		clearTimeout(drapeTimer);
		if (!m || !entered || !s) return;
		if (!on || !sol || !f || !sz) {
			if (m.getLayer('calib-drape')) m.setLayoutProperty('calib-drape', 'visibility', 'none');
			return;
		}
		drapeTimer = setTimeout(async () => {
			if (framePixels?.url !== f.url) framePixels = { url: f.url, data: await imageData(f.url) };
			if (scope !== s) return;
			const gz = groundHeight(pts);
			const d = drape(sol.pose, sz, framePixels.data, gz, footprint(sol.pose, sz, gz, 200));
			if (!d) return;
			const src = m.getSource('calib-drape') as ImageSource | undefined;
			if (src) src.updateImage({ url: d.url, coordinates: d.coordinates });
			else {
				s.addSource('calib-drape', { type: 'image', url: d.url, coordinates: d.coordinates });
				s.addLayer({ id: 'calib-drape', type: 'raster', source: 'calib-drape', paint: { 'raster-fade-duration': 0 } }, 'calib-cone-fill');
			}
			m.setLayoutProperty('calib-drape', 'visibility', 'visible');
		}, 250);
		return () => clearTimeout(drapeTimer);
	});

	const compass = (h: number) => ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(h / 45) % 8];
	const residualClass = (r: number) => (r < 2 ? 'good' : r < 5 ? 'fair' : 'bad');
</script>

<svelte:head>
	<title>Calibrate {camera.name} · Treasure Valley Traffic</title>
</svelte:head>

<div class="calibrator card" bind:this={panel} aria-label="Calibrate {camera.name}">
	<PanelBoundary name="Calibrator">
		<header>
			<button class="back" onclick={leave} aria-label="Leave calibration">← Leave</button>
			<h1>{camera.name}</h1>
			{#if camera.views.length > 1}
				<select bind:value={viewIdx} aria-label="Camera view">
					{#each camera.views as v, i (v.id)}<option value={i}>View {i + 1}</option>{/each}
				</select>
			{/if}
			<span class="sub num">ACHD #{camera.achdCamId} · 511 image {view.imageId}</span>
		</header>

		<section class="frame-pane">
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

		{#if app.map && !app.manifest?.terrain}
			<p class="warn">Terrain isn’t built yet, so ground heights aren’t available.</p>
		{/if}

		<section class="pairs-pane">
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
	</PanelBoundary>
</div>

<style>
	/* Docked left at 45% on wide screens; across the top on narrow ones. The map's padding follows it. */
	.calibrator {
		position: absolute;
		top: 10px;
		left: 10px;
		bottom: 10px;
		z-index: 20;
		width: 45%;
		box-sizing: border-box;
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 10px 14px;
		overflow: auto;
	}
	@media (max-width: 899px) {
		.calibrator {
			right: 10px;
			bottom: auto;
			width: auto;
			max-height: 58%;
		}
	}
	header,
	section,
	.warn {
		flex-shrink: 0;
	}
	header {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: 6px 14px;
	}
	.back {
		border: 0;
		background: none;
		padding: 0;
		color: var(--ink);
		font: 600 15px var(--font-body);
		cursor: pointer;
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
		display: flex;
		flex-direction: column;
	}
	.frame {
		position: relative;
		width: 100%;
		margin: 0 auto;
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
	.warn {
		margin: 0;
		padding: 6px 10px;
		border-radius: 8px;
		background: var(--panel);
		border: 2px solid var(--alert);
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
