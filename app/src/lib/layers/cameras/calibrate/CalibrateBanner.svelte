<script lang="ts">
	import type { AppCtx } from '#lib/app/context.js';
	import Icon from '#lib/ui/Icon.svelte';
	import { CALIBRATE } from '../icons.js';
	import { calibrate } from './state.svelte.js';

	/**
	 * Calibrate mode's strip (docs/14 §14.3, "Modes"): shown in place of the
	 * toolbar through WP2's banner slot. It says what mode the map is in, what
	 * the next click does, and how to get out; the panel holds the actions.
	 * It sits centred over the map's part of the screen (the panel takes the
	 * left 45%).
	 */
	// The banner slot passes the app; this strip reads only the calibrator's state.
	let { app: _app }: { app: AppCtx } = $props();

	const next = $derived(
		calibrate.step === 'map'
			? 'now click the same spot on the map'
			: calibrate.step === 'image'
				? 'now click the same spot in the picture'
				: 'click a ground feature in the picture, then on the map'
	);
</script>

<div class="calib-banner card" role="group" aria-label="Calibrate mode">
	<span class="mode"><Icon icon={CALIBRATE} size={18} /> Calibrating</span>
	<span class="name">{calibrate.name}</span>
	<span class="next">{next}</span>
	<span class="fit num">
		{calibrate.pairs} pair{calibrate.pairs === 1 ? '' : 's'}{#if calibrate.rms !== null} · fit {calibrate.rms.toFixed(2)} px{/if}{#if calibrate.draft} · draft kept{/if}
	</span>
	<kbd>Esc</kbd><span class="esc">leaves (the draft is kept)</span>
</div>

<style>
	.calib-banner {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 12px;
		max-width: min(560px, 50vw);
		padding: 8px 14px;
		font-size: 13px;
		/* Centred over the map, right of the 45% panel. */
		transform: translateX(22.5vw);
	}
	.mode {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font: 600 14px var(--font-display);
	}
	.name {
		font-weight: 700;
	}
	.next {
		color: var(--ink);
	}
	.fit {
		color: var(--ink-soft);
		font-size: 12px;
	}
	kbd {
		padding: 0 5px;
		border: 1.5px solid var(--panel-edge);
		border-radius: 5px;
		font: 600 11px var(--font-mono);
	}
	.esc {
		color: var(--ink-soft);
		font-size: 12px;
	}
</style>
