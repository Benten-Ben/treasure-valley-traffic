<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import { Z_BASE, type Rect, type WindowManager, type WinState } from '#lib/state/windows.svelte.js';
	import Icon from './Icon.svelte';
	import { CLOSE, DOCK_LEFT, DOCK_RIGHT, PIN } from './window-icons.js';
	import { tipFor, tooltip } from './tooltip.svelte.js';

	/**
	 * A floating window's frame (docs/14 §14.6, "Camera windows"; WP3): a
	 * non-modal dialog in band 30–39 whose content is the window's own
	 * component (WP12's camera view, WP16's station tabs, the test window).
	 *
	 * - Header: number badge, title, status (shape and word), then Pin, Dock
	 *   left, Dock right and Close. Dragging the header moves it (pointer
	 *   capture; `transform` while dragging), snapping within 8 px and never
	 *   going under the bars.
	 * - The grip in the corner resizes by width; the picture keeps its aspect.
	 *   ← and → on the focused grip resize it from the keyboard, and the dock
	 *   buttons place it without dragging (WCAG 2.5.7).
	 * - Focus moves in when it opens and back when it closes (the manager);
	 *   focusing or clicking it raises it.
	 */
	let { win, manager }: { win: WinState; manager: WindowManager } = $props();

	let el: HTMLElement;
	const uid = Math.random().toString(36).slice(2, 8);
	const titleId = `win-${uid}-title`;
	const z = $derived(Z_BASE + manager.rank(win.key));
	const room = $derived(manager.safe.bottom - manager.safe.top);
	const RESIZE_STEP = 20;

	// --- moving ------------------------------------------------------------------------
	let drag: { id: number; sx: number; sy: number; x0: number; y0: number; last: Rect | null } | null = null;

	function dragStart(e: PointerEvent) {
		if (e.button !== 0 || (e.target as Element).closest('button, a, input, select, textarea, [data-no-drag]')) return;
		manager.focus(win.key);
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		drag = { id: e.pointerId, sx: e.clientX, sy: e.clientY, x0: win.rect.x, y0: win.rect.y, last: null };
		el.classList.add('dragging');
		e.preventDefault();
	}

	function dragMove(e: PointerEvent) {
		if (!drag || e.pointerId !== drag.id) return;
		const r = manager.placeFor(win.key, { x: drag.x0 + e.clientX - drag.sx, y: drag.y0 + e.clientY - drag.sy });
		drag.last = r;
		el.style.transform = `translate(${r.x}px, ${r.y}px)`;
	}

	function dragEnd(e: PointerEvent) {
		if (!drag || e.pointerId !== drag.id) return;
		const d = drag;
		drag = null;
		el.classList.remove('dragging');
		if (d.last && (d.last.x !== win.rect.x || d.last.y !== win.rect.y)) manager.move(win.key, { x: d.last.x, y: d.last.y }, { snap: false });
		else el.style.transform = `translate(${win.rect.x}px, ${win.rect.y}px)`;
	}

	// --- resizing (by width; the picture keeps its aspect) -------------------------------
	let size: { id: number; sx: number; w0: number; last: number } | null = null;

	function sizeStart(e: PointerEvent) {
		if (e.button !== 0) return;
		manager.focus(win.key);
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		size = { id: e.pointerId, sx: e.clientX, w0: win.rect.w, last: win.rect.w };
		el.classList.add('resizing');
		e.preventDefault();
	}

	function sizeMove(e: PointerEvent) {
		if (!size || e.pointerId !== size.id) return;
		size.last = manager.widthFor(win.key, size.w0 + e.clientX - size.sx);
		el.style.width = `${size.last}px`;
	}

	function sizeEnd(e: PointerEvent) {
		if (!size || e.pointerId !== size.id) return;
		const s = size;
		size = null;
		el.classList.remove('resizing');
		if (s.last !== win.rect.w) manager.resize(win.key, s.last, { snap: false });
		else el.style.width = `${win.rect.w}px`;
	}

	function sizeKey(e: KeyboardEvent) {
		const step = e.key === 'ArrowRight' ? RESIZE_STEP : e.key === 'ArrowLeft' ? -RESIZE_STEP : 0;
		if (!step) return;
		e.preventDefault();
		e.stopPropagation();
		manager.resize(win.key, win.rect.w + step);
	}

	// --- height, focus ---------------------------------------------------------------------
	let observer: ResizeObserver | undefined;
	onMount(() => {
		observer = new ResizeObserver(() => {
			if (el) manager.measured(win.key, el.offsetHeight);
		});
		observer.observe(el);
		manager.measured(win.key, el.offsetHeight);
	});
	onDestroy(() => observer?.disconnect());

	$effect(() => {
		if (!win.takeFocus || !el) return;
		el.focus({ preventScroll: true });
		manager.focused(win.key);
	});

	function tip(e: Event, title: string, lines: string[] = []) {
		tooltip.show(tipFor(e.currentTarget as Element, title, lines));
	}
</script>

<div
	bind:this={el}
	class="window card"
	class:pinned={win.pinned}
	role="dialog"
	aria-labelledby={titleId}
	tabindex="-1"
	data-window-key={win.key}
	data-window-number={win.number}
	style:transform="translate({win.rect.x}px, {win.rect.y}px)"
	style:width="{win.rect.w}px"
	style:max-height="{room}px"
	style:z-index={z}
	onpointerdowncapture={() => manager.focus(win.key)}
	onfocusin={() => manager.focus(win.key)}
>
	<!-- Dragging is for pointers; the dock buttons place a window from the keyboard (WCAG 2.5.7). -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<header class="bar" onpointerdown={dragStart} onpointermove={dragMove} onpointerup={dragEnd} onpointercancel={dragEnd}>
		<span class="number num" aria-hidden="true">{win.number}</span>
		<div class="names">
			<h2 id={titleId} title={win.title}><span class="sr-only">Window {win.number}: </span>{win.title}</h2>
			{#if win.status}
				<p class="status" title={win.status.detail}>
					<span class="shape" style:color={win.status.color} aria-hidden="true">{win.status.shape}</span>
					{win.status.word}
				</p>
			{/if}
		</div>
		<div class="tools">
			<button
				class="tool"
				aria-pressed={win.pinned}
				aria-label={win.pinned ? 'Unpin' : 'Pin'}
				onclick={() => manager.pin(win.key)}
				onpointerenter={(e) => tip(e, win.pinned ? 'Unpin' : 'Pin', ['A pinned window stays open and comes back next visit'])}
				onpointerleave={() => tooltip.hide()}
			>
				<Icon icon={PIN} size={18} />
			</button>
			<button
				class="tool"
				aria-label="Dock left"
				onclick={() => manager.dock(win.key, 'left')}
				onpointerenter={(e) => tip(e, 'Dock left')}
				onpointerleave={() => tooltip.hide()}
			>
				<Icon icon={DOCK_LEFT} size={18} />
			</button>
			<button
				class="tool"
				aria-label="Dock right"
				onclick={() => manager.dock(win.key, 'right')}
				onpointerenter={(e) => tip(e, 'Dock right')}
				onpointerleave={() => tooltip.hide()}
			>
				<Icon icon={DOCK_RIGHT} size={18} />
			</button>
			<button
				class="tool close"
				aria-label="Close {win.title}"
				onclick={() => {
					tooltip.hide();
					manager.close(win.key);
				}}
				onpointerenter={(e) => tip(e, 'Close', ['Esc'])}
				onpointerleave={() => tooltip.hide()}
			>
				<Icon icon={CLOSE} size={18} />
			</button>
		</div>
	</header>
	<div class="content" style:--aspect={win.aspect ?? 'auto'}>
		<PanelBoundary name={win.title}>
			<win.component {...win.props} {win} />
		</PanelBoundary>
	</div>
	<button
		class="grip"
		aria-label="Resize {win.title} (← narrower, → wider)"
		onpointerdown={sizeStart}
		onpointermove={sizeMove}
		onpointerup={sizeEnd}
		onpointercancel={sizeEnd}
		onkeydown={sizeKey}
	>
		<svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M11 3 3 11M11 7 7 11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" /></svg>
	</button>
</div>

<style>
	.window {
		position: absolute;
		top: 0;
		left: 0;
		box-sizing: border-box;
		display: flex;
		flex-direction: column;
		min-width: 0;
		overflow: hidden;
		border-top-width: 4px;
		border-top-color: var(--accent-2);
		animation: pop 160ms ease-out;
	}
	/* The frame takes focus only so keys reach it (Esc, Tab into it); its controls show the focus ring. */
	.window:focus {
		outline: none;
	}
	.window.pinned {
		border-color: var(--ink);
		border-top-color: var(--accent-2);
	}
	.window:global(.dragging) {
		cursor: grabbing;
		will-change: transform;
		box-shadow:
			0 8px 0 rgb(60 45 20 / 0.12),
			0 16px 36px rgb(60 45 20 / 0.2);
	}
	@keyframes pop {
		from {
			opacity: 0;
			scale: 0.96;
		}
	}
	.bar {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 6px 6px 6px 10px;
		border-bottom: 2px solid var(--panel-edge);
		cursor: grab;
		touch-action: none;
		user-select: none;
	}
	.number {
		flex: none;
		display: grid;
		place-items: center;
		width: 24px;
		height: 24px;
		border-radius: 50%;
		background: var(--ink);
		color: var(--panel);
		font-size: 13px;
		font-weight: 600;
	}
	.names {
		flex: 1;
		min-width: 0;
	}
	h2 {
		margin: 0;
		overflow: hidden;
		font: 600 15px/1.25 var(--font-display);
		white-space: nowrap;
		text-overflow: ellipsis;
	}
	.status {
		margin: 0;
		overflow: hidden;
		color: var(--ink);
		font-size: 12px;
		line-height: 1.3;
		white-space: nowrap;
		text-overflow: ellipsis;
	}
	.shape {
		font-size: 11px;
	}
	.tools {
		flex: none;
		display: flex;
		gap: 2px;
	}
	.tool {
		display: grid;
		place-items: center;
		width: 30px;
		height: 30px;
		padding: 0;
		border: 0;
		border-radius: 9px;
		background: none;
		color: var(--ink-soft);
		cursor: pointer;
	}
	.tool:hover {
		background: rgb(43 42 51 / 0.08);
		color: var(--ink);
	}
	.tool[aria-pressed='true'] {
		background: var(--ink);
		color: var(--panel);
	}
	.tool:focus-visible,
	.grip:focus-visible {
		outline: none;
		box-shadow:
			0 0 0 2px var(--ink),
			0 0 0 5px var(--accent);
	}
	.content {
		flex: 1 1 auto;
		min-height: 0;
		overflow: auto;
		overscroll-behavior: contain;
	}
	.grip {
		position: absolute;
		right: 2px;
		bottom: 2px;
		display: grid;
		place-items: center;
		width: 20px;
		height: 20px;
		padding: 0;
		border: 0;
		border-radius: 6px;
		background: var(--panel);
		color: var(--ink-soft);
		cursor: nwse-resize;
		touch-action: none;
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
	@media (prefers-reduced-motion: reduce) {
		.window {
			animation: none;
		}
	}
</style>
