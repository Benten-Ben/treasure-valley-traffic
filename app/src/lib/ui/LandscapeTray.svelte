<script module lang="ts">
	import type { LayerDef } from '#lib/layers/types.js';
	import type { IconData } from './icons.js';

	/**
	 * Phosphor's Mountains, duotone (MIT): the Landscape button's icon, as path data like the layers' own.
	 * Copied from phosphor-svelte's `MountainsIcon`; `keymap.test.ts` checks it against the installed package.
	 */
	export const LANDSCAPE: IconData = {
		name: 'Mountains',
		tone: 'M144,52a20,20,0,1,1,20,20A20,20,0,0,1,144,52Zm49.44,55.92a8,8,0,0,0-13.77,0l-33,55.75-21-35.67H50.35L8,200H248Z',
		line: 'M164,80a28,28,0,1,0-28-28A28,28,0,0,0,164,80Zm0-40a12,12,0,1,1-12,12A12,12,0,0,1,164,40Zm90.88,155.92-54.56-92.08A15.87,15.87,0,0,0,186.55,96h0a15.85,15.85,0,0,0-13.76,7.84L146.63,148l-44.84-76.1a16,16,0,0,0-27.58,0L1.11,195.94A8,8,0,0,0,8,208H248a8,8,0,0,0,6.88-12.08ZM88,80l23.57,40H64.43ZM22,192l33-56h66l33,56Zm150.57,0-16.66-28.28L186.55,112,234,192Z'
	};

	/**
	 * Whether the Landscape tray is open (the toolbar's popover on a desktop; a tab in the sheet on a phone).
	 * One flag for the button, the popover and the sheet's tab.
	 */
	export const tray = $state({ open: false });

	/** The defs that sit in the tray, in toolbar order (`LayerDef.group`). */
	export const inTray = (d: LayerDef): boolean => d.group === 'landscape';
</script>

<script lang="ts">
	import { layerIcon } from '#lib/layers/icons.js';
	import type { AppCtx } from '#lib/app/context.js';
	import Icon from './Icon.svelte';
	import { tipFor, tooltip } from './tooltip.svelte.js';

	/**
	 * The Landscape tray (landscape sprint plan §3.7; S3b): a row per layer that sits in it (Trees, Crop
	 * fields, Soils, Water, Trails, Fences), with its icon, title, blurb, the reason it can't be used yet, and
	 * its loading or problem state as the toolbar's buttons show them. A click toggles the layer and Shift+click
	 * solos it (Shift+Enter from the keyboard); the digit keys leave the tray alone, 1 (all off) covers it.
	 * Rows are 44 px tall, the touch target (§14.3).
	 */
	let { app, variant = 'popover' }: { app: AppCtx; variant?: 'popover' | 'sheet' } = $props();
	const manager = $derived(app.layers);
	const defs = $derived(manager.defs.filter(inTray));

	function press(e: MouseEvent, d: LayerDef, why: true | string) {
		tooltip.hide();
		if (why !== true) return;
		if (e.shiftKey) manager.solo(d.id);
		else manager.toggle(d.id);
	}

	function tip(e: Event, d: LayerDef) {
		const m = manager.modules[d.id];
		const age = m?.age?.();
		const lines = [d.blurb, age ? `${d.source} · ${age}` : d.source, 'Shift+click: only this layer'];
		tooltip.show(tipFor(e.currentTarget as Element, d.title, lines));
	}
</script>

<ul class="tray" class:popover={variant === 'popover'} class:sheet={variant === 'sheet'} aria-label="Landscape layers">
	{#each defs as d (d.id)}
		{@const status = manager.status(d.id)}
		{@const why = manager.available(d.id)}
		{@const on = manager.isOn(d.id)}
		{@const busy = on && (status === 'loading' || status === 'idle')}
		{@const problem = status === 'error' || status === 'stale' ? (manager.error(d.id) ?? 'Something went wrong') : null}
		<li>
			<button
				class="row"
				class:on
				data-layer={d.id}
				aria-pressed={on}
				aria-busy={busy}
				aria-disabled={why === true ? undefined : true}
				onclick={(e) => press(e, d, why)}
				onfocus={(e) => tip(e, d)}
				onblur={() => tooltip.hide()}
				onpointerenter={(e) => tip(e, d)}
				onpointerleave={() => tooltip.hide()}
			>
				<span class="disc">
					<Icon icon={layerIcon(d)} size={22} />
					{#if busy}<span class="ring" aria-hidden="true"></span>{/if}
				</span>
				<span class="text">
					<span class="title">{d.title}</span>
					<span class="blurb">{why === true ? d.blurb : why}</span>
					{#if busy}<span class="state" role="status">{d.loadingText ?? 'Loading…'}</span>{/if}
					{#if problem}<span class="state">▲ {problem}</span>{/if}
				</span>
				<span class="word" aria-hidden="true">{on ? 'On' : 'Off'}</span>
			</button>
		</li>
	{/each}
</ul>

<style>
	.tray {
		display: flex;
		flex-direction: column;
		gap: 4px;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.popover {
		width: 290px;
		max-height: min(70vh, 480px);
		overflow-y: auto;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 10px;
		width: 100%;
		min-height: 44px;
		box-sizing: border-box;
		padding: 4px 8px;
		border: 2px solid transparent;
		border-radius: 14px;
		background: none;
		color: var(--ink);
		font: 14px var(--font-body);
		text-align: left;
		cursor: pointer;
	}
	.row[aria-disabled='true'] {
		cursor: default;
	}
	.row[aria-disabled='true'] .disc,
	.row[aria-disabled='true'] .title {
		opacity: 0.55;
	}
	.row:hover:not([aria-disabled='true']) {
		background: rgb(43 42 51 / 0.06);
	}
	.row:focus-visible {
		outline: none;
		box-shadow:
			0 0 0 2px var(--ink),
			0 0 0 5px var(--accent);
	}
	.disc {
		position: relative;
		flex: none;
		display: grid;
		place-items: center;
		box-sizing: border-box;
		width: 36px;
		height: 36px;
		border: 2px solid var(--panel-edge);
		border-radius: 50%;
		background: var(--panel);
	}
	.on .disc {
		background: var(--ink);
		border-color: var(--ink);
		color: var(--panel);
	}
	.ring {
		position: absolute;
		inset: -4px;
		border: 3px solid transparent;
		border-top-color: var(--accent-2);
		border-radius: 50%;
		animation: spin 0.9s linear infinite;
	}
	@media (prefers-reduced-motion: reduce) {
		.ring {
			border: 2px dashed var(--accent-2);
			animation: none;
		}
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.text {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}
	.title {
		font: 600 14px var(--font-display);
	}
	.blurb,
	.state {
		font-size: 12px;
		color: var(--ink-soft);
	}
	.state {
		color: var(--ink);
	}
	.word {
		flex: none;
		font: 600 12px var(--font-body);
		color: var(--ink-soft);
	}
	.on .word {
		color: var(--ink);
	}
</style>
