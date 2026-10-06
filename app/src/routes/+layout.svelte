<script lang="ts">
	// Global CSS only (docs/14 §14.8). The favicon is linked from app.html; the
	// map and its chrome live in the (map) layout.
	import '../app.css';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

{@render children()}
