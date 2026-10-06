<script lang="ts">
	import type { Badge } from '#lib/layers/types.js';
	import { haloFor } from '#lib/overlay/sprites.js';

	/**
	 * A route badge (docs/14 §14.3, the badge rule): numerals at least 14 px
	 * bold in the slot's text color; where that misses 4.5:1 on the plate, a
	 * 2 px halo in the opposite tone fills the digits' counters.
	 */
	let { badge, big = false }: { badge: Badge; big?: boolean } = $props();
	const halo = $derived(badge.halo ? haloFor(badge.textColor) : null);
</script>

<span
	class="badge num"
	class:big
	class:halo={Boolean(halo)}
	style:background={badge.color}
	style:color={badge.textColor}
	style:--halo={halo}>{badge.text}</span
>

<style>
	.badge {
		display: inline-block;
		min-width: 28px;
		box-sizing: border-box;
		padding: 1px 6px;
		border-radius: 999px;
		font: 700 14px/1.35 var(--font-body);
		text-align: center;
		box-shadow:
			0 0 0 1.5px var(--panel),
			0 0 0 2.5px rgb(43 42 51 / 0.35);
		flex: none;
	}
	.big {
		font-size: 16px;
		margin-right: 4px;
		vertical-align: 2px;
	}
	.halo {
		text-shadow:
			0 0 2px var(--halo),
			1.5px 0 0 var(--halo),
			-1.5px 0 0 var(--halo),
			0 1.5px 0 var(--halo),
			0 -1.5px 0 var(--halo),
			1px 1px 0 var(--halo),
			-1px -1px 0 var(--halo),
			1px -1px 0 var(--halo),
			-1px 1px 0 var(--halo);
	}
</style>
