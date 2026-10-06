<script lang="ts">
	import { onMount } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import type { Look } from '#lib/layers/manager.svelte.js';
	import { GROUND } from '#lib/map/flavors.js';

	/**
	 * The Base popover (docs/14 §14.3, "Base"; §14.5): Look (Auto · Map · Clay;
	 * Auto means Clay whenever a data layer is on), Aerial, Buildings, Terrain
	 * and Labels. Look picks the basemap flavor: Map is the Valley look, Clay
	 * the pale backdrop for data, crossfading in 350 ms.
	 */
	let { app, onclose }: { app: AppCtx; onclose: () => void } = $props();
	const base = $derived(app.layers.base.settings);
	const looks: { id: Look; label: string; hint: string }[] = [
		{ id: 'auto', label: 'Auto', hint: 'Clay whenever a data layer is on' },
		{ id: 'map', label: 'Map', hint: 'The full-color valley' },
		{ id: 'clay', label: 'Clay', hint: 'Pale and quiet, so data stands out' }
	];
	const flavor = $derived(app.layers.flavor);
	const exploring = $derived(app.modes.current === 'explore');
	/** What the Look does right now, in words. */
	const now = $derived.by(() => {
		if (!exploring) return 'Map look while this mode is open';
		if (base.look === 'auto') return flavor === 'clay' ? 'Now Clay: a data layer is on' : 'Now Map: no data layer is on';
		return base.look === 'clay' ? 'Clay, whatever is on' : 'Map, whatever is on';
	});
	let first: HTMLInputElement | undefined = $state();
	onMount(() => first?.focus());
</script>

<div class="base-popover card" id="base-popover" role="dialog" aria-label="Base map">
	<fieldset>
		<legend>Look</legend>
		<div class="seg">
			{#each looks as l, i (l.id)}
				<label title={l.hint}>
					{#if i === 0}
						<input bind:this={first} type="radio" name="look" value={l.id} checked={base.look === l.id} onchange={() => app.layers.setBase('look', l.id)} />
					{:else}
						<input type="radio" name="look" value={l.id} checked={base.look === l.id} onchange={() => app.layers.setBase('look', l.id)} />
					{/if}
					<span>{l.label}</span>
				</label>
			{/each}
		</div>
		<p class="now" data-flavor={flavor}><i class="chip" style:background={flavor === 'clay' ? GROUND.clay : GROUND.valley} aria-hidden="true"></i>{now}</p>
	</fieldset>
	{#if app.manifest?.imagery}
		<label class="switch">
			<input type="checkbox" role="switch" checked={app.aerial} onchange={(e) => app.setAerial(e.currentTarget.checked)} />
			<span>Aerial photos <small>(NAIP{flavor === 'clay' ? ', muted in Clay' : ''})</small></span>
		</label>
	{/if}
	{#if app.manifest?.buildings}
		<label class="switch">
			<input type="checkbox" role="switch" checked={base.buildings} onchange={(e) => app.layers.setBase('buildings', e.currentTarget.checked)} />
			<span>3D buildings</span>
		</label>
	{/if}
	{#if app.manifest?.terrain}
		<label class="switch">
			<input type="checkbox" role="switch" checked={base.terrain} onchange={(e) => app.layers.setBase('terrain', e.currentTarget.checked)} />
			<span>Terrain</span>
		</label>
	{/if}
	<fieldset>
		<legend>Labels</legend>
		<div class="seg">
			<label><input type="radio" name="labels" value="full" checked={base.labels === 'full'} onchange={() => app.layers.setBase('labels', 'full')} /><span>Full</span></label>
			<label><input type="radio" name="labels" value="fewer" checked={base.labels === 'fewer'} onchange={() => app.layers.setBase('labels', 'fewer')} /><span>Fewer</span></label>
		</div>
		{#if flavor === 'clay' && base.labels === 'full'}
			<p class="now">Clay leaves out addresses, places of interest and minor street names</p>
		{/if}
	</fieldset>
	<button class="done pill" onclick={onclose}>Done</button>
</div>

<style>
	.base-popover {
		position: absolute;
		left: 0;
		bottom: calc(100% + 10px);
		z-index: 50;
		width: 250px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 12px 14px;
		font-size: 14px;
	}
	fieldset {
		margin: 0;
		padding: 0;
		border: 0;
	}
	legend {
		margin-bottom: 4px;
		font: 600 13px var(--font-display);
		color: var(--ink-soft);
	}
	.seg {
		display: flex;
		gap: 2px;
		padding: 3px;
		border-radius: 12px;
		background: var(--ground);
	}
	.seg label {
		flex: 1;
		position: relative;
	}
	.seg input {
		position: absolute;
		opacity: 0;
		inset: 0;
		margin: 0;
		cursor: pointer;
	}
	.seg span {
		display: block;
		padding: 5px 0;
		border-radius: 9px;
		text-align: center;
		font: 600 13px var(--font-body);
	}
	.seg input:checked + span {
		background: var(--ink);
		color: var(--panel);
	}
	.seg input:focus-visible + span {
		box-shadow:
			0 0 0 2px var(--ink),
			0 0 0 5px var(--accent);
	}
	.now {
		display: flex;
		align-items: center;
		gap: 6px;
		margin: 6px 2px 0;
		font-size: 12px;
		line-height: 1.3;
		color: var(--ink-soft);
	}
	.chip {
		flex: none;
		width: 12px;
		height: 12px;
		border-radius: 4px;
		box-shadow: inset 0 0 0 1px #b9ad99;
	}
	.switch {
		display: flex;
		align-items: center;
		gap: 8px;
		cursor: pointer;
	}
	.switch input {
		width: 18px;
		height: 18px;
		accent-color: var(--ink);
	}
	small {
		color: var(--ink-soft);
	}
	.done {
		align-self: flex-end;
	}
</style>
