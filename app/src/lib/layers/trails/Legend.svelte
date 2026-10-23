<script lang="ts">
	import { PAVED_FROM_ZOOM } from '#lib/base/trails/paved.js';
	import type { LegendProps } from '../types.js';
	import type { TrailsModule } from './index.svelte.js';
	import { countsText, DASHED, INFORMAL_LOOK, INFORMAL_WORDS, LOOKS, UMBER, type Sev } from './trails.js';

	/**
	 * The Trails legend (plan K8: each dash has its word): the trail umber, the line for each state with
	 * what it means (the icons beside them), the informal ways, the paved ones in the base, and where the
	 * status comes from, with R2R's counts and when it was last polled. A status is never told by color.
	 */
	let { module }: LegendProps = $props();
	const trails = $derived(module as unknown as TrailsModule);
	const status = $derived(trails.trail);
	const counts = $derived(status ? countsText(status.counts) : []);
	const ORDER: Sev[] = ['open', 'not_evaluated', ...DASHED];
	const W = 2.6;
	const dash = (d: readonly number[] | null) => (d ? d.map((x) => +(x * W).toFixed(2)).join(' ') : undefined);
	const ICON: Record<string, string> = { caution: '▲', do_not_use: '■', closed: '✕', detour: '➤' };
</script>

<p class="legend-title">Status and kind</p>
<ul class="keys" aria-label="Trail status">
	{#each ORDER as sev (sev)}
		{@const look = LOOKS[sev]}
		<li data-sev={sev}>
			<svg viewBox="0 0 36 12" width="36" height="12" aria-hidden="true">
				<line
					x1="1"
					y1="6"
					x2="35"
					y2="6"
					stroke={UMBER}
					stroke-width={W * look.width}
					stroke-opacity={look.opacity}
					stroke-linecap={look.cap}
					stroke-dasharray={dash(look.dash)}
				/>
			</svg>
			<span><b>{look.word}</b>{#if ICON[sev]}{' '}<span class="mark" aria-hidden="true">{ICON[sev]}</span>{/if}: {look.about}. <span class="shape">{look.shape}.</span></span>
		</li>
	{/each}
	<li data-sev="informal">
		<svg viewBox="0 0 36 12" width="36" height="12" aria-hidden="true">
			<line x1="1" y1="6" x2="35" y2="6" stroke={UMBER} stroke-width={W * 0.9} stroke-linecap="round" stroke-dasharray={dash(INFORMAL_LOOK.dash)} />
		</svg>
		<span><b>{INFORMAL_LOOK.word}</b>: {INFORMAL_WORDS}, shown from z16. <span class="shape">{INFORMAL_LOOK.shape}.</span></span>
	</li>
</ul>
<p class="hint">
	Ridge to Rivers' statuses are its advice, not an order. A Greenbelt closure or detour is the City's. Paved paths show in the base from z{PAVED_FROM_ZOOM}; private ways and canal banks are left out.
</p>
{#if counts.length}
	<p class="counts"><span class="num">{counts.join(' · ')}</span> <span class="how">of Ridge to Rivers' trails now</span></p>
{/if}
{#if trails.age()}
	<p class="hint" data-age>{trails.age()}.</p>
{/if}
{#if trails.error}
	<p class="note" role="alert">▲ {trails.error}</p>
{/if}
<p class="credit">
	Ways and routes © OpenStreetMap contributors. Status: City of Boise Parks &amp; Recreation (Ridge to Rivers; Greenbelt closures). The City's lines are shown per trail on this private map only (no licence stated; not republished).
</p>

<style>
	li {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		font-size: 12px;
	}
	svg {
		flex: none;
		margin-top: 2px;
	}
	.mark {
		font-size: 11px;
	}
	.shape {
		color: var(--ink-soft);
	}
	.counts,
	.note {
		margin: 6px 0 0;
		font-size: 12px;
		color: var(--ink);
	}
	.how {
		color: var(--ink-soft);
	}
</style>
