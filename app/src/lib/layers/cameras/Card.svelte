<script lang="ts">
	import type { CardProps } from '../types.js';
	import { CREDIT, STATUS_SHAPE, STATUS_TEXT, type CameraProps } from './cameras.js';

	let { selection }: CardProps = $props();
	const cam = $derived(selection.data as CameraProps);
</script>

<h2>{cam.name}</h2>
<p class="meta">
	<i class="dot {cam.status.replace('_', '-')}" aria-hidden="true"></i>{STATUS_SHAPE[cam.status]}
	{STATUS_TEXT[cam.status]}{#if cam.achdCamId}<span class="num"> · ACHD #{cam.achdCamId}</span>{/if}
</p>
{#if cam.status !== 'no_image'}
	<a class="pill primary" href={`/calibrate/${cam.id}`}>{cam.status === 'calibrated' ? 'Review calibration' : 'Calibrate'}</a>
{/if}
<p class="credit">{CREDIT}</p>
