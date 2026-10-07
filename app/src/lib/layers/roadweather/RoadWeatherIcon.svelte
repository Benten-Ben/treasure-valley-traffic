<script lang="ts">
	import { partTransform, ROAD_WEATHER_ICON } from './icons.js';

	/**
	 * The Road weather layer's icon: Phosphor's ThermometerSimple and
	 * RoadHorizon, duotone, in one box (icons.ts). Drawn like Icon.svelte
	 * draws a single icon, so it fits the toolbar, legend and tab bar.
	 */
	let { size = 24 }: { weight?: 'duotone'; size?: number | string; 'aria-hidden'?: 'true' } = $props();
</script>

<svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 256 256" fill="currentColor" aria-hidden="true">
	{#each ROAD_WEATHER_ICON as p (p.icon.name)}
		<g transform={partTransform(p)}><path d={p.icon.tone} opacity="0.2" /><path d={p.icon.line} /></g>
	{/each}
</svg>
