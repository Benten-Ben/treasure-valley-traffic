<script lang="ts">
	import { afterNavigate, goto, replaceState } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount, untrack } from 'svelte';
	import { getAppCtx } from '#lib/app/context.js';
	import { groundHeight, MIN_PAIRS, project, solve, type LngLatZ, type Pixel } from '#lib/calibration/solver.js';
	import type { SavedFrame } from '#lib/contracts/live.js';
	import Icon from '#lib/ui/Icon.svelte';
	import { ESC, onEscape, register } from '#lib/ui/keys.js';
	import { slots } from '#lib/ui/slots.svelte.js';
	import { viewLabel, type CameraDetail, type CameraDetailView } from '../detail.js';
	import { formatAge } from '../freshness.js';
	import { LOOK } from '../icons.js';
	import type { CamerasModule } from '../index.svelte.js';
	import { liveOf } from '../live.svelte.js';
	import { afterSave, type Saved } from './after.js';
	import CalibrateBanner from './CalibrateBanner.svelte';
	import {
		aimAt,
		clearDraft,
		compass,
		complete,
		frameChoice,
		moveGround,
		movePixel,
		nextStep,
		pendingIndex,
		placeGround,
		placePixel,
		quality,
		readDraft,
		removePair,
		rescalePairs,
		residualMark,
		sameWork,
		Undo,
		writeDraft,
		type DraftPair,
		type RefFrame
	} from './draft.js';
	import { REMOVE, SAVE, UNDO, CANCEL } from './icons.js';
	import { calibrateKey } from './keys.js';
	import LiveInset from './LiveInset.svelte';
	import { CalibrateMap, type Aim } from './mapside.js';
	import ReferenceFrame from './ReferenceFrame.svelte';
	import { calibrate } from './state.svelte.js';

	/**
	 * Calibrate mode's panel (docs/14 §14.6, "Calibrating on the map"; WP14),
	 * over the one shared map. `/calibrate/[id]?view=` renders only this.
	 *
	 * - **Entering and leaving:** see mapside.ts. Browser Back leaves, Forward
	 *   re-enters, Esc leaves; the draft is kept each time, and a reload
	 *   resumes it. Cancel asks first when the pairs changed.
	 * - **The panel** (docked left at 45%, on screens 900 px wide and more;
	 *   the map's left padding is its width): the frozen reference frame (zoom
	 *   and pan), the Live inset with "Use this frame", Blink and New frame,
	 *   the numbered pairs and the live solve (height, heading, tilt, field of
	 *   view, each pair's error, RMS), Check alignment (look-through with the
	 *   unsaved pose), the drape toggle, and Save.
	 * - **Keys:** Ctrl+Z undoes, Delete removes the selected pair, Ctrl+S
	 *   saves (Cmd on a Mac).
	 * - **Save** posts the calibration, refreshes the camera data, restores the
	 *   snapshot, reopens the window and offers "Look through to check".
	 * - **The first frame** of a new calibration is the newest picture (the
	 *   server's choice: the archive's when it's under 2 minutes old, else the
	 *   live fetcher's), kept at once; whatever is shown is what's saved.
	 * - Under 900 px wide: "Calibration needs a larger screen".
	 */
	let { camera, viewId }: { camera: CameraDetail; viewId: number | null } = $props();
	const app = getAppCtx();
	const feed = liveOf(app);
	const cam = untrack(() => camera);

	// --- the screen ------------------------------------------------------------------------

	const WIDE = '(min-width: 900px)';
	let wide = $state(typeof matchMedia === 'undefined' ? true : matchMedia(WIDE).matches);
	$effect(() => {
		if (typeof matchMedia === 'undefined') return;
		const m = matchMedia(WIDE);
		const sync = () => (wide = m.matches);
		m.addEventListener('change', sync);
		return () => m.removeEventListener('change', sync);
	});

	// --- the view and its work -------------------------------------------------------------------

	const usable = cam.views.filter((v) => v.imageId !== null);
	let viewIdx = $state(Math.max(0, usable.findIndex((v) => v.id === untrack(() => viewId))));
	const view = $derived<CameraDetailView | null>(usable[viewIdx] ?? null);

	type Work = { pairs: DraftPair[]; frame: RefFrame | null };
	let frame = $state.raw<RefFrame | null>(null);
	let pairs = $state.raw<DraftPair[]>([]);
	let selected = $state<number | null>(null);
	/** What this view's work started from: its saved calibration, or (a new one) the first frame. */
	let base = $state.raw<Work & { id: number | null }>({ pairs: [], frame: null, id: null });
	/** When the resumed draft was last changed (epoch ms), or null when this isn't a resumed draft. */
	let resumed = $state<number | null>(null);
	const undo = new Undo<Work>();
	let undoable = $state(0);
	let busy = $state<string | null>(null);
	let message = $state<{ kind: 'ok' | 'problem'; text: string } | null>(null);
	let confirming = $state(false);
	let showDrape = $state(true);
	let blink = $state(false);
	let checking = $state(false);

	const done = $derived(complete(pairs));
	const size = $derived(frame ? { width: frame.width, height: frame.height } : null);
	const solution = $derived(size && done.length >= MIN_PAIRS ? solve(done, size, cam.pole) : null);
	const groundZ = $derived(done.length ? groundHeight(done) : null);
	const dirty = $derived(!sameWork({ pairs, frame }, base));
	const fit = $derived(solution ? quality(solution.rms) : null);
	const step = $derived(nextStep(pairs));
	/** Per pair: its error and where the solved camera puts its ground point. */
	const errors = $derived.by(() => {
		const out: { residual: number | null; projected: Pixel | null }[] = pairs.map(() => ({ residual: null, projected: null }));
		if (!solution || !size) return out;
		let k = 0;
		pairs.forEach((p, i) => {
			if (!p.pixel || !p.ground) return;
			out[i] = { residual: solution.residuals[k++] ?? null, projected: project(solution.pose, size, p.ground) };
		});
		return out;
	});

	/** Start (or resume) work on a view: its draft, else its saved calibration, else a new frame. */
	function start(v: CameraDetailView) {
		const cal = v.calibration;
		const calFrame: RefFrame | null = cal?.frame
			? { frame: cal.frame, url: `/frames/${cal.frame}`, width: cal.imageWidth, height: cal.imageHeight, capturedAt: cal.createdAt }
			: null;
		base = { id: cal?.id ?? null, frame: calFrame, pairs: cal ? cal.pairs.map((p) => ({ pixel: p.pixel, ground: p.ground })) : [] };
		undo.clear();
		undoable = 0;
		selected = null;
		confirming = false;
		blink = false;
		message = null;
		const d = readDraft(v.id, cam.id);
		if (d) {
			frame = d.frame;
			pairs = d.pairs;
			resumed = d.savedAt;
		} else {
			frame = base.frame;
			pairs = base.pairs;
			resumed = null;
		}
		if (!frame) void newFrame(true);
	}

	let started: number | null = null;
	$effect(() => {
		const v = view;
		if (!v || v.id === started) return;
		started = v.id;
		untrack(() => start(v));
	});

	/** Keep the draft in step: written on every change, removed when it's back to where it started. */
	function persist() {
		const v = view;
		if (!v) return;
		if (sameWork({ pairs, frame }, base)) clearDraft(v.id);
		else writeDraft({ v: 1, cameraId: cam.id, viewId: v.id, frame, pairs, base: base.id, savedAt: Date.now() });
	}

	function change(next: Partial<Work>) {
		undo.push({ pairs, frame });
		undoable = undo.size;
		if (next.pairs) pairs = next.pairs;
		if (next.frame !== undefined) frame = next.frame;
		confirming = false;
		persist();
	}

	function undoLast() {
		const s = undo.pop();
		undoable = undo.size;
		if (!s) return;
		pairs = s.pairs;
		frame = s.frame;
		selected = null;
		persist();
	}

	function removeAt(i: number) {
		if (i < 0 || i >= pairs.length) return;
		change({ pairs: removePair(pairs, i) });
		selected = null;
	}

	function removeSelected() {
		const i = selected ?? pendingIndex(pairs);
		if (i !== -1 && i !== null) removeAt(i);
	}

	function onPlace(px: Pixel) {
		const r = placePixel(pairs, px);
		change({ pairs: r.pairs });
		selected = r.index;
		message = null;
	}

	function onGround(g: LngLatZ | null, why?: string) {
		if (!g) {
			message = { kind: 'problem', text: why ?? 'No ground height here.' };
			return;
		}
		const r = placeGround(pairs, g);
		change({ pairs: r.pairs });
		selected = r.index;
		message = null;
	}

	/** Start over from the saved calibration (or a new frame), dropping the draft. */
	function discardDraft() {
		const v = view;
		if (!v) return;
		clearDraft(v.id);
		started = null;
		start(v);
		started = v.id;
		if (mapSide.entered) mapSide.aim(aimFor(), padding());
	}

	// --- frames ----------------------------------------------------------------------------

	const live = $derived(view ? (feed.views[view.id] ?? null) : null);
	let now = $state(Date.now());
	const liveAge = $derived(live?.frame ? feed.ageOf(live.frame, now) : null);

	/** Make a kept frame the reference; the pairs' image points carry over when the picture's shape allows. */
	function setReference(saved: SavedFrame, note: string, initial = false) {
		const ref: RefFrame = { frame: saved.frame, url: saved.url, width: saved.width, height: saved.height, capturedAt: saved.capturedAt };
		if (initial) {
			base = { ...base, frame: ref };
			frame = ref;
			persist();
			return;
		}
		let next = pairs;
		let text = note;
		if (frame && (frame.width !== ref.width || frame.height !== ref.height)) {
			const scaled = rescalePairs(pairs, frame, ref);
			if (scaled) {
				next = scaled;
				if (pairs.some((p) => p.pixel)) text += ` The image points were scaled from ${frame.width}×${frame.height}: check them.`;
			} else {
				next = [];
				text += ' The picture has another shape, so the pairs were cleared (Ctrl+Z brings them back with the old frame).';
			}
		}
		change({ frame: ref, pairs: next });
		blink = false;
		message = { kind: 'ok', text };
	}

	async function postFrame(body: unknown): Promise<SavedFrame> {
		const v = view!;
		const res = await fetch(`/api/views/${v.id}/frame`, {
			method: 'POST',
			...(body === null ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
		});
		if (!res.ok) {
			const why = (await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`;
			throw Object.assign(new Error(why), { status: res.status });
		}
		return res.json();
	}

	/** "Use this frame": keep exactly the live picture shown in the inset. */
	async function useThisFrame() {
		const f = live?.frame;
		if (!f || !view || busy) return;
		const age = liveAge;
		busy = 'Keeping this picture as the reference…';
		message = null;
		try {
			const saved = await postFrame(frameChoice(f));
			setReference(saved, `Now using the live picture${age === null ? '' : ` seen ${formatAge(age)} ago`} as the reference.`);
		} catch (e) {
			const status = (e as { status?: number }).status;
			message =
				status === 410
					? { kind: 'problem', text: `That picture is gone from the server (${(e as Error).message}). Pick the current frame again.` }
					: { kind: 'problem', text: `Couldn’t keep that picture: ${(e as Error).message}` };
		} finally {
			busy = null;
		}
	}

	/** "New frame" (and a new calibration's first): the server keeps its newest picture of this view. */
	async function newFrame(initial = false) {
		if (!view || (busy && !initial)) return;
		busy = 'Fetching the camera’s newest picture…';
		if (!initial) message = null;
		try {
			const saved = await postFrame(null);
			setReference(saved, 'Now using the newest picture as the reference.', initial && !frame);
		} catch (e) {
			message = { kind: 'problem', text: `Couldn’t get a picture: ${(e as Error).message}` };
		} finally {
			busy = null;
		}
	}

	// --- the map side ------------------------------------------------------------------------------

	let panel = $state<HTMLElement | null>(null);
	let entered = $state(false);
	let gone = false;
	let after: Saved | null = null;

	const mapSide = new CalibrateMap(app, {
		cameraId: cam.id,
		viewId: untrack(() => viewId) ?? usable[0]?.id ?? 0,
		name: cam.name,
		pole: cam.pole,
		onGround,
		onPick: (i) => (selected = i),
		onMoveGround: (i, g) => change({ pairs: moveGround(pairs, i, g) })
	});

	/** The map's padding: the docked panel's side of the screen isn't map. */
	function padding() {
		const r = panel?.getBoundingClientRect();
		return { top: 0, right: 0, bottom: 0, left: r ? Math.round(r.right) : 0 };
	}

	/** Where to look (draft.ts's aimAt): the worked footprint, facing the solved heading, or the pole facing north. */
	function aimFor(): Aim {
		const heading = solution?.pose.heading ?? view?.calibration?.pose.heading ?? null;
		return aimAt(cam.pole, pairs, heading);
	}

	let undoMode: (() => void)[] = [];

	function enterMode() {
		if (entered || gone || !wide || !view) return;
		if (!mapSide.enter(aimFor(), padding())) return;
		entered = true;
		undoMode.push(slots.setBanner('calibrate', CalibrateBanner));
		undoMode.push(
			onEscape(ESC.calibrate, () => {
				if (app.modes.current !== 'calibrate') return false;
				// Cancel's question first, like a popover; then leave, keeping the draft.
				if (confirming) confirming = false;
				else leave();
				return true;
			})
		);
		// Listed in Help; the keys themselves are handled below (the registry ignores Ctrl and Cmd).
		const help = (id: string, label: string, description: string) => ({ id, codes: [], label, description, group: 'Calibrate', modes: ['calibrate'] as const, run: () => false });
		undoMode.push(
			register([
				help('calibrate-undo', 'Ctrl+Z', 'Undo the last change to the pairs or frame'),
				help('calibrate-remove', 'Delete', 'Remove the selected pair'),
				help('calibrate-save', 'Ctrl+S', 'Save the calibration')
			])
		);
	}

	function exitMode() {
		for (const f of undoMode.splice(0)) f();
		if (!entered) return;
		entered = false;
		blink = false;
		mapSide.leave();
	}

	// Enter once the map's style is there (and on a wide screen); leave if the screen gets narrow.
	let styled = $state(false);
	onMount(() => {
		app.track(
			app.styleReady
				.then(() => {
					if (!gone) styled = true;
				})
				.catch(() => {})
		);
		const tick = setInterval(() => (now = Date.now()), 1000);
		return () => {
			gone = true;
			clearInterval(tick);
			exitMode();
			mapSide.destroy();
			const s = after;
			after = null;
			// Once the snapshot is back (and the cameras module has seen Explore again).
			if (s) setTimeout(() => afterSave(app, s), 0);
		};
	});

	// Keep the map's left padding equal to the panel's size.
	$effect(() => {
		const el = panel;
		if (!el) return;
		const ro = new ResizeObserver(() => {
			if (entered) mapSide.setPadding(padding());
		});
		ro.observe(el);
		return () => ro.disconnect();
	});

	$effect(() => {
		const want = styled && wide && !!view;
		untrack(() => {
			if (want && !entered) enterMode();
			else if (!want && entered) exitMode();
		});
	});

	// Another view of the camera: aim again (the map is already in the mode).
	let aimedAt: number | null = null;
	$effect(() => {
		const v = view;
		const on = entered;
		if (!on || !v) return;
		if (aimedAt === null) aimedAt = v.id;
		else if (aimedAt !== v.id) {
			aimedAt = v.id;
			untrack(() => mapSide.aim(aimFor(), padding()));
		}
	});

	// The live picture of the view being calibrated, while in the mode.
	$effect(() => {
		const v = view;
		if (!entered || !v || v.imageId === null) return;
		return feed.watch([v.id]);
	});

	// The map follows the work.
	$effect(() => {
		const p = pairs;
		const sel = selected;
		if (entered) untrack(() => mapSide.setPairs(p, sel));
	});
	$effect(() => {
		const s = solution;
		const sz = size;
		const z = groundZ;
		if (!entered) return;
		untrack(() => mapSide.setSolved(s && sz && z !== null ? { pose: s.pose, size: sz, groundZ: z } : null));
	});
	$effect(() => {
		const s = solution;
		const sz = size;
		const z = groundZ;
		const f = frame;
		const on = showDrape;
		if (!entered) return;
		untrack(() => mapSide.setDrape(on && s && sz && f && z !== null ? { pose: s.pose, size: sz, groundZ: z, url: f.url } : null));
	});

	// Look-through over the calibration (Check alignment): the panel and the map side step aside.
	const looking = $derived(entered && app.modes.current === 'look');
	$effect(() => {
		const away = looking;
		if (entered) untrack(() => mapSide.setHidden(away));
	});

	// The banner's words.
	$effect(() => {
		calibrate.name = cam.name;
		calibrate.step = step;
		calibrate.pairs = done.length;
		calibrate.rms = solution?.rms ?? null;
		calibrate.draft = dirty;
	});

	// --- leaving -----------------------------------------------------------------------------------

	// Leave goes Back when the entry before this one is the map; otherwise to the map.
	let cameFromMap = false;
	afterNavigate((nav) => {
		if (nav.from?.route.id === nav.to?.route.id && nav.from?.params?.id === nav.to?.params?.id) return;
		const fromMap = nav.from?.route.id === '/(map)';
		cameFromMap = fromMap && (nav.type === 'link' || nav.type === 'goto' || (nav.type === 'popstate' && (nav.delta ?? 0) > 0));
	});

	let leaving = false;
	function leave() {
		confirming = false;
		// Once: a second Back would go past the map.
		if (leaving) return;
		leaving = true;
		if (cameFromMap) history.back();
		else void goto('/');
	}

	/** Cancel: leave, asking first when the work changed. */
	function cancel() {
		if (dirty && !confirming) {
			confirming = true;
			return;
		}
		leave();
	}

	function discardAndLeave() {
		if (view) clearDraft(view.id);
		leave();
	}

	async function save() {
		const v = view;
		const s = solution;
		const f = frame;
		if (!v || !s || !f || busy) return;
		busy = 'Saving…';
		message = null;
		try {
			const res = await fetch(`/api/views/${v.id}/calibrations`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ pose: s.pose, pairs: done, imageWidth: f.width, imageHeight: f.height, frame: f.frame })
			});
			const body = await res.json().catch(() => null);
			if (!res.ok) throw new Error(body?.message ?? `HTTP ${res.status}`);
			clearDraft(v.id);
			base = { id: body.id, frame: f, pairs };
			after = { cameraId: cam.id, viewId: v.id, id: body.id, rms: body.rms, name: cam.name };
			app.notify('cameras');
			leave();
		} catch (e) {
			message = { kind: 'problem', text: `Not saved: ${(e as Error).message}` };
		} finally {
			busy = null;
		}
	}

	/** Check alignment: look through the camera at the unsaved pose (Step out comes back here). */
	async function checkAlignment() {
		const mod = cams;
		const s = solution;
		const v = view;
		if (!mod || !s || !size || !v || groundZ === null || checking) return;
		checking = true;
		message = null;
		try {
			const ok = await mod.lookThrough(cam.id, v.id, { draft: { pose: s.pose, size, groundZ, frame: frame?.frame ?? null } });
			if (!ok) message = { kind: 'problem', text: 'Couldn’t look through at this pose (see the message below the map).' };
		} finally {
			checking = false;
		}
	}

	const cams = $derived(app.layers?.modules.cameras as CamerasModule | undefined);

	function chooseView(i: number) {
		viewIdx = i;
		const v = usable[i];
		if (!v) return;
		const url = new URL(page.url.href);
		url.searchParams.set('view', String(v.id));
		replaceState(url, page.state);
	}

	// --- keys ----------------------------------------------------------------------------------------

	function onkeydown(e: KeyboardEvent) {
		if (e.defaultPrevented || !entered || app.modes.current !== 'calibrate') return;
		const k = calibrateKey(e);
		if (!k) return;
		e.preventDefault();
		if (k === 'undo') undoLast();
		else if (k === 'remove') removeSelected();
		else void save();
	}

	// --- the debug handle (tests and the console): `__tvtCalib` ---------------------------------------------

	onMount(() => {
		const handle = Object.freeze({
			state: () => ({
				cameraId: cam.id,
				viewId: view?.id ?? null,
				entered,
				mode: app.modes.current,
				frame,
				pairs,
				selected,
				dirty,
				resumed,
				busy,
				undo: undoable,
				solution: solution ? { pose: solution.pose, rms: solution.rms, residuals: solution.residuals } : null,
				groundZ,
				message: message?.text ?? null,
				map: mapSide.info()
			}),
			/** The true ground height the calibrator reads under a point now. */
			groundAt: (lng: number, lat: number) => mapSide.groundAt({ lng, lat })
		});
		Object.defineProperty(globalThis, '__tvtCalib', { value: handle, configurable: true, enumerable: false, writable: false });
		return () => {
			if ((globalThis as { __tvtCalib?: unknown }).__tvtCalib === handle) Reflect.deleteProperty(globalThis, '__tvtCalib');
		};
	});

	const keptAt = $derived.by(() => {
		const t = frame?.capturedAt ? new Date(frame.capturedAt) : null;
		if (!t || Number.isNaN(t.getTime())) return null;
		return t.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
	});
	const resumedAt = $derived(resumed === null ? null : new Date(resumed).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }));
	const hint = $derived(
		step === 'map'
			? 'Now click the same spot on the map →'
			: step === 'image'
				? '← Now click the same spot in this picture'
				: 'Click a sharp ground feature in the picture (a stop-bar end, a lane-line corner, a crosswalk corner), then the same spot on the map.'
	);
</script>

<svelte:window {onkeydown} />

{#if !wide}
	<div class="narrow card" role="alert">
		<h1>Calibration needs a larger screen</h1>
		<p>Calibrating puts the camera's picture and the map side by side, which needs a window at least 900 px wide.</p>
		<button class="pill primary" onclick={leave}>Back to the map</button>
	</div>
{:else}
	<div class="calibrator card" class:away={looking} bind:this={panel} role="region" aria-label="Calibrate {cam.name}">
		<header>
			<button class="back" onclick={cancel} aria-label="Cancel: leave calibration" title="Leave (Esc leaves too, keeping the draft)">
				<Icon icon={CANCEL} size={18} /> Cancel
			</button>
			<h1>{cam.name}</h1>
			{#if usable.length > 1}
				<select value={viewIdx} aria-label="Camera view" onchange={(e) => chooseView(Number((e.currentTarget as HTMLSelectElement).value))}>
					{#each usable as v, i (v.id)}<option value={i}>{viewLabel(v, i)}</option>{/each}
				</select>
			{/if}
			<span class="sub num">{#if cam.achdCamId}ACHD #{cam.achdCamId} · {/if}511 image {view?.imageId ?? '—'}</span>
		</header>

		{#if confirming}
			<div class="confirm" role="alertdialog" aria-label="Unsaved changes" aria-describedby="calib-confirm-text">
				<p id="calib-confirm-text"><span aria-hidden="true">▲</span> The pairs or the frame changed since {base.id ? 'the saved calibration' : 'you started'}.</p>
				<div class="row">
					<button class="pill" onclick={discardAndLeave}>Discard the changes</button>
					<button class="pill" onclick={leave}>Keep the draft and leave</button>
					<button class="pill primary" onclick={() => (confirming = false)}>Stay</button>
				</div>
			</div>
		{/if}

		{#if !view}
			<p class="note"><span aria-hidden="true">■</span> Not on 511 Idaho: this camera has no picture to calibrate.</p>
		{:else}
			{#if resumedAt}
				<p class="note draft">
					<span aria-hidden="true">●</span> Your unsaved draft from {resumedAt}, resumed.
					<button class="link" onclick={discardDraft}>{base.id ? 'Back to the saved calibration' : 'Start over'}</button>
				</p>
			{/if}

			<section class="frame-pane" aria-label="Reference frame">
				{#if frame}
					<p class="caption">
						<b>Reference frame</b> <span>(frozen: the pairs are clicked on it)</span>{#if keptAt}<span>· kept {keptAt}</span>{/if}
						<span class="num">{frame.width}×{frame.height}</span>
					</p>
					<ReferenceFrame
						{frame}
						live={live?.frame ?? null}
						{blink}
						{pairs}
						{selected}
						projected={errors.map((e) => e.projected)}
						residuals={errors.map((e) => e.residual)}
						onplace={onPlace}
						onselect={(i) => (selected = i)}
						onmove={(i, px) => change({ pairs: movePixel(pairs, i, px) })}
						onrefused={(why) => (message = { kind: 'problem', text: why })}
					/>
					<p class="step" class:next={step !== 'either'}>{hint}</p>
				{:else}
					<p class="note">{busy ?? 'No reference frame yet.'}</p>
				{/if}
			</section>

			<LiveInset {live} age={liveAge} refSize={size} bind:blink busy={!!busy} onuse={useThisFrame} onnew={() => void newFrame()} />

			{#if app.map && !app.manifest?.terrain}
				<p class="warn"><span aria-hidden="true">▲</span> Terrain isn’t built yet, so ground heights aren’t available.</p>
			{/if}

			<div class="work">
				<section class="pairs-pane" aria-label="Point pairs">
					<h2>
						Point pairs <span class="num">{done.length}</span>
						<button class="pill tiny" onclick={undoLast} disabled={!undoable} title="Undo (Ctrl+Z)"><Icon icon={UNDO} size={14} /> Undo</button>
					</h2>
					{#if pairs.length === 0}
						<p class="muted">Aim for 6 or more, spread across the picture: near and far, left and right.</p>
					{/if}
					<ol class="pairs">
						{#each pairs as p, i (i)}
							{@const r = errors[i]?.residual ?? null}
							<li class:selected={i === selected}>
								<button class="n" aria-pressed={i === selected} aria-label="Select pair {i + 1}" onclick={() => (selected = selected === i ? null : i)}>{i + 1}</button>
								<span class="num">{p.pixel ? `${p.pixel[0].toFixed(0)}, ${p.pixel[1].toFixed(0)}` : 'picture…'}</span>
								<span class="num">{p.ground ? `${p.ground[2].toFixed(1)} m` : 'map…'}</span>
								{#if r !== null}
									{@const m = residualMark(r)}
									<span class="res {m.cls} num"><span aria-hidden="true">{m.shape}</span> {r.toFixed(1)} px</span>
								{:else}
									<span></span>
								{/if}
								<button class="x" aria-label="Remove pair {i + 1}" title="Remove (Delete)" onclick={() => removeAt(i)}><Icon icon={REMOVE} size={15} /></button>
							</li>
						{/each}
					</ol>
				</section>

				<section class="solve" aria-label="Camera">
					<h2>Camera</h2>
					{#if solution && fit}
						<dl class="pose num">
							<dt>Height</dt><dd>{solution.heightAboveGround.toFixed(1)} m above the road</dd>
							<dt>Facing</dt><dd>{solution.pose.heading.toFixed(1)}° ({compass(solution.pose.heading)})</dd>
							<dt>Tilt</dt><dd>{solution.pose.tilt.toFixed(1)}° down{Math.abs(solution.pose.roll) > 0.5 ? `, roll ${solution.pose.roll.toFixed(1)}°` : ''}</dd>
							<dt>View</dt><dd>{solution.hfov.toFixed(0)}° × {solution.pose.vfov.toFixed(0)}°</dd>
							<dt>Fit</dt><dd class="q {fit.word}"><span aria-hidden="true">{residualMark(solution.rms).shape}</span> {solution.rms.toFixed(2)} px, {fit.text}</dd>
						</dl>
					{:else}
						<p class="muted">Solves by itself once there are {MIN_PAIRS} complete pairs ({Math.max(0, MIN_PAIRS - done.length)} to go).</p>
					{/if}
					<label class="toggle"><input type="checkbox" bind:checked={showDrape} /> Drape the reference frame on the map (a check)</label>
				</section>
			</div>

			<footer class="actions">
				<div class="buttons">
				<button class="pill" onclick={checkAlignment} disabled={!solution || !cams || checking} title="Look through the camera at this unsaved pose">
					<Icon icon={LOOK} size={18} /> Check alignment
				</button>
				<button class="pill primary" onclick={save} disabled={!solution || !!busy} title="Save (Ctrl+S)">
					<Icon icon={SAVE} size={18} /> Save calibration
				</button>
				</div>
				{#if message}
					<p class="msg {message.kind}" role={message.kind === 'problem' ? 'alert' : 'status'}>
						<span aria-hidden="true">{message.kind === 'problem' ? '▲' : '●'}</span> {message.text}
					</p>
				{/if}
				{#if busy && frame}<p class="muted">{busy}</p>{/if}
				<p class="keys">
					<kbd>Ctrl</kbd>+<kbd>Z</kbd> undo · <kbd>Delete</kbd> removes the selected pair · <kbd>Ctrl</kbd>+<kbd>S</kbd> saves · <kbd>Esc</kbd> leaves, keeping the draft
				</p>
			</footer>
		{/if}
	</div>
{/if}

<style>
	/* Docked left at 45%; the map's left padding follows it. */
	.calibrator {
		position: absolute;
		container: calibrator / inline-size;
		scrollbar-width: thin;
		top: 10px;
		left: 10px;
		bottom: 10px;
		z-index: 20;
		width: 45%;
		box-sizing: border-box;
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 10px 14px 12px;
		overflow: auto;
	}
	.calibrator.away {
		display: none;
	}
	.narrow {
		position: absolute;
		top: 84px;
		left: 16px;
		right: 16px;
		z-index: 60;
		max-width: 420px;
		margin: 0 auto;
		padding: 14px 16px;
	}
	.narrow h1 {
		margin: 0 0 6px;
		font: 600 19px var(--font-display);
	}
	.narrow p {
		margin: 0 0 12px;
		font-size: 14px;
	}
	header,
	section,
	.work,
	.actions,
	.warn,
	.note,
	.confirm {
		flex-shrink: 0;
	}
	header {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: 4px 12px;
	}
	.back {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		border: 0;
		background: none;
		padding: 0;
		color: var(--ink);
		font: 600 15px var(--font-body);
		cursor: pointer;
		align-self: center;
	}
	h1 {
		margin: 0;
		font: 600 20px var(--font-display);
	}
	select {
		font: 600 13px var(--font-body);
	}
	.sub {
		color: var(--ink-soft);
		font-size: 12px;
	}
	.confirm {
		padding: 10px 12px;
		border: 2px solid var(--ink);
		border-radius: 12px;
		background: var(--panel);
	}
	.confirm p {
		margin: 0 0 8px;
		font-size: 14px;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.note {
		margin: 0;
		font-size: 13px;
	}
	.note.draft {
		padding: 6px 10px;
		border-radius: 10px;
		background: var(--ground);
	}
	button.link {
		border: 0;
		background: none;
		padding: 0;
		color: var(--ink);
		font: 600 13px var(--font-body);
		text-decoration: underline;
		cursor: pointer;
	}
	.frame-pane {
		display: flex;
		flex-direction: column;
	}
	.caption {
		display: flex;
		flex-wrap: wrap;
		gap: 0 6px;
		margin: 0 0 4px;
		color: var(--ink-soft);
		font-size: 12px;
	}
	.caption b {
		color: var(--ink);
	}
	.caption .num {
		margin-left: auto;
	}
	.step {
		margin: 6px 0 0;
		font-size: 14px;
		color: var(--ink);
	}
	.step.next {
		font-weight: 600;
	}
	.warn {
		margin: 0;
		padding: 6px 10px;
		border-radius: 8px;
		background: var(--panel);
		border: 2px solid var(--alert);
		font-size: 13px;
	}
	.work {
		display: grid;
		grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
		gap: 14px;
	}
	/* Pairs and solve side by side only when the panel is wide enough (it's 45% of the screen). */
	@container calibrator (max-width: 700px) {
		.work {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	h2 {
		display: flex;
		align-items: center;
		gap: 8px;
		margin: 0 0 6px;
		font: 600 16px var(--font-display);
	}
	.pill.tiny {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		margin-left: auto;
		padding: 2px 9px;
		font-size: 12px;
	}
	.muted {
		color: var(--ink-soft);
		margin: 4px 0;
		font-size: 13px;
	}
	.pairs {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 2px;
	}
	.pairs li {
		display: grid;
		grid-template-columns: 26px 84px 68px 1fr 26px;
		white-space: nowrap;
		align-items: center;
		gap: 6px;
		font-size: 13px;
		border-radius: 8px;
	}
	.pairs li.selected {
		background: var(--ground);
		box-shadow: inset 0 0 0 2px var(--ink);
	}
	.n {
		display: inline-grid;
		place-items: center;
		width: 22px;
		height: 22px;
		padding: 0;
		border: 2px solid #fff;
		border-radius: 50%;
		background: var(--accent);
		color: var(--ink);
		font: 700 11px var(--font-body);
		cursor: pointer;
	}
	.n[aria-pressed='true'] {
		border-color: var(--ink);
	}
	.x {
		display: inline-grid;
		place-items: center;
		border: 0;
		background: none;
		padding: 2px;
		cursor: pointer;
		color: var(--ink-soft);
	}
	.res.good :first-child { color: var(--accent-2); }
	.res.fair :first-child { color: #b07400; }
	.res.bad :first-child { color: var(--alert); }
	.pose {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 2px 12px;
		margin: 0;
		font-size: 13px;
	}
	.pose dt {
		color: var(--ink-soft);
		font-family: var(--font-body);
	}
	.pose dd {
		margin: 0;
	}
	.q.great :first-child,
	.q.good :first-child { color: var(--accent-2); }
	.q.rough :first-child { color: #b07400; }
	.q.poor :first-child { color: var(--alert); }
	.toggle {
		display: block;
		margin-top: 8px;
		font-size: 13px;
	}
	/* The actions stay in reach however long the pairs list grows. */
	.actions {
		position: sticky;
		bottom: -12px;
		z-index: 1;
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin: 0 -14px -12px;
		padding: 8px 14px 10px;
		border-top: 2px solid var(--panel-edge);
		background: var(--panel);
	}
	.buttons {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.actions :global(.pill) {
		display: inline-flex;
		align-items: center;
		gap: 5px;
	}
	.msg {
		margin: 0;
		font-size: 13px;
	}
	.msg.ok span { color: var(--accent-2); }
	.msg.problem span { color: var(--alert); }
	.keys {
		margin: 0;
		color: var(--ink-soft);
		font-size: 12px;
	}
	kbd {
		padding: 0 4px;
		border: 1.5px solid var(--panel-edge);
		border-radius: 4px;
		font: 600 11px var(--font-mono);
		color: var(--ink);
	}
	:global(.calib-pair) {
		width: 24px;
		height: 24px;
		padding: 0;
		border-radius: 50%;
		background: var(--accent);
		border: 2px solid #fff;
		display: grid;
		place-items: center;
		font: 700 11px var(--font-body);
		color: var(--ink);
		box-shadow: 0 1px 4px rgb(0 0 0 / 0.4);
		cursor: grab;
	}
	:global(.calib-pair.pending) {
		border-style: dashed;
		border-color: var(--ink);
	}
	:global(.calib-pair.selected) {
		border-color: var(--ink);
		box-shadow:
			0 0 0 3px var(--panel),
			0 1px 4px rgb(0 0 0 / 0.4);
	}
	:global(.calib-pole) {
		width: 14px;
		height: 14px;
		border-radius: 3px;
		background: var(--ink);
		border: 2px solid #fff;
		box-shadow: 0 1px 4px rgb(0 0 0 / 0.4);
		pointer-events: none;
	}
</style>
