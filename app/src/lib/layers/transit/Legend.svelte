<script lang="ts">
	import Badge from '#lib/ui/Badge.svelte';
	import type { LegendProps } from '../types.js';
	import type { TransitModule } from './index.svelte.js';
	import { routeBadge } from './index.svelte.js';
	import { CREDIT, liveByRoute, UNKNOWN_COLOR } from './transit.js';

	let { module }: LegendProps = $props();
	const transit = $derived(module as unknown as TransitModule);
	const byRoute = $derived(liveByRoute(transit.vehicles, transit.feedNow));
	const running = $derived(transit.routes.filter((r) => byRoute[r.route_id]));
	const idle = $derived(transit.routes.filter((r) => !byRoute[r.route_id]));
	const busCount = $derived(Object.values(byRoute).reduce((a, b) => a + b, 0));
</script>

<p class="legend-title">Routes <span class="num">· live buses</span></p>
{#snippet row(r: (typeof transit.routes)[number])}
	<li>
		<button
			class="route"
			class:spot={transit.spot === r.route_id}
			class:idle={!byRoute[r.route_id]}
			aria-pressed={transit.spot === r.route_id}
			onclick={() => transit.selectRoute(transit.spot === r.route_id ? null : r.route_id)}
		>
			<Badge badge={routeBadge(r)} />
			<span class="route-name">{r.long_name}</span>
			<span class="num count">{byRoute[r.route_id] ?? ''}</span>
		</button>
	</li>
{/snippet}
{#if running.length}
	<p class="group">Running now <span class="num">({busCount} bus{busCount === 1 ? '' : 'es'})</span></p>
	<ul class="routes">
		{#each running as r (r.route_id)}{@render row(r)}{/each}
		{#if byRoute['?']}
			<li class="unknown">
				<Badge badge={{ text: '?', color: UNKNOWN_COLOR, textColor: '#2b2a33', halo: true }} />
				<span class="route-name">Route not reported</span>
				<span class="num count">{byRoute['?']}</span>
			</li>
		{/if}
	</ul>
{/if}
<p class="group">{running.length ? 'Not running now' : 'No buses reporting in the last 15 minutes'}</p>
<ul class="routes">
	{#each idle as r (r.route_id)}{@render row(r)}{/each}
</ul>
<p class="hint">Faded: no bus in the last 15 min</p>
<p class="credit">Live positions: {CREDIT}</p>

<style>
	.routes {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.group {
		margin: 6px 0 2px;
		font: 600 12px var(--font-body);
		color: var(--ink-soft);
	}
	.route,
	.unknown {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		padding: 2px 4px;
		border: 0;
		border-radius: 8px;
		background: none;
		font: 13px var(--font-body);
		color: var(--ink);
		text-align: left;
		cursor: pointer;
	}
	.route:hover,
	.route.spot {
		background: rgb(43 42 51 / 0.08);
	}
	.route.idle .route-name {
		color: var(--ink-soft);
	}
	.route.idle :global(.badge) {
		opacity: 0.55;
	}
	.route-name {
		flex: 1;
	}
	.count {
		font-size: 12px;
		color: var(--ink-soft);
	}
</style>
