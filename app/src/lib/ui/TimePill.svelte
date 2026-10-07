<script lang="ts">
	import type { AppCtx } from '#lib/app/context.js';
	import { clockOf, DELAYS, minSec } from '#lib/state/clock.svelte.js';
	import { ESC, onEscape } from './keys.js';

	/**
	 * The time pill beside the clock (docs/14 §14.3, "Top bar, clock and time
	 * pill"; WP8, replacing WP2's stub):
	 *
	 * - `LIVE −1:30` (filled) at the normal delay; a click opens the delay
	 *   (1, 1.5, 2, 3 or 5 min; 1 min says "buses may pause"), Pause and Go
	 *   live;
	 * - `PAUSED −3:05` while paused (the data keeps buffering);
	 * - `BEHIND −3:05` after playing on from a pause, until Go live;
	 * - `LIVE · no new GPS for 3 min` with a hollow dot when the feed stalls;
	 * - `REPLAY · Oct 6` for a `?at=` link (the time bar comes later).
	 *
	 * Space pauses and plays, L goes back to live (the keymap registry), while
	 * the pill or the Transit layer is there.
	 */
	let { app }: { app: AppCtx } = $props();
	const clock = $derived(clockOf(app));
	// Space and L, while the pill is there.
	$effect(() => clock.holdKeys());

	let open = $state(false);
	let root: HTMLDivElement | undefined = $state();
	let first: HTMLInputElement | undefined = $state();
	const mode = $derived(clock.state);
	const label = $derived(clock.label);

	const delayLabel = (s: number) => `${s % 60 ? (s / 60).toFixed(1) : s / 60} min`;

	$effect(() => {
		if (!open) return;
		first?.focus();
		const stop = onEscape(ESC.popover, () => {
			open = false;
			return true;
		});
		const outside = (e: PointerEvent) => {
			if (root && !root.contains(e.target as Node)) open = false;
		};
		window.addEventListener('pointerdown', outside, true);
		return () => {
			stop();
			window.removeEventListener('pointerdown', outside, true);
		};
	});
</script>

<div class="time" bind:this={root}>
	<button
		class="pill-button num {mode}"
		aria-haspopup="dialog"
		aria-expanded={open}
		aria-controls="time-popover"
		title="Playback: the delay behind live, pause and go live"
		onclick={() => (open = !open)}
	>
		<span class="mark" aria-hidden="true">{mode === 'paused' ? '❚❚' : mode === 'behind' ? '▶' : mode === 'replay' ? '↺' : ''}</span>{label}
	</button>
	{#if open}
		<div class="popover card" id="time-popover" role="dialog" aria-label="Playback">
			<fieldset>
				<legend>Delay behind live</legend>
				{#each DELAYS as d, i (d)}
					<label>
						{#if i === 0}
							<input bind:this={first} type="radio" name="delay" value={d} checked={clock.delay === d} onchange={() => clock.setDelay(d)} />
						{:else}
							<input type="radio" name="delay" value={d} checked={clock.delay === d} onchange={() => clock.setDelay(d)} />
						{/if}
						<span>{delayLabel(d)}{#if d === 60}<small>{' · buses may pause'}</small>{/if}</span>
					</label>
				{/each}
			</fieldset>
			<div class="row">
				<button class="pill" onclick={() => clock.toggle()}>{clock.paused === null ? 'Pause' : 'Play'} <kbd>Space</kbd></button>
				<button class="pill" disabled={mode === 'live' || mode === 'stalled'} onclick={() => clock.goLive()}>Go live <kbd>L</kbd></button>
			</div>
			<p class="note">
				Buses are drawn {minSec(clock.delay)} behind live, between the positions they reported: GPS takes up to a minute to reach us, and
				nothing is guessed ahead of it.
			</p>
		</div>
	{/if}
</div>

<style>
	.time {
		position: relative;
	}
	.pill-button {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		height: 40px;
		box-sizing: border-box;
		padding: 0 14px;
		border: 2px solid var(--ink);
		border-radius: 999px;
		background: var(--panel);
		color: var(--ink);
		box-shadow: 0 3px 0 rgb(60 45 20 / 0.12);
		font: 700 13px var(--font-body);
		letter-spacing: 0.02em;
		white-space: nowrap;
		cursor: pointer;
	}
	.pill-button:focus-visible {
		outline: none;
		box-shadow:
			0 0 0 2px var(--ink),
			0 0 0 5px var(--accent);
	}
	/* Live: filled, with a filled dot; stalled: the dot goes hollow. */
	.live,
	.stalled {
		background: var(--ink);
		color: var(--panel);
	}
	.live .mark,
	.stalled .mark {
		width: 9px;
		height: 9px;
		border-radius: 50%;
		background: var(--panel);
		box-sizing: border-box;
	}
	.stalled .mark {
		background: none;
		border: 2px solid var(--panel);
	}
	.mark {
		font-size: 11px;
		line-height: 1;
	}
	.popover {
		position: absolute;
		right: 0;
		top: calc(100% + 10px);
		z-index: 50;
		width: 260px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 12px 14px;
		font-size: 14px;
	}
	fieldset {
		display: flex;
		flex-direction: column;
		gap: 2px;
		margin: 0;
		padding: 0;
		border: 0;
	}
	legend {
		margin-bottom: 4px;
		font: 600 12px var(--font-body);
		color: var(--ink-soft);
	}
	label {
		display: flex;
		align-items: center;
		gap: 8px;
		min-height: 28px;
		cursor: pointer;
	}
	small {
		color: var(--ink-soft);
	}
	.row {
		display: flex;
		gap: 8px;
	}
	kbd {
		font: 11px var(--font-mono);
		opacity: 0.7;
	}
	.note {
		margin: 0;
		font-size: 12px;
		color: var(--ink-soft);
	}
</style>
