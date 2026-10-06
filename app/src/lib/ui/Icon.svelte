<script lang="ts">
	import type { Icon } from '#lib/layers/types.js';

	/** A Phosphor duotone icon: path data from icons.ts, or a phosphor-svelte component (deep import). */
	let { icon, size = 24 }: { icon: Icon; size?: number } = $props();
</script>

{#if typeof icon === 'function'}
	{@const C = icon}
	<C weight="duotone" {size} aria-hidden="true" />
{:else}
	<svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 256 256" fill="currentColor" aria-hidden="true">
		<path d={icon.tone} opacity="0.2" /><path d={icon.line} />
	</svg>
{/if}
