<script lang="ts">
	import type { Map } from 'maplibre-gl';
	import { onDestroy, untrack } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import { historyOf } from '#lib/state/history.svelte.js';
	import Icon from './Icon.svelte';
	import { HOME as HOME_VIEW, reducedMotion } from './keymap.js';
	import { slots } from './slots.svelte.js';
	import { tooltip } from './tooltip.svelte.js';
	import { HOME, OVERVIEW, ZOOM_IN, ZOOM_OUT } from './window-icons.js';

	/**
	 * The camera widget (docs/14 §14.3, right column; WP3), in place of
	 * MapLibre's NavigationControl: a column of 40 px game buttons.
	 *
	 * - Compass: the needle's solid ink half points north (the outlined half
	 *   south) and leans with the pitch; a click turns the map back to north.
	 * - Zoom in and out (disabled at the limits).
	 * - 2D/3D: flat, or back to the last tilt (50° the first time).
	 * - Home (over Meridian, as H) and Overview (the whole valley from above,
	 *   as O). Both are flies, so the view they leave goes on the history.
	 *
	 * The needle turns by direct style writes on every rotate and pitch event;
	 * Svelte state changes only on `moveend` (no state writes per frame).
	 */
	let { app }: { app: AppCtx } = $props();
	const ctx = untrack(() => app);
	const history = historyOf(ctx);

	let needle: HTMLElement | undefined = $state();
	let bearing = $state(0);
	let pitch = $state(0);
	let zoom = $state(0);
	let minZoom = $state(0);
	let maxZoom = $state(24);
	let lastPitch = 50;
	let map: Map | null = null;
	let gone = false;

	const duration = (ms: number) => (reducedMotion() ? 0 : ms);

	function turn() {
		if (!map || !needle) return;
		needle.style.transform = `rotateX(${map.getPitch()}deg) rotateZ(${-map.getBearing()}deg)`;
	}

	function settle() {
		if (!map) return;
		turn();
		bearing = map.getBearing();
		pitch = map.getPitch();
		zoom = map.getZoom();
		minZoom = map.getMinZoom();
		maxZoom = map.getMaxZoom();
		if (pitch > 1) lastPitch = pitch;
	}

	void ctx.styleReady
		.then((m) => {
			if (gone) return;
			map = m;
			m.on('rotate', turn);
			m.on('pitch', turn);
			m.on('moveend', settle);
			settle();
		})
		.catch(() => {});

	// The needle element arrives after the map in some orders: point it once it's there.
	$effect(() => {
		if (needle) turn();
	});

	onDestroy(() => {
		gone = true;
		map?.off('rotate', turn);
		map?.off('pitch', turn);
		map?.off('moveend', settle);
		map = null;
	});

	const is3d = $derived(pitch > 1);
	const facing = $derived(compassWord(bearing));

	function compassWord(b: number): string {
		const n = ((b % 360) + 360) % 360;
		if (n < 0.5 || n > 359.5) return 'north';
		return `${['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'][Math.round(n / 45) % 8]} (${Math.round(n)}°)`;
	}

	function north() {
		map?.easeTo({ bearing: 0, duration: duration(300) });
	}

	function zoomBy(dz: number) {
		if (!map) return;
		if (dz > 0) map.zoomIn({ duration: duration(250) });
		else map.zoomOut({ duration: duration(250) });
	}

	function toggle3d() {
		if (!map) return;
		if (map.getPitch() > 1) {
			lastPitch = map.getPitch();
			map.easeTo({ pitch: 0, duration: duration(400) });
		} else map.easeTo({ pitch: Math.min(lastPitch, map.getMaxPitch()), duration: duration(400) });
	}

	function home() {
		history.fly({ ...HOME_VIEW, duration: 1200 });
	}

	function overview() {
		const b = ctx.manifest?.bounds;
		if (!map || !b) return;
		const cam = map.cameraForBounds(
			[
				[b[0], b[1]],
				[b[2], b[3]]
			],
			{ padding: 40, bearing: 0, pitch: 0 }
		);
		if (cam) history.fly({ ...cam, bearing: 0, pitch: 0, duration: 1200 });
	}

	/** The tooltip goes to the left of the column, never over the widget's other buttons. */
	function tip(e: Event, title: string, lines: string[]) {
		const r = (e.currentTarget as Element).getBoundingClientRect();
		// 'cursor' placement flips to the left of x at the screen's right edge; the top lands at y + 12.
		tooltip.show({ x: r.left, y: r.top - 12, placement: 'cursor', title, lines });
	}
	const hide = () => tooltip.hide();
</script>

<div class="widget" role="group" aria-label="Map camera">
	<button
		class="btn compass"
		aria-label="Turn back to north (facing {facing})"
		onclick={north}
		onpointerenter={(e) => tip(e, 'North up', [`Facing ${facing}`, 'Q / E rotate'])}
		onfocus={(e) => tip(e, 'North up', [`Facing ${facing}`, 'Q / E rotate'])}
		onpointerleave={hide}
		onblur={hide}
	>
		<span class="needle" bind:this={needle} aria-hidden="true">
			<svg viewBox="0 0 24 24" width="28" height="28">
				<path d="M12 2 16 12H8Z" fill="var(--ink)" />
				<path d="M12 22 8 12h8Z" fill="var(--panel)" stroke="var(--ink-soft)" stroke-width="1.2" stroke-linejoin="round" />
			</svg>
		</span>
	</button>

	<div class="pair">
		<button
			class="btn"
			aria-label="Zoom in"
			disabled={zoom >= maxZoom - 1e-6}
			onclick={() => zoomBy(1)}
			onpointerenter={(e) => tip(e, 'Zoom in', ['+ or the wheel'])}
			onfocus={(e) => tip(e, 'Zoom in', ['+ or the wheel'])}
			onpointerleave={hide}
			onblur={hide}><Icon icon={ZOOM_IN} size={20} /></button
		>
		<button
			class="btn"
			aria-label="Zoom out"
			disabled={zoom <= minZoom + 1e-6}
			onclick={() => zoomBy(-1)}
			onpointerenter={(e) => tip(e, 'Zoom out', ['− or the wheel'])}
			onfocus={(e) => tip(e, 'Zoom out', ['− or the wheel'])}
			onpointerleave={hide}
			onblur={hide}><Icon icon={ZOOM_OUT} size={20} /></button
		>
	</div>

	<button
		class="btn dim"
		aria-label="3D view"
		aria-pressed={is3d}
		onclick={toggle3d}
		onpointerenter={(e) => tip(e, is3d ? '3D view (tilted)' : '2D view (from above)', [is3d ? 'Click for a flat map' : 'Click to tilt', 'R / F tilt'])}
		onfocus={(e) => tip(e, is3d ? '3D view (tilted)' : '2D view (from above)', [is3d ? 'Click for a flat map' : 'Click to tilt', 'R / F tilt'])}
		onpointerleave={hide}
		onblur={hide}>3D</button
	>

	<div class="pair">
		<button
			class="btn"
			aria-label="Home: over Meridian"
			onclick={home}
			onpointerenter={(e) => tip(e, 'Home', ['Over Meridian · key H'])}
			onfocus={(e) => tip(e, 'Home', ['Over Meridian · key H'])}
			onpointerleave={hide}
			onblur={hide}><Icon icon={HOME} size={20} /></button
		>
		<button
			class="btn"
			aria-label="Overview: the whole valley"
			onclick={overview}
			onpointerenter={(e) => tip(e, 'Overview', ['The whole valley, from above · key O'])}
			onfocus={(e) => tip(e, 'Overview', ['The whole valley, from above · key O'])}
			onpointerleave={hide}
			onblur={hide}><Icon icon={OVERVIEW} size={20} /></button
		>
	</div>
	{#each slots.items('camera-widget') as it (it.id)}<it.component {...it.props} />{/each}
</div>

<style>
	.widget {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
		pointer-events: auto;
	}
	.btn {
		position: relative;
		display: grid;
		place-items: center;
		box-sizing: border-box;
		width: 40px;
		height: 40px;
		padding: 0;
		border: 2px solid var(--panel-edge);
		border-radius: 50%;
		background: var(--panel);
		box-shadow: 0 3px 0 rgb(60 45 20 / 0.16);
		color: var(--ink);
		cursor: pointer;
		transition:
			transform 80ms,
			box-shadow 80ms,
			background 120ms;
	}
	.btn:active:not(:disabled) {
		transform: translateY(2px);
		box-shadow: 0 1px 0 rgb(60 45 20 / 0.16);
	}
	.btn:disabled {
		cursor: default;
		color: var(--ink-soft);
		opacity: 0.5;
	}
	.btn:focus {
		outline: none;
	}
	.btn:focus-visible {
		box-shadow:
			0 0 0 2px var(--ink),
			0 0 0 5px var(--accent);
		z-index: 1;
	}
	.pair {
		display: flex;
		flex-direction: column;
		border: 2px solid var(--panel-edge);
		border-radius: 20px;
		background: var(--panel);
		box-shadow: 0 3px 0 rgb(60 45 20 / 0.16);
	}
	.pair .btn {
		width: 36px;
		height: 40px;
		border: 0;
		border-radius: 18px;
		background: none;
		box-shadow: none;
	}
	.pair .btn + .btn {
		border-top: 2px solid var(--panel-edge);
		border-radius: 0 0 18px 18px;
	}
	.pair .btn:first-child {
		border-radius: 18px 18px 0 0;
	}
	.pair .btn:hover:not(:disabled),
	.btn:hover:not(:disabled) {
		background: #f6efe2;
	}
	.compass {
		perspective: 120px;
	}
	.needle {
		display: grid;
		place-items: center;
		transform-style: preserve-3d;
	}
	.dim {
		font: 600 14px var(--font-display);
	}
	.dim[aria-pressed='true'] {
		transform: translateY(2px);
		background: var(--ink);
		border-color: var(--ink);
		color: var(--panel);
		box-shadow: 0 1px 0 rgb(60 45 20 / 0.16);
	}
	.dim[aria-pressed='true']:hover {
		background: var(--ink);
	}
</style>
