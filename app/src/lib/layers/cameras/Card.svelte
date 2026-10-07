<script lang="ts">
	import type { CardProps } from '../types.js';
	import { CREDIT, STATUS_SHAPE, STATUS_TEXT, type CameraProps } from './cameras.js';
	import type { CamerasModule } from './index.svelte.js';

	/**
	 * The selected camera's inspect card: name, status (shape and word), ACHD
	 * number, whether it's recorded, and a way to its window (a click on the
	 * camera has already opened one; this brings it back after closing).
	 */
	let { selection, module }: CardProps = $props();
	const cam = $derived(selection.data as CameraProps);
	const cams = $derived(module as unknown as CamerasModule);
	const recorded = $derived(cams.recorded.has(cam.id));
</script>

<h2>{cam.name}</h2>
<p class="meta">
	<i class="dot {cam.status.replace('_', '-')}" aria-hidden="true"></i>{STATUS_SHAPE[cam.status]}
	{STATUS_TEXT[cam.status]}{#if cam.achdCamId}<span class="num"> · ACHD #{cam.achdCamId}</span>{/if}{#if recorded} · recorded{/if}
</p>
<div class="row">
	<button class="pill" onclick={() => cams.open(cam.id)}>{cams.windowOf(cam.id) === null ? 'Open its window' : 'Show its window'}</button>
	{#if cam.status !== 'no_image'}
		<a class="pill" href={`/calibrate/${cam.id}`}>{cam.status === 'calibrated' ? 'Review calibration' : 'Configure'}</a>
	{/if}
</div>
<p class="credit">{CREDIT}</p>

<style>
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
</style>
