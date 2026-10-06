<script lang="ts">
	import { onDestroy } from 'svelte';
	import type { AppCtx } from '#lib/app/context.js';

	/**
	 * "Building the valley…" (docs/14 §14.3, "Loading, errors and honesty"):
	 * real steps (style, terrain, each enabled layer with counts), fading on
	 * the map's first `idle`. It never takes input.
	 */
	let { app }: { app: AppCtx } = $props();
	let idle = $state(false);
	let terrainLoaded = $state(false);
	let gone = $state(false);

	$effect(() => {
		const map = app.map;
		if (!map) return;
		const onIdle = () => {
			idle = true;
			setTimeout(() => (gone = true), 600);
		};
		const onData = (e: { sourceId?: string; isSourceLoaded?: boolean }) => {
			if (e.sourceId === 'terrain' && map.isSourceLoaded('terrain')) terrainLoaded = true;
		};
		map.once('idle', onIdle);
		map.on('sourcedata', onData);
		return () => {
			map.off('idle', onIdle);
			map.off('sourcedata', onData);
		};
	});
	onDestroy(() => (gone = true));

	const steps = $derived.by(() => {
		const out: { label: string; done: boolean; bad?: boolean; note?: string }[] = [];
		out.push({ label: 'Basemap and style', done: app.status === 'ready', bad: app.status === 'error' || app.status === 'unavailable' });
		if (app.manifest?.terrain) out.push({ label: 'Terrain', done: terrainLoaded || idle });
		for (const d of app.layers.defs) {
			if (!app.layers.isOn(d.id)) continue;
			const s = app.layers.status(d.id);
			const note = app.layers.modules[d.id]?.summary?.() ?? undefined;
			out.push({ label: d.title, done: s === 'ready' || s === 'stale', bad: s === 'error', note: s === 'error' ? 'failed' : note });
		}
		return out;
	});
</script>

{#if !gone && app.status !== 'unavailable' && app.status !== 'error'}
	<div class="loading card" class:fade={idle} role="status" aria-live="polite">
		<p class="title">Building the valley…</p>
		<ul>
			{#each steps as s (s.label)}
				<li class:done={s.done} class:bad={s.bad}>
					<span class="mark" aria-hidden="true">{s.bad ? '▲' : s.done ? '●' : '◌'}</span>
					{s.label}{#if s.note}<span class="note num"> · {s.note}</span>{/if}
				</li>
			{/each}
		</ul>
	</div>
{/if}

<style>
	.loading {
		position: absolute;
		top: 76px;
		left: 50%;
		z-index: 60;
		transform: translateX(-50%);
		min-width: 220px;
		padding: 10px 16px;
		font-size: 13px;
		pointer-events: none;
		transition: opacity 500ms;
	}
	.fade {
		opacity: 0;
	}
	.title {
		margin: 0 0 4px;
		font: 600 15px var(--font-display);
	}
	ul {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	li {
		color: var(--ink-soft);
	}
	li.done {
		color: var(--ink);
	}
	.mark {
		display: inline-block;
		width: 16px;
		color: var(--accent-2);
	}
	.bad .mark {
		color: var(--alert);
	}
	.note {
		color: var(--ink-soft);
		font-size: 12px;
	}
</style>
