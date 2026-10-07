<script lang="ts">
	import { tick, untrack, type Snippet } from 'svelte';
	import { getAppCtx } from '#lib/app/context.js';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import { windowsOf } from '#lib/state/windows.svelte.js';
	import Icon from './Icon.svelte';
	import { slots } from './slots.svelte.js';
	import { CLOSE, PIN } from './window-icons.js';

	/**
	 * The phone's bottom sheet (docs/14 §14.3, under 600 px; WP3): one sheet
	 * above the tab bar holds the legends and the inspect card (the Map tab)
	 * and up to 3 windows as tabs (on a phone, windows never float).
	 *
	 * - Snap points: 25%, 55% and 90% of the screen's height. Drag the handle
	 *   (it snaps to the nearest on release), tap it to step through them, or
	 *   use ↑ and ↓ on it.
	 * - A window that opens takes its tab and lifts the sheet to at least
	 *   55%; selecting something on the map shows the Map tab.
	 * - Every control in it is at least 44 px (§14.3: touch targets), its own
	 *   and the legends' and cards' inside it.
	 */
	let { children, label = 'Details' }: { children: Snippet; label?: string } = $props();
	const app = getAppCtx();
	const windows = windowsOf(app);

	const SNAPS = [0.25, 0.55, 0.9] as const;
	/** Tab bar (64) plus the gaps above, below and between (8 each). */
	const BELOW = 64 + 8 + 8;
	const TOP_GAP = 8;

	let snap = $state(0);
	let vh = $state(typeof innerHeight === 'number' ? innerHeight : 800);
	let dragH = $state<number | null>(null);
	const maxH = $derived(Math.max(120, vh - BELOW - TOP_GAP));
	const heightAt = (i: number) => Math.min(maxH, Math.round(SNAPS[i] * vh));
	const height = $derived(dragH ?? heightAt(snap));

	const panelId = (k: string) => `sheet-panel-${k.replace(/[^a-z0-9]/gi, '-')}`;
	const tabId = (k: string) => `sheet-tab-${k.replace(/[^a-z0-9]/gi, '-')}`;

	type Tab = 'details' | string;
	let active = $state<Tab>('details');
	const wins = $derived(windows.list);

	// A window that opens (or is opened again) with focus takes its tab, lifts the sheet and gets
	// the focus; a closed one gives the Map tab back.
	let windowAt = -Infinity;
	$effect(() => {
		const list = wins;
		untrack(() => {
			for (const w of list)
				if (w.takeFocus) {
					active = w.key;
					windowAt = performance.now();
					if (snap < 1) snap = 1;
					windows.focused(w.key);
					void tick().then(() => document.getElementById(panelId(w.key))?.focus({ preventScroll: true }));
				}
			if (active !== 'details' && !list.some((w) => w.key === active)) active = 'details';
		});
	});

	// Something selected on the map: its card is on the Map tab (unless the same click opened a
	// window, as a camera's does: then the window's tab wins).
	$effect(() => {
		if (app.selection.current) untrack(() => performance.now() - windowAt > 300 && (active = 'details'));
	});

	// --- the handle --------------------------------------------------------------------
	let press: { id: number; y0: number; h0: number; moved: boolean } | null = null;
	let suppressClick = false;

	function down(e: PointerEvent) {
		if (e.button !== 0) return;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		press = { id: e.pointerId, y0: e.clientY, h0: height, moved: false };
	}

	function move(e: PointerEvent) {
		if (!press || e.pointerId !== press.id) return;
		const dy = e.clientY - press.y0;
		if (!press.moved && Math.abs(dy) < 6) return;
		press.moved = true;
		dragH = Math.min(maxH, Math.max(heightAt(0), press.h0 - dy));
	}

	function up(e: PointerEvent) {
		if (!press || e.pointerId !== press.id) return;
		const p = press;
		press = null;
		if (!p.moved) return;
		suppressClick = true;
		const h = dragH ?? height;
		let best = 0;
		for (let i = 1; i < SNAPS.length; i++) if (Math.abs(heightAt(i) - h) < Math.abs(heightAt(best) - h)) best = i;
		snap = best;
		dragH = null;
	}

	function click() {
		if (suppressClick) {
			suppressClick = false;
			return;
		}
		snap = (snap + 1) % SNAPS.length;
	}

	function key(e: KeyboardEvent) {
		if (e.key === 'ArrowUp' && snap < SNAPS.length - 1) snap += 1;
		else if (e.key === 'ArrowDown' && snap > 0) snap -= 1;
		else return;
		e.preventDefault();
		e.stopPropagation();
	}

	// --- tabs ----------------------------------------------------------------------------
	let tabEls: HTMLButtonElement[] = $state([]);
	const tabIds = $derived(['details', ...wins.map((w) => w.key)]);

	function tabKey(e: KeyboardEvent) {
		if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
		e.preventDefault();
		e.stopPropagation();
		const i = tabIds.indexOf(active);
		const next = (i + (e.key === 'ArrowRight' ? 1 : -1) + tabIds.length) % tabIds.length;
		active = tabIds[next];
		tabEls[next]?.focus();
	}

	// The selected tab is always in view (the row scrolls sideways).
	$effect(() => {
		const i = tabIds.indexOf(active);
		const el = i >= 0 ? tabEls[i] : undefined;
		if (el) untrack(() => el.scrollIntoView({ inline: 'nearest', block: 'nearest' }));
	});

</script>

<svelte:window onresize={() => (vh = innerHeight)} />

<section class="sheet card" aria-label={label} style:height="{height}px" data-snap={SNAPS[snap]} class:dragging={dragH !== null}>
	<button
		class="handle"
		aria-label="Panel size: {Math.round(SNAPS[snap] * 100)}% of the screen. Tap for the next size, or use the up and down arrows"
		onpointerdown={down}
		onpointermove={move}
		onpointerup={up}
		onpointercancel={up}
		onclick={click}
		onkeydown={key}
	>
		<span class="bar" aria-hidden="true"></span>
	</button>

	{#if wins.length}
		<div class="tabs" role="tablist" aria-label="Panels" tabindex="-1" onkeydown={tabKey}>
			<button
				bind:this={tabEls[0]}
				role="tab"
				id={tabId('details')}
				aria-selected={active === 'details'}
				aria-controls={panelId('details')}
				tabindex={active === 'details' ? 0 : -1}
				onclick={() => (active = 'details')}>Map</button
			>
			{#each wins as w, i (w.key)}
				<button
					bind:this={tabEls[i + 1]}
					role="tab"
					id={tabId(w.key)}
					aria-selected={active === w.key}
					aria-controls={panelId(w.key)}
					tabindex={active === w.key ? 0 : -1}
					onclick={() => (active = w.key)}
				>
					<span class="number num" aria-hidden="true">{w.number}</span>
					<span class="name">{w.title}</span>
				</button>
			{/each}
		</div>
	{/if}

	<div class="panel" role={wins.length ? 'tabpanel' : undefined} id={panelId('details')} aria-labelledby={wins.length ? tabId('details') : undefined} hidden={active !== 'details'}>
		{@render children()}
		{#each slots.items('sheet') as it (it.id)}<it.component {...it.props} />{/each}
	</div>

	{#each wins as w (w.key)}
		<div class="panel win" role="tabpanel" id={panelId(w.key)} aria-labelledby={tabId(w.key)} data-window-key={w.key} tabindex="-1" hidden={active !== w.key}>
			<header class="win-head">
				<span class="number num" aria-hidden="true">{w.number}</span>
				<div class="names">
					<h2>{w.title}</h2>
					{#if w.status}
						<p class="status"><span class="shape" style:color={w.status.color} aria-hidden="true">{w.status.shape}</span> {w.status.word}</p>
					{/if}
				</div>
				<button class="tool" aria-pressed={w.pinned} aria-label={w.pinned ? 'Unpin' : 'Pin'} onclick={() => windows.pin(w.key)}><Icon icon={PIN} size={20} /></button>
				<button class="tool" aria-label="Close {w.title}" onclick={() => windows.close(w.key)}><Icon icon={CLOSE} size={20} /></button>
			</header>
			<PanelBoundary name={w.title}>
				<w.component {...w.props} win={w} />
			</PanelBoundary>
		</div>
	{/each}
</section>

<style>
	.sheet {
		display: flex;
		flex-direction: column;
		box-sizing: border-box;
		min-height: 0;
		border-radius: 20px 20px 16px 16px;
		overflow: hidden;
		transition: height 220ms cubic-bezier(0.3, 1.3, 0.6, 1);
	}
	.sheet.dragging {
		transition: none;
	}
	.handle {
		flex: none;
		display: grid;
		place-items: center;
		width: 100%;
		min-height: 44px;
		border: 0;
		background: none;
		cursor: grab;
		touch-action: none;
	}
	.handle:focus-visible,
	.tabs button:focus-visible,
	.tool:focus-visible {
		outline: none;
		box-shadow:
			inset 0 0 0 2px var(--ink),
			inset 0 0 0 5px var(--accent);
	}
	.bar {
		width: 44px;
		height: 5px;
		border-radius: 3px;
		background: var(--panel-edge);
	}
	.tabs {
		flex: none;
		display: flex;
		gap: 4px;
		padding: 0 8px 6px;
		overflow-x: auto;
		scrollbar-width: none;
	}
	.tabs button {
		flex: none;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		max-width: 46%;
		min-height: 44px;
		padding: 0 12px;
		border: 2px solid var(--panel-edge);
		border-radius: 14px;
		background: var(--panel);
		color: var(--ink);
		font: 600 14px var(--font-body);
		cursor: pointer;
	}
	.tabs button[aria-selected='true'] {
		background: var(--ink);
		border-color: var(--ink);
		color: var(--panel);
	}
	.tabs .name {
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}
	.number {
		flex: none;
		display: grid;
		place-items: center;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: var(--ink);
		color: var(--panel);
		font-size: 12px;
		font-weight: 600;
	}
	.tabs button[aria-selected='true'] .number {
		background: var(--panel);
		color: var(--ink);
	}
	.panel {
		flex: 1 1 auto;
		min-height: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: 0 8px 8px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.panel[hidden] {
		display: none;
	}
	.win-head {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.names {
		flex: 1;
		min-width: 0;
	}
	h2 {
		margin: 0;
		overflow: hidden;
		font: 600 16px var(--font-display);
		white-space: nowrap;
		text-overflow: ellipsis;
	}
	.status {
		margin: 0;
		font-size: 12px;
	}
	.tool {
		display: grid;
		place-items: center;
		width: 44px;
		height: 44px;
		padding: 0;
		border: 0;
		border-radius: 12px;
		background: none;
		color: var(--ink-soft);
		cursor: pointer;
	}
	.tool[aria-pressed='true'] {
		background: var(--ink);
		color: var(--panel);
	}
	/* Touch targets: the legends' and cards' controls inside the sheet are 44 px too (§14.3). */
	.panel :global(button),
	.panel :global(a[href]),
	.panel :global(summary) {
		min-height: 44px;
	}
	.panel :global(button.close),
	.panel :global(button.pill.small) {
		min-width: 44px;
	}
	.panel :global(input[type='checkbox']),
	.panel :global(input[type='radio']) {
		width: 22px;
		height: 22px;
	}
	.panel :global(label.toggle) {
		display: flex;
		align-items: center;
		gap: 8px;
		min-height: 44px;
	}
	@media (prefers-reduced-motion: reduce) {
		.sheet {
			transition: none;
		}
	}
</style>
