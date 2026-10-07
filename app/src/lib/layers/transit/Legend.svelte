<script lang="ts">
	import Badge from '#lib/ui/Badge.svelte';
	import { dayText, timeText } from '#lib/state/clock.svelte.js';
	import type { LegendProps } from '../types.js';
	import { routeBadge, type TransitModule } from './index.svelte.js';
	import { CREDIT, INK, UNKNOWN_COLOR } from './transit.js';

	/**
	 * The Transit legend (docs/14 §14.4, "Running and not-running routes"):
	 * "Running now (n buses)" and "Not running now", the dormant routes ("no
	 * buses seen since …"), the key line in words, and the trails switch.
	 * Clicking a route selects and spotlights it.
	 */
	let { module }: LegendProps = $props();
	const transit = $derived(module as unknown as TransitModule);
	const byRoute = $derived(transit.busesByRoute());
	const dormantIds = $derived(new Set(transit.network?.dormant.map((d) => d.routeId) ?? []));
	const routes = $derived((transit.network?.routes ?? []).filter((r) => !dormantIds.has(r.id)));
	const running = $derived(routes.filter((r) => transit.running.has(r.id)));
	const idle = $derived(routes.filter((r) => !transit.running.has(r.id)));
	const dormant = $derived(
		(transit.network?.dormant ?? []).map((d) => ({ d, r: transit.route(d.routeId) })).filter((x) => x.r)
	);
	const busCount = $derived(Object.values(byRoute).reduce((a, b) => a + b, 0));
	const noBuses = $derived(busCount === 0);
</script>

<p class="legend-title">Routes <span class="num">· buses {transit.clock?.state === 'replay' ? 'replayed' : 'a little behind live'}</span></p>
{#snippet row(r: (typeof routes)[number])}
	<li>
		<button
			class="route"
			class:spot={transit.spot === r.id}
			class:idle={!transit.running.has(r.id)}
			aria-pressed={transit.spot === r.id}
			onclick={() => transit.selectRoute(transit.spot === r.id ? null : r.id)}
		>
			<Badge badge={routeBadge(r)} />
			<span class="route-name">{r.longName ?? `Route ${r.shortName}`}</span>
			<span class="num count">{byRoute[r.id] ?? ''}</span>
		</button>
	</li>
{/snippet}
{#if noBuses}
	<p class="chip-line" role="status">
		<span aria-hidden="true">■</span> No buses reporting{transit.lastFix ? ` · last fix ${timeText(transit.lastFix)}, ${dayText(transit.lastFix)}` : ''}
	</p>
{/if}
{#if running.length}
	<p class="group">Running now <span class="num">({busCount} bus{busCount === 1 ? '' : 'es'})</span></p>
	<ul class="routes">
		{#each running as r (r.id)}{@render row(r)}{/each}
		{#if byRoute['?']}
			<li class="unknown">
				<Badge badge={{ text: '?', color: UNKNOWN_COLOR, textColor: INK, halo: true }} />
				<span class="route-name">Route not reported</span>
				<span class="num count">{byRoute['?']}</span>
			</li>
		{/if}
	</ul>
{/if}
{#if idle.length}
	<p class="group">Not running now</p>
	<ul class="routes">
		{#each idle as r (r.id)}{@render row(r)}{/each}
	</ul>
{/if}
<p class="hint"><span class="ghost-key" aria-hidden="true"></span>Faded: no bus in the last 15 min</p>
{#if dormant.length}
	<p class="group">Not in service</p>
	<ul class="routes dormant">
		{#each dormant as { d, r } (d.routeId)}
			<li class="unknown">
				<Badge badge={routeBadge(r!)} />
				<span class="route-name">{r!.longName ?? `Route ${r!.shortName}`}</span>
				<span class="since">{d.lastFix ? `no buses seen since ${dayText(d.lastFix)}` : 'no buses seen'}</span>
			</li>
		{/each}
	</ul>
{/if}
<label class="trails">
	<input type="checkbox" checked={transit.trails.value} onchange={(e) => transit.setTrails(e.currentTarget.checked)} />
	Trails (last 5 min)
</label>
<p class="credit">Positions: {CREDIT}. Drawn between reported positions, never ahead of them.</p>

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
		min-height: 28px;
		padding: 2px 4px;
		border: 0;
		border-radius: 8px;
		background: none;
		font: 13px var(--font-body);
		color: var(--ink);
		text-align: left;
	}
	.route {
		cursor: pointer;
	}
	.route:hover,
	.route.spot {
		background: rgb(43 42 51 / 0.08);
	}
	.route.spot {
		box-shadow: inset 0 0 0 2px var(--ink);
	}
	.route:focus-visible {
		outline: none;
		box-shadow:
			0 0 0 2px var(--ink),
			0 0 0 5px var(--accent);
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
	.count,
	.since {
		font-size: 12px;
		color: var(--ink-soft);
	}
	.dormant :global(.badge) {
		opacity: 0.45;
	}
	.hint {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.ghost-key {
		display: inline-block;
		width: 22px;
		height: 4px;
		border-radius: 2px;
		background: #b1c6e2;
		box-shadow: 0 0 0 1.5px #86837f;
	}
	.chip-line {
		margin: 4px 0;
		font: 600 13px var(--font-body);
	}
	.trails {
		display: flex;
		align-items: center;
		gap: 6px;
		margin: 8px 0 2px;
		font: 13px var(--font-body);
		cursor: pointer;
	}
</style>
