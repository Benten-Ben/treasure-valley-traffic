<script lang="ts">
	/**
	 * The map layout (docs/14 §14.8, "Routes and files"): the one map, created
	 * once per visit by MapHost, with today's lens UI over it, and the child
	 * pages ("/" and /calibrate/[id]) rendered on top. Navigating between them
	 * never rebuilds the map.
	 *
	 * The lens UI is the pre-v2 page moved here almost verbatim, with its map
	 * modules adapted to the app context. WP2 replaces it with the layer
	 * system and Chrome.
	 */
	import { afterNavigate, beforeNavigate, goto } from '$app/navigation';
	import { navigating, page, updated } from '$app/state';
	import { onDestroy, untrack } from 'svelte';
	import { App } from '#lib/app/app.svelte.js';
	import { setAppCtx } from '#lib/app/context.js';
	import { ignoreKey } from '#lib/app/keyguard.js';
	import MapHost from '#lib/components/MapHost.svelte';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import { CameraLayer, type Calibration, type CameraCounts, type CameraProps } from '#lib/map/cameras.js';
	import {
		ageText,
		isStale,
		stopText,
		TransitLayer,
		UNKNOWN_COLOR,
		type TransitRoute,
		type Vehicle
	} from '#lib/map/transit.js';
	import { oneWayText, SPEED_BINS, speedColor, StreetsLayer, type StreetProps } from '#lib/map/streets.js';
	import { readLegacy } from '#lib/state/persisted.svelte.js';

	let { children } = $props();

	/** The explore page's route id: the only place the view module writes the hash. */
	const EXPLORE_ROUTE = '/(map)';

	const app = new App({
		writeHash: (hash) => {
			const url = `${page.url.pathname}${page.url.search}${hash}`;
			goto(url, { shallow: true, replace: true, state: page.state }).catch(() => {});
		},
		canWriteHash: () => page.route.id === EXPLORE_ROUTE && navigating.type === null,
		routerUrl: () => page.url.href
	});
	setAppCtx(app);
	app.install();

	// A navigation in progress counts as "not ready" until it completes.
	beforeNavigate((nav) => {
		if (nav.shallow || nav.willUnload) return;
		app.navigationStarted(nav.complete);
	});
	afterNavigate((nav) => {
		if (!nav.shallow) app.navigationFinished();
	});

	/** Typing a `#map=…` hash (or following a link to one) moves the map there. */
	function onHashChange() {
		if (page.route.id === EXPLORE_ROUTE && app.modes.current === 'explore') app.view.applyHash();
	}

	// --- today's lens UI --------------------------------------------------------

	let selected = $state<CameraProps | null>(null);
	let counts = $state<CameraCounts | null>(null);
	let cameraProblem = $state<string | null>(null);
	let calibrations = $state.raw<Calibration[]>([]);
	let showImages = $state(false);

	// Lenses (docs/13 §13.5): what the map is about right now. Hotkeys follow the design's numbering.
	type Lens = 'streets' | 'transit' | 'cameras';
	const LENSES: { id: Lens; name: string; icon: string; key: string }[] = [
		{ id: 'streets', name: 'Streets', icon: '🛣️', key: '2' },
		{ id: 'transit', name: 'Transit', icon: '🚌', key: '4' },
		{ id: 'cameras', name: 'Cameras', icon: '📷', key: '7' }
	];
	const isLens = (v: unknown): v is Lens => v === 'streets' || v === 'transit' || v === 'cameras';
	const saved = readLegacy('tvt-lens');
	let lens = $state<Lens>(isLens(saved) ? saved : 'cameras');
	let routes = $state.raw<TransitRoute[]>([]);
	let transitReady = $state(false);
	let transitProblem = $state<string | null>(null);
	let vehicles = $state.raw<Vehicle[]>([]);
	let feedNow = $state(0);
	let busId = $state<string | null>(null);
	let street = $state<StreetProps | null>(null);
	let spot = $state<string | null>(null);
	let dismissedUpdate = $state(false);
	const exploring = $derived(app.modes.current === 'explore');
	const bus = $derived(vehicles.find((v) => v.vehicleId === busId) ?? null);
	const live = $derived(vehicles.filter((v) => !isStale(v, feedNow)));
	const liveByRoute = $derived(
		live.reduce<Record<string, number>>((n, v) => ((n[v.routeId ?? '?'] = (n[v.routeId ?? '?'] ?? 0) + 1), n), {})
	);

	// The three lens modules start their data fetches now, before the map exists
	// (docs/14 §14.8 "Boot"), and attach their layers on the style's `style.load`.
	const transit = new TransitLayer(app, {
		onSelect: (v) => (busId = v?.vehicleId ?? null),
		onUpdate: (vs, now) => {
			vehicles = vs;
			feedNow = now;
		},
		onError: (m) => (transitProblem = m)
	});
	const streets = new StreetsLayer(app, (s) => (street = s));
	const cameras = new CameraLayer(app, {
		onSelect: (c) => (selected = c),
		onCounts: (c) => (counts = c),
		onCalibrations: (c) => (calibrations = c),
		onError: (m) => (cameraProblem = m)
	});
	void transit.load().then((ok) => {
		transitReady = ok;
		routes = transit.routes;
		if (!ok && lens === 'transit') lens = 'cameras';
	});
	void streets.load();
	void cameras.load();

	// A calibration was saved: camera statuses, counts and cones change.
	const unsubscribe = app.subscribe('cameras', () => {
		void cameras.reload().then(() => {
			const id = selected?.id;
			if (id !== undefined) selected = cameras.cameras.find((c) => c.id === id) ?? selected;
		});
	});

	onDestroy(() => {
		unsubscribe();
		transit.destroy();
		streets.destroy();
		cameras.destroy();
		app.uninstall();
	});

	// Only the chosen lens is drawn, and none while a mode (calibrating) owns the map.
	$effect(() => {
		const shown = exploring ? lens : null;
		const images = showImages;
		untrack(() => {
			transit.setVisible(shown === 'transit');
			streets.setVisible(shown === 'streets');
			cameras.setVisible(shown === 'cameras', images);
		});
	});

	// Snapshots carry the lens, so leaving a mode puts it back as it was.
	app.view.register('layers', {
		save: () => ({ lens, showImages }),
		restore: (v) => {
			const s = v as { lens?: unknown; showImages?: unknown } | null;
			if (isLens(s?.lens)) lens = s.lens;
			if (typeof s?.showImages === 'boolean') showImages = s.showImages;
		}
	});
	app.layersInfo = () => ({ lens, shown: exploring ? lens : null, transit: transitReady, cameras: counts !== null });

	function setLens(next: Lens) {
		lens = next;
		try {
			localStorage.setItem('tvt-lens', next);
		} catch {
			/* per-viewer convenience only */
		}
		if (next !== 'cameras') selected = null;
		if (next !== 'transit') busId = null;
		if (next !== 'streets') street = null;
	}

	function onKey(e: KeyboardEvent) {
		if (ignoreKey(e) || !exploring) return;
		const l = LENSES.find((x) => x.key === e.key);
		if (l && (l.id !== 'transit' || transitReady)) setLens(l.id);
	}

	function spotlight(routeId: string | null) {
		spot = routeId;
		transit.spotlight(routeId);
	}

	const statusText = {
		calibrated: 'Calibrated',
		uncalibrated: 'Needs calibration',
		no_image: 'No camera image linked yet'
	};
</script>

<svelte:window onkeydown={onKey} onhashchange={onHashChange} />

<main>
	<MapHost {app} />

	{#if exploring}
		<header class="card">
			<h1>Treasure Valley</h1>
			{#if lens === 'streets'}
				<p class="num">Ada County roads · posted speeds (ACHD)</p>
			{:else if lens === 'transit'}
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

		{#if lens === 'transit' && transitReady}
			<PanelBoundary name="Routes legend">
				<aside class="legend transit-legend card" aria-label="Bus routes">
					<p class="legend-title">Routes <span class="num">· live buses</span></p>
					<ul>
						{#each routes as r (r.route_id)}
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
			</PanelBoundary>
		{/if}

		{#if lens === 'streets'}
			<PanelBoundary name="Speed legend">
				<aside class="legend card" aria-label="Posted speed legend">
					<p class="legend-title">Posted speed</p>
					{#each SPEED_BINS as b (b.from)}
						<span><i class="swatch" style="background:{b.color}"></i>{b.label}</span>
					{/each}
					<span class="hint">Wider line: bigger road class · ›› one-way</span>
					<p class="credit">Ada County: ACHD road centerlines. Canyon County isn't covered yet.<br />Most local streets read 20 mph, likely a default.</p>
				</aside>
			</PanelBoundary>
		{/if}

		{#if street}
			<PanelBoundary name="Road card">
				<section class="camera card" aria-label="Selected road">
					<button class="close" aria-label="Close" onclick={() => (street = null)}>×</button>
					<h2>{street.name ?? 'Unnamed road'}</h2>
					<p class="speed-line">
						<span class="speed-sign"><small>SPEED LIMIT</small><b>{street.speed ?? '?'}</b></span>
						<span class="meta">
							{street.class ?? 'Unknown class'}{#if street.community} · {street.community}{/if}<br />
							{oneWayText(street)}{#if street.elevated} · bridge or overpass{/if}{#if street.private} · private{/if}
						</span>
					</p>
					<p class="credit">Source: ACHD road centerlines <i class="swatch small" style="background:{speedColor(street.speed)}"></i></p>
				</section>
			</PanelBoundary>
		{/if}

		{#if lens === 'transit' && transitProblem}
			<p class="notice card" role="alert">{transitProblem}</p>
		{/if}

		{#if bus}
			<PanelBoundary name="Bus card">
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
					{#if bus.routeMatched}<p class="meta">Route matched from the bus's path: the feed doesn't name it.</p>{/if}
				</section>
			</PanelBoundary>
		{/if}

		{#if counts && lens === 'cameras'}
			<PanelBoundary name="Camera legend">
				<aside class="legend card" aria-label="Camera legend">
					<span><i class="dot calibrated"></i>Calibrated</span>
					<span><i class="dot uncalibrated"></i>Needs calibration</span>
					<span><i class="dot no-image"></i>No image yet</span>
					{#if calibrations.length}
						<span><i class="cone"></i>View cone (calibrated)</span>
						<label><input type="checkbox" bind:checked={showImages} /> Camera images on the map</label>
					{/if}
				</aside>
			</PanelBoundary>
		{/if}

		{#if cameraProblem && lens === 'cameras'}
			<p class="notice card" role="alert">{cameraProblem}</p>
		{/if}

		{#if selected}
			<PanelBoundary name="Camera card">
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
			</PanelBoundary>
		{/if}
	{/if}

	{@render children()}

	{#if updated.current && !dismissedUpdate}
		<div class="toast card" role="status">
			<span>New version: reload when convenient.</span>
			<button class="pill" onclick={() => location.reload()}>Reload</button>
			<button class="close-toast" aria-label="Dismiss" onclick={() => (dismissedUpdate = true)}>×</button>
		</div>
	{/if}
</main>

<style>
	main {
		position: fixed;
		inset: 0;
	}
	/* Stacking follows docs/14 §14.3's bands: panels 20, bars 40, toasts 70. */
	header {
		position: absolute;
		top: 10px;
		left: 10px;
		z-index: 40;
		padding: 8px 14px;
	}
	.toast {
		position: absolute;
		left: 50%;
		bottom: 40px;
		z-index: 70;
		transform: translateX(-50%);
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 10px 8px 16px;
		font-size: 14px;
	}
	.close-toast {
		border: 0;
		background: none;
		font-size: 20px;
		cursor: pointer;
		color: var(--ink-soft);
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
		z-index: 20;
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
		z-index: 20;
		margin: 0;
		padding: 8px 12px;
	}
	.camera {
		position: absolute;
		right: 10px;
		bottom: 36px;
		z-index: 20;
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
		z-index: 40;
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
	.swatch {
		display: inline-block;
		width: 22px;
		height: 6px;
		margin-right: 8px;
		border-radius: 3px;
		vertical-align: 2px;
	}
	.swatch.small {
		width: 14px;
	}
	.hint {
		margin-top: 4px;
		font-size: 12px;
		color: var(--ink-soft);
	}
	.speed-line {
		display: flex;
		gap: 12px;
		align-items: center;
		margin: 4px 0 8px;
	}
	.speed-sign {
		display: flex;
		flex-direction: column;
		align-items: center;
		min-width: 58px;
		padding: 4px 6px;
		border: 2.5px solid var(--ink);
		border-radius: 8px;
		background: #fff;
		color: var(--ink);
		line-height: 1;
	}
	.speed-sign small {
		font: 700 8px var(--font-body);
		letter-spacing: 0.04em;
		text-align: center;
	}
	.speed-sign b {
		font: 700 26px var(--font-body);
	}
	.speed-line .meta {
		margin: 0;
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
