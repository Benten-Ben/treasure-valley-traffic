<script lang="ts">
	import type { LegendProps } from '../types.js';
	import { CREDIT } from './cameras.js';
	import type { CamerasModule } from './index.svelte.js';

	let { module }: LegendProps = $props();
	const cams = $derived(module as unknown as CamerasModule);
</script>

<p class="legend-title">Cameras</p>
<ul class="keys">
	<li><i class="dot calibrated"></i>Calibrated {#if cams.counts}<span class="num">({cams.counts.calibrated})</span>{/if}</li>
	<li><i class="dot uncalibrated"></i>Needs calibration {#if cams.counts}<span class="num">({cams.counts.uncalibrated})</span>{/if}</li>
	<li><i class="dot no-image"></i>No image yet {#if cams.counts}<span class="num">({cams.counts.no_image})</span>{/if}</li>
	{#if cams.calibrations.length}
		<li><i class="cone"></i>View cone (calibrated)</li>
	{/if}
</ul>
{#if cams.calibrations.length}
	<label class="toggle"><input type="checkbox" checked={cams.images} onchange={(e) => cams.setImages(e.currentTarget.checked)} /> Camera images on the map</label>
{/if}
<p class="credit">{CREDIT}</p>
