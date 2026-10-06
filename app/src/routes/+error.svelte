<script lang="ts">
	/** The plain error page for routes outside the map layout. */
	import { page } from '$app/state';
</script>

<svelte:head>
	<title>{page.status} · Treasure Valley Traffic</title>
</svelte:head>

<main class="card">
	<h1>{page.status === 404 ? 'Not found' : 'Something went wrong'}</h1>
	<p>{page.error?.message ?? 'Unknown error'}</p>
	<a href="/">Back to the map</a>
</main>

<style>
	main {
		max-width: 32rem;
		margin: 15vh auto 0;
		padding: 1rem 1.5rem;
	}
	h1 {
		margin: 0 0 8px;
		font: 600 24px var(--font-display);
	}
	a {
		color: var(--ink);
		font-weight: 600;
	}
</style>
