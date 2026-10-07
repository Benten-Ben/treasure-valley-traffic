<script lang="ts">
	import { page } from '$app/state';
	import { onDestroy, onMount, untrack } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import { followOf } from '#lib/state/follow.svelte.js';
	import { historyOf } from '#lib/state/history.svelte.js';
	import { SAFE_BOTTOM, SAFE_TOP, windowsOf, type Bars } from '#lib/state/windows.svelte.js';
	import { ESC, onEscape, register } from './keys.js';
	import { slots } from './slots.svelte.js';
	import Window from './Window.svelte';

	/**
	 * The floating-window layer (docs/14 §14.3 "Floating layer", band 30–39;
	 * WP3), and the home of WP3's per-visit machinery, since it's the part of
	 * the chrome that is always mounted:
	 *
	 * - the window manager (`app.windows`), told the screen size and where the
	 *   bars are, so windows stay below the top bar and above the toolbar;
	 * - the view history (`app.history`) and Backspace; follow (`app.follow`);
	 * - the Esc closers for the focused window and for follow;
	 * - the open windows as a part of every view snapshot.
	 *
	 * On a phone the windows are tabs of the bottom sheet (Sheet.svelte), so
	 * nothing floats here. `?window-test` adds the test window (the `windows`
	 * spec), whose code loads only then.
	 */
	let { app }: { app: AppCtx } = $props();
	const ctx = untrack(() => app);
	const windows = windowsOf(ctx);
	const history = historyOf(ctx);
	const follow = followOf(ctx);
	const phone = $derived(windows.layout === 'phone');
	let gone = false;

	const undo: (() => void)[] = [];
	void ctx.styleReady
		.then((map) => {
			if (gone) return;
			history.attach(map);
			follow.attach(map, ctx.loop ?? null);
		})
		.catch(() => {});
	undo.push(() => {
		history.detach();
		follow.detach();
	});
	undo.push(ctx.view.register('windows', windows.part()));
	undo.push(
		register({
			id: 'view-back',
			codes: ['Backspace'],
			label: 'Backspace',
			description: 'Back to the previous view',
			group: 'Camera',
			run: () => history.back()
		})
	);
	undo.push(
		onEscape(ESC.window, () => {
			const key = (document.activeElement?.closest('[data-window-key]') as HTMLElement | null)?.dataset.windowKey;
			if (!key || !windows.isOpen(key)) return false;
			windows.close(key);
			return true;
		})
	);
	undo.push(
		onEscape(ESC.follow, () => {
			if (!follow.current) return false;
			follow.stop();
			return true;
		})
	);

	/** Where the bars are now: the top bar's bottom and the toolbar's (or a mode banner's) top, plus a 12 px gap. */
	function bars(): Bars {
		const vh = innerHeight;
		const top = document.querySelector('.chrome header.topbar')?.getBoundingClientRect();
		const bottom = document.querySelector('.chrome .bottom')?.getBoundingClientRect();
		return {
			top: Math.max(SAFE_TOP, top && top.height > 0 ? Math.ceil(top.bottom + 12) : 0),
			bottom: Math.max(SAFE_BOTTOM, bottom && bottom.height > 0 ? Math.ceil(vh - bottom.top + 12) : 0)
		};
	}

	function measure() {
		if (gone) return;
		windows.setViewport(innerWidth, innerHeight, bars());
	}

	let observer: ResizeObserver | undefined;
	let frame = 0;
	onMount(() => {
		measure();
		// The bars render with the rest of the chrome; measure once they're laid out, and when they change size.
		frame = requestAnimationFrame(() => {
			measure();
			observer = new ResizeObserver(() => measure());
			for (const el of document.querySelectorAll('.chrome header.topbar, .chrome .bottom')) observer.observe(el);
		});
	});

	// The bars differ between modes (a banner instead of the toolbar, no top bar).
	$effect(() => {
		void app.modes.current;
		const f = requestAnimationFrame(() => {
			measure();
			if (observer) for (const el of document.querySelectorAll('.chrome header.topbar, .chrome .bottom')) observer.observe(el);
		});
		return () => cancelAnimationFrame(f);
	});

	if (page.url.searchParams.has('window-test')) {
		void import('./window-test.js').then((m) => {
			if (!gone) undo.push(m.startWindowTest(ctx, windows));
		});
	}

	onDestroy(() => {
		gone = true;
		cancelAnimationFrame(frame);
		observer?.disconnect();
		for (const f of undo.splice(0).reverse()) f();
	});
</script>

<svelte:window onresize={measure} />

{#if !phone}
	{#each windows.list as win (win.key)}
		<Window {win} manager={windows} />
	{/each}
{/if}
{#each slots.items('windows') as it (it.id)}
	<PanelBoundary name={it.id}><it.component {...it.props} /></PanelBoundary>
{/each}
