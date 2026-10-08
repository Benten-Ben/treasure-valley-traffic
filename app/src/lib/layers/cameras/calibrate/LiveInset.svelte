<script lang="ts">
	import type { LiveView } from '#lib/contracts/live.js';
	import Icon from '#lib/ui/Icon.svelte';
	import { footText, SEEN_NOTE, shown } from '../freshness.js';
	import { BLINK, NEW_FRAME, USE_FRAME } from './icons.js';

	/**
	 * The small Live inset (docs/14 §14.6, "Panel"): the camera's live picture
	 * as the app's one live poll has it, with its "seen" age and status in a
	 * shape and a word, and:
	 *
	 * - **Use this frame**: freeze exactly this picture as the new reference
	 *   (the panel posts its identity, and the server keeps those bytes);
	 * - **Blink**: alternate it over the reference, to see whether the camera
	 *   has moved (same size only);
	 * - **New frame**: ask the server for the newest picture instead (it
	 *   becomes the reference, and is shown as such): the way in when there's
	 *   no live picture here (live images off, robots.txt says no).
	 */
	let {
		live,
		age,
		refSize,
		blink = $bindable(false),
		busy = false,
		onuse,
		onnew
	}: {
		live: LiveView | null;
		age: number | null;
		refSize: { width: number; height: number } | null;
		blink?: boolean;
		busy?: boolean;
		onuse: () => void;
		onnew: () => void;
	} = $props();

	const frame = $derived(live?.frame ?? null);
	const status = $derived(shown(live, age));
	const same = $derived(!!frame && !!refSize && frame.width === refSize.width && frame.height === refSize.height);
	const sizeNote = $derived(frame && refSize && !same ? `${frame.width}×${frame.height}, the reference is ${refSize.width}×${refSize.height}` : null);
</script>

<section class="live" aria-label="Live picture">
	<div class="thumb" style:aspect-ratio={frame ? `${frame.width} / ${frame.height}` : '768 / 466'}>
		{#if frame}
			<img src={frame.url} alt="Live from the camera" draggable="false" />
		{:else}
			<span class="empty"><span aria-hidden="true">{status.shape}</span> {status.word}</span>
		{/if}
	</div>
	<div class="side">
		<p class="head">
			<span class="shape" style:color={status.color} aria-hidden="true">{status.shape}</span>
			<b>Live picture</b>
			<span class="word">· {status.word}</span>
		</p>
		<p class="seen num" title={SEEN_NOTE}>{footText(live, age)}</p>
		{#if live && live.state !== 'ok' && live.state !== 'waiting'}<p class="why">{status.detail}</p>{/if}
		{#if sizeNote}<p class="why">▲ {sizeNote}</p>{/if}
		<div class="buttons">
			<button class="pill" disabled={!frame || busy} onclick={onuse} title="Freeze this live picture as the reference the pairs are clicked on">
				<Icon icon={USE_FRAME} size={16} /> Use this frame
			</button>
			<button class="pill" aria-pressed={blink} disabled={!same} onclick={() => (blink = !blink)} title="Alternate the live picture over the reference, to see whether the camera has moved">
				<Icon icon={BLINK} size={16} /> Blink
			</button>
			<button class="pill" disabled={busy} onclick={onnew} title="Ask for the newest picture and use it as the reference">
				<Icon icon={NEW_FRAME} size={16} /> New frame
			</button>
		</div>
	</div>
</section>

<style>
	.live {
		display: grid;
		grid-template-columns: 168px 1fr;
		gap: 10px;
		align-items: start;
	}
	.thumb {
		position: relative;
		width: 168px;
		overflow: hidden;
		border-radius: 8px;
		background: var(--ground);
	}
	.thumb img {
		display: block;
		width: 100%;
		height: 100%;
	}
	.empty {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		color: var(--ink-soft);
		font-size: 12px;
	}
	.side {
		min-width: 0;
	}
	.head {
		display: flex;
		align-items: baseline;
		gap: 6px;
		margin: 0;
		font-size: 13px;
	}
	.shape {
		font-size: 11px;
	}
	.word {
		color: var(--ink);
	}
	.seen {
		margin: 2px 0 0;
		font-size: 12px;
	}
	.why {
		margin: 2px 0 0;
		color: var(--ink-soft);
		font-size: 12px;
	}
	.buttons {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-top: 6px;
	}
	.buttons :global(.pill) {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 4px 10px;
		font-size: 13px;
	}
	.buttons :global(.pill[aria-pressed='true']) {
		border-color: var(--ink);
		background: var(--ink);
		color: var(--panel);
	}
</style>
