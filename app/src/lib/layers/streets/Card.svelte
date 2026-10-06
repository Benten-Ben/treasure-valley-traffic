<script lang="ts">
	import type { CardProps } from '../types.js';
	import { oneWayText, speedColor, type StreetProps } from './streets.js';

	let { selection }: CardProps = $props();
	const street = $derived(selection.data as StreetProps);
</script>

<h2>{street.name ?? 'Unnamed road'}</h2>
<div class="speed-line">
	<span class="speed-sign"><small>SPEED LIMIT</small><b class="num">{street.speed ?? '?'}</b></span>
	<p class="meta">
		{street.class ?? 'Unknown class'}{#if street.community} · {street.community}{/if}<br />
		{oneWayText(street)}{#if street.elevated} · bridge or overpass{/if}{#if street.private} · private{/if}
	</p>
</div>
<p class="credit">Source: ACHD road centerlines <i class="swatch small" style:background={speedColor(street.speed)}></i></p>
