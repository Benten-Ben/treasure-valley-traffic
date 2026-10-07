<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import { clockOf, minSec } from '#lib/state/clock.svelte.js';
	import Icon from '#lib/ui/Icon.svelte';
	import { NEXT, PREV, STEP_OUT } from './icons.js';
	import { liveOf } from './live.svelte.js';
	import { look } from './look.svelte.js';

	/**
	 * Look-through's mode strip (docs/14 §14.6 "Look through", step 9; WP13),
	 * shown in place of the toolbar through WP2's banner slot:
	 *
	 * - the camera's name and where it is in the ← → order;
	 * - the opacity slider;
	 * - both clocks: "picture seen 0:48 ago · buses 1:30 behind" (the bus part
	 *   only with Transit on); the picture is "seen", never "taken";
	 * - ← and → to the previous or next calibrated camera by distance;
	 * - Step out (also Esc).
	 *
	 * On a phone it's a bottom strip with the slider and Step out.
	 */
	let { app }: { app: AppCtx } = $props();
	// The app context never changes for the life of the chrome.
	const feed = untrack(() => liveOf(app));
	let now = $state(Date.now());
	const tick = setInterval(() => (now = Date.now()), 1000);
	onDestroy(() => clearInterval(tick));

	const frame = $derived(look.viewId !== null ? (feed.views[look.viewId]?.frame ?? null) : null);
	const age = $derived(frame && !look.reference ? feed.ageOf(frame, now) : null);
	const transit = $derived(app.layers?.isOn('transit') ?? false);
	const behind = $derived.by(() => {
		void now;
		return transit ? clockOf(app).behind : null;
	});
	const picture = $derived(
		look.reference ? 'reference picture (no live one yet)' : age === null ? 'waiting for the picture' : `picture seen ${minSec(age)} ago`
	);
	const busy = $derived(look.phase !== 'looking');
</script>

<div class="look card" role="group" aria-label="Look-through" data-phase={look.phase}>
	<div class="who">
		<span class="name">{look.name}</span>
		{#if look.count > 1}<span class="count num">{look.index + 1}/{look.count}</span>{/if}
	</div>
	<label class="slider">
		<span>Opacity</span>
		<input
			type="range"
			min="0"
			max="100"
			step="5"
			value={Math.round(look.slider * 100)}
			aria-label="Picture opacity"
			oninput={(e) => look.actions?.setSlider(Number((e.currentTarget as HTMLInputElement).value) / 100)}
		/>
	</label>
	<span class="clocks num" title="Seen: when our server first got the picture. The time printed on the picture is ACHD's own clock.">
		{picture}{#if behind !== null} · buses {minSec(behind)} behind{/if}
	</span>
	<div class="nav">
		<button class="pill icon" aria-label="Previous camera (←)" title="Previous camera (←)" disabled={busy || look.count < 2} onclick={() => look.actions?.next(-1)}>
			<Icon icon={PREV} size={18} />
		</button>
		<button class="pill icon" aria-label="Next camera (→)" title="Next camera (→)" disabled={busy || look.count < 2} onclick={() => look.actions?.next(1)}>
			<Icon icon={NEXT} size={18} />
		</button>
	</div>
	<button class="pill primary out" title="Step out (Esc)" onclick={() => look.actions?.stepOut()}>
		<Icon icon={STEP_OUT} size={18} /> Step out
	</button>
</div>

<style>
	.look {
		display: flex;
		align-items: center;
		gap: 8px 14px;
		padding: 8px 12px;
		/* The banner slot is centred and shrink-to-fit: keep one row while the screen has room. */
		width: max-content;
		max-width: min(980px, calc(100vw - 32px));
		flex-wrap: wrap;
	}
	.who {
		display: flex;
		align-items: baseline;
		gap: 6px;
		min-width: 0;
	}
	.name {
		font: 600 15px var(--font-display);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 260px;
	}
	.count {
		color: var(--ink-soft);
		font-size: 12px;
	}
	.slider {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 13px;
	}
	.slider input {
		width: 110px;
		accent-color: var(--ink);
	}
	.clocks {
		font-size: 12px;
		color: var(--ink);
		white-space: nowrap;
	}
	.nav {
		display: flex;
		gap: 4px;
	}
	button.icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 40px;
		min-height: 36px;
		padding: 4px 8px;
	}
	button.out {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 36px;
	}
	/* Phones: a bottom strip with the slider and Step out (§14.3). */
	@media (max-width: 599px) {
		.look {
			box-sizing: border-box;
			width: 100%;
			max-width: none;
			justify-content: space-between;
			border-radius: 14px;
		}
		.who,
		.nav,
		.clocks {
			display: none;
		}
		.slider input {
			width: min(40vw, 180px);
		}
		button.out {
			min-height: 44px;
		}
	}
</style>
