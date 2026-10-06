<script lang="ts">
	import { onDestroy, untrack, type Component } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import CameraWidget from './CameraWidget.svelte';
	import InspectCard from './InspectCard.svelte';
	import { ESC, handleKey, onEscape } from './keys.js';
	import { registerDefaultKeys } from './keymap.js';
	import LegendStack from './LegendStack.svelte';
	import LoadingCard from './LoadingCard.svelte';
	import Sheet from './Sheet.svelte';
	import { slots } from './slots.svelte.js';
	import TabBar from './TabBar.svelte';
	import Toasts from './Toasts.svelte';
	import Toolbar from './Toolbar.svelte';
	import Tooltip from './Tooltip.svelte';
	import { MAP_DELAY, tooltip } from './tooltip.svelte.js';
	import TopBar from './TopBar.svelte';
	import ViewHistoryChip from './ViewHistoryChip.svelte';
	import WindowLayer from './WindowLayer.svelte';

	/**
	 * The chrome (docs/14 §14.3, "The screen"): every region around the map,
	 * and the slots later packages plug into (`slots.svelte.ts`).
	 *
	 * - Desktop: top bar; the legend stack in the left column; the camera
	 *   widget and the docked inspect card in the right column; floating
	 *   windows; the toolbar at the bottom centre.
	 * - Tablet (600–1023 px): toolbar labels hidden, legends collapsed, a
	 *   narrower inspect card.
	 * - Phone (under 600 px): a compact top bar, the tab bar instead of the
	 *   toolbar, and one bottom sheet instead of the side panels.
	 * - In a mode (look-through, calibrate) the mode's banner replaces the
	 *   toolbar, and the mode's own panel takes the screen.
	 *
	 * It also owns the one key handler (the keymap registry), WP2's keys, and
	 * the map's hover tooltip.
	 */
	let { app }: { app: AppCtx } = $props();

	let phone = $state(false);
	let tablet = $state(false);
	if (typeof matchMedia !== 'undefined') {
		const p = matchMedia('(max-width: 599px)');
		const t = matchMedia('(max-width: 1023px)');
		const sync = () => {
			phone = p.matches;
			tablet = t.matches && !p.matches;
		};
		sync();
		p.addEventListener('change', sync);
		t.addEventListener('change', sync);
		onDestroy(() => {
			p.removeEventListener('change', sync);
			t.removeEventListener('change', sync);
		});
	}

	const exploring = $derived(app.modes.current === 'explore');
	const banner = $derived(slots.banner(app.modes.current));

	let helpOpen = $state(false);
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let Help = $state<Component<any> | null>(null);

	/** Open or close Help (the ? key and button); its code loads the first time. */
	async function toggleHelp(force?: boolean) {
		const next = force ?? !helpOpen;
		if (next && !Help) Help = (await import('./HelpOverlay.svelte')).default;
		helpOpen = next;
	}

	// The app context never changes for the life of the layout.
	const ctx = untrack(() => app);
	const unkeys = registerDefaultKeys(ctx, { help: () => toggleHelp() });
	const stopEsc = onEscape(ESC.popover + 1, () => {
		if (!helpOpen) return false;
		helpOpen = false;
		return true;
	});

	// The map's hover tooltip: the hovered thing's name, one fact, and source.
	const unhover = ctx.picker.onHover((h) => {
		if (!h) return tooltip.hide();
		const rect = ctx.map?.getContainer().getBoundingClientRect();
		const tip = {
			x: (rect?.left ?? 0) + h.x,
			y: (rect?.top ?? 0) + h.y,
			placement: 'cursor' as const,
			title: h.selection.title,
			lines: [h.selection.fact, h.selection.source].filter((x): x is string => Boolean(x))
		};
		if (tooltip.current) tooltip.move(tip);
		else tooltip.show(tip, MAP_DELAY);
	});

	onDestroy(() => {
		unkeys();
		stopEsc();
		unhover();
		tooltip.hide();
	});
</script>

<svelte:window onkeydown={(e) => handleKey(e, app.modes.current)} />

<div class="chrome" class:phone class:tablet>
	{#if exploring}
		<TopBar {app} {phone} onhelp={() => toggleHelp()} />
		{#if !phone}
			<aside class="left" aria-label="Legends">
				<LegendStack {app} collapsed={tablet} />
			</aside>
			<div class="right">
				<div class="widget"><CameraWidget {app} /></div>
				<div class="inspect-slot"><InspectCard {app} /></div>
			</div>
		{/if}
		<ViewHistoryChip {app} />
	{/if}

	<WindowLayer {app} />

	<div class="bottom">
		{#if exploring}
			{#if phone}
				<Sheet>
					<InspectCard {app} />
					<LegendStack {app} />
				</Sheet>
				<TabBar {app} />
			{:else}
				<Toolbar {app} compact={tablet} />
			{/if}
		{:else if banner}
			{@const Banner = banner}
			<PanelBoundary name="Mode banner"><Banner {app} /></PanelBoundary>
		{/if}
	</div>

	<LoadingCard {app} />
	<Tooltip />
	{#if helpOpen && Help}<Help onclose={() => (helpOpen = false)} />{/if}
	<Toasts {app} />
</div>

<style>
	.chrome {
		position: absolute;
		inset: 0;
		pointer-events: none;
	}
	.chrome > :global(*) {
		pointer-events: auto;
	}
	.left {
		position: absolute;
		top: 76px;
		left: 16px;
		bottom: 104px;
		z-index: 20;
		width: 280px;
		display: flex;
		flex-direction: column;
		pointer-events: none;
	}
	.left > :global(*) {
		pointer-events: auto;
	}
	.right {
		position: absolute;
		top: 76px;
		right: 16px;
		bottom: 104px;
		z-index: 20;
		width: 360px;
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 10px;
		pointer-events: none;
	}
	.right > :global(*) {
		pointer-events: auto;
	}
	/* Room for the camera widget (MapLibre's controls until WP3's). */
	.widget {
		min-height: 104px;
		pointer-events: none;
	}
	.inspect-slot {
		width: 100%;
		min-height: 0;
		display: flex;
	}
	.bottom {
		position: absolute;
		left: 50%;
		bottom: 16px;
		z-index: 40;
		transform: translateX(-50%);
		max-width: calc(100% - 32px);
	}
	.tablet .right {
		width: 320px;
	}
	.phone .bottom {
		left: 8px;
		right: 8px;
		bottom: 8px;
		transform: none;
		max-width: none;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
</style>
