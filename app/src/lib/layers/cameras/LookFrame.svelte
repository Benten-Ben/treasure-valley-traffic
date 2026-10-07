<script lang="ts">
	import { look } from './look.svelte.js';

	/**
	 * The look-through picture's frame (docs/14 §14.6 "Look through", step 8;
	 * WP13): a 40% ink vignette outside the letterboxed picture and a 2 px cream
	 * viewfinder edge around it. The picture itself is the photo plane in the
	 * scene, so every data layer still draws; this is only the frame, and it
	 * lets every pointer event through to the map (moving fades the picture).
	 * The fade sets this element's opacity directly (look.fade), never per frame
	 * through Svelte.
	 */
	let el = $state<HTMLElement | undefined>();
	$effect(() => {
		const mine = el ?? null;
		look.frame = mine;
		return () => {
			if (look.frame === mine) look.frame = null;
		};
	});
</script>

{#if look.shown}
	{@const b = look.shown}
	<div class="look-frame" bind:this={el} aria-hidden="true" data-look-frame>
		<div class="hole" style:left="{b.x}px" style:top="{b.y}px" style:width="{b.width}px" style:height="{b.height}px"></div>
	</div>
{/if}

<style>
	.look-frame {
		position: absolute;
		inset: 0;
		z-index: 25;
		overflow: hidden;
		pointer-events: none !important;
	}
	.hole {
		position: absolute;
		box-sizing: content-box;
		/* The vignette: 40% ink everywhere outside the picture. */
		box-shadow: 0 0 0 200vmax rgb(43 42 51 / 0.4);
		/* The viewfinder edge, just outside the picture so it covers none of it. */
		outline: 2px solid var(--panel);
		outline-offset: 0;
	}
</style>
