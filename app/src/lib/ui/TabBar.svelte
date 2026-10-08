<script lang="ts">
	import { onDestroy, type Component } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import type { LayerDef } from '#lib/layers/types.js';
	import Icon from './Icon.svelte';
	import { STACK } from './chrome-icons.js';
	import { ESC, onEscape } from './keys.js';
	import { slots } from './slots.svelte.js';
	import { tipFor, tooltip } from './tooltip.svelte.js';

	/**
	 * The phone's tab bar (docs/14 §14.3, under 600 px; WP3): the toolbar as a
	 * 64 px row that scrolls sideways, one labelled tab per layer and Base at
	 * its end.
	 *
	 * - Each tab is at least 64 × 44 px; on is pressed (ink), loading shows a
	 *   ring (`aria-busy`), a problem shows ▲.
	 * - A long press (500 ms) shows the layer's tooltip instead of toggling it.
	 * - ← and → move between the tabs (roving tabindex); Esc closes Base.
	 */
	let { app }: { app: AppCtx } = $props();
	const manager = $derived(app.layers);
	let baseOpen = $state(false);
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let Popover = $state<Component<any> | null>(null);
	let current = $state(0);
	let tabs: HTMLButtonElement[] = $state([]);

	async function toggleBase() {
		if (!Popover) Popover = (await import('./BasePopover.svelte')).default;
		baseOpen = !baseOpen;
	}

	const stopEsc = onEscape(ESC.popover, () => {
		if (!baseOpen) return false;
		baseOpen = false;
		return true;
	});

	// --- long press -------------------------------------------------------------------
	const LONG_MS = 500;
	let pressTimer: ReturnType<typeof setTimeout> | undefined;
	let hideTimer: ReturnType<typeof setTimeout> | undefined;
	let longPressed = false;

	function pressStart(e: PointerEvent, title: string, lines: string[]) {
		longPressed = false;
		clearTimeout(pressTimer);
		const el = e.currentTarget as HTMLElement;
		pressTimer = setTimeout(() => {
			longPressed = true;
			tooltip.show(tipFor(el, title, lines), 0);
			clearTimeout(hideTimer);
			hideTimer = setTimeout(() => tooltip.hide(), 2500);
		}, LONG_MS);
	}

	function pressEnd() {
		clearTimeout(pressTimer);
	}

	/** A click that ends a long press only showed the tooltip. */
	function activate(run: () => void) {
		if (longPressed) {
			longPressed = false;
			return;
		}
		tooltip.hide();
		run();
	}

	onDestroy(() => {
		stopEsc();
		clearTimeout(pressTimer);
		clearTimeout(hideTimer);
	});

	function tipLines(d: LayerDef): string[] {
		const why = manager.available(d.id);
		const problem = manager.status(d.id) === 'error' || manager.status(d.id) === 'stale' ? manager.error(d.id) : null;
		return [d.blurb, d.source, ...(problem ? [`▲ ${problem}`] : []), ...(why === true ? [] : [why])];
	}

	function roving(e: KeyboardEvent) {
		if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
		e.preventDefault();
		e.stopPropagation();
		const n = tabs.filter(Boolean).length;
		if (!n) return;
		current = (current + (e.key === 'ArrowRight' ? 1 : -1) + n) % n;
		tabs[current]?.focus();
		tabs[current]?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
	}

	function outside(e: PointerEvent) {
		if (!baseOpen) return;
		const t = e.target as Element | null;
		if (t?.closest('.base-popover') || t?.closest('.base-tab')) return;
		baseOpen = false;
	}
</script>

<svelte:window onpointerdown={outside} />

<nav class="tabbar card" aria-label="Map layers">
	{#each manager.defs as d, i (d.id)}
		{@const status = manager.status(d.id)}
		{@const why = manager.available(d.id)}
		{@const busy = manager.isOn(d.id) && (status === 'loading' || status === 'idle')}
		<button
			bind:this={tabs[i]}
			class="tab"
			aria-pressed={manager.isOn(d.id)}
			aria-busy={busy}
			aria-disabled={why === true ? undefined : true}
			tabindex={current === i ? 0 : -1}
			onfocus={() => (current = i)}
			onkeydown={roving}
			onpointerdown={(e) => pressStart(e, d.key ? `${d.title} · key ${d.key}` : d.title, tipLines(d))}
			onpointerup={pressEnd}
			onpointerleave={pressEnd}
			onpointercancel={pressEnd}
			oncontextmenu={(e) => e.preventDefault()}
			onclick={() => activate(() => why === true && manager.toggle(d.id))}
		>
			<span class="icon">
				<Icon icon={d.icon} size={24} />
				{#if busy}<span class="ring" aria-hidden="true"></span>{/if}
				{#if status === 'error' || status === 'stale'}<span class="warn" aria-hidden="true">▲</span>{/if}
			</span>
			<span class="label">{d.title}</span>
			{#if status === 'error' || status === 'stale'}<span class="sr-only">: a problem (long-press for why)</span>{/if}
		</button>
	{/each}
	{#each slots.items('tabbar') as it (it.id)}<it.component {...it.props} />{/each}
	<button
		bind:this={tabs[manager.defs.length]}
		class="tab base-tab"
		aria-expanded={baseOpen}
		aria-controls="base-popover"
		tabindex={current === manager.defs.length ? 0 : -1}
		onfocus={() => (current = manager.defs.length)}
		onkeydown={roving}
		onpointerdown={(e) => pressStart(e, 'Base', ['Map look, aerial photos, buildings, terrain and labels'])}
		onpointerup={pressEnd}
		onpointerleave={pressEnd}
		onpointercancel={pressEnd}
		oncontextmenu={(e) => e.preventDefault()}
		onclick={() => activate(toggleBase)}
	>
		<span class="icon"><Icon icon={STACK} size={24} /></span>
		<span class="label">Base</span>
	</button>
</nav>
{#if baseOpen && Popover}
	<div class="pop"><Popover {app} onclose={() => (baseOpen = false)} /></div>
{/if}

<style>
	.tabbar {
		position: relative;
		display: flex;
		gap: 2px;
		height: 64px;
		box-sizing: border-box;
		padding: 4px;
		border-radius: 20px;
		overflow-x: auto;
		overscroll-behavior-x: contain;
		scrollbar-width: none;
	}
	.tabbar::-webkit-scrollbar {
		display: none;
	}
	.tab {
		/* At least 64 px, and as wide as its label: "Road weather" overflowed a 64 px share and its
		   cream text ran off the pressed tab (WP15's review). Past the screen's width the bar scrolls. */
		flex: 1 0 auto;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 2px;
		min-width: 64px;
		min-height: 52px;
		padding: 0 6px;
		border: 0;
		border-radius: 14px;
		background: none;
		color: var(--ink);
		font: 600 12px var(--font-body);
		cursor: pointer;
		-webkit-touch-callout: none;
		user-select: none;
		transition:
			transform 80ms,
			background 120ms;
	}
	.tab:active {
		transform: translateY(2px);
	}
	.tab[aria-pressed='true'] {
		background: var(--ink);
		color: var(--panel);
	}
	.tab[aria-disabled='true'] {
		opacity: 0.45;
		cursor: default;
	}
	.tab:focus-visible {
		outline: none;
		box-shadow:
			inset 0 0 0 2px var(--ink),
			inset 0 0 0 5px var(--accent);
	}
	.base-tab {
		border-left: 2px solid var(--panel-edge);
		border-radius: 0 14px 14px 0;
	}
	.icon {
		position: relative;
		display: grid;
		place-items: center;
	}
	.label {
		white-space: nowrap;
	}
	.ring {
		position: absolute;
		inset: -5px;
		border: 3px solid transparent;
		border-top-color: var(--accent-2);
		border-radius: 50%;
		animation: spin 0.9s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.ring {
			border: 2px dashed var(--accent-2);
		}
	}
	.warn {
		position: absolute;
		top: -6px;
		right: -10px;
		display: grid;
		place-items: center;
		width: 16px;
		height: 16px;
		border: 2px solid var(--panel);
		border-radius: 50%;
		background: var(--alert);
		color: #fff;
		font-size: 9px;
		line-height: 1;
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
	.pop {
		position: fixed;
		right: 8px;
		bottom: 84px;
		z-index: 50;
		max-width: calc(100vw - 16px);
	}
	.pop :global(.base-popover) {
		position: static;
	}
	.pop :global(.base-popover label),
	.pop :global(.base-popover button) {
		min-height: 44px;
	}
</style>
