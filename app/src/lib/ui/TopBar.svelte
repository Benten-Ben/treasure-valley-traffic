<script lang="ts">
	import type { AppCtx } from '#lib/app/context.js';
	import { clockOf, clockText } from '#lib/state/clock.svelte.js';
	import Icon from './Icon.svelte';
	import { QUESTION } from './chrome-icons.js';
	import { slots } from './slots.svelte.js';
	import TimePill from './TimePill.svelte';
	import { tipFor, tooltip } from './tooltip.svelte.js';

	/**
	 * The top bar (docs/14 §14.3, "Top bar, clock and time pill"): the
	 * nameplate and stat chips on the left; the clock, the time pill, other
	 * packages' pieces (the `topbar-right` slot) and Help on the right.
	 *
	 * - The clock is the playhead in Boise (WP8's clock): the moment the
	 *   buses on the map are at.
	 * - A chip shows its source and age on hover, turns its layer on when
	 *   clicked, shows — while loading and ▲ when its feed is old; a polite
	 *   live region announces only threshold crossings.
	 */
	let { app, phone = false, onhelp }: { app: AppCtx; phone?: boolean; onhelp: () => void } = $props();

	// The playhead: the moment the buses on the map are at (WP8's clock, ticking once a second).
	const playhead = $derived(clockOf(app));
	const clock = $derived(clockText(playhead.T));

	const chips = $derived(app.layers.chips());

	// Chips that don't fit stay one scroll away, and the row says so: a fade at the cut edge and a
	// "+2" chip that brings the hidden ones into view (and back).
	let row: HTMLUListElement | undefined = $state();
	let hidden = $state(0);
	let cut = $state<{ left: boolean; right: boolean }>({ left: false, right: false });
	function measureChips() {
		const ul = row;
		if (!ul) return;
		const box = ul.getBoundingClientRect();
		let n = 0;
		for (const li of ul.children) {
			const r = li.getBoundingClientRect();
			if (r.left < box.left - 1 || r.right > box.left + ul.clientWidth + 1) n++;
		}
		hidden = n;
		const left = ul.scrollLeft > 1;
		const right = ul.scrollLeft + ul.clientWidth < ul.scrollWidth - 1;
		if (left !== cut.left || right !== cut.right) cut = { left, right };
	}
	function showMore() {
		const ul = row;
		if (!ul) return;
		const smooth = typeof matchMedia !== 'undefined' && !matchMedia('(prefers-reduced-motion: reduce)').matches;
		ul.scrollTo({ left: cut.right ? ul.scrollWidth : 0, behavior: smooth ? 'smooth' : 'auto' });
	}
	$effect(() => {
		const ul = row;
		if (!ul) return;
		const ro = new ResizeObserver(() => measureChips());
		ro.observe(ul);
		return () => ro.disconnect();
	});
	// The chips' words change with the data.
	$effect(() => {
		void chips.map((c) => c.text).join('|');
		requestAnimationFrame(measureChips);
	});

	// Announce only threshold crossings (a feed going stale or recovering).
	let announce = $state('');
	let wasStale = new Map<string, boolean>();
	$effect(() => {
		for (const c of chips) {
			const key = `${c.layer}:${c.id}`;
			const before = wasStale.get(key);
			const stale = Boolean(c.stale);
			if (before !== undefined && before !== stale) announce = stale ? `${c.text}: data is old` : `${c.text}: data is fresh again`;
			wasStale.set(key, stale);
		}
	});
</script>

<header class="topbar" class:phone>
	<div class="left">
		<div class="nameplate card">
			<h1>Treasure Valley</h1>
			{#if phone}<span class="clock num" aria-label="Time in Boise">{clock}</span>{/if}
		</div>
		<div class="chip-row" class:cut-left={cut.left} class:cut-right={cut.right}>
			<ul class="chips" aria-label="Stats" bind:this={row} onscroll={measureChips}>
				{#each chips as c (c.layer + c.id)}
					<li>
						<button
							class="chip num"
							class:stale={c.stale}
							onclick={() => app.layers.setOn(c.layer, true)}
							onpointerenter={(e) => tooltip.show(tipFor(e.currentTarget, c.text, [c.title, app.layers.isOn(c.layer) ? '' : 'Click to turn the layer on'].filter(Boolean)))}
							onpointerleave={() => tooltip.hide()}
							onfocus={(e) => tooltip.show(tipFor(e.currentTarget, c.text, [c.title]))}
							onblur={() => tooltip.hide()}
						>
							{c.text}{#if c.stale}<span class="warn" aria-label="old data"> ▲</span>{/if}
						</button>
					</li>
				{/each}
			</ul>
			{#if hidden > 0}
				<button
					class="chip more num"
					aria-label={cut.right ? `${hidden} more ${hidden === 1 ? 'stat' : 'stats'}: show them` : `Back to the first stats`}
					onclick={showMore}
					onpointerenter={(e) => tooltip.show(tipFor(e.currentTarget, `${hidden} more`, ['Show the stats that don’t fit']))}
					onpointerleave={() => tooltip.hide()}>{cut.right ? `+${hidden}` : '‹'}</button
				>
			{/if}
		</div>
	</div>
	{#if !phone}
		<div class="right">
			<span class="clock card num" title="The time the buses on the map are at (Boise)">{clock}</span>
			<TimePill {app} />
			{#each slots.items('topbar-right') as it (it.id)}<it.component {...it.props} />{/each}
			<button class="help card" aria-label="Help and keys (?)" onclick={onhelp}><Icon icon={QUESTION} size={22} /></button>
		</div>
	{/if}
	<p class="sr-only" aria-live="polite">{announce}</p>
</header>

<style>
	/* Two tracks: the left (nameplate and stat chips) takes what the right side leaves, so the chips' row
	   (and its "+N" chip) stays clear of the clock, the time pill, the status chip and Help. The chip row can
	   shrink to nothing; the nameplate does not shrink below its own width, so on a very narrow bar the
	   nameplate can still extend past its track. Check the floor at 700 px before relying on it. */
	.topbar {
		position: absolute;
		top: 12px;
		left: 16px;
		right: 16px;
		z-index: 40;
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: start;
		gap: 12px;
		pointer-events: none;
	}
	.topbar > * {
		pointer-events: auto;
	}
	.left {
		display: flex;
		align-items: center;
		gap: 10px;
		min-width: 0;
		/* Nothing from the left track may sit under the right side. The padding and negative margin
		   keep the cards' drop shadows and focus rings from being clipped. */
		overflow: hidden;
		padding: 4px 6px 8px 6px;
		margin: -4px -6px -8px -6px;
	}
	.nameplate {
		display: flex;
		align-items: center;
		gap: 10px;
		height: 52px;
		box-sizing: border-box;
		padding: 0 18px;
		border-radius: 18px;
	}
	h1 {
		margin: 0;
		font: 600 21px var(--font-display);
		white-space: nowrap;
	}
	.chip-row {
		display: flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
	}
	.chips {
		display: flex;
		gap: 6px;
		min-width: 0;
		/* Room for the chips' 3 px drop shadow, which the scroller would clip (the margin keeps the row's height). */
		margin: 0 0 -3px;
		padding: 0 0 3px;
		list-style: none;
		overflow-x: auto;
		scrollbar-width: none;
	}
	.chips::-webkit-scrollbar {
		display: none;
	}
	/* A fade at each edge that cuts a chip off. */
	.cut-right .chips {
		mask-image: linear-gradient(to right, #000 calc(100% - 28px), transparent);
	}
	.cut-left .chips {
		mask-image: linear-gradient(to left, #000 calc(100% - 28px), transparent);
	}
	.cut-left.cut-right .chips {
		mask-image: linear-gradient(to right, transparent, #000 28px, #000 calc(100% - 28px), transparent);
	}
	.more {
		flex: none;
		min-width: 44px;
		padding: 0 10px;
		font-weight: 700;
	}
	.chip {
		height: 34px;
		padding: 0 12px;
		border: 2px solid var(--panel-edge);
		border-radius: 999px;
		background: var(--panel);
		box-shadow: 0 3px 0 rgb(60 45 20 / 0.12);
		color: var(--ink);
		font-size: 13px;
		white-space: nowrap;
		cursor: pointer;
	}
	.chip:focus-visible,
	.help:focus-visible {
		outline: none;
		box-shadow:
			0 0 0 2px var(--ink),
			0 0 0 5px var(--accent);
	}
	.chip.stale {
		border-style: dashed;
	}
	.warn {
		color: var(--ink);
	}
	.right {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.clock {
		display: inline-flex;
		align-items: center;
		height: 40px;
		padding: 0 14px;
		border-radius: 14px;
		font-size: 14px;
		white-space: nowrap;
	}
	.help {
		display: grid;
		place-items: center;
		width: 44px;
		height: 44px;
		padding: 0;
		border-radius: 50%;
		cursor: pointer;
		color: var(--ink);
	}
	.phone {
		top: 8px;
		left: 8px;
		right: 8px;
	}
	.phone .left {
		flex-direction: column;
		align-items: stretch;
		gap: 6px;
		width: 100%;
	}
	.phone .nameplate {
		align-self: flex-start;
		height: 40px;
		padding: 0 14px;
		border-radius: 999px;
	}
	.phone h1 {
		font-size: 17px;
	}
	.phone .nameplate .clock {
		height: auto;
		padding: 0;
		font-size: 12px;
	}
	.phone .chip {
		height: 44px;
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
</style>
