<script lang="ts">
	import { onMount } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import type { Look } from '#lib/layers/manager.svelte.js';

	/**
	 * The Base popover (docs/14 §14.3, "Base"): Look (Auto · Map · Clay; Auto
	 * means Clay whenever a data layer is on), Aerial, Buildings, Terrain and
	 * Labels. Look drives the one temporary wash until WP4's flavors replace it.
	 */
	let { app, onclose }: { app: AppCtx; onclose: () => void } = $props();
	const base = $derived(app.layers.base.settings);
	const looks: { id: Look; label: string; hint: string }[] = [
		{ id: 'auto', label: 'Auto', hint: 'Clay whenever a data layer is on' },
		{ id: 'map', label: 'Map', hint: 'The full-color map' },
		{ id: 'clay', label: 'Clay', hint: 'Muted, so data stands out' }
	];
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
	</fieldset>
	{#if app.manifest?.imagery}
		<label class="switch">
			<input type="checkbox" role="switch" checked={app.aerial} onchange={(e) => app.setAerial(e.currentTarget.checked)} />
			<span>Aerial photos <small>(NAIP)</small></span>
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
