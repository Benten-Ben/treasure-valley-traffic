<script lang="ts">
	import type { Shown } from './freshness.js';

	/**
	 * The freshness chip (docs/14 §14.6, "Freshness"): the status's shape (●
	 * live, ▲ late, ■ stale or offline, ◌ waiting) in its color, a thin ring
	 * around it that fills over the cadence, and a pulse when a new picture
	 * arrives (none under reduced motion). The word beside it says the same
	 * thing; the shape and word carry it, never the color alone.
	 */
	let { shown, progress = 0, pulse = null }: { shown: Shown; progress?: number; pulse?: string | null } = $props();

	const R = 8;
	const C = 2 * Math.PI * R;
</script>

<span class="chip" title={shown.detail} data-freshness={shown.kind}>
	{#key pulse}
		<svg class="dot" class:pulse={pulse !== null} viewBox="0 0 20 20" width="20" height="20" aria-hidden="true">
			<circle class="track" cx="10" cy="10" r={R} />
			<circle
				class="ring"
				cx="10"
				cy="10"
				r={R}
				stroke={shown.color}
				stroke-dasharray="{(C * Math.min(1, Math.max(0, progress))).toFixed(2)} {C.toFixed(2)}"
				transform="rotate(-90 10 10)"
			/>
			{#if shown.shape === '●'}
				<circle cx="10" cy="10" r="4.5" fill={shown.color} stroke="var(--ink)" stroke-width="1" />
			{:else if shown.shape === '▲'}
				<path d="M10 4.5 15.2 14H4.8Z" fill={shown.color} stroke="var(--ink)" stroke-width="1" stroke-linejoin="round" />
			{:else if shown.shape === '■'}
				<rect x="5.5" y="5.5" width="9" height="9" rx="1" fill={shown.color} stroke="var(--ink)" stroke-width="1" />
			{:else}
				<circle cx="10" cy="10" r="4.5" fill="none" stroke="var(--ink-soft)" stroke-width="1.5" stroke-dasharray="2 1.6" />
			{/if}
		</svg>
	{/key}
	<span class="word">{shown.word}</span>
</span>

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		color: var(--ink);
		font-size: 12px;
		font-weight: 600;
		white-space: nowrap;
	}
	.dot {
		flex: none;
	}
	.track {
		fill: none;
		stroke: rgb(43 42 51 / 0.12);
		stroke-width: 1.5;
	}
	.ring {
		fill: none;
		stroke-width: 1.5;
		stroke-linecap: round;
		transition: stroke-dasharray 1s linear;
	}
	.pulse {
		animation: pulse 600ms ease-out;
		transform-origin: 50% 50%;
	}
	@keyframes pulse {
		0% {
			transform: scale(1);
		}
		40% {
			transform: scale(1.35);
		}
		100% {
			transform: scale(1);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.pulse {
			animation: none;
		}
		.ring {
			transition: none;
		}
	}
</style>
