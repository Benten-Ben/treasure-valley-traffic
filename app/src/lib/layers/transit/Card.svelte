<script lang="ts">
	import type { NetworkHub, NetworkStop } from '#lib/contracts/network.js';
	import { clockText, minSec } from '#lib/state/clock.svelte.js';
	import Badge from '#lib/ui/Badge.svelte';
	import type { CardProps } from '../types.js';
	import { busBadge, routeBadge, type TransitModule } from './index.svelte.js';
	import { speedText } from './playback.js';
	import { CREDIT } from './transit.js';

	/**
	 * The bus, route, stop and hub cards (docs/14 §14.4, "Cards"). They read
	 * the module's once-a-second state, never per frame.
	 *
	 * - Bus: route badge and name, bus number, headsign, the current step's
	 *   speed ("18 mph" or "stopped"), the last fix time and its age at the
	 *   playhead, how the position and route are known, the credit, Follow.
	 * - Route: name, running buses, Spotlight.
	 * - Stop and hub: name, routes served, which are running.
	 */
	let { selection, module }: CardProps = $props();
	const transit = $derived(module as unknown as TransitModule);
	const clock = $derived(transit.clock);
	const T = $derived(clock ? clock.T : Date.now() / 1000);
	const byRoute = $derived(transit.busesByRoute());

	const vid = $derived(selection.kind === 'bus' ? selection.id : null);
	const v = $derived(vid ? transit.vehicles[vid] : undefined);
	const b = $derived(vid ? transit.buses[vid] : undefined);
	const busRoute = $derived(transit.route(v?.routeId));
	const following = $derived(Boolean(vid && transit.follow?.is('bus', vid)));

	const route = $derived(selection.kind === 'route' ? transit.route(selection.id) : undefined);
	const place = $derived(selection.kind === 'stop' || selection.kind === 'hub' ? (selection.data as NetworkStop | NetworkHub) : null);

	/** How the position is known, in words. */
	const how = $derived.by(() => {
		if (!b) return null;
		switch (b.state) {
			case 'moving':
				return 'Between reported positions (interpolated)';
			case 'still':
				return 'At its reported position';
			case 'gap':
				return 'Between reported positions: a gap in its GPS';
			case 'waiting':
				return 'At its last reported position, waiting for GPS';
			case 'stale':
				return `▲ No new GPS for ${minSec(T - b.fix)}: shown hollow`;
			default:
				return '■ Not reporting now';
		}
	});
	const routeHow = $derived(
		v?.routeSource === 'path' ? 'Route guessed from its path' : v?.routeSource === 'matched' ? 'Route matched from its path' : null
	);
</script>

{#if selection.kind === 'bus'}
	{#if v}
		<h2><Badge badge={busBadge(v)} big />{busRoute?.longName ?? (v.routeId ? `Route ${v.shortName ?? v.routeId}` : 'Route not reported')}</h2>
		<p class="meta">
			Bus <span class="num">{v.label ?? vid}</span>{#if v.headsign} · toward {v.headsign}{/if}
		</p>
		{#if b && (b.state === 'moving' || b.state === 'still')}
			<p class="meta"><strong>{b.state === 'moving' ? (speedText(b.stepSpeed) ?? 'moving') : 'stopped'}</strong></p>
		{/if}
		{#if b}
			<p class="meta num">Last fix {clockText(b.fix)} · {minSec(Math.max(0, T - b.fix))} before the time shown</p>
		{/if}
		{#if how}<p class="meta">{how}</p>{/if}
		{#if routeHow}<p class="meta">{routeHow}</p>{/if}
		<button class="pill" aria-pressed={following} disabled={!transit.follow || b?.state === 'hidden'} onclick={() => vid && transit.toggleFollow(vid)}>
			{following ? 'Following · Esc to stop' : 'Follow'}
		</button>
	{:else}
		<h2>{selection.title}</h2>
		<p class="meta">This bus is no longer reporting.</p>
	{/if}
{:else if selection.kind === 'route' && route}
	<h2><Badge badge={routeBadge(route)} big />{route.longName ?? `Route ${route.shortName}`}</h2>
	<p class="meta">
		{#if transit.running.has(route.id)}● Running now · {byRoute[route.id] ?? 0} bus{(byRoute[route.id] ?? 0) === 1 ? '' : 'es'} on the map{:else}◌ Not running now: no bus in the last 15 min{/if}
	</p>
	<button class="pill" aria-pressed={transit.spot === route.id} onclick={() => transit.spotlight(transit.spot === route.id ? null : route.id)}>
		{transit.spot === route.id ? 'Spotlight on' : 'Spotlight'}
	</button>
{:else if place}
	<h2>{place.name ?? 'Stop'}</h2>
	<p class="meta">{selection.kind === 'hub' ? 'Routes that meet here' : 'Routes that stop here'}:</p>
	<ul class="served">
		{#each place.routes as id (id)}
			{@const r = transit.route(id)}
			{#if r}
				<li>
					<Badge badge={routeBadge(r)} />
					<span class:idle={!transit.running.has(id)}>{transit.running.has(id) ? '● running' : '◌ not running'}</span>
				</li>
			{/if}
		{/each}
	</ul>
{:else}
	<h2>{selection.title}</h2>
{/if}
<p class="credit">{CREDIT}</p>

<style>
	.served {
		display: flex;
		flex-wrap: wrap;
		gap: 6px 12px;
		margin: 0 0 6px;
		padding: 0;
		list-style: none;
	}
	.served li {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-size: 12px;
	}
	.idle {
		color: var(--ink-soft);
	}
</style>
