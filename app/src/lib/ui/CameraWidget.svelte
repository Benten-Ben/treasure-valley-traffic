<script lang="ts">
	import type { AppCtx } from '#lib/app/context.js';
	import { slots } from './slots.svelte.js';

	/**
	 * Stub (WP2): the camera widget (compass and reset north, zoom ±, 2D/3D,
	 * Home, Overview; docs/14 §14.3) is WP3's, which replaces this file and
	 * MapLibre's NavigationControl. Until then MapLibre's control sits in this
	 * place in the right column, and H and O work from the keyboard.
	 */
	let props: { app: AppCtx } = $props();
</script>

{#each slots.items('camera-widget') as it (it.id)}<it.component {...it.props} />{/each}
