<script lang="ts">
	/**
	 * The map layout (docs/14 §14.8, "Routes and files"): the one map, created
	 * once per visit by MapHost, the chrome around it with its slots (WP2), and
	 * the child pages ("/" and /calibrate/[id]) rendered on top. Navigating
	 * between them never rebuilds the map.
	 *
	 * WP2 adds the layer system to the app context: the layer manager, the one
	 * picker, the render loop, the always-loaded overlay and the selection.
	 */
	import '#lib/layers/context.js';
	import { afterNavigate, beforeNavigate, goto } from '$app/navigation';
	import { navigating, page } from '$app/state';
	import { onDestroy } from 'svelte';
	import { App } from '#lib/app/app.svelte.js';
	import { setAppCtx } from '#lib/app/context.js';
	import MapHost from '#lib/components/MapHost.svelte';
	import { LayerManager } from '#lib/layers/manager.svelte.js';
	import { LAYER_DEFS, LAYER_IDS } from '#lib/layers/registry.js';
	import { Loop } from '#lib/map/loop.js';
	import { Picker } from '#lib/map/picker.js';
	import { Overlay } from '#lib/overlay/overlay.svelte.js';
	import { installScene } from '#lib/scene/install.svelte.js';
	import { parseLayerList, sameSet } from '#lib/state/layers.svelte.js';
	import { SelectionState } from '#lib/state/selection.svelte.js';
	import Chrome from '#lib/ui/Chrome.svelte';
	import { ranLog } from '#lib/ui/keylog.js';

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
	// The layer system (WP2), before anything reads the context.
	app.selection = new SelectionState();
	app.loop = new Loop();
	app.overlay = new Overlay();
	app.picker = new Picker({
		canPick: () => app.modes.current === 'explore',
		select: (s) => app.selection.select(s)
	});
	app.picker.addSource(app.overlay);
	app.layers = new LayerManager(app, LAYER_DEFS);
	// The 3D scene (WP9): app.scene(), a lazy chunk never requested before the first idle.
	const uninstallScene = installScene(app);
	setAppCtx(app);
	app.install();
	app.layersInfo = () => ({
		...app.layers.info(),
		overlay: { ok: app.overlay.ok, error: app.overlay.error, frames: app.overlay.frames },
		keys: [...ranLog]
	});

	// The map's shared machinery attaches on the style's load, before any layer module.
	void app.styleReady
		.then((map) => {
			app.loop.attach(map);
			app.picker.attach(map);
			app.overlay.attach(map, app.loop);
		})
		.catch(() => {});
	app.layers.start();

	// `?overlay-test`: the overlay's test grid (the `layers` spec); its code loads only then.
	if (page.url.searchParams.has('overlay-test')) {
		void app.whenReady().then(async () => {
			const { startOverlayTest } = await import('#lib/overlay/test-sprites.js');
			Object.defineProperty(globalThis, '__tvtOverlayTest', { value: startOverlayTest(app), configurable: true });
		});
	}

	// A navigation in progress counts as "not ready" until it completes.
	beforeNavigate((nav) => {
		if (nav.shallow || nav.willUnload) return;
		app.navigationStarted(nav.complete);
	});
	afterNavigate((nav) => {
		if (!nav.shallow) app.navigationFinished();
	});

	/** Typing a `#map=…` hash (or following a link to one) moves the map there, and its `layers=` sets the layers. */
	function onHashChange() {
		if (page.route.id !== EXPLORE_ROUTE || app.modes.current !== 'explore') return;
		app.view.applyHash();
		const ids = parseLayerList(app.view.getParam('layers'), LAYER_IDS);
		if (ids && !sameSet(ids, app.layers.set.enabled)) app.layers.set.replace(ids);
	}

	onDestroy(() => {
		uninstallScene();
		app.layers.destroy();
		app.overlay.detach();
		app.picker.detach();
		app.loop.detach();
		app.uninstall();
	});
</script>

<svelte:window onhashchange={onHashChange} />

<main>
	<MapHost {app} />
	<Chrome {app} />
	{@render children()}
</main>

<style>
	main {
		position: fixed;
		inset: 0;
		overflow: hidden;
	}
</style>
