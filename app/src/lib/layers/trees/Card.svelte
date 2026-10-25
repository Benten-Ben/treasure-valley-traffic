<script lang="ts">
	import type { CardProps } from '../types.js';
	import ShrubCard from './ShrubCard.svelte';
	import TreeCard from './TreeCard.svelte';

	/** The Trees layer's card: a shrub's small card, or a tree's panel (docs/19 §19.6, §19.8). */
	let props: CardProps = $props();
</script>

{#if props.selection.kind === 'shrub'}
	<ShrubCard {...props} />
{:else}
	<TreeCard {...props} />
{/if}
