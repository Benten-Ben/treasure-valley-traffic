<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { getAppCtx } from '#lib/app/context.js';
	import type { LiveView } from '#lib/contracts/live.js';
	import { windowsOf, type WindowStatus, type WinState } from '#lib/state/windows.svelte.js';
	import Icon from '#lib/ui/Icon.svelte';
	import Frame from '../cameras/Frame.svelte';
	import Freshness from '../cameras/Freshness.svelte';
	import { footText, ringProgress, shown, THRESHOLDS, type Shown } from '../cameras/freshness.js';
	import { FLY_TO } from '../cameras/icons.js';
	import { liveOf } from '../cameras/live.svelte.js';
	import type { RoadWeatherModule } from './index.svelte.js';
	import { creditOf, NO_FEED_AFTER_S, type RoadWeatherView } from './model.js';

	/**
	 * A road-weather station's window (docs/14 §14.6 "Road weather"; WP16):
	 * one tab per view (direction), each with the newest captured picture and
	 * its age, on the road-weather freshness thresholds (live under 20 min,
	 * stale over 45; cameras/freshness.ts). WP3's frame draws the header
	 * (number badge, name, status as shape and word), Pin, Dock and Close.
	 *
	 * The pictures come through the app's one live feed (WP12's batched poll of
	 * /api/cameras/live, every 60 s when every view is a road-weather one) for
	 * every view of the station that 511 doesn't list as disabled, while the
	 * window is open; closing it releases them at once. A view that 511 lists
	 * as disabled, or whose capture has had no new picture for 45 minutes,
	 * shows 511's "no live feed" picture (model.ts), and the tab says so.
	 */
	let { stationId, name, win }: { stationId: number; name: string; win: WinState } = $props();
	const app = getAppCtx();
	const feed = liveOf(app);
	const windows = windowsOf(app);
	const id = untrack(() => stationId);
	const key = untrack(() => win.key);
	const uid = Math.random().toString(36).slice(2, 8);
	const SOFT = 'var(--ink-soft)';
	const SEEN = "Seen: when our capture first got this picture (511 refreshes road-weather pictures about every 15 minutes). The time printed on the picture is the station's own clock.";

	const mod = () => app.layers?.modules.weather as RoadWeatherModule | undefined;
	const station = $derived(mod()?.data?.stations.find((s) => s.id === id) ?? null);
	const views = $derived(station?.views ?? []);
	let picked = $state<number | null>(null);
	// The first tab with a live picture, until the viewer picks one.
	const tab = $derived.by(() => {
		if (picked !== null && picked < views.length) return picked;
		const live = views.findIndex((v) => v.feed === 'live');
		return live === -1 ? 0 : live;
	});
	const view = $derived<RoadWeatherView | null>(views[tab] ?? null);

	// Poll every view of the station that can have a picture, while the window is open.
	const watchIds = $derived(views.filter((v) => !v.disabled && v.imageId !== null).map((v) => v.id));
	const watchKey = $derived(watchIds.join(','));
	$effect(() => {
		void watchKey;
		const ids = untrack(() => watchIds);
		if (!ids.length) return;
		return feed.watch(ids);
	});

	// The UI's 1 Hz clock: ages move once a second, never per frame.
	let now = $state(Date.now());
	const tick = setInterval(() => (now = Date.now()), 1000);
	onDestroy(() => clearInterval(tick));

	const liveOfView = (v: RoadWeatherView): LiveView | null => feed.views[v.id] ?? null;

	/** Seconds since its newest picture: the live answer's, else the station list's. */
	function ageOf(v: RoadWeatherView, t: number): number | null {
		const live = liveOfView(v);
		if (live?.frame) return feed.ageOf(live.frame, t);
		const m = mod();
		return v.seenAt === null || !m ? null : Math.max(0, (t + m.skew) / 1000 - v.seenAt);
	}

	/** A view's status, in a shape and a word. */
	function stateOf(v: RoadWeatherView, t: number): Shown {
		if (v.disabled)
			return { kind: 'offline', shape: '■', word: 'no live feed', color: SOFT, detail: "511 lists this view as disabled: it shows 511's “no live feed” picture" };
		const live = liveOfView(v);
		const age = ageOf(v, t);
		if (!live?.frame && v.feed === 'no_feed')
			return { kind: 'offline', shape: '■', word: 'no live feed', color: SOFT, detail: "No picture recorded lately while capture runs: 511 is showing its “no live feed” picture" };
		if (!live && age !== null)
			return shown({ viewId: v.id, imageId: v.imageId, source: 'archive', frame: { url: '', firstSeenAt: v.seenAt ?? 0, width: 0, height: 0, sha: '' }, cadence: 'road_weather', cadenceS: 600, state: 'ok' }, age);
		return shown(live, age);
	}

	/** "4 min", "1 h", "2 d": the tab's short age. */
	function shortAge(s: number): string {
		if (s < 60) return '<1 min';
		if (s < 3600) return `${Math.floor(s / 60)} min`;
		if (s < 86_400) return `${Math.floor(s / 3600)} h`;
		return `${Math.floor(s / 86_400)} d`;
	}

	const live = $derived(view ? liveOfView(view) : null);
	const frame = $derived(live?.frame ?? null);
	const age = $derived(view ? ageOf(view, now) : null);
	const status = $derived<Shown | null>(view ? stateOf(view, now) : null);
	const aspect = $derived(frame && frame.width && frame.height ? frame.width / frame.height : 800 / 486);
	const credit = $derived(station ? creditOf(station.provider) : 'ITD 511 road weather');
	const noFeed = $derived(status?.word === 'no live feed');
	const staleNoFeed = $derived(!!view && !view.disabled && view.feed === 'no_feed' && !!frame && (age ?? 0) > NO_FEED_AFTER_S);

	/** The header's status, without the age (so it changes only when the state does). */
	function headerStatus(s: Shown | null): WindowStatus {
		if (!station) return { shape: '◌', word: 'waiting', color: SOFT, detail: 'Loading the station…' };
		if (station.hollow) return { shape: '■', word: 'no live feed', color: SOFT, detail: "Every view shows 511's “no live feed” picture" };
		if (!s) return { shape: '◌', word: 'no views', color: SOFT, detail: 'No views are listed for this station' };
		const t = THRESHOLDS.road_weather;
		const detail: Partial<Record<Shown['kind'], string>> = {
			fresh: `Live: a new picture within the last ${t.fresh / 60} min`,
			late: `Late: no new picture for over ${t.fresh / 60} min`,
			stale: `Stale: no new picture for over ${t.late / 60} min`
		};
		return { shape: s.shape, word: s.word, color: s.color, detail: detail[s.kind] ?? s.detail };
	}

	let pushed = '';
	$effect(() => {
		const st = headerStatus(status);
		const a = aspect;
		const sig = `${st.shape}|${st.word}|${a.toFixed(4)}`;
		if (sig === pushed) return;
		pushed = sig;
		untrack(() => windows.update(key, { status: st, aspect: a }));
	});

	// Arrow keys move along the tabs (the WAI-ARIA tabs pattern); the panel follows.
	let tabEls: HTMLButtonElement[] = $state([]);
	function tabKey(e: KeyboardEvent, i: number) {
		const n = views.length;
		const to = e.key === 'ArrowRight' ? (i + 1) % n : e.key === 'ArrowLeft' ? (i - 1 + n) % n : e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : -1;
		if (to < 0) return;
		e.preventDefault();
		e.stopPropagation();
		picked = to;
		tabEls[to]?.focus();
	}

	const tabId = (i: number) => `rw-${uid}-tab-${i}`;
	const panelId = `rw-${uid}-panel`;
</script>

<div class="rw" data-station-id={id} data-view-id={view?.id} data-state={status?.kind ?? 'loading'}>
	{#if !station}
		<p class="note">◌ Loading the station…</p>
	{:else if !views.length}
		<p class="note"><span class="shape" aria-hidden="true">■</span> 511 lists no views for this station.</p>
	{:else}
		<div class="tabs" role="tablist" aria-label="Views of {name}">
			{#each views as v, i (v.id)}
				{@const s = stateOf(v, now)}
				{@const a = ageOf(v, now)}
				<button
					bind:this={tabEls[i]}
					class="tab"
					role="tab"
					id={tabId(i)}
					aria-selected={i === tab}
					aria-controls={panelId}
					tabindex={i === tab ? 0 : -1}
					title={s.detail}
					data-view-id={v.id}
					data-state={s.kind}
					data-age={a === null ? '' : Math.round(a)}
					onclick={() => (picked = i)}
					onkeydown={(e) => tabKey(e, i)}
				>
					<span class="shape" style:color={s.color} aria-hidden="true">{s.shape}</span>
					<span class="label">{v.label}</span>
					{#if a !== null && !v.disabled}<span class="age num">{shortAge(a)}</span>{/if}
					<span class="sr">, {s.word}</span>
				</button>
			{/each}
		</div>
		<div class="panel" role="tabpanel" id={panelId} aria-labelledby={tabId(tab)}>
			<!-- One frame per view: another tab never shows the last tab's picture (nor crossfades from it). -->
			{#key view?.id}
				<Frame
					url={frame?.url ?? null}
					alt="Road-weather picture from {name}, {view?.label} ({credit})"
					{aspect}
					empty={noFeed && !frame
						? 'No live feed: 511 has no picture from this camera now'
						: live && live.state !== 'ok' && live.state !== 'waiting'
							? `No picture: ${status?.word}`
							: null}
				/>
			{/key}
			<div class="foot">
				{#if status}
					<Freshness shown={status} progress={age === null || !live ? 0 : ringProgress(age, live.cadenceS)} pulse={frame?.sha ?? null} />
				{/if}
				<span class="seen num" title={SEEN} data-age={age === null ? '' : Math.round(age)}>
					{view?.disabled
						? 'no live feed · 511 lists this view as disabled'
						: noFeed && !frame
							? 'no live feed · no picture recorded lately'
							: footText(live, age)}
				</span>
				<span class="credit">{credit}</span>
			</div>
			{#if staleNoFeed}
				<p class="note"><span class="shape" aria-hidden="true">■</span> No new picture for over 45 minutes: 511 is probably showing its “no live feed” picture.</p>
			{:else if live && live.state !== 'ok' && live.state !== 'waiting' && status}
				<p class="note"><span class="shape" style:color={status.color} aria-hidden="true">{status.shape}</span> {status.detail}</p>
			{/if}
		</div>
	{/if}
	<div class="actions">
		<button class="pill" disabled={!station} onclick={() => mod()?.flyTo(id)}><Icon icon={FLY_TO} size={18} /> Fly to</button>
		{#if station}<span class="provider">{station.provider} · {views.length} view{views.length === 1 ? '' : 's'}</span>{/if}
	</div>
</div>

<style>
	.rw {
		display: flex;
		flex-direction: column;
	}
	.tabs {
		display: flex;
		gap: 4px;
		padding: 6px 8px;
		flex-wrap: wrap;
	}
	.tab {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		min-height: 30px;
		max-width: 180px;
		padding: 2px 10px;
		border: 2px solid var(--panel-edge);
		border-radius: 999px;
		background: var(--panel);
		color: var(--ink);
		font: 600 12px var(--font-body);
		white-space: nowrap;
		cursor: pointer;
	}
	.tab[aria-selected='true'] {
		border-color: var(--ink);
		background: var(--ink);
		color: var(--panel);
	}
	/* On the ink tab the shape turns cream: the shape carries the status, never the color alone. */
	.tab[aria-selected='true'] .shape {
		color: var(--panel) !important;
	}
	.tab:focus-visible {
		outline: 2px solid var(--ink);
		outline-offset: 2px;
		box-shadow: 0 0 0 5px var(--accent);
	}
	.label {
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.age {
		font-family: var(--font-mono);
		font-size: 11px;
		font-weight: 500;
		opacity: 0.85;
	}
	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
	.foot {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 4px 10px;
		padding: 6px 28px 2px 10px;
		font-size: 12px;
	}
	.seen {
		flex: 1 1 auto;
		min-width: 0;
		color: var(--ink);
		font-family: var(--font-mono);
		font-size: 12px;
	}
	.credit,
	.provider {
		color: var(--ink-soft);
		font-size: 11px;
	}
	.note {
		margin: 6px 10px 0;
		color: var(--ink);
		font-size: 13px;
		line-height: 1.35;
	}
	.shape {
		font-size: 11px;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px 10px;
		padding: 8px 28px 8px 10px;
	}
	.actions :global(.pill) {
		display: inline-flex;
		align-items: center;
		gap: 5px;
	}
</style>
