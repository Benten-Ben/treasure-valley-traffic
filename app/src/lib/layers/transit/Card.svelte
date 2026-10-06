<script lang="ts">
	import Badge from '#lib/ui/Badge.svelte';
	import type { CardProps } from '../types.js';
	import { badgeFor, routeBadge, type TransitModule } from './index.svelte.js';
	import { ageText, CREDIT, isStale, liveByRoute, stopText, type Stop } from './transit.js';

	let { selection, module }: CardProps = $props();
	const transit = $derived(module as unknown as TransitModule);
	const bus = $derived(selection.kind === 'bus' ? (transit.vehicles.find((v) => v.vehicleId === selection.id) ?? null) : null);
	const route = $derived(selection.kind === 'route' ? (transit.routes.find((r) => r.route_id === selection.id) ?? null) : null);
	const stop = $derived(selection.kind === 'stop' ? (selection.data as Stop) : null);
	const byRoute = $derived(liveByRoute(transit.vehicles, transit.feedNow));
</script>

{#if selection.kind === 'bus'}
	{#if bus}
		<h2><Badge badge={badgeFor(bus)} big />{bus.longName ?? 'Route not reported'}</h2>
		<p class="meta">
			Bus <span class="num">{bus.label ?? bus.vehicleId}</span> · updated {ageText(transit.feedNow - bus.ts)}
			{#if isStale(bus, transit.feedNow)}<strong> · ▲ not reporting</strong>{/if}
		</p>
		{#if stopText(bus)}<p class="meta">{stopText(bus)}</p>{/if}
		{#if bus.routeMatched}<p class="meta">Route matched from the bus's path: the feed doesn't name it.</p>{/if}
		<p class="meta">Drawn where it last reported (not extrapolated).</p>
	{:else}
		<h2>{selection.title}</h2>
		<p class="meta">This bus is no longer reporting.</p>
	{/if}
{:else if selection.kind === 'route' && route}
	<h2><Badge badge={routeBadge(route)} big />{route.long_name ?? `Route ${route.short_name}`}</h2>
	<p class="meta">
		{#if byRoute[route.route_id]}● {byRoute[route.route_id]} bus{byRoute[route.route_id] === 1 ? '' : 'es'} running now{:else}◌ Not running now: no bus in the last 15 min{/if}
	</p>
	<button class="pill" aria-pressed={transit.spot === route.route_id} onclick={() => transit.spotlight(transit.spot === route.route_id ? null : route.route_id)}>
		{transit.spot === route.route_id ? 'Spotlight on' : 'Spotlight'}
	</button>
{:else if stop}
	<h2>{stop.name}</h2>
	<p class="meta">Routes that stop here:</p>
	<p class="badges">
		{#each stop.routeIds as id (id)}
			{@const r = transit.routes.find((x) => x.route_id === id)}
			{#if r}<span class="served" class:idle={!byRoute[id]} title={byRoute[id] ? 'Running now' : 'Not running now'}><Badge badge={routeBadge(r)} />{byRoute[id] ? '●' : '◌'}</span>{/if}
		{/each}
	</p>
{:else}
	<h2>{selection.title}</h2>
{/if}
<p class="credit">{CREDIT}</p>

<style>
	.badges {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin: 0 0 6px;
	}
	.served {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		font-size: 12px;
	}
</style>
