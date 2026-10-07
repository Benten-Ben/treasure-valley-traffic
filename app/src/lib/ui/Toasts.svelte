<script lang="ts">
	import { updated } from '$app/state';
	import type { AppCtx } from '#lib/app/context.js';
	import { slots } from './slots.svelte.js';
	import { toasts } from './toasts.svelte.js';

	/**
	 * Toasts (docs/14 §14.3, band 70; WP3): bottom centre above the toolbar
	 * (top on a phone, above the sheet's reach). Anything can show one through
	 * `toasts.show()` (toasts.svelte.ts). Each carries a shape and a word, never
	 * color alone: ● for news, ▲ for a problem (announced at once).
	 *
	 * It also shows the new-version toast (SvelteKit's version polling): "New
	 * version: reload when convenient".
	 */
	let props: { app: AppCtx } = $props();
	let dismissed = $state(false);
</script>

<div class="toasts" aria-live="polite">
	{#if updated.current && !dismissed}
		<div class="toast card" role="status">
			<span class="shape" aria-hidden="true">●</span>
			<span class="text">New version: reload when convenient.</span>
			<button class="pill" onclick={() => location.reload()}>Reload</button>
			<button class="close" aria-label="Dismiss" onclick={() => (dismissed = true)}>×</button>
		</div>
	{/if}
	{#each toasts.list as t (t.id)}
		<div class="toast card" class:problem={t.kind === 'problem'} role={t.kind === 'problem' ? 'alert' : 'status'}>
			<span class="shape" aria-hidden="true">{t.kind === 'problem' ? '▲' : '●'}</span>
			<span class="text">{t.text}</span>
			{#if t.action}
				{@const action = t.action}
				<button
					class="pill"
					onclick={() => {
						toasts.dismiss(t.id);
						action.run();
					}}>{action.label}</button
				>
			{/if}
			<button class="close" aria-label="Dismiss" onclick={() => toasts.dismiss(t.id)}>×</button>
		</div>
	{/each}
	{#each slots.items('toasts') as it (it.id)}<it.component {...it.props} />{/each}
</div>

<style>
	.toasts {
		position: absolute;
		left: 50%;
		bottom: 112px;
		z-index: 70;
		transform: translateX(-50%);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
		width: max-content;
		max-width: calc(100% - 32px);
		pointer-events: none;
	}
	.toast {
		display: flex;
		align-items: center;
		gap: 10px;
		max-width: 100%;
		box-sizing: border-box;
		padding: 6px 6px 6px 14px;
		font-size: 14px;
		pointer-events: auto;
		animation: rise 250ms cubic-bezier(0.3, 1.4, 0.6, 1);
	}
	.toast.problem {
		border-color: var(--alert);
	}
	.shape {
		flex: none;
		color: var(--accent-2);
		font-size: 12px;
	}
	.problem .shape {
		color: var(--alert);
	}
	.text {
		min-width: 0;
	}
	.close {
		flex: none;
		width: 36px;
		height: 36px;
		border: 0;
		border-radius: 50%;
		background: none;
		font-size: 20px;
		cursor: pointer;
		color: var(--ink-soft);
	}
	.close:hover {
		background: rgb(43 42 51 / 0.08);
	}
	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(10px);
		}
	}
	@media (max-width: 599px) {
		.toasts {
			top: 160px;
			bottom: auto;
		}
		.close {
			width: 44px;
			height: 44px;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.toast {
			animation: none;
		}
	}
</style>
