import type { Map, MapSourceDataEvent, PaddingOptions } from 'maplibre-gl';
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
import type { LiveFrame, LiveView } from '#lib/contracts/live.js';
import type { Scene, ScenePhoto } from '#lib/scene/index.js';
import type { ViewSnapshot } from '#lib/state/view.svelte.js';
import { toasts } from '#lib/ui/toasts.svelte.js';
import type { Calibration } from './cameras.js';
import { sizeChanged } from './freshness.js';
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
 * 5. **Place** with `calculateCameraOptionsFromCameraLngLatAltRotation`, with
 *    the centre first on the calibration's ground height along the view axis
 *    (never on the height the centre had before, which can be at or above the
 *    eye: `Grounding`), then on the terrain under the axis without moving the
 *    eye, so restoring the clamp later doesn't jump. A terrain pass that would
 *    reach the eye or jump more than a few metres isn't taken; as terrain tiles
 *    arrive while looking, the centre is put on them again (the eye stays).
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

/** "Image size changed (768×466 → 1920×1166); recalibrate" when a live frame isn't the calibrated size (the window's words), else null. */
export function resizedText(size: ImageSize, frame: { width: number; height: number } | null | undefined): string | null {
	return sizeChanged(frame, { imageWidth: size.width, imageHeight: size.height });
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
 * Where a placement puts the map's centre (step 5). MapLibre puts the centre
 * where the view axis meets the height the centre has *now*, and when that
 * height is at or above the eye (the view before entering was over higher
 * ground, or at the 1.3× terrain) the axis never meets it: the centre lands
 * 10 km out and kilometres underground, the zoom drops to about 12 and the
 * near plane to 140–200 m, and the map draws as streaks. So the centre first
 * goes onto a height known to be below the eye (the calibration's ground
 * height), and only then onto the terrain, where that's believable.
 */
export interface Grounding {
	/** The height the centre goes to along the view axis first, true metres; kept at least ANCHOR_BELOW_M below the eye. */
	anchor: number;
	/** Then onto the terrain under the axis, in up to two passes, each taken only when `usableGround` says so. */
	terrain?: boolean;
	/** The most one terrain pass may move the centre's height, m (default GROUND_JUMP_M). */
	maxJump?: number;
}
/** The anchor stays at least this far below the eye, m. */
export const ANCHOR_BELOW_M = 1;
/**
 * A terrain pass moving the centre's height further than this is a guess
 * (a tile not loaded yet reads 0, a far parent tile can be hundreds of metres
 * off), so it isn't taken, m.
 */
export const GROUND_JUMP_M = 6;
/** Terrain this close below the eye, or above it, never takes the centre, m. */
export const EYE_CLEAR_M = 0.5;
/** The centre counts as on the terrain within this, m (otherwise look-through places it again as tiles arrive). */
export const ON_GROUND_M = 0.5;

/** Whether a terrain height `g` may take a centre now at `z`: known, below the eye, and not a jump. */
export function usableGround(g: number | null, z: number, eyeAlt: number, maxJump = GROUND_JUMP_M): g is number {
	return g !== null && Number.isFinite(g) && g < eyeAlt - EYE_CLEAR_M && Math.abs(g - z) <= maxJump;
}

/**
 * Put the map's eye at a pose, without animation. The field of view first
 * (the zoom depends on it). With `ground`, the centre goes onto its anchor
 * height along the view axis, then (with `terrain`) onto the terrain there,
 * keeping the eye where it is. Every jump happens before the next frame is
 * drawn, so the in-between camera is never seen.
 */
export function placeEye(map: Map, e: EyePose, padding?: PaddingOptions, ground?: Grounding): void {
	if (Math.abs(map.getVerticalFieldOfView() - e.fov) > 1e-9) map.setVerticalFieldOfView(e.fov);
	const at = (): void => {
		const opts = map.calculateCameraOptionsFromCameraLngLatAltRotation([e.lng, e.lat], e.alt, e.bearing, e.pitch, e.roll);
		map.jumpTo(padding ? { ...opts, padding } : opts);
	};
	if (ground) {
		const anchor = Math.min(ground.anchor, e.alt - ANCHOR_BELOW_M);
		if (Math.abs(map.getCenterElevation() - anchor) > 1e-9) map.jumpTo({ elevation: anchor });
	}
	at();
	if (!ground?.terrain || !map.getTerrain()) return;
	for (let pass = 0; pass < 2; pass++) {
		const c = map.getCenter();
		const z = map.getCenterElevation();
		const g = map.queryTerrainElevation([c.lng, c.lat]);
		if (!usableGround(g, z, e.alt, ground.maxJump) || Math.abs(g - z) < 0.01) break;
		map.jumpTo({ elevation: g });
		at();
	}
}

/** How far the centre is from the terrain under it, m (null when that terrain isn't a usable height). */
export function offGround(map: Map, eyeAlt: number): number | null {
	if (!map.getTerrain()) return null;
	const c = map.getCenter();
	const z = map.getCenterElevation();
	const g = map.queryTerrainElevation([c.lng, c.lat]);
	return usableGround(g, z, eyeAlt) ? Math.abs(g - z) : null;
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
	/** "Image size changed (… → …); recalibrate" while the live picture is of another size, else null. */
	resized: string | null;
	/** The live picture is of another size and there's no reference frame to show instead: step out. */
	noPicture: boolean;
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
	/** Check the centre against the terrain after the next frame (a terrain tile arrived). */
	#groundDue = false;
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
		map.on('sourcedata', this.#onTerrainData);
		map.on('render', this.#onRender);
		this.#cleanup.push(() => {
			map.off('move', this.#onMove);
			map.off('resize', this.#onResize);
			map.off('sourcedata', this.#onTerrainData);
			map.off('render', this.#onRender);
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
		return resizedText(cal.size, this.#feed.views[cal.viewId]?.frame);
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
		// The picture above the 511 bar. A plane drawn over everything has no cream edge of its own (the scene's
		// PhotoBatch): the frame's 2 px viewfinder edge goes just outside it (LookFrame.svelte).
		const crop = photoCrop(cal.size, false);
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
			resized: null,
			noPicture: false,
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
		look.seen = null;
		look.problem = null;
		this.#src.exclude([cal.cameraId]);
		this.#picture(t);

		// Step 7, first: place, read back and go back, in one task (nothing is drawn in between).
		const start = eyeNow(map);
		const startPad = map.getPadding();
		// The height the centre has now is below the eye now (MapLibre placed it so), so it anchors the way back.
		const startGround = map.getCenterElevation();
		this.#busy = true;
		placeEye(map, t.eye, ZERO, this.#grounding(t));
		const err = this.#readback(t);
		this.#setDistance(t);
		placeEye(map, start, startPad, { anchor: startGround });
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
		const flown = await this.#fly(start, t.eye, startPad, ZERO, [startGround, t.cal.groundZ]);
		if (!flown || this.#target !== t) return false;
		this.#busy = true;
		placeEye(map, t.eye, ZERO, this.#grounding(t));
		this.#busy = false;
		const after = this.#readback(t);
		if (!(after <= READBACK_M)) {
			this.#abort(`Can't place the map camera at this pose (the eye reads back ${after.toFixed(2)} m off)`);
			return false;
		}
		// The live picture changed size on the way in, and there's no reference frame to show instead.
		if (t.noPicture) {
			this.#abort(t.resized ?? "There's no picture of the calibrated size to look through");
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
		this.#groundDue = true;
		map.triggerRepaint();
		return true;
	}

	/** How far the eye is from the target's, metres (read back from the map's public state). */
	#readback(t: Target): number {
		return metresBetween([t.pose.lon, t.pose.lat, t.pose.alt], [...eyeOf(mapCamera(this.#map))] as [number, number, number]);
	}

	/** Where the target's placement puts the centre: on the calibration's ground height, then on the terrain under the axis. */
	#grounding(t: Target): Grounding {
		return { anchor: t.cal.groundZ, terrain: true };
	}

	/**
	 * Our own animation-frame flight between two eyes (a jump under reduced
	 * motion), the centre's height eased between `ground`'s two (each below its
	 * eye, so every eye in between is above it too). False when cut short.
	 */
	#fly(from: EyePose, to: EyePose, padFrom: PaddingOptions, padTo: PaddingOptions, ground: [number, number]): Promise<boolean> {
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
				this.#busy = true;
				placeEye(map, interpolate(from, to, k), lerpPad(padFrom, padTo, k), { anchor: lerp(ground[0], ground[1], k) });
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
	 * calibration's reference frame, labelled as such.
	 *
	 * A frame of another size never replaces the picture (it would land in the
	 * wrong place). Look-through says so ("Image size changed (… → …);
	 * recalibrate", as a toast, in `look.problem` and on the strip) and keeps
	 * the live picture of the calibrated size it shows, if any, or else shows
	 * the reference frame, labelled. With no reference frame either, it steps
	 * out. When the size comes back, the live picture does too.
	 */
	#picture(t: Target) {
		const live = this.#views[t.cal.viewId] ?? this.#feed.views[t.cal.viewId];
		const f = live?.frame ?? null;
		const resized = resizedText(t.size, f);
		this.#setResized(t, resized);
		if (f && !resized) {
			if (f.sha !== t.sha && f.sha !== t.loading) void this.#load(t, f.sha, f.url, f);
		} else if ((resized || (live && live.state !== 'waiting')) && !t.sha && !t.loading) {
			if (t.cal.frame) void this.#load(t, 'ref', `/frames/${t.cal.frame}`, null);
			else if (resized) this.#noPicture(t);
		}
	}

	/** The live picture's size changed (a message), or came back (null). */
	#setResized(t: Target, resized: string | null) {
		if (t.resized === resized) return;
		t.resized = resized;
		if (this.#target !== t) return;
		look.problem = resized;
		if (resized) this.#tell(resized);
	}

	/** Nothing of the calibrated size to show: step out (at once, or when the flight in lands). */
	#noPicture(t: Target) {
		t.noPicture = true;
		if (this.#target === t && look.phase === 'looking') void this.stepOut();
	}

	/** Decode a picture into the plane: a live frame, or (`frame` null) the reference frame. */
	async #load(t: Target, sha: string, url: string, frame: LiveFrame | null) {
		const reference = frame === null;
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
		if (this.#target === t) {
			look.reference = reference;
			look.seen = frame;
		}
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
		placeEye(this.#map, t.eye, ZERO, this.#grounding(t));
		this.#busy = false;
		this.#setDistance(t);
		look.box = t.box;
		look.shown = t.shown;
		this.#show();
	};

	/** A terrain tile arrived: check the centre after the next frame (once it's drawn, the terrain reads as drawn). */
	#onTerrainData = (e: MapSourceDataEvent) => {
		if (this.#target && e.tile && e.sourceId === this.#map.getTerrain()?.source) this.#groundDue = true;
	};

	/**
	 * After a frame that follows a terrain tile's arrival (or the arrival in
	 * look-through): if the centre isn't on the terrain under the axis (that
	 * tile wasn't there when it was placed), place it again (step 5). The eye
	 * stays where it is, so nothing on screen moves; only the near plane and
	 * the tiles' level of detail follow the centre. Not once the user has moved
	 * the map camera.
	 */
	#onRender = () => {
		if (!this.#groundDue) return;
		const t = this.#target;
		const map = this.#map;
		if (!t || look.phase !== 'looking' || this.#busy) return;
		this.#groundDue = false;
		if (deviation(eyeNow(map), t.eye, t.D) > 1e-3) return;
		const off = offGround(map, t.eye.alt);
		if (off === null || off <= ON_GROUND_M) return;
		this.#busy = true;
		placeEye(map, t.eye, ZERO, this.#grounding(t));
		this.#busy = false;
		this.#setDistance(t);
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
		// The centre's height now is below the eye (the user's moves keep it so), so it anchors the placement;
		// the terrain here may be anywhere the user went, so any believable height under the axis is taken.
		map.setMaxZoom(s.maxZoom);
		map.setMaxPitch(s.maxPitch);
		placeEye(map, eyeNow(map), undefined, { anchor: map.getCenterElevation(), terrain: true, maxJump: Infinity });
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
		// The exaggeration is easing, so the drawn ground moves further each step than a look-through placement allows.
		placeEye(map, { ...eye, alt: g + END.clearM }, undefined, { anchor: map.getCenterElevation(), terrain: true, maxJump: Infinity });
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
			/** The map's centre: its height, and the drawn terrain there (null without terrain). */
			centre: { zoom: map.getZoom(), elevation: map.getCenterElevation(), ground: map.getTerrain() ? map.queryTerrainElevation(map.getCenter()) : null },
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
