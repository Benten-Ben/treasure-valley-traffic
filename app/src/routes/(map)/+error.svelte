<script lang="ts">
	/**
	 * Errors under the map layout render inside it (docs/14 §14.8), so the map
	 * survives a bad link such as a calibration for a camera that doesn't exist.
	 */
	import { page } from '$app/state';
</script>

<svelte:head>
	<title>{page.status} · Treasure Valley Traffic</title>
</svelte:head>

<section class="error card" role="alert">
	<h2>{page.status === 404 ? 'Not found' : 'Something went wrong'}</h2>
	<p>{page.error?.message ?? 'Unknown error'}</p>
	<a class="pill" href="/">Back to the map</a>
</section>

<style>
	.error {
		position: absolute;
		top: 50%;
		left: 50%;
		z-index: 60;
		transform: translate(-50%, -50%);
		box-sizing: border-box;
		width: min(26rem, calc(100% - 2rem));
		padding: 1rem 1.25rem;
	}
	h2 {
		margin: 0 0 6px;
		font: 600 20px var(--font-display);
	}
	p {
		margin: 0 0 12px;
		color: var(--ink-soft);
	}
	.pill {
		display: inline-block;
		border: 2px solid #d68d00;
		border-radius: 999px;
		padding: 6px 16px;
		background: var(--accent);
		color: var(--ink);
		font: 600 14px var(--font-body);
		text-decoration: none;
		box-shadow: 0 3px 0 rgb(60 45 20 / 0.14);
	}
</style>
