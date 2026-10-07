<script lang="ts">
	/**
	 * Calibrating on the map (docs/14 §14.6; WP14): a child route of the map
	 * layout, so it renders only the calibration panel over the same map.
	 * Browser Back leaves, Forward re-enters, and a reload resumes the draft.
	 * The panel, the mode and the map side are in
	 * #lib/layers/cameras/calibrate/ (Calibrator.svelte, mapside.ts).
	 *
	 * A calibration link opened fresh has no view to go back to: the map opens
	 * at the camera (z16, pitch 50), and that's where leaving goes.
	 */
	import { untrack } from 'svelte';
	import { getAppCtx } from '#lib/app/context.js';
	import PanelBoundary from '#lib/components/PanelBoundary.svelte';
	import Calibrator from '#lib/layers/cameras/calibrate/Calibrator.svelte';

	let { data } = $props();
	const app = getAppCtx();

	// A deep link: open the map at this camera rather than somewhere else first (before the map exists).
	untrack(() => app.view.preferInitial({ center: data.camera.pole, zoom: 16, bearing: 0, pitch: 50 }));
</script>

<svelte:head>
	<title>Calibrate {data.camera.name} · Treasure Valley Traffic</title>
</svelte:head>

{#key data.camera.id}
	<PanelBoundary name="Calibrator">
		<Calibrator camera={data.camera} viewId={data.viewId} />
	</PanelBoundary>
{/key}
