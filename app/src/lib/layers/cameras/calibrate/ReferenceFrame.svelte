<script lang="ts">
	import { barPx, type Pixel } from '#lib/calibration/solver.js';
	import Icon from '#lib/ui/Icon.svelte';
	import { pairNear, residualMark, type DraftPair, type RefFrame } from './draft.js';
	import { FIT } from './icons.js';

	/**
	 * The frozen reference frame (docs/14 §14.6, "Panel"): the one picture the
	 * pairs are clicked on.
	 *
	 * - A click places the next image point (or moves the pending one); a click
	 *   on a numbered point selects its pair; dragging a point moves it.
	 * - The wheel zooms (up to 8×) around the pointer; dragging pans once
	 *   zoomed; Fit goes back to the whole picture.
	 * - The 511 timestamp bar (its height worked out per frame) is shaded:
	 *   it isn't ground, and clicks on it are refused.
	 * - With a solution, each pair shows where the solved camera puts its
	 *   ground point (a cross) and a line to the clicked point, marked with
	 *   the error's shape (● ▲ ■), never color alone.
	 * - Blink alternates the live picture over it (same size only), to see
	 *   whether the camera has moved since.
	 */
	let {
		frame,
		live = null,
		blink = false,
		pairs,
		selected = null,
		projected = [],
		residuals = [],
		onplace,
		onselect,
		onmove,
		onrefused
	}: {
		frame: RefFrame;
		live?: { url: string; width: number; height: number } | null;
		blink?: boolean;
		pairs: readonly DraftPair[];
		selected?: number | null;
		/** Per pair: where the solved pose projects its ground point (null when unsolved). */
		projected?: readonly (Pixel | null)[];
		residuals?: readonly (number | null)[];
		onplace: (px: Pixel) => void;
		onselect: (i: number) => void;
		onmove: (i: number, px: Pixel) => void;
		onrefused?: (why: string) => void;
	} = $props();

	const MAX_ZOOM = 8;
	let cw = $state(0);
	let zoom = $state(1);
	let pan = $state({ x: 0, y: 0 });
	let box: HTMLDivElement | null = $state(null);
	let showLive = $state(false);
	let drag: { i: number; px: Pixel } | null = $state(null);

	const ch = $derived(cw ? (cw * frame.height) / frame.width : 0);
	/** Image px per screen px: markers keep their size on screen at any zoom. */
	const unit = $derived(cw ? frame.width / (cw * zoom) : 1);
	const bar = $derived(barPx(frame.width, frame.height));
	const sameSize = $derived(!!live && live.width === frame.width && live.height === frame.height);

	// A new reference (or size) starts at the whole picture.
	$effect(() => {
		void frame.url;
		zoom = 1;
		pan = { x: 0, y: 0 };
	});

	// Blink: the live picture over the reference, on and off.
	$effect(() => {
		if (!blink || !sameSize) {
			showLive = false;
			return;
		}
		showLive = true;
		const t = setInterval(() => (showLive = !showLive), 650);
		return () => clearInterval(t);
	});

	function clampPan(p: { x: number; y: number }, z: number) {
		return { x: Math.min(0, Math.max(cw - cw * z, p.x)), y: Math.min(0, Math.max(ch - ch * z, p.y)) };
	}

	function onwheel(e: WheelEvent) {
		if (!box) return;
		e.preventDefault();
		const r = box.getBoundingClientRect();
		const cx = e.clientX - r.left;
		const cy = e.clientY - r.top;
		const z = Math.min(MAX_ZOOM, Math.max(1, zoom * Math.exp(-e.deltaY * 0.0015)));
		const k = z / zoom;
		pan = clampPan({ x: cx - (cx - pan.x) * k, y: cy - (cy - pan.y) * k }, z);
		zoom = z;
	}

	// The wheel must be able to cancel the panel's scroll, so it's not a passive listener.
	$effect(() => {
		const el = box;
		if (!el) return;
		el.addEventListener('wheel', onwheel, { passive: false });
		return () => el.removeEventListener('wheel', onwheel);
	});

	function fit() {
		zoom = 1;
		pan = { x: 0, y: 0 };
	}

	/** Screen point → image pixel. */
	function toImage(clientX: number, clientY: number): Pixel {
		const r = box!.getBoundingClientRect();
		const x = (clientX - r.left - pan.x) / zoom;
		const y = (clientY - r.top - pan.y) / zoom;
		return [(x / cw) * frame.width, (y / ch) * frame.height];
	}

	let down: { x: number; y: number; pan: { x: number; y: number }; pair: number; moved: boolean; id: number } | null = null;

	function onpointerdown(e: PointerEvent) {
		if (!box || e.button !== 0) return;
		const px = toImage(e.clientX, e.clientY);
		const pair = pairNear(pairs, px, 12 * unit);
		down = { x: e.clientX, y: e.clientY, pan: { ...pan }, pair, moved: false, id: e.pointerId };
		box.setPointerCapture?.(e.pointerId);
	}

	function onpointermove(e: PointerEvent) {
		if (!down || e.pointerId !== down.id) return;
		const dx = e.clientX - down.x;
		const dy = e.clientY - down.y;
		if (!down.moved && Math.hypot(dx, dy) < 4) return;
		down.moved = true;
		if (down.pair !== -1) drag = { i: down.pair, px: clampPx(toImage(e.clientX, e.clientY)) };
		else if (zoom > 1) pan = clampPan({ x: down.pan.x + dx, y: down.pan.y + dy }, zoom);
	}

	function clampPx(px: Pixel): Pixel {
		return [Math.min(frame.width, Math.max(0, px[0])), Math.min(frame.height - bar - 0.5, Math.max(0, px[1]))];
	}

	function onpointerup(e: PointerEvent) {
		const d = down;
		down = null;
		if (!d || e.pointerId !== d.id) return;
		if (d.moved) {
			if (drag) onmove(drag.i, drag.px);
			drag = null;
			return;
		}
		if (d.pair !== -1) {
			onselect(d.pair);
			return;
		}
		const px = toImage(e.clientX, e.clientY);
		if (px[0] < 0 || px[1] < 0 || px[0] > frame.width || px[1] > frame.height) return;
		if (px[1] >= frame.height - bar) {
			onrefused?.('That’s the 511 timestamp bar, not ground: click on the road above it.');
			return;
		}
		onplace(px);
	}

	function onpointercancel() {
		down = null;
		drag = null;
	}

	/** Each pair's image point as drawn (a dragged one follows the pointer). */
	const points = $derived(pairs.map((p, i) => (drag && drag.i === i ? drag.px : (p.pixel ?? null))));
</script>

<div class="ref">
	<div
		class="frame"
		class:zoomed={zoom > 1}
		bind:this={box}
		bind:clientWidth={cw}
		style:aspect-ratio="{frame.width} / {frame.height}"
		role="application"
		aria-label="Reference frame: click a ground feature to place a point; the wheel zooms"
		data-frame={frame.frame}
		{onpointerdown}
		{onpointermove}
		{onpointerup}
		{onpointercancel}
	>
		<div class="inner" style:transform="translate({pan.x}px, {pan.y}px) scale({zoom})">
			<img class="pic" src={frame.url} alt="Reference frame used for calibration" draggable="false" />
			{#if live && sameSize}
				<img class="pic live" class:on={showLive} src={live.url} alt="" aria-hidden="true" draggable="false" />
			{/if}
			<svg viewBox="0 0 {frame.width} {frame.height}" preserveAspectRatio="none" aria-hidden="true">
				<rect class="bar" x="0" y={frame.height - bar} width={frame.width} height={bar} />
				{#each pairs as p, i (i)}
					{@const at = points[i]}
					{#if at}
						{@const q = projected[i]}
						{@const r = residuals[i]}
						{#if q && r !== null && r !== undefined && !(drag && drag.i === i)}
							{@const m = residualMark(r)}
							<line x1={at[0]} y1={at[1]} x2={q[0]} y2={q[1]} class="err {m.cls}" stroke-width={2 * unit} />
							<path d="M{q[0] - 5 * unit} {q[1]}h{10 * unit}M{q[0]} {q[1] - 5 * unit}v{10 * unit}" class="proj" stroke-width={2 * unit} />
						{/if}
						<circle cx={at[0]} cy={at[1]} r={9 * unit} class="pt" class:waiting={!p.ground} class:selected={i === selected} stroke-width={2 * unit} />
						<text x={at[0]} y={at[1] + 4 * unit} class="pt-label" font-size={11 * unit} stroke-width={2 * unit}>{i + 1}</text>
					{/if}
				{/each}
			</svg>
		</div>
		{#if live && sameSize && blink}
			<span class="which" aria-live="off">{showLive ? '● live' : '■ reference'}</span>
		{/if}
		{#if zoom > 1}
			<button class="fit pill" type="button" onpointerdown={(e) => e.stopPropagation()} onclick={fit} title="Back to the whole picture">
				<Icon icon={FIT} size={16} /> Fit <span class="num">{zoom.toFixed(1)}×</span>
			</button>
		{/if}
	</div>
</div>

<style>
	.ref {
		width: 100%;
	}
	.frame {
		position: relative;
		width: 100%;
		overflow: hidden;
		border-radius: 10px;
		background: var(--ground);
		cursor: crosshair;
		touch-action: none;
		user-select: none;
	}
	.frame.zoomed {
		cursor: crosshair;
	}
	.inner {
		position: absolute;
		inset: 0;
		transform-origin: 0 0;
	}
	.pic,
	svg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}
	.pic {
		display: block;
		image-rendering: auto;
	}
	.live {
		visibility: hidden;
	}
	.live.on {
		visibility: visible;
	}
	.bar {
		fill: rgb(43 42 51 / 0.35);
	}
	.pt {
		fill: rgb(242 162 12 / 0.35);
		stroke: #fff;
	}
	.pt.waiting {
		fill: rgb(242 162 12 / 0.9);
	}
	.pt.selected {
		stroke: var(--ink);
		fill: rgb(255 251 244 / 0.6);
	}
	.pt-label {
		font-family: var(--font-body);
		font-weight: 700;
		fill: #fff;
		text-anchor: middle;
		pointer-events: none;
		paint-order: stroke;
		stroke: rgb(0 0 0 / 0.6);
	}
	.proj {
		stroke: #fff;
	}
	.err.good {
		stroke: var(--accent-2);
	}
	.err.fair {
		stroke: var(--accent);
	}
	.err.bad {
		stroke: var(--alert);
	}
	.which {
		position: absolute;
		top: 6px;
		left: 6px;
		padding: 1px 8px;
		border-radius: 999px;
		background: var(--panel);
		color: var(--ink);
		font: 600 12px var(--font-body);
	}
	.fit {
		position: absolute;
		top: 6px;
		right: 6px;
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 2px 10px;
		font-size: 12px;
	}
</style>
