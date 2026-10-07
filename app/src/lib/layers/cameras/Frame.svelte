<script lang="ts">
	import { onDestroy } from 'svelte';
	import { IDENTITY, isIdentity, panBy, wheelFactor, zoomAt, type ZoomState } from './zoom.js';

	/**
	 * A camera picture (docs/14 §14.6, "Camera windows"; WP12): the newest
	 * frame, decoded before it's shown and crossfaded over the last one in
	 * 200 ms (at once under reduced motion). The wheel zooms up to 4× about
	 * the pointer, a drag pans, a double-click resets. A frame that fails to
	 * load keeps the last one on screen.
	 */
	let {
		url,
		alt,
		aspect,
		empty = null,
		onshown
	}: {
		/** The frame's URL (immutable: a new picture has a new URL); null for none yet. */
		url: string | null;
		alt: string;
		/** width / height */
		aspect: number;
		/** What the box says while there's no picture (default: waiting for one). */
		empty?: string | null;
		/** A frame is on screen (its URL). */
		onshown?: (url: string) => void;
	} = $props();

	const FADE_MS = 200;
	const reduced = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

	interface Layer {
		url: string;
		id: number;
	}
	let layers = $state<Layer[]>([]);
	let failed = $state<string | null>(null);
	let seq = 0;
	let wanted: string | null = null;
	let timers: ReturnType<typeof setTimeout>[] = [];
	let gone = false;

	async function show(next: string) {
		wanted = next;
		const img = new Image();
		img.decoding = 'async';
		img.src = next;
		try {
			await img.decode();
		} catch {
			if (wanted === next && !gone) failed = next;
			return;
		}
		// A newer frame was asked for meanwhile, or the window closed.
		if (wanted !== next || gone) return;
		failed = null;
		const id = ++seq;
		const instant = reduced() || layers.length === 0;
		layers = [...layers.slice(-1), { url: next, id }];
		onshown?.(next);
		const drop = () => {
			if (!gone) layers = layers.filter((l) => l.id >= id);
		};
		if (instant) drop();
		else timers.push(setTimeout(drop, FADE_MS + 20));
	}

	$effect(() => {
		const u = url;
		if (u && u !== layers.at(-1)?.url && u !== wanted) void show(u);
	});

	onDestroy(() => {
		gone = true;
		for (const t of timers) clearTimeout(t);
	});

	// --- zoom and pan ------------------------------------------------------------------
	let box: HTMLElement;
	let z = $state<ZoomState>(IDENTITY);
	let drag: { id: number; x: number; y: number } | null = null;

	function size() {
		const r = box.getBoundingClientRect();
		return { w: r.width, h: r.height, left: r.left, top: r.top };
	}

	function wheel(e: WheelEvent) {
		e.preventDefault();
		const b = size();
		const dy = e.deltaMode === 1 ? e.deltaY * 40 : e.deltaY;
		z = zoomAt(z, wheelFactor(dy), e.clientX - b.left, e.clientY - b.top, b.w, b.h);
	}

	function down(e: PointerEvent) {
		if (e.button !== 0 || isIdentity(z)) return;
		box.setPointerCapture(e.pointerId);
		drag = { id: e.pointerId, x: e.clientX, y: e.clientY };
		e.preventDefault();
	}

	function move(e: PointerEvent) {
		if (!drag || e.pointerId !== drag.id) return;
		const b = size();
		z = panBy(z, e.clientX - drag.x, e.clientY - drag.y, b.w, b.h);
		drag = { ...drag, x: e.clientX, y: e.clientY };
	}

	function up(e: PointerEvent) {
		if (drag && e.pointerId === drag.id) drag = null;
	}

	// The wheel must be able to cancel the page's scroll, so it's not a passive listener.
	$effect(() => {
		const el = box;
		el.addEventListener('wheel', wheel, { passive: false });
		return () => el.removeEventListener('wheel', wheel);
	});
</script>

<!-- Zoom and pan are for pointers; the picture is complete at 1×, and double-click resets. -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	bind:this={box}
	class="frame"
	class:zoomed={!isIdentity(z)}
	style:aspect-ratio={aspect}
	data-no-drag
	onpointerdown={down}
	onpointermove={move}
	onpointerup={up}
	onpointercancel={up}
	ondblclick={() => (z = IDENTITY)}
>
	<div class="zoom" style:transform="translate({z.x}px, {z.y}px) scale({z.s})">
		{#each layers as l (l.id)}
			<img
				src={l.url}
				{alt}
				class="pic"
				class:enter={layers.length > 1 && l.id === layers.at(-1)?.id}
				aria-hidden={l.id !== layers.at(-1)?.id ? 'true' : undefined}
				draggable="false"
				data-frame-url={l.url}
			/>
		{/each}
	</div>
	{#if !layers.length}
		<p class="empty">{failed ? 'This picture failed to load' : (empty ?? 'Waiting for a picture…')}</p>
	{/if}
	{#if z.s > 1}<span class="scale num" aria-hidden="true">{z.s.toFixed(1)}×</span>{/if}
</div>

<style>
	.frame {
		position: relative;
		width: 100%;
		overflow: hidden;
		background:
			repeating-linear-gradient(135deg, rgb(43 42 51 / 0.06) 0 8px, transparent 8px 16px),
			var(--ground);
		touch-action: pan-y;
		user-select: none;
	}
	.frame.zoomed {
		cursor: grab;
		touch-action: none;
	}
	.zoom {
		position: absolute;
		inset: 0;
		transform-origin: 0 0;
	}
	.pic {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: contain;
		-webkit-user-drag: none;
	}
	.pic.enter {
		animation: fade 200ms ease-out;
	}
	@keyframes fade {
		from {
			opacity: 0;
		}
	}
	.empty {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		margin: 0;
		color: var(--ink-soft);
		font-size: 13px;
	}
	.scale {
		position: absolute;
		top: 6px;
		right: 6px;
		padding: 1px 6px;
		border-radius: 999px;
		background: var(--panel);
		color: var(--ink);
		font-size: 11px;
	}
	@media (prefers-reduced-motion: reduce) {
		.pic.enter {
			animation: none;
		}
	}
</style>
