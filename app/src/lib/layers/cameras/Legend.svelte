<script lang="ts">
	import type { LegendProps } from '../types.js';
	import { AMBER, CREAM, CREDIT, INK, TEAL } from './cameras.js';
	import type { CamerasModule } from './index.svelte.js';

	/**
	 * The Cameras legend (docs/14 §14.6, "What a camera looks like"): each key
	 * drawn as the map draws it, with the counts, and how to open a camera.
	 */
	let { module }: LegendProps = $props();
	const cams = $derived(module as unknown as CamerasModule);
</script>

<p class="legend-title">Cameras</p>
<ul class="keys">
	<li>
		<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
			<circle cx="10" cy="10" r="7" fill={TEAL} stroke={CREAM} stroke-width="2" />
			<path d="M6.8 10.2 9 12.4l4.4-4.6" fill="none" stroke={CREAM} stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
		</svg>
		Calibrated {#if cams.counts}<span class="num">({cams.counts.calibrated})</span>{/if}
	</li>
	<li>
		<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
			<circle cx="10" cy="10" r="6.5" fill={CREAM} stroke={AMBER} stroke-width="3" />
			<text x="10" y="13.4" text-anchor="middle" font-size="9.5" font-weight="700" fill={INK}>?</text>
		</svg>
		Needs calibration {#if cams.counts}<span class="num">({cams.counts.uncalibrated})</span>{/if}
	</li>
	<li>
		<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><circle cx="10" cy="10" r="3.5" fill="#9a958c" stroke={CREAM} stroke-width="1" /></svg>
		Not on 511 Idaho {#if cams.counts}<span class="num">({cams.counts.no_image})</span>{/if}
	</li>
	{#if cams.recorded.size}
		<li>
			<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
				<circle cx="10" cy="11.5" r="6" fill={TEAL} stroke={CREAM} stroke-width="2" />
				<rect x="6.5" y="1.5" width="7" height="5" rx="1.2" fill={INK} stroke={CREAM} stroke-width="1" />
			</svg>
			Recorded (the ink notch) <span class="num">({cams.recorded.size})</span>
		</li>
	{/if}
	{#if cams.calibrations.length}
		<li>
			<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
				<path d="M10 17 2.5 4.5h15Z" fill={TEAL} fill-opacity="0.2" stroke={TEAL} stroke-opacity="0.8" stroke-width="1.5" stroke-linejoin="round" />
			</svg>
			View footprint (calibrated, from z14)
		</li>
	{/if}
</ul>
<p class="hint">Click a camera to fly there and open its live picture.</p>
<p class="credit">{CREDIT}</p>

<style>
	li {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	svg {
		flex: none;
	}
	.hint {
		margin: 6px 0 0;
		color: var(--ink-soft);
		font-size: 12px;
	}
</style>
