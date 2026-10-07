import type { Map, PaddingOptions } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import {
	axisDistance,
	deviation,
	easeInOut,
	eyeOf,
	eyePose,
	interpolate,
	letterbox,
	mapFov,
	metresBetween,
	nearMetres,
	photoCrop,
	framedCrop,
	photoDistance,
	photoPlane,
	planeApex,
	groundMetres,
	type Box,
	type Crop,
	type EyePose,
	type MapCamera,
	type PhotoPlane
} from '#lib/calibration/frustum.js';
import type { ImageSize, Pose } from '#lib/calibration/solver.js';
import type { LiveView } from '#lib/contracts/live.js';
import type { Scene, ScenePhoto } from '#lib/scene/index.js';
import type { ViewSnapshot } from '#lib/state/view.svelte.js';
import { toasts } from '#lib/ui/toasts.svelte.js';
import type { Calibration } from './cameras.js';
import type { LiveFeed } from './live.svelte.js';
import { look } from './look.svelte.js';

/**
 * Look-through (docs/14 §14.6 "Look through"; WP13): the map's own camera at
 * a calibrated camera's pose, with its picture drawn as a plane inside the
 * view cone, so the map and the picture line up.
 *
 * 1. **Save** the view: `modes.enter('look')` pushes the full snapshot (§14.3).
 * 2. **Terrain at true scale:** exaggeration 1 (poses are in true metres).
 * 3. **Limits:** max pitch 89, max zoom 24, no ground clamp, and padding 0
 *    (eased during the flight in).
 * 4. **Fit the picture:** letterboxed at its aspect, `h_img = min(0.92·H,
 *    0.96·W·h/w)`, and the map's field of view `Vm = 2·atan(tan(Vc/2)·H/h_img)`,
 *    set before the camera options are worked out.
 * 5. **Place** with `calculateCameraOptionsFromCameraLngLatAltRotation`, then
 *    a second pass puts the centre on the terrain under the view axis without
 *    moving the eye, so restoring the clamp later doesn't jump.
 * 6. **Fly in** with our own 1.2 s animation-frame loop (the eye, with a 40 m
 *    arc on flights over 300 m; bearing, pitch, roll and field of view; the
 *    field of view set first each frame). A jump under reduced motion.
 * 7. **Check** the eye read back: within 0.1 m, or "Can't place the map
 *    camera at this pose" and out again. It's checked before flying too, in
 *    one synchronous place-read-restore (nothing is drawn in between).
 * 8. **Show** the plane at `d = max(2 m, 2 × near)` from the eye, at 85%
 *    opacity, over everything (no depth test), with the 40% ink vignette and
 *    the 2 px cream edge outside it (LookFrame.svelte). The camera's own model
 *    and cone are hidden.
 * 9. **HUD** (LookBanner.svelte): the slider, both clocks, ← and →, Step out.
 * 10. **Fade on user moves:** `e = max(Δangle/4°, |eye shift|/(0.08·D),
 *     |Δroll|/3°, |ln(fov ratio)|/0.15)`, opacity `clamp(1 − e) × slider`.
 *     After 300 ms at 0 it ends where the user is: pitch, zoom and field of
 *     view ease back within Explore's limits over 400 ms, the limits and the
 *     ground clamp come back without a jump, then the exaggeration eases back
 *     with the eye kept 10 m above the drawn ground.
 *
 * Esc or Step out fades the picture out (200 ms) and restores the snapshot
 * exactly, with `jumpTo` (a change from §14.6's "flies back", the same
 * choice Calibrate makes): a flight back passes through zooms in between,
 * where MapLibre asks again for the overscaled basemap and building tiles it
 * already had, and the round-trip target (§14.9) allows no tile loaded before
 * entering to be requested again on the way back.
 */
export const LOOK_GROUP = 'cameras-look';
export const FLY_MS = 1200;
export const PHOTO_OPACITY = 0.85;
/** The eye must read back within this, metres (step 7). */
export const READBACK_M = 0.1;
export const LOOK_LIMITS = { maxPitch: 89, maxZoom: 24 } as const;
/** Step out's fade of the picture before the view comes back, ms. */
export const OUT_MS = 200;
/** Ending in place (step 10). */
export const END = { pitch: 75, zoom: 22, fov: 36.87, ms: 400, zeroMs: 300, clearM: 10 } as const;

const ZERO: PaddingOptions = { top: 0, right: 0, bottom: 0, left: 0 };
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const lerpPad = (a: PaddingOptions, b: PaddingOptions, t: number): PaddingOptions => ({
	top: lerp(a.top ?? 0, b.top ?? 0, t),
	right: lerp(a.right ?? 0, b.right ?? 0, t),
	bottom: lerp(a.bottom ?? 0, b.bottom ?? 0, t),
	left: lerp(a.left ?? 0, b.left ?? 0, t)
});
const reducedMotion = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * The scene's photo planes draw a cream edge over the outer 1.2% of their
 * texture (PhotoBatch's `edge`). Look-through grows its crop by as much
 * (`framedCrop`), so the edge frames the picture instead of covering it.
 */
export const SCENE_PHOTO_EDGE = 0.012;

/** Every animation takes at least this many frames, however slow they come, so nothing ever jumps. */
export const MIN_STEPS = 8;

/**
 * An animation's progress (0–1) after `elapsed` of `ms`, at its `step`th
 * frame: by time, but never more than step/MIN_STEPS, so on a slow machine
 * it takes longer instead of skipping.
 */
export function progress(elapsed: number, ms: number, step: number): number {
	return Math.min(1, elapsed / ms, step / MIN_STEPS);
}

/** Where a crop of the picture lands in its letterbox. */
export function shownBox(box: Box, size: ImageSize, crop: Crop): Box {
	const k = box.height / size.height;
	return { x: box.x + crop.x * k, y: box.y + crop.y * k, width: crop.width * k, height: crop.height * k };
}

/** The canvas size MapLibre uses (it floors the container's). */
function canvasSize(map: Map): { w: number; h: number } {
	const c = map.getContainer();
	return { w: Math.floor(c.clientWidth) || 400, h: Math.floor(c.clientHeight) || 300 };
}

/** The map camera's public state. */
export function mapCamera(map: Map): MapCamera {
	const c = map.getCenter();
	return {
		center: [c.lng, c.lat],
		elevation: map.getCenterElevation(),
		zoom: map.getZoom(),
		pitch: map.getPitch(),
		bearing: map.getBearing(),
		fov: map.getVerticalFieldOfView(),
		height: canvasSize(map).h
	};
}

/** The map's eye and rotation now. */
export function eyeNow(map: Map): EyePose {
	const [lng, lat, alt] = eyeOf(mapCamera(map));
	return { lng, lat, alt, bearing: map.getBearing(), pitch: map.getPitch(), roll: map.getRoll(), fov: map.getVerticalFieldOfView() };
}

/** MapLibre's own idea of the eye (its transform is internal in 6.12), for the readback check's cross-check. */
export function internalEye(map: Map): [number, number, number] | null {
	const tr = (map as unknown as { _camera?: { transform?: { getCameraLngLat?(): { lng: number; lat: number }; getCameraAltitude?(): number } } })._camera?.transform;
	if (!tr?.getCameraLngLat || !tr.getCameraAltitude) return null;
	const ll = tr.getCameraLngLat();
	return [ll.lng, ll.lat, tr.getCameraAltitude()];
}

/**
 * Put the map's eye at a pose, without animation. The field of view first
 * (the zoom depends on it). With `ground`, a second pass moves the centre
 * onto the terrain under the view axis, keeping the eye where it is.
 */
export function placeEye(map: Map, e: EyePose, padding?: PaddingOptions, ground = false): void {
	if (Math.abs(map.getVerticalFieldOfView() - e.fov) > 1e-9) map.setVerticalFieldOfView(e.fov);
	const at = (): void => {
		const opts = map.calculateCameraOptionsFromCameraLngLatAltRotation([e.lng, e.lat], e.alt, e.bearing, e.pitch, e.roll);
		map.jumpTo(padding ? { ...opts, padding } : opts);
	};
	at();
	if (!ground || !map.getTerrain()) return;
	for (let pass = 0; pass < 2; pass++) {
		const c = map.getCenter();
		const g = map.queryTerrainElevation([c.lng, c.lat]);
		if (g === null || Math.abs(g - map.getCenterElevation()) < 0.01) break;
		// Both jumps happen before the next frame is drawn, so the in-between camera is never seen.
		map.jumpTo({ elevation: g });
		at();
	}
}

interface Target {
	cal: Calibration;
	pose: Pose;
	size: ImageSize;
	name: string;
	/** The letterbox on the canvas, the map's field of view, and the eye there. */
	box: Box;
	/** The part of the letterbox the plane covers (the vignette's hole). */
	shown: Box;
	eye: EyePose;
	/** D for the fade: (alt − ground)/sin(tilt). */
	D: number;
	crop: Crop;
	plane: PhotoPlane;
	/** The plane's distance from the eye, and the near distance it was worked out from. */
	d: number;
	near: number;
	photo: ScenePhoto;
	/** The picture shown (live frame sha, or 'ref' for the reference frame), and the one decoding. */
	sha: string | null;
	loading: string | null;
	unwatch: () => void;
}

interface Entry {
	snapshot: ViewSnapshot;
	keyboard: boolean;
	/** Calibrated views by distance from the first camera: ← and → walk this. */
	order: Calibration[];
}

/** One sample of the map camera during a transition (tests: "never jumps"). */
export interface TraceSample {
	t: number;
	phase: string;
	pitch: number;
	zoom: number;
	fov: number;
	exaggeration: number;
	eye: [number, number, number];
	/** The drawn ground under the eye. */
	ground: number | null;
}

/** How to look through: another pose for the saved calibration, or a whole draft one (WP14's Check alignment). */
export interface LookOptions {
	pose?: Pose;
	draft?: { pose: Pose; size: ImageSize; groundZ: number; frame?: string | null };
}

export interface LookSource {
	calibrations(): readonly Calibration[];
	nameOf(cameraId: number): string;
	/** Hide these cameras' 3D models (the one looked through). */
	exclude(ids: number[]): void;
}

export class LookThrough {
	#ctx: AppCtx;
	#map: Map;
	#scene: Scene;
	#feed: LiveFeed;
	#src: LookSource;
	#entry: Entry | null = null;
	#target: Target | null = null;
	#flight = 0;
	#busy = false;
	#zeroTimer: ReturnType<typeof setTimeout> | undefined;
	#views: Record<number, LiveView> = {};
	#trace: TraceSample[] | null = null;
	#cleanup: (() => void)[] = [];
	#destroyed = false;

	constructor(ctx: AppCtx, map: Map, scene: Scene, feed: LiveFeed, src: LookSource) {
		this.#ctx = ctx;
		this.#map = map;
		this.#scene = scene;
		this.#feed = feed;
		this.#src = src;
		scene.setPhotos(LOOK_GROUP, []);
		map.on('move', this.#onMove);
		map.on('resize', this.#onResize);
		this.#cleanup.push(() => {
			map.off('move', this.#onMove);
			map.off('resize', this.#onResize);
		});
		look.actions = {
			stepOut: () => void this.stepOut(),
			next: (dir) => void this.next(dir),
			setSlider: (v) => this.setSlider(v)
		};
	}

	get phase() {
		return look.phase;
	}

	// --- entering ------------------------------------------------------------------------------

	/**
	 * Look through a calibrated view (the first of a camera's when `viewId`
	 * isn't given). `pose` overrides the calibration's (Check alignment with an
	 * unsaved pose, and the registration tests). Resolves once it's looking,
	 * or false when it couldn't.
	 */
	async enter(cameraId: number, viewId?: number | null, o: LookOptions = {}): Promise<boolean> {
		const ctx = this.#ctx;
		const map = this.#map;
		// From Explore, or from Calibrate (Check alignment, WP14): the mode stack nests.
		if (this.#destroyed || look.phase !== 'off' || (ctx.modes.current !== 'explore' && ctx.modes.current !== 'calibrate')) return false;
		const cals = this.#src.calibrations();
		let cal = cals.find((c) => (viewId ? c.viewId === viewId : c.cameraId === cameraId));
		// An unsaved pose for a view with no saved calibration yet: the draft stands in for it.
		if (o.draft && viewId) cal = { calibrationId: -1, viewId, cameraId, pose: o.draft.pose, size: o.draft.size, groundZ: o.draft.groundZ, frame: o.draft.frame ?? cal?.frame ?? '' };
		if (!cal || cal.cameraId !== cameraId) {
			this.#tell('Look-through needs a calibration: configure this camera first');
			return false;
		}
		const sized = this.#sizeProblem(cal);
		if (sized) {
			this.#tell(sized);
			return false;
		}
		if (!this.#scene.ok) {
			this.#tell("Look-through needs the 3D view, which couldn't start here");
			return false;
		}
		map.stop();
		const keyboard = map.keyboard.isEnabled();
		const { snapshot } = ctx.modes.enter('look');
		this.#entry = { snapshot, keyboard, order: this.#orderFrom(cal, cals) };
		look.problem = null;
		look.phase = 'flying';
		map.keyboard.disable();
		// Step 2 and 3: true-scale terrain, look-through's limits, no ground clamp.
		ctx.setExaggeration(1);
		map.setMaxPitch(LOOK_LIMITS.maxPitch);
		map.setMaxZoom(LOOK_LIMITS.maxZoom);
		map.setCenterClampedToGround(false);
		return this.#flyTo(cal, o.pose ?? cal.pose);
	}

	/** Why a view's live picture can't be looked through (its size changed), or null. */
	#sizeProblem(cal: Calibration): string | null {
		const f = this.#feed.views[cal.viewId]?.frame;
		if (!f || (f.width === cal.size.width && f.height === cal.size.height)) return null;
		return `Image size changed (${cal.size.width}×${cal.size.height} → ${f.width}×${f.height}); recalibrate`;
	}

	/** ← and → order: every calibrated view, nearest the first camera first. */
	#orderFrom(first: Calibration, cals: readonly Calibration[]): Calibration[] {
		const at: [number, number] = [first.pose.lon, first.pose.lat];
		const rest = cals.filter((c) => c.viewId !== first.viewId && c.pose).sort((a, b) => groundMetres(at, [a.pose.lon, a.pose.lat]) - groundMetres(at, [b.pose.lon, b.pose.lat]));
		return [first, ...rest];
	}

	/** Work out a target (steps 4 and 8) without moving the map. */
	#makeTarget(cal: Calibration, pose: Pose): Target {
		const { w, h } = canvasSize(this.#map);
		const box = letterbox(w, h, cal.size);
		const fov = mapFov(pose.vfov, h, box.height);
		// The picture above the 511 bar, grown so the plane's cream edge falls just outside it.
		const crop = framedCrop(photoCrop(cal.size, false), SCENE_PHOTO_EDGE);
		const plane = photoPlane(pose, cal.size, crop);
		const name = this.#src.nameOf(cal.cameraId);
		const photo: ScenePhoto = {
			id: `look-${cal.viewId}`,
			apex: [pose.lon, pose.lat, pose.alt],
			groundAlt: cal.groundZ,
			right: plane.right,
			down: plane.down,
			forward: plane.forward,
			tx: plane.tx,
			ty: plane.ty,
			d: 2,
			label: name,
			opacity: 0,
			depthTest: true
		};
		return {
			cal,
			pose,
			size: cal.size,
			name,
			box,
			shown: shownBox(box, cal.size, crop),
			eye: eyePose(pose, fov),
			D: axisDistance(pose, cal.groundZ),
			crop,
			plane,
			d: 2,
			near: 0,
			photo,
			sha: null,
			loading: null,
			unwatch: this.#feed.watch([cal.viewId])
		};
	}

	/** The plane's distance from the eye for the camera as placed now (step 8), and its apex. */
	#setDistance(t: Target) {
		const map = this.#map;
		t.near = nearMetres(canvasSize(map).h, map.getZoom(), map.getCenter().lat);
		t.d = photoDistance(t.near);
		t.photo.d = t.d;
		t.photo.apex = planeApex(t.pose, t.plane, t.d);
	}

	/** Steps 4–8 for one view: check, fly, check again, show. */
	async #flyTo(cal: Calibration, pose: Pose): Promise<boolean> {
		const map = this.#map;
		const t = this.#makeTarget(cal, pose);
		const old = this.#target;
		this.#target = t;
		look.cameraId = cal.cameraId;
		look.viewId = cal.viewId;
		look.name = t.name;
		look.index = this.#entry?.order.findIndex((c) => c.viewId === cal.viewId) ?? 0;
		look.count = this.#entry?.order.length ?? 1;
		look.box = null;
		look.shown = null;
		look.reference = false;
		this.#src.exclude([cal.cameraId]);
		this.#picture(t);

		// Step 7, first: place, read back and go back, in one task (nothing is drawn in between).
		const start = eyeNow(map);
		const startPad = map.getPadding();
		this.#busy = true;
		placeEye(map, t.eye, ZERO, true);
		const err = this.#readback(t);
		this.#setDistance(t);
		placeEye(map, start, startPad);
		this.#busy = false;
		if (old && old !== t) this.#drop(old);
		if (!(err <= READBACK_M)) {
			this.#abort(`Can't place the map camera at this pose (the eye reads back ${err.toFixed(2)} m off)`);
			return false;
		}

		// Step 6: fly in, the picture's plane in place (depth-tested, as the window we zoom into).
		t.photo.depthTest = true;
		t.photo.opacity = PHOTO_OPACITY * look.slider;
		this.#show();
		const flown = await this.#fly(start, t.eye, startPad, ZERO);
		if (!flown || this.#target !== t) return false;
		this.#busy = true;
		placeEye(map, t.eye, ZERO, true);
		this.#busy = false;
		const after = this.#readback(t);
		if (!(after <= READBACK_M)) {
			this.#abort(`Can't place the map camera at this pose (the eye reads back ${after.toFixed(2)} m off)`);
			return false;
		}
		this.#setDistance(t);
		// Step 8: over everything, at 85% (times the slider), framed.
		t.photo.depthTest = false;
		t.photo.opacity = PHOTO_OPACITY * look.slider;
		this.#show();
		look.box = t.box;
		look.shown = t.shown;
		look.phase = 'looking';
		look.fade(1);
		return true;
	}

	/** How far the eye is from the target's, metres (read back from the map's public state). */
	#readback(t: Target): number {
		return metresBetween([t.pose.lon, t.pose.lat, t.pose.alt], [...eyeOf(mapCamera(this.#map))] as [number, number, number]);
	}

	/** Our own animation-frame flight between two eyes (a jump under reduced motion). False when cut short. */
	#fly(from: EyePose, to: EyePose, padFrom: PaddingOptions, padTo: PaddingOptions, exag?: [number, number]): Promise<boolean> {
		const id = ++this.#flight;
		const map = this.#map;
		const ms = reducedMotion() ? 0 : FLY_MS;
		return new Promise((resolve) => {
			const t0 = performance.now();
			let frames = 0;
			const frame = () => {
				if (this.#destroyed || id !== this.#flight) return resolve(false);
				const t = ms ? progress(performance.now() - t0, ms, ++frames) : 1;
				const k = easeInOut(t);
				if (exag) this.#exaggerate(lerp(exag[0], exag[1], k), t === 1);
				this.#busy = true;
				placeEye(map, interpolate(from, to, k), lerpPad(padFrom, padTo, k));
				this.#busy = false;
				this.#sample('fly');
				if (t < 1) requestAnimationFrame(frame);
				else resolve(true);
			};
			if (ms) requestAnimationFrame(frame);
			else frame();
		});
	}

	/** Set the exaggeration, skipping steps too small to see (each one rebuilds the terrain). */
	#exaggerate(x: number, last: boolean) {
		const now = this.#ctx.exaggeration();
		if (last ? now !== x : Math.abs(now - x) >= 0.01) this.#ctx.setExaggeration(x);
	}

	// --- the picture ------------------------------------------------------------------------------

	/** The live feed's newest answers: a new picture for the view looked through is decoded, then swapped in. */
	setFrames(views: Record<number, LiveView>): void {
		this.#views = views;
		const t = this.#target;
		if (t) this.#picture(t);
	}

	/**
	 * Load the target's newest picture: the live frame; or, once the live feed
	 * has answered that there's none (blocked, capped, images off…), the
	 * calibration's reference frame, labelled as such. A frame of another size
	 * never replaces the picture (it would land in the wrong place).
	 */
	#picture(t: Target) {
		const live = this.#views[t.cal.viewId] ?? this.#feed.views[t.cal.viewId];
		const f = live?.frame ?? null;
		if (f) {
			if (f.width === t.size.width && f.height === t.size.height && f.sha !== t.sha && f.sha !== t.loading) void this.#load(t, f.sha, f.url, false);
		} else if (live && live.state !== 'waiting' && !t.sha && !t.loading && t.cal.frame) {
			void this.#load(t, 'ref', `/frames/${t.cal.frame}`, true);
		}
	}

	async #load(t: Target, sha: string, url: string, reference: boolean) {
		t.loading = sha;
		const key = `look:${t.cal.viewId}:${sha}`;
		try {
			await this.#scene.textures.load(key, url, t.crop);
		} catch (e) {
			if (t.loading === sha) t.loading = null;
			console.warn(`Look-through picture for view ${t.cal.viewId}: ${e instanceof Error ? e.message : e}`);
			return;
		}
		if (this.#target !== t || t.loading !== sha) {
			if (t.photo.texture !== key) this.#scene.textures.release(key);
			return;
		}
		const old = t.photo.texture;
		t.photo.texture = key;
		t.sha = sha;
		t.loading = null;
		if (old && old !== key) this.#scene.textures.release(old);
		if (this.#target === t) look.reference = reference;
		this.#show();
	}

	#show() {
		const t = this.#target;
		this.#scene.setPhotos(LOOK_GROUP, t ? [t.photo] : []);
	}

	/** Forget a target: its picture, its poll. */
	#drop(t: Target) {
		t.unwatch();
		if (t.photo.texture) this.#scene.textures.release(t.photo.texture);
		t.photo.texture = undefined;
	}

	setSlider(v: number): void {
		look.slider = clamp01(v);
		this.#refade();
	}

	// --- the fade --------------------------------------------------------------------------------

	#onMove = () => {
		if (look.phase === 'looking' && !this.#busy) this.#refade();
	};

	/** Step 10: the picture fades as the user moves the map camera away from the pose. */
	#refade() {
		const t = this.#target;
		if (!t || look.phase !== 'looking') return;
		const e = deviation(eyeNow(this.#map), t.eye, t.D);
		const f = clamp01(1 - e);
		t.photo.opacity = PHOTO_OPACITY * f * look.slider;
		look.fade(f);
		this.#map.triggerRepaint();
		if (f > 0) {
			clearTimeout(this.#zeroTimer);
			this.#zeroTimer = undefined;
		} else if (!this.#zeroTimer) {
			this.#zeroTimer = setTimeout(() => this.#zeroed(), END.zeroMs);
		}
	}

	/** 300 ms at 0: end here, once the user's gesture has stopped. */
	#zeroed() {
		this.#zeroTimer = undefined;
		const t = this.#target;
		if (!t || look.phase !== 'looking') return;
		if (deviation(eyeNow(this.#map), t.eye, t.D) < 1) return;
		if (this.#map.isMoving()) {
			this.#map.once('moveend', () => {
				if (look.phase === 'looking') void this.endInPlace();
			});
			return;
		}
		void this.endInPlace();
	}

	#onResize = () => {
		const t = this.#target;
		if (!t || look.phase !== 'looking') return;
		if (deviation(eyeNow(this.#map), t.eye, t.D) > 0.05) return;
		// Fit the picture to the new canvas, at the same pose.
		const { w, h } = canvasSize(this.#map);
		t.box = letterbox(w, h, t.size);
		t.shown = shownBox(t.box, t.size, t.crop);
		t.eye = eyePose(t.pose, mapFov(t.pose.vfov, h, t.box.height));
		this.#busy = true;
		placeEye(this.#map, t.eye, ZERO, true);
		this.#busy = false;
		this.#setDistance(t);
		look.box = t.box;
		look.shown = t.shown;
		this.#show();
	};

	// --- the next camera --------------------------------------------------------------------------

	/** ← and →: fly to the next or previous calibrated camera by distance, still looking through. */
	async next(dir: 1 | -1): Promise<boolean> {
		const e = this.#entry;
		const t = this.#target;
		if (!e || !t || look.phase !== 'looking' || e.order.length < 2) return false;
		const i = Math.max(0, e.order.findIndex((c) => c.viewId === t.cal.viewId));
		const cal = e.order[(i + dir + e.order.length) % e.order.length];
		const sized = this.#sizeProblem(cal);
		if (sized) {
			this.#tell(`${this.#src.nameOf(cal.cameraId)}: ${sized}`);
			return false;
		}
		clearTimeout(this.#zeroTimer);
		this.#zeroTimer = undefined;
		look.phase = 'flying';
		look.fade(0);
		return this.#flyTo(cal, cal.pose);
	}

	// --- leaving -----------------------------------------------------------------------------------

	/** Esc or Step out: fade the picture out, then restore the saved view exactly (jumpTo: no tile asked for again). */
	async stepOut(): Promise<void> {
		const e = this.#entry;
		if (!e || (look.phase !== 'looking' && look.phase !== 'flying')) return;
		const id = ++this.#flight;
		look.phase = 'leaving';
		// The picture and its frame fade out; then the snapshot comes back with jumpTo, in one step.
		const t = this.#target;
		const o0 = t?.photo.opacity ?? 0;
		await this.#ease(reducedMotion() ? 0 : OUT_MS, id, (k) => {
			if (t) t.photo.opacity = o0 * (1 - k);
			look.fade(1 - k);
			this.#map.triggerRepaint();
		});
		this.#hidePicture();
		this.#finish(false);
	}

	/**
	 * Faded out by moving: end where the user is (step 10). Nothing jumps: the
	 * pitch, zoom, field of view and padding ease back within the snapshot's
	 * limits, the limits and the ground clamp come back with the eye kept in
	 * place, and the exaggeration eases back with the eye kept 10 m above the
	 * drawn ground. The snapshot then restores only what isn't the camera.
	 */
	async endInPlace(): Promise<void> {
		const e = this.#entry;
		const map = this.#map;
		if (!e || look.phase !== 'looking') return;
		this.#flight++;
		const id = this.#flight;
		look.phase = 'ending';
		this.#hidePicture();
		const s = e.snapshot;
		const still = reducedMotion();
		// A: pitch, zoom, field of view and padding, over 400 ms.
		const p0 = map.getPitch();
		const z0 = map.getZoom();
		const f0 = map.getVerticalFieldOfView();
		const pad0 = map.getPadding();
		const p1 = Math.min(p0, END.pitch, s.maxPitch);
		const z1 = Math.min(z0, END.zoom, s.maxZoom);
		const f1 = s.fov;
		await this.#ease(still ? 0 : END.ms, id, (k) => {
			map.setVerticalFieldOfView(lerp(f0, f1, k));
			map.jumpTo({ pitch: lerp(p0, p1, k), zoom: lerp(z0, z1, k), padding: lerpPad(pad0, s.padding, k) });
			this.#sample('end:camera');
		});
		if (id !== this.#flight) return;
		// B: the limits, and the centre back on the terrain under the axis with the eye kept, then the clamp.
		map.setMaxZoom(s.maxZoom);
		map.setMaxPitch(s.maxPitch);
		placeEye(map, eyeNow(map), undefined, true);
		map.setCenterClampedToGround(s.centerClampedToGround);
		this.#sample('end:limits');
		// C: the exaggeration, keeping the eye clear of the drawn ground.
		const x0 = this.#ctx.exaggeration();
		const x1 = s.exaggeration ?? x0;
		await this.#ease(still || x0 === x1 ? 0 : END.ms, id, (k) => {
			this.#exaggerate(lerp(x0, x1, k), k === 1);
			this.#keepClear();
			this.#sample('end:terrain');
		});
		if (id !== this.#flight) return;
		this.#finish(true);
	}

	/** Raise the eye if it's less than 10 m above the drawn ground under it. */
	#keepClear() {
		const map = this.#map;
		const eye = eyeNow(map);
		const g = map.queryTerrainElevation([eye.lng, eye.lat]);
		if (g === null || eye.alt >= g + END.clearM) return;
		placeEye(map, { ...eye, alt: g + END.clearM }, undefined, true);
	}

	/** Run `step(k)` with k eased from 0 to 1 over `ms` (once with 1 when ms is 0). */
	#ease(ms: number, id: number, step: (k: number) => void): Promise<void> {
		return new Promise((resolve) => {
			const t0 = performance.now();
			let frames = 0;
			const frame = () => {
				if (this.#destroyed || id !== this.#flight) return resolve();
				const t = ms ? progress(performance.now() - t0, ms, ++frames) : 1;
				step(easeInOut(t));
				if (t < 1) requestAnimationFrame(frame);
				else resolve();
			};
			if (ms) requestAnimationFrame(frame);
			else frame();
		});
	}

	#hidePicture() {
		clearTimeout(this.#zeroTimer);
		this.#zeroTimer = undefined;
		look.box = null;
		look.shown = null;
		look.fade(0);
		const t = this.#target;
		if (t) t.photo.opacity = 0;
		this.#scene.setPhotos(LOOK_GROUP, []);
	}

	/**
	 * Leave the mode. `inPlace`: the snapshot's camera becomes where the map is
	 * now, so its restore puts back only the rest (limits, clamp, exaggeration,
	 * layers, aerial, windows) and the camera doesn't move.
	 */
	#finish(inPlace: boolean) {
		const e = this.#entry;
		const map = this.#map;
		const t = this.#target;
		this.#target = null;
		if (t) this.#drop(t);
		this.#scene.setPhotos(LOOK_GROUP, []);
		this.#src.exclude([]);
		if (e && inPlace) {
			const s = e.snapshot;
			const c = map.getCenter();
			const p = map.getPadding();
			s.center = [c.lng, c.lat];
			s.zoom = map.getZoom();
			s.bearing = map.getBearing();
			s.pitch = map.getPitch();
			s.roll = map.getRoll();
			s.fov = map.getVerticalFieldOfView();
			s.padding = { top: p.top ?? 0, right: p.right ?? 0, bottom: p.bottom ?? 0, left: p.left ?? 0 };
		}
		this.#entry = null;
		if (this.#ctx.modes.current === 'look' || this.#ctx.modes.snapshotOf('look')) this.#ctx.modes.leave('look');
		if (e?.keyboard) map.keyboard.enable();
		look.phase = 'off';
		look.box = null;
		look.shown = null;
		look.cameraId = null;
		look.viewId = null;
		this.#sample('left');
	}

	/** Couldn't place the camera (or something else went wrong): say so and restore the view. */
	#abort(message: string) {
		this.#flight++;
		this.#hidePicture();
		this.#tell(message);
		look.problem = message;
		this.#finish(false);
	}

	#tell(text: string) {
		toasts.show(text, { kind: 'problem', key: 'look-through' });
	}

	// --- tests ------------------------------------------------------------------------------------

	/** Start (or stop and return) recording the map camera on every animation step. */
	trace(on: boolean): TraceSample[] {
		const out = this.#trace ?? [];
		this.#trace = on ? [] : null;
		return out;
	}

	#sample(phase: string) {
		if (!this.#trace) return;
		const map = this.#map;
		const eye = eyeOf(mapCamera(map));
		this.#trace.push({
			t: performance.now(),
			phase,
			pitch: map.getPitch(),
			zoom: map.getZoom(),
			fov: map.getVerticalFieldOfView(),
			exaggeration: this.#ctx.exaggeration(),
			eye,
			ground: map.queryTerrainElevation([eye[0], eye[1]])
		});
	}

	/** What the readback and the picture's plane look like now (tests and the console). */
	inspect() {
		const map = this.#map;
		const t = this.#target;
		const eye = eyeOf(mapCamera(map));
		const internal = internalEye(map);
		const want: [number, number, number] | null = t ? [t.pose.lon, t.pose.lat, t.pose.alt] : null;
		const { h } = canvasSize(map);
		return {
			phase: look.phase,
			cameraId: look.cameraId,
			viewId: look.viewId,
			eye,
			internal,
			pose: t?.pose ?? null,
			errorM: want ? metresBetween(want, eye) : null,
			internalErrorM: want && internal ? metresBetween(want, internal) : null,
			box: t?.box ?? null,
			shown: t?.shown ?? null,
			fov: map.getVerticalFieldOfView(),
			near: nearMetres(h, map.getZoom(), map.getCenter().lat),
			plane: t ? { d: t.d, near: t.near, opacity: t.photo.opacity ?? 1, depthTest: t.photo.depthTest !== false, texture: t.photo.texture ?? null, layer: this.#scene.textures.layer(t.photo.texture) } : null,
			limits: { maxPitch: map.getMaxPitch(), maxZoom: map.getMaxZoom(), clamp: map.getCenterClampedToGround(), exaggeration: this.#ctx.exaggeration() }
		};
	}

	destroy(): void {
		const leaving = look.phase !== 'off';
		this.#destroyed = true;
		this.#flight++;
		clearTimeout(this.#zeroTimer);
		if (leaving) this.#finish(false);
		for (const f of this.#cleanup.splice(0)) f();
		this.#scene.remove(LOOK_GROUP);
		look.actions = null;
	}
}
