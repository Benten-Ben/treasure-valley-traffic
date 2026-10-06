<script lang="ts">
	import type { WinState } from '#lib/state/windows.svelte.js';

	/**
	 * The test window's content (`?window-test`, the `windows` spec): a drawn
	 * test pattern at 16:9 where a camera picture would be, and a footer in
	 * the camera window's style. No camera image is used.
	 */
	let { n, win }: { n: number; win: WinState } = $props();
	const opened = Date.now();
	let now = $state(Date.now());
	$effect(() => {
		const t = setInterval(() => (now = Date.now()), 1000);
		return () => clearInterval(t);
	});
	const age = $derived(Math.max(0, Math.round((now - opened) / 1000)));
	const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
</script>

<div class="picture" style:--hue={(n * 47) % 360} role="img" aria-label="Test pattern {n} (no camera image)">
	<span class="label">Test pattern {n}</span>
	<span class="size num">{win.rect.w} px</span>
</div>
<p class="foot num">opened {fmt(age)} ago · a test window, not a camera</p>

<style>
	.picture {
		position: relative;
		aspect-ratio: 16 / 9;
		background:
			repeating-linear-gradient(90deg, hsl(var(--hue) 40% 82%) 0 12.5%, hsl(calc(var(--hue) + 40) 35% 72%) 12.5% 25%),
			var(--ground);
		display: grid;
		place-items: center;
	}
	.label {
		padding: 4px 10px;
		border-radius: 999px;
		background: var(--panel);
		font: 600 15px var(--font-display);
	}
	.size {
		position: absolute;
		right: 8px;
		bottom: 6px;
		font-size: 11px;
		color: var(--ink);
	}
	.foot {
		margin: 0;
		padding: 6px 28px 8px 10px;
		font-size: 12px;
		color: var(--ink-soft);
	}
</style>
