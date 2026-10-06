<script lang="ts">
	import type { Icon as IconT } from '#lib/layers/types.js';
	import Icon from './Icon.svelte';
	import { tipFor, tooltip } from './tooltip.svelte.js';

	/**
	 * A 52 px round info-view button (docs/14 §14.3, "Buttons"): a duotone
	 * Phosphor icon with its label under it on hover or focus (always at
	 * 1280 px or wider).
	 *
	 * | state | look |
	 * |---|---|
	 * | off | panel background |
	 * | on | pressed in 2 px, ink background, cream icon (`aria-pressed`) |
	 * | focus | 2 px ink ring inside a 3 px amber ring |
	 * | loading | a rotating ring segment, `aria-busy` (static dashed under reduced motion) |
	 * | error | a ▲ badge; the tooltip gives the reason |
	 */
	let {
		label,
		icon,
		pressed = undefined,
		busy = false,
		problem = null,
		disabled = null,
		tip,
		tabindex = 0,
		expanded = undefined,
		controls = undefined,
		onclick,
		onkeydown,
		onfocus,
		element = $bindable()
	}: {
		label: string;
			icon: IconT;
		pressed?: boolean;
		busy?: boolean;
		/** The ▲ badge and the reason (error or stale). */
		problem?: string | null;
		/** The reason it can't be used. */
		disabled?: string | null;
		tip: { title: string; lines: string[] };
		tabindex?: number;
		expanded?: boolean;
		controls?: string;
		onclick: () => void;
		onkeydown?: (e: KeyboardEvent) => void;
		onfocus?: () => void;
		element?: HTMLButtonElement;
	} = $props();

	function show(e: Event) {
		const lines = [...tip.lines];
		if (problem) lines.push(`▲ ${problem}`);
		if (disabled) lines.push(disabled);
		tooltip.show(tipFor(e.currentTarget as Element, tip.title, lines));
	}
</script>

<button
	bind:this={element}
	class="round"
	class:on={pressed}
	class:busy
	aria-pressed={pressed}
	aria-busy={busy}
	aria-disabled={disabled ? true : undefined}
	aria-expanded={expanded}
	aria-controls={controls}
	aria-describedby={tooltip.current ? 'tvt-tooltip' : undefined}
	{tabindex}
	onclick={() => {
		tooltip.hide();
		if (!disabled) onclick();
	}}
	{onkeydown}
	onfocus={(e) => {
		onfocus?.();
		show(e);
	}}
	onblur={() => tooltip.hide()}
	onpointerenter={show}
	onpointerleave={() => tooltip.hide()}
>
	<span class="disc">
		<Icon {icon} size={26} />
		{#if busy}<span class="ring" aria-hidden="true"></span>{/if}
		{#if problem}<span class="warn" aria-hidden="true">▲</span>{/if}
	</span>
	<span class="label">{label}</span>
</button>

<style>
	.round {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 3px;
		width: 64px;
		padding: 0;
		border: 0;
		background: none;
		color: var(--ink);
		font: 600 12px var(--font-body);
		cursor: pointer;
	}
	.round[aria-disabled='true'] {
		cursor: default;
	}
	.round[aria-disabled='true'] .disc {
		opacity: 0.45;
	}
	.disc {
		position: relative;
		display: grid;
		place-items: center;
		box-sizing: border-box;
		width: 52px;
		height: 52px;
		border: 2px solid var(--panel-edge);
		border-radius: 50%;
		background: var(--panel);
		box-shadow: 0 3px 0 rgb(60 45 20 / 0.16);
		transition:
			transform 80ms,
			box-shadow 80ms,
			background 120ms;
	}
	.on .disc {
		transform: translateY(2px);
		background: var(--ink);
		border-color: var(--ink);
		color: var(--panel);
		box-shadow: 0 1px 0 rgb(60 45 20 / 0.16);
	}
	.round:active:not([aria-disabled='true']) .disc {
		transform: translateY(2px);
		box-shadow: 0 1px 0 rgb(60 45 20 / 0.16);
	}
	.round:focus {
		outline: none;
	}
	.round:focus-visible .disc {
		box-shadow:
			0 0 0 2px var(--ink),
			0 0 0 5px var(--accent);
	}
	.ring {
		position: absolute;
		inset: -5px;
		border: 3px solid transparent;
		border-top-color: var(--accent-2);
		border-radius: 50%;
		animation: spin 0.9s linear infinite;
	}
	@media (prefers-reduced-motion: reduce) {
		.ring {
			border: 2px dashed var(--accent-2);
		}
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.warn {
		position: absolute;
		top: -4px;
		right: -4px;
		display: grid;
		place-items: center;
		width: 20px;
		height: 20px;
		border: 2px solid var(--panel);
		border-radius: 50%;
		background: var(--alert);
		color: var(--panel);
		font-size: 10px;
		line-height: 1;
	}
	.label {
		padding: 1px 6px;
		border-radius: 999px;
		background: var(--panel);
		white-space: nowrap;
		opacity: 0;
		transition: opacity 120ms;
	}
	.round:hover .label,
	.round:focus-visible .label {
		opacity: 1;
	}
	@media (min-width: 1280px) {
		.label {
			opacity: 1;
		}
	}
</style>
