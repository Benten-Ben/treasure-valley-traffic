<script lang="ts">
	import { tooltip } from './tooltip.svelte.js';

	/** The one tooltip element (band 50). It flips to stay on screen. */
	let w = $state(0);
	let h = $state(0);
	let vw = $state(1280);
	let vh = $state(800);

	const pos = $derived.by(() => {
		const t = tooltip.current;
		if (!t) return null;
		const pad = 8;
		let left: number;
		let top: number;
		if (t.placement === 'cursor') {
			left = t.x + 12;
			top = t.y + 12;
			if (left + w > vw - pad) left = t.x - 12 - w;
			if (top + h > vh - pad) top = t.y - 12 - h;
		} else {
			left = t.x - w / 2;
			top = t.placement === 'above' ? t.y - h - 10 : t.y + 10;
		}
		left = Math.max(pad, Math.min(vw - w - pad, left));
		top = Math.max(pad, Math.min(vh - h - pad, top));
		return { left, top };
	});
</script>

<svelte:window bind:innerWidth={vw} bind:innerHeight={vh} />

{#if tooltip.current && pos}
	<div class="tip" role="tooltip" id="tvt-tooltip" style:left="{pos.left}px" style:top="{pos.top}px" bind:clientWidth={w} bind:clientHeight={h}>
		<strong>{tooltip.current.title}</strong>
		{#each tooltip.current.lines as line, i (i)}<span>{line}</span>{/each}
	</div>
{/if}

<style>
	.tip {
		position: fixed;
		z-index: 50;
		max-width: 260px;
		display: flex;
		flex-direction: column;
		gap: 1px;
		padding: 6px 10px;
		border-radius: 10px;
		background: var(--ink);
		color: var(--panel);
		font: 12px/1.35 var(--font-body);
		box-shadow: 0 4px 14px rgb(30 20 10 / 0.25);
		pointer-events: none;
	}
	strong {
		font: 600 13px var(--font-body);
	}
	span {
		color: #e9e2d6;
	}
</style>
