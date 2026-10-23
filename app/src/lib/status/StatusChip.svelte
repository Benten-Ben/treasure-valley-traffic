<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';
	import type { DataMeta } from '#lib/contracts/meta.js';
	import { Poller } from '#lib/state/poll.svelte.js';
	import { tipFor, tooltip } from '#lib/ui/tooltip.svelte.js';
	import { POLL_MS, levelChanged, refetchOnFocus } from './chip.js';
	import { statusChip, type StatusLevel } from './summary.js';

	/**
	 * The status chip (landscape sprint, M1): the shape in its colour and the
	 * headline in ink, from /api/meta's `status`. The lines go in the shared
	 * tooltip. Polls every five minutes while the page is visible, and on focus
	 * when the last answer is old. The live region speaks only on a change of level.
	 */
	let { app }: { app: AppCtx } = $props();

	// The answer this chip has fetched itself; until then, the one the boot fetched.
	let polled = $state<DataMeta | null>(null);
	// Consecutive failed polls. One miss (a server restart) keeps the last good answer;
	// the chip says "unknown" only after two in a row.
	let failures = $state(0);
	// When the last poll started (ms), so a focus during an outage still honours the gap.
	let lastAt: number | null = null;

	const chip = $derived(statusChip(failures >= 2 ? null : (polled ?? app.meta)));

	const poller = new Poller(
		async (signal) => {
			lastAt = Date.now();
			try {
				const r = await fetch('/api/meta', { signal, cache: 'no-store' });
				if (!r.ok) throw new Error(`/api/meta ${r.status}`);
				polled = (await r.json()) as DataMeta;
				failures = 0;
			} catch (e) {
				if (signal.aborted) return;
				failures += 1;
				throw e;
			}
		},
		{ interval: POLL_MS, immediate: false }
	);

	function onFocus() {
		if (refetchOnFocus(lastAt, Date.now())) poller.poke();
	}

	onMount(() => {
		poller.start();
		window.addEventListener('focus', onFocus);
		return () => {
			window.removeEventListener('focus', onFocus);
			poller.stop();
		};
	});

	let announce = $state('');
	let prev: StatusLevel | null = null;
	$effect(() => {
		const { level, headline } = chip;
		untrack(() => {
			if (levelChanged(prev, level)) announce = `Status: ${headline}`;
			prev = level;
		});
	});

	function show(el: Element) {
		tooltip.show(tipFor(el, chip.headline, chip.lines));
	}
</script>

<span class="status" data-level={chip.level}>
	<button
		type="button"
		class="chip card num"
		onpointerenter={(e) => show(e.currentTarget)}
		onpointerleave={() => tooltip.hide()}
		onfocus={(e) => show(e.currentTarget)}
		onblur={() => tooltip.hide()}
	>
		<span class="shape" style:color={chip.color} aria-hidden="true">{chip.shape}</span>
		<span class="words">{chip.headline}</span>
	</button>
	<span class="sr-only" aria-live="polite">{announce}</span>
</span>

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.4em;
		color: var(--ink);
		font: inherit;
		cursor: default;
		white-space: nowrap;
	}
	.shape {
		font-size: 1.05em;
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
</style>
