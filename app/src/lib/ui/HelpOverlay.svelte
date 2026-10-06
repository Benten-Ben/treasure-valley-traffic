<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { allBindings, onBindingsChange, type KeyBinding } from './keys.js';

	/**
	 * Help (docs/14 §14.3, "Keymap"): every key in the registry, grouped, plus
	 * MapLibre's own and the Esc order. Esc or × closes it.
	 */
	let { onclose }: { onclose: () => void } = $props();
	let list = $state.raw<readonly KeyBinding[]>([...allBindings()]);
	const groups = $derived.by(() => {
		const out = new Map<string, KeyBinding[]>();
		for (const b of list) {
			if (b.help === false) continue;
			const g = out.get(b.group) ?? [];
			g.push(b);
			out.set(b.group, g);
		}
		return [...out.entries()];
	});
	// Esc is handled by the chrome, which opened this.
	const stopChange = onBindingsChange(() => (list = [...allBindings()]));
	onDestroy(stopChange);
	let closeButton: HTMLButtonElement | undefined = $state();
	onMount(() => closeButton?.focus());
</script>

<div class="scrim" role="presentation" onclick={onclose}></div>
<div class="help card" role="dialog" aria-modal="false" aria-labelledby="help-title">
	<header>
		<h2 id="help-title">Keys</h2>
		<button bind:this={closeButton} class="close" aria-label="Close help" onclick={onclose}>×</button>
	</header>
	<div class="cols">
		{#each groups as [group, items] (group)}
			<section>
				<h3>{group}</h3>
				<dl>
					{#each items as b (b.id)}
						<dt><kbd>{b.label}</kbd></dt>
						<dd>{b.description}</dd>
					{/each}
				</dl>
			</section>
		{/each}
		<section>
			<h3>Map</h3>
			<dl>
				<dt><kbd>← ↑ → ↓</kbd></dt>
				<dd>Pan (with the map focused)</dd>
				<dt><kbd>+ −</kbd></dt>
				<dd>Zoom</dd>
				<dt><kbd>Shift+arrows</kbd></dt>
				<dd>Rotate and tilt</dd>
				<dt><kbd>Esc</kbd></dt>
				<dd>Close: help or a popover, a window, look-through, calibrate, follow, the card, the selection</dd>
			</dl>
		</section>
	</div>
	<p class="note">Keys do nothing while you type in a box, or with Ctrl, Cmd or Alt held.</p>
</div>

<style>
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 60;
		background: rgb(43 42 51 / 0.25);
	}
	.help {
		position: fixed;
		top: 50%;
		left: 50%;
		z-index: 61;
		transform: translate(-50%, -50%);
		box-sizing: border-box;
		width: min(720px, calc(100vw - 24px));
		max-height: calc(100vh - 24px);
		overflow-y: auto;
		padding: 16px 20px;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	h2 {
		margin: 0;
		font: 600 22px var(--font-display);
	}
	.close {
		width: 40px;
		height: 40px;
		border: 0;
		border-radius: 50%;
		background: none;
		font-size: 24px;
		cursor: pointer;
		color: var(--ink-soft);
	}
	.cols {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: 4px 24px;
	}
	h3 {
		margin: 12px 0 4px;
		font: 600 15px var(--font-display);
	}
	dl {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 4px 10px;
		margin: 0;
		font-size: 13px;
	}
	dt {
		white-space: nowrap;
	}
	dd {
		margin: 0;
	}
	kbd {
		display: inline-block;
		padding: 1px 6px;
		border: 1.5px solid var(--panel-edge);
		border-bottom-width: 3px;
		border-radius: 6px;
		background: #fff;
		font: 600 12px var(--font-mono);
	}
	.note {
		margin: 14px 0 0;
		font-size: 12px;
		color: var(--ink-soft);
	}
</style>
