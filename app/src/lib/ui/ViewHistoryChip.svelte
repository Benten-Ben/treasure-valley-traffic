<script lang="ts">
	import { untrack } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import { followOf } from '#lib/state/follow.svelte.js';
	import { historyOf } from '#lib/state/history.svelte.js';
	import Icon from './Icon.svelte';
	import { slots } from './slots.svelte.js';
	import { BACK, FOLLOW } from './window-icons.js';

	/**
	 * Top centre, under the top bar (docs/14 §14.3; WP3):
	 *
	 * - the "↩ Back to previous view" chip, for 8 s after each programmatic
	 *   fly; it (or Backspace) flies back to the view before;
	 * - while following, the "Following bus 2213 · Esc" banner, with Stop.
	 */
	let { app }: { app: AppCtx } = $props();
	const ctx = untrack(() => app);
	const history = historyOf(ctx);
	const follow = followOf(ctx);

	let now = $state(Date.now());
	// Hide the chip when its 8 s are up (a timer per push, not a ticking clock).
	$effect(() => {
		const until = history.chipUntil;
		const left = until - Date.now();
		now = Date.now();
		if (left <= 0) return;
		const t = setTimeout(() => (now = Date.now()), left + 20);
		return () => clearTimeout(t);
	});
	const chip = $derived(history.stack.length > 0 && history.chipUntil > now);
</script>

<div class="top" class:empty={!chip && !follow.current && !slots.items('history').length}>
	{#if chip}
		<button class="chip card" onclick={() => history.back()} aria-keyshortcuts="Backspace">
			<Icon icon={BACK} size={18} />
			<span>Back to previous view</span>
			<kbd class="num">Backspace</kbd>
		</button>
	{/if}
	{#if follow.current}
		<div class="follow card" role="status">
			<Icon icon={FOLLOW} size={18} />
			<span>Following {follow.current.label} · <kbd class="num">Esc</kbd></span>
			<button class="pill stop" onclick={() => follow.stop()}>Stop</button>
		</div>
	{/if}
	{#each slots.items('history') as it (it.id)}<it.component {...it.props} />{/each}
</div>

<style>
	.top {
		position: absolute;
		top: 76px;
		left: 50%;
		z-index: 40;
		transform: translateX(-50%);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		max-width: calc(100% - 32px);
		pointer-events: none;
	}
	.top.empty {
		display: none;
	}
	.top > :global(*) {
		pointer-events: auto;
	}
	.chip,
	.follow {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		min-height: 40px;
		box-sizing: border-box;
		padding: 0 14px;
		border-radius: 999px;
		color: var(--ink);
		font: 600 14px var(--font-body);
		white-space: nowrap;
		animation: drop 250ms cubic-bezier(0.3, 1.4, 0.6, 1);
	}
	.chip {
		cursor: pointer;
	}
	.chip:active {
		transform: translateY(2px);
	}
	.chip:focus-visible {
		outline: none;
		box-shadow:
			0 0 0 2px var(--ink),
			0 0 0 5px var(--accent);
	}
	.follow {
		padding-right: 4px;
	}
	kbd {
		padding: 1px 6px;
		border: 1.5px solid var(--panel-edge);
		border-radius: 6px;
		background: var(--ground);
		font-size: 11px;
		font-weight: 600;
	}
	.stop {
		padding: 4px 12px;
		font-size: 13px;
	}
	@keyframes drop {
		from {
			opacity: 0;
			transform: translateY(-8px);
		}
	}
	@media (max-width: 599px) {
		.top {
			top: 106px;
		}
		.chip,
		.follow {
			min-height: 44px;
		}
		.stop {
			min-height: 36px;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.chip,
		.follow {
			animation: none;
		}
	}
</style>
