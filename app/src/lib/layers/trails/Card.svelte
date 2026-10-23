<script lang="ts">
	import type { CardProps } from '../types.js';
	import type { TrailsModule } from './index.svelte.js';
	import type { LineCard, WayCard } from '#lib/server/trails/card.js';
	import {
		CREDIT_OSM,
		dateText,
		INFORMAL_WORDS,
		kindWord,
		LOOKS,
		stateWord,
		surfaceText,
		UMBER,
		widthText,
		worstSev,
		type Sev,
		type TrailData
	} from './trails.js';

	/**
	 * The trail card (plan §3.3, "trail"): a way's kind, name, surface (Ridge to Rivers' dirt default shows here
	 * and nowhere else), width (tagged or estimated), whether it's informal, and each agency line on it with
	 * its status, in the agency's words, and who said so. An agency line's own card gives its state and how much
	 * of it draws itself. A paved area says what it is. Estimates say so.
	 */
	let { selection, module }: CardProps = $props();
	const trails = $derived(module as unknown as TrailsModule);
	const data = $derived(selection.data as TrailData);

	let way = $state<WayCard | null>(null);
	let line = $state<LineCard | null>(null);
	let loading = $state(false);
	let problem = $state<string | null>(null);

	$effect(() => {
		const d = data;
		way = null;
		line = null;
		problem = null;
		if (d.type === 'area') {
			loading = false;
			return;
		}
		let live = true;
		loading = true;
		const ask = d.type === 'way' ? trails.detail<WayCard>('way', d.id) : trails.detail<LineCard>('line', d.id);
		ask.then(
			(c) => {
				if (!live) return;
				loading = false;
				if (!c) problem = d.type === 'way' ? 'This way is not on the map any more.' : 'This line is not in the City’s layer any more.';
				else if (d.type === 'way') way = c as WayCard;
				else line = c as LineCard;
			},
			(e) => {
				if (!live) return;
				loading = false;
				problem = `Couldn't load its details: ${e instanceof Error ? e.message : e}`;
			}
		);
		return () => {
			live = false;
		};
	});

	const surface = $derived(way ? surfaceText(way) : null);
	const width = $derived(way ? widthText(way) : null);
	const sev = $derived<Sev | null>(way ? worstSev(way.lines) : line ? (line.severity ?? null) : null);
	const areaProps = $derived((data.type === 'area' ? data.props : {}) as Record<string, unknown>);

	/** The look's line, drawn as the map draws it (the dash is the state, not the color). */
	function swatch(s: Sev | null) {
		const look = LOOKS[s ?? 'open'];
		return { dash: look.dash ? look.dash.map((x) => +(x * 2.6).toFixed(2)).join(' ') : undefined, cap: look.cap, w: 2.6 * look.width, o: look.opacity };
	}
	const sw = $derived(swatch(sev));
</script>

<h2>{way?.name ?? line?.name ?? selection.title}</h2>
{#if data.type === 'area'}
	<p class="meta">{areaProps.kind === 'pedestrian' ? 'Pedestrian plaza' : 'Paved footway area'} · paved</p>
	<p class="explain">A paved area drawn from OpenStreetMap; the base shows it from z15.5.</p>
	<p class="credit">{CREDIT_OSM}</p>
{:else}
	<p class="meta kind-line">
		<svg viewBox="0 0 36 12" width="36" height="12" aria-hidden="true">
			<line x1="1" y1="6" x2="35" y2="6" stroke={UMBER} stroke-width={sw.w} stroke-opacity={sw.o} stroke-linecap={sw.cap} stroke-dasharray={sw.dash} />
		</svg>
		<span>
			{#if data.type === 'line'}
				{line ? (line.kind === 'detour' ? 'Detour' : line.kind === 'closure' ? 'Closure' : 'Trail') : 'Trail'}
			{:else}
				<b>{way ? kindWord(way.kind) : kindWord(String(data.props.kind ?? 'path'))}</b>
			{/if}
			{#if sev}{' · '}{LOOKS[sev].word}{/if}
		</span>
	</p>
	{#if way?.informal || (data.type === 'way' && data.props.informal === true)}
		<p class="explain" data-informal>{INFORMAL_WORDS.replace(/^./, (c) => c.toUpperCase())}. Ridge to Rivers and the City do not list it.</p>
	{/if}

	{#if way}
		<dl class="facts">
			{#if surface}
				<dt>Surface</dt>
				<dd>{surface.text} <span class="how">{surface.how}</span></dd>
			{/if}
			{#if width}
				<dt>Width</dt>
				<dd><span class="num">{width.text}</span> <span class="how">{width.how}</span></dd>
			{/if}
			{#if way.length_m}
				<dt>Length</dt>
				<dd class="num">{way.length_m.toLocaleString('en-US')} m</dd>
			{/if}
			{#if way.ref}
				<dt>Reference</dt>
				<dd>{way.ref}</dd>
			{/if}
			{#if way.bridge}
				<dt>Crossing</dt>
				<dd>Bridge</dd>
			{/if}
			{#if way.greenbelt}
				<dt>Route</dt>
				<dd>Boise River Greenbelt</dd>
			{/if}
		</dl>
		{#if way.lines.length}
			<h3>Status</h3>
			<ul class="lines" aria-label="Status of this trail">
				{#each way.lines as l (l.source + (l.line_id ?? ''))}
					<li data-state={l.state}>
						<b>{stateWord(l.state, l.label)}</b>
						{#if l.name}<span class="how">{' · '}{l.name}{l.system ? ` (${l.system})` : ''}</span>{/if}
						<br />
						<span class="how">
							{#if l.source === 'r2r_trails'}Ridge to Rivers' advice{l.set_at ? `, set ${dateText(l.set_at)}` : ''}.
							{:else}City of Boise Parks and Recreation{l.since ? `, seen since ${dateText(l.since)}` : ''}.{/if}
							{#if !l.paints}{' '}Only part of this way lies along it.{/if}
						</span>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="meta">No status is posted for this trail.</p>
		{/if}
	{:else if line}
		<dl class="facts">
			<dt>Status</dt>
			<dd><b>{stateWord(line.state, line.label)}</b> <span class="how">{line.source === 'r2r_trails' ? "Ridge to Rivers' advice" : 'City of Boise'}{line.set_at ? `, set ${dateText(line.set_at)}` : ''}</span></dd>
			{#if line.system}
				<dt>System</dt>
				<dd>{line.system}</dd>
			{/if}
			{#if line.line_m}
				<dt>Length</dt>
				<dd class="num">{line.line_m.toLocaleString('en-US')} m</dd>
			{/if}
			<dt>On the map</dt>
			<dd>
				{#if line.ways}Along {line.ways} OpenStreetMap {line.ways === 1 ? 'way' : 'ways'}{:else}Drawn from the City's own line; no OpenStreetMap way lies along it{/if}
				{#if line.drawn_m}<span class="how"> ({line.drawn_m.toLocaleString('en-US')} m of it drawn on its own)</span>{/if}
			</dd>
		</dl>
	{/if}
	{#if loading}
		<p class="meta" role="status">Loading what we know…</p>
	{:else if problem}
		<p class="meta" role="alert">▲ {problem}</p>
	{/if}
	<p class="credit">
		{CREDIT_OSM}{#if sev || line}. Status: City of Boise Parks &amp; Recreation (Ridge to Rivers; Greenbelt). Ridge to Rivers' statuses are advice, not closure orders.{/if}
		{#if (way?.surface_default === 'Ridge to Rivers trail')} Dirt is assumed where a Ridge to Rivers trail runs along an untagged way.{/if}
	</p>
{/if}

<style>
	.kind-line {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 4px;
		color: var(--ink);
	}
	.explain {
		margin: 0 0 8px;
		font-size: 13px;
	}
	.facts {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 2px 10px;
		margin: 0 0 8px;
		font-size: 13px;
	}
	dt {
		color: var(--ink-soft);
	}
	dd {
		margin: 0;
	}
	.how {
		color: var(--ink-soft);
		font-size: 12px;
	}
	h3 {
		margin: 8px 0 4px;
		font: 600 14px var(--font-display);
	}
	.lines {
		margin: 0;
		padding: 0;
		list-style: none;
		font-size: 13px;
	}
	.lines li + li {
		margin-top: 4px;
	}
</style>
