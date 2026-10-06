<script lang="ts">
	import type { AppCtx } from '#lib/app/context.js';
	import { slots } from './slots.svelte.js';

	/**
	 * Stub (WP2): the "↩ Back to previous view" chip and its view history
	 * (docs/14 §14.3) are WP3's, which replaces this file.
	 */
	let props: { app: AppCtx } = $props();
</script>

{#each slots.items('history') as it (it.id)}<it.component {...it.props} />{/each}
