<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { getAppCtx } from '#lib/app/context.js';
	import { windowsOf, type WindowStatus, type WinState } from '#lib/state/windows.svelte.js';
	import Icon from '#lib/ui/Icon.svelte';
	import { CREDIT } from './cameras.js';
	import { fetchCamera, viewLabel, type CameraDetail } from './detail.js';
	import { footText, ringProgress, SEEN_NOTE, shown, sizeChanged, THRESHOLDS, type Shown } from './freshness.js';
	import Freshness from './Freshness.svelte';
	import Frame from './Frame.svelte';
	import { cameraHooks, lookThroughBlocked } from './hooks.svelte.js';
	import { CALIBRATE, FLY_TO, LOOK, PHOTO_3D } from './icons.js';
	import type { CamerasModule } from './index.svelte.js';
	import { liveOf } from './live.svelte.js';
	import { flyToCamera } from './fly.js';
	import { landBeside, landing } from './place.js';

	/**
	 * A camera window's content (docs/14 §14.6, "Camera windows" and "Live
	 * images"; WP12). WP3's frame draws the header (number badge, name, status
	 * as shape and word), Pin, Dock and Close; this is the rest:
	 *
	 * - the live picture (Frame.svelte): decoded, then crossfaded in; wheel
	 *   zoom up to 4×, drag pan, double-click reset;
	 * - the footer: the freshness chip, "seen 0:48 ago · updates about every
	 *   minute" in mono, and the credit;
	 * - the actions: Look through (calibrated only, else disabled with the
	 *   reason, including the image-size check), Configure or Recalibrate, Fly
	 *   to, and the 3D photo once WP13 provides it;
	 * - not calibrated: "Location ±25 m (ACHD) · not calibrated", with
	 *   Configure as the main button; no view: "Not on 511 Idaho".
	 *
	 * The picture is polled through the app's one live feed while the window is
	 * open; closing it releases the view at once.
	 */
	let { cameraId, name, win }: { cameraId: number; name: string; win: WinState } = $props();
	const app = getAppCtx();
	const feed = liveOf(app);
	const windows = windowsOf(app);
	const id = untrack(() => cameraId);
	const key = untrack(() => win.key);
	const uid = Math.random().toString(36).slice(2, 8);

	let camera = $state.raw<CameraDetail | null>(null);
	let problem = $state<string | null>(null);
	let viewIdx = $state(0);
	let gone = false;
	let ac: AbortController | null = null;

	async function load() {
		ac?.abort();
		const mine = (ac = new AbortController());
		try {
			const c = await fetchCamera(id, mine.signal);
			if (gone || mine.signal.aborted) return;
			camera = c;
			problem = null;
		} catch (e) {
			if (gone || mine.signal.aborted) return;
			problem = `This camera couldn't be loaded: ${e instanceof Error ? e.message : e}`;
		}
	}
	void load();
	// A calibration was saved somewhere: its window shows the new state.
	const unsubscribe = app.subscribe('cameras', () => void load());

	const view = $derived(camera ? (camera.views[viewIdx] ?? camera.views[0] ?? null) : null);
	const noView = $derived(!!camera && (camera.views.length === 0 || camera.views.every((v) => v.imageId === null)));
	const cal = $derived(view?.calibration ?? null);

	// Poll this view's picture while the window is open (and only this view). Keyed by the id, so
	// a refetched camera doesn't restart the poll.
	const watched = $derived(view && view.imageId !== null ? view.id : null);
	$effect(() => {
		const v = watched;
		if (v === null) return;
		return feed.watch([v]);
	});
	// The photo in the cone (WP13) hangs this window's view.
	$effect(() => {
		const v = view?.id ?? null;
		cameraHooks.photo?.view?.(id, v);
	});

	// The UI's 1 Hz clock: ages and the ring move once a second, never per frame.
	let now = $state(Date.now());
	const tick = setInterval(() => (now = Date.now()), 1000);

	const live = $derived(view ? (feed.views[view.id] ?? null) : null);
	const frame = $derived(live?.frame ?? null);
	const age = $derived(frame ? feed.ageOf(frame, now) : null);
	const status = $derived<Shown>(shown(live, age));
	const resized = $derived(sizeChanged(frame, cal));
	const blocked = $derived(
		lookThroughBlocked({ calibrated: !!cal, sizeChanged: resized, available: cameraHooks.lookThrough !== null })
	);
	const aspect = $derived(frame ? frame.width / frame.height : cal ? cal.imageWidth / cal.imageHeight : 768 / 466);
	const photo = $derived(cameraHooks.photo);

	/** The header's status, without the age (so it changes only when the state does). */
	function headerStatus(s: Shown): WindowStatus {
		if (noView) return { shape: '■', word: 'not on 511', color: 'var(--ink-soft)', detail: 'No 511 Idaho image is linked to this camera' };
		const t = THRESHOLDS[live?.cadence ?? 'key'];
		const detail: Partial<Record<Shown['kind'], string>> = {
			fresh: `Live: a new picture within the last ${Math.round(t.fresh / 60)} min`,
			late: `Late: no new picture for over ${Math.round(t.fresh / 60)} min`,
			stale: `Stale: no new picture for over ${Math.round(t.late / 60)} min`
		};
		return { shape: s.shape, word: s.word, color: s.color, detail: detail[s.kind] ?? s.detail };
	}

	let pushed = '';
	$effect(() => {
		const st = headerStatus(status);
		const a = aspect;
		const sig = `${st.shape}|${st.word}|${st.detail}|${a.toFixed(4)}`;
		if (sig === pushed) return;
		pushed = sig;
		untrack(() => windows.update(key, { status: st, aspect: a }));
	});

	/** Fly to the camera, landing it beside this window (above the sheet on a phone). */
	function flyTo() {
		const map = app.map;
		if (!map || !camera) return;
		const box = map.getContainer().getBoundingClientRect();
		const w = windows.get(key);
		const land = windows.layout === 'phone' || !w ? landing(box, win.rect.w, windows.layout) : landBeside(w.rect, box);
		flyToCamera(app, map, camera.pole, land);
	}

	const module = () => app.layers?.modules.cameras as CamerasModule | undefined;

	onDestroy(() => {
		gone = true;
		ac?.abort();
		clearInterval(tick);
		unsubscribe();
		module()?.highlight(id, false);
		cameraHooks.photo?.view?.(id, null);
	});

	const reasonId = `cam-${uid}-why`;
	const calibrateHref = $derived(view ? `/calibrate/${id}?view=${view.id}` : `/calibrate/${id}`);
</script>

<!-- Hovering the window lights up its camera's footprint on the map (a pointer nicety only). -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="cam"
	data-camera-id={id}
	data-view-id={view?.id}
	data-state={noView ? 'no_view' : status.kind}
	onpointerenter={() => module()?.highlight(id, true)}
	onpointerleave={() => module()?.highlight(id, false)}
>
	{#if camera && camera.views.length > 1}
		<div class="views" role="group" aria-label="Views">
			{#each camera.views as v, i (v.id)}
				<button class="view" aria-pressed={i === viewIdx} onclick={() => (viewIdx = i)}>{viewLabel(v, i)}</button>
			{/each}
		</div>
	{/if}

	{#if problem}
		<p class="note bad" role="alert"><span aria-hidden="true">▲</span> {problem} <button class="pill small" onclick={() => void load()}>Retry</button></p>
	{:else if noView}
		<p class="note"><span class="shape" aria-hidden="true">■</span> Not on 511 Idaho: no live picture for this camera.</p>
	{:else}
		<Frame
			url={frame?.url ?? null}
			alt="Live picture from {name} ({CREDIT})"
			{aspect}
			empty={live && live.state !== 'ok' && live.state !== 'waiting' ? `No picture: ${status.word}` : null}
		/>
		<div class="foot">
			<Freshness shown={status} progress={age === null || !live ? 0 : ringProgress(age, live.cadenceS)} pulse={frame?.sha ?? null} />
			<span class="seen num" title={SEEN_NOTE} data-age={age === null ? '' : Math.round(age)}>{footText(live, age)}</span>
			<span class="credit">{CREDIT}</span>
		</div>
		{#if live && live.state !== 'ok' && live.state !== 'waiting'}
			<p class="note why"><span class="shape" style:color={status.color} aria-hidden="true">{status.shape}</span> {status.detail}</p>
		{/if}
	{/if}

	{#if camera && !noView && !cal}
		<p class="note"><span class="shape" aria-hidden="true">◌</span> Location ±25 m (ACHD) · not calibrated</p>
	{/if}

	<div class="actions">
		{#if camera && !noView}
			{#if cal}
				<button
					class="pill primary"
					disabled={blocked !== null}
					aria-describedby={blocked ? reasonId : undefined}
					onclick={() => camera && view && cameraHooks.lookThrough?.(camera, view)}
				>
					<Icon icon={LOOK} size={18} /> Look through
				</button>
				{#if photo}
					<button class="pill" aria-pressed={photo.isOn(id)} onclick={() => photo.set(id, !photo.isOn(id))}>
						<Icon icon={PHOTO_3D} size={18} /> 3D photo
					</button>
				{/if}
				<a class="pill secondary" href={calibrateHref}><Icon icon={CALIBRATE} size={18} /> Recalibrate</a>
			{:else}
				<a class="pill" href={calibrateHref}><Icon icon={CALIBRATE} size={18} /> Configure</a>
				<button class="pill" disabled aria-describedby={reasonId}><Icon icon={LOOK} size={18} /> Look through</button>
			{/if}
		{/if}
		<button class="pill" disabled={!camera} onclick={flyTo}><Icon icon={FLY_TO} size={18} /> Fly to</button>
	</div>
	{#if camera && !noView && blocked}
		<p class="reason" id={reasonId}><span aria-hidden="true">◌</span> {blocked}</p>
	{/if}
</div>

<style>
	.cam {
		display: flex;
		flex-direction: column;
	}
	.views {
		display: flex;
		gap: 4px;
		padding: 6px 8px;
		overflow-x: auto;
	}
	.view {
		min-height: 28px;
		padding: 2px 10px;
		border: 2px solid var(--panel-edge);
		border-radius: 999px;
		background: var(--panel);
		color: var(--ink);
		font: 600 12px var(--font-body);
		cursor: pointer;
	}
	.view[aria-pressed='true'] {
		border-color: var(--ink);
		background: var(--ink);
		color: var(--panel);
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
	.credit {
		color: var(--ink-soft);
		font-size: 11px;
	}
	.note {
		margin: 6px 10px 0;
		color: var(--ink);
		font-size: 13px;
		line-height: 1.35;
	}
	.note.bad {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
	}
	.shape {
		font-size: 11px;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		padding: 8px 28px 8px 10px;
	}
	.actions :global(.pill) {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		text-decoration: none;
	}
	.actions a.secondary {
		border-color: var(--panel-edge);
		background: var(--panel);
	}
	.actions :global(.pill[disabled]) {
		cursor: not-allowed;
		opacity: 0.55;
	}
	.reason {
		margin: -4px 28px 8px 10px;
		color: var(--ink-soft);
		font-size: 12px;
	}
</style>
