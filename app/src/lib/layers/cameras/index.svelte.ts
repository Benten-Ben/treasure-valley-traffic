import type { FeatureCollection } from 'geojson';
import type { GeoJSONSource, MapGeoJSONFeature, MapMouseEvent } from 'maplibre-gl';
import { untrack } from 'svelte';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import type { Pose } from '#lib/calibration/solver.js';
import type { CamerasStatus } from '#lib/contracts/live.js';
import { addSlotted } from '#lib/map/order.js';
import { discSprite, type OverlayInstance } from '#lib/overlay/index.js';
import type { Scene } from '#lib/scene/index.js';
import { historyOf, sameView } from '#lib/state/history.svelte.js';
import type { CameraView } from '#lib/state/view.svelte.js';
import { WIDTH, windowsOf, type Point, type WindowSpec } from '#lib/state/windows.svelte.js';
import { ESC, onEscape, register } from '#lib/ui/keys.js';
import { slots } from '#lib/ui/slots.svelte.js';
import { toasts } from '#lib/ui/toasts.svelte.js';
import { take } from '../prefetch.js';
import { PRIORITY, type Chip, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import CameraWindow from './CameraWindow.svelte';
import {
	ALL_LAYERS,
	CAMERA_LAYERS,
	cameraLayers,
	CHECK_IMAGE,
	checkImage,
	CONES,
	counts,
	CREAM,
	CREDIT,
	INK,
	MOVES,
	movedLines,
	NOTCH_IMAGE,
	notchImage,
	SOURCE,
	STATUS_TEXT,
	type Calibration,
	type CameraCounts,
	type CameraProps
} from './cameras.js';
import type { PhotoCards, PhotoWant } from './card3d.js';
import Card from './Card.svelte';
import def from './def.js';
import type { CameraViewRow } from './detail.js';
import { cameraHooks } from './hooks.svelte.js';
import Legend from './Legend.svelte';
import { liveOf } from './live.svelte.js';
import { look } from './look.svelte.js';
import LookBanner from './LookBanner.svelte';
import LookFrame from './LookFrame.svelte';
import type { LookThrough } from './lookthrough.js';
import { flyToCamera } from './fly.js';
import { cameraIdOf, cameraKey, landBeside, landing } from './place.js';
import type { Cameras3D } from './scene.js';

async function getJson(url: string, init?: RequestInit) {
	const res = await take(url, init);
	if (!res.ok) {
		const msg = (await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`;
		throw new Error(msg);
	}
	return res.json();
}


/** The overlay group of window number badges on cameras. */
export const BADGES = 'camera-windows';
/** The same badges on the 3D heads, from z15 (§14.6: "in 2D and 3D"). */
export const BADGES_3D = 'camera-windows-3d';
/** Ask for the 3D scene once the map is zoomed in this far (models dither in from 14.7). */
const SCENE_FROM_ZOOM = 14.5;
/** The models' and photos' dither-in (scene.ts's modelFade, kept here so this chunk doesn't load scene.ts). */
const modelFade = (zoom: number) => Math.min(1, Math.max(0, (zoom - 14.7) / 0.3));
/** A second click on the same camera within this is a double-click (MapLibre's own is 500 ms), ms. */
const DOUBLE_MS = 600;
/** Badge sprites, one per window number (desktop windows are 1–4). */
const badgeKey = (n: number) => `camera-window-${n}`;
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };

interface Cam {
	props: CameraProps;
	at: [number, number];
}

/**
 * The Cameras module (docs/14 §14.6; WP2's port, WP12's icons and windows):
 *
 * - camera icons from /api/cameras and calibrated footprints from
 *   /api/calibrations (both versioned by /api/meta), the "recorded" notch
 *   from /api/cameras/views joined with /api/cameras/status, and the moved
 *   lines; a refresh when a calibration is saved ('cameras' topic);
 * - **a click on a camera** flies to it (zoom 18, keeping the bearing, pitch
 *   50) and opens its window beside it (the owner's Q2 answer); **a
 *   double-click** on a calibrated camera, or Enter on its focused window or
 *   while it's selected, goes straight into look-through, from the view
 *   before the clicks' fly (WP13); MapLibre's double-click zoom is
 *   suppressed on a camera;
 * - each open window's number badge drawn on its camera (the overlay), and
 *   from z15 on its 3D head too;
 * - hovering a camera (or its window) lights its footprint up;
 * - pinned camera windows reopen on the next visit ('camera' window kind);
 * - while a mode (calibrate, look-through) is active, camera windows step
 *   aside; the mode's view snapshot brings them back when it ends;
 * - **3D cameras** from z15 (scene.ts) and **the photo in the cone** for open
 *   windows (card3d.ts), once the scene engine has loaded (asked for near
 *   z15); **look-through** (lookthrough.ts), its mode strip
 *   (LookBanner.svelte, WP2's banner slot), its frame (LookFrame.svelte, the
 *   windows slot), and ← → and Esc through the keymap registry. Those three
 *   modules are their own chunks, loaded when first needed.
 *
 * The ground drape of reference frames is gone from the main map (§14.6);
 * calibration keeps its own.
 */
export class CamerasModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	cameras = $state.raw<CameraProps[]>([]);
	calibrations = $state.raw<Calibration[]>([]);
	counts = $state.raw<CameraCounts | null>(null);
	/** Views the capture services record (from /api/cameras/status), or null when unknown. */
	recording = $state<number | null>(null);
	/** Cameras with a recorded view (the notch). */
	recorded = $state.raw<ReadonlySet<number>>(new Set());
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{
			layerIds: CAMERA_LAYERS,
			priority: PRIORITY.camera,
			pick: (f: MapGeoJSONFeature): Selection | null => {
				const id = Number(f.properties?.id);
				const cam = this.#byId.get(id);
				const p = cam?.props ?? (f.properties as CameraProps | undefined);
				if (!p) return null;
				const at = cam?.at ?? (f.geometry.type === 'Point' ? (f.geometry.coordinates.slice(0, 2) as [number, number]) : undefined);
				return this.#selection(p, at);
			}
		}
	];
	#ctx: AppCtx | null = null;
	#scope: MapScope | null = null;
	#byId = new Map<number, Cam>();
	#visible = false;
	#destroyed = false;
	#hoverCamera: number | null = null;
	#windowCamera: number | null = null;
	#lit: number[] = [];
	/** The badges set on the overlay now: window key → number. */
	#badges = new Map<string, number>();
	#debug: object | null = null;
	#lookDebug: object | null = null;
	// WP13: the scene engine, 3D cameras, the photo in the cone and look-through (each loaded when first needed).
	#scene: Promise<Scene | null> | null = null;
	#models: Cameras3D | null = null;
	#cards: PhotoCards | null = null;
	#look: Promise<LookThrough | null> | null = null;
	#lookThrough: LookThrough | null = null;
	/** Cameras whose "3D photo" is turned off (window toggle). */
	photoOff = $state.raw<ReadonlySet<number>>(new Set());
	/** The view each camera window shows (reported by the window). */
	#shownView = new Map<number, number>();
	/** The first click of a possible double-click: the camera and the view before its fly. */
	#lastClick: { id: number; at: number; view: CameraView | null } | null = null;

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		const cameras = ctx.dataUrl('/api/cameras', 'cameras').then((u) => getJson(u));
		const cones = ctx
			.dataUrl('/api/calibrations', 'calibrations')
			.then((u) => getJson(u))
			.catch(() => null);
		const views = ctx
			.dataUrl('/api/cameras/views', 'cameras')
			.then((u) => getJson(u))
			.catch(() => null);
		const status = getJson('/api/cameras/status').catch(() => null);
		let data: FeatureCollection;
		try {
			data = await cameras;
		} catch (e) {
			this.status = 'error';
			this.error = `Cameras unavailable: ${e instanceof Error ? e.message : e}`;
			throw new Error(this.error);
		}
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		const scope = (this.#scope = new MapScope(map));
		scope.addImage(NOTCH_IMAGE, notchImage(2), { pixelRatio: 2 });
		scope.addImage(CHECK_IMAGE, checkImage(2), { pixelRatio: 2 });
		scope.addSource(SOURCE, { type: 'geojson', data });
		scope.addSource(CONES, { type: 'geojson', data: EMPTY });
		scope.addSource(MOVES, { type: 'geojson', data: EMPTY });
		addSlotted(map, cameraLayers(), def.order, (l, before) => scope.addLayer(l, before));
		this.#setCameras(data);
		const c = await cones;
		if (this.#destroyed) return;
		this.#setCones(c ?? EMPTY);
		void this.#setRecorded(views, status);

		// A click on a camera flies there and opens its window; a double-click doesn't zoom.
		scope.on('click', this.#onClick);
		scope.on('dblclick', this.#onDblClick);
		scope.defer(ctx.picker.onHover((h) => this.#hover(h?.selection ?? null)));
		// A calibration was saved: statuses, counts and footprints change.
		scope.defer(ctx.subscribe('cameras', () => void this.reload()));

		// Windows: pinned ones reopen; each open one's number goes on its camera.
		const windows = windowsOf(ctx);
		for (let n = 1; n <= 4; n++) ctx.overlay.sprite(discSprite({ key: badgeKey(n), text: String(n), color: INK, textColor: CREAM, size: 22 }));
		scope.defer(windows.registerKind('camera', (d) => this.#reopen(d)));
		scope.defer(
			windows.listen(() => {
				this.#syncBadges();
				this.#syncPhotos();
			})
		);
		// A mode (calibrate, look-through) owns the screen: camera windows step aside. The mode's
		// view snapshot holds them (§14.3), so leaving the mode puts them back.
		scope.defer(
			$effect.root(() => {
				$effect(() => {
					if (ctx.modes.current !== 'explore') untrack(() => this.#closeWindows());
				});
			})
		);
		scope.defer(() => ctx.overlay.remove(BADGES));
		scope.defer(() => ctx.overlay.remove(BADGES_3D));
		this.#install3d(scope);
		this.#installDebug();
		scope.defer(() => this.#uninstallDebug());

		this.status = 'ready';
		this.updatedAt = Date.now();
		this.setVisible(this.#visible);
	}

	#setCameras(data: FeatureCollection) {
		const byId = new Map<number, Cam>();
		const list: CameraProps[] = [];
		for (const f of data.features) {
			const p = f.properties as CameraProps;
			list.push(p);
			if (f.geometry?.type === 'Point') byId.set(p.id, { props: p, at: f.geometry.coordinates.slice(0, 2) as [number, number] });
		}
		this.#byId = byId;
		this.cameras = list;
		this.counts = counts(list);
		this.#models?.setData([...byId.values()], this.calibrations);
	}

	#setCones(c: FeatureCollection) {
		this.calibrations = c.features.map((f) => f.properties as Calibration);
		const map = this.#scope?.map;
		(map?.getSource(CONES) as GeoJSONSource | undefined)?.setData(c);
		const poles = new Map([...this.#byId].map(([id, cam]) => [id, cam.at] as const));
		(map?.getSource(MOVES) as GeoJSONSource | undefined)?.setData(movedLines(poles, this.calibrations));
		this.#light();
		this.#models?.setData([...this.#byId.values()], this.calibrations);
		this.#cards?.setCalibrations(this.calibrations);
		this.#syncPhotos();
	}

	/** The notch: cameras with a view the capture services record. */
	async #setRecorded(viewsP: Promise<{ views: CameraViewRow[] } | null>, statusP: Promise<CamerasStatus | null>) {
		const [views, status] = await Promise.all([viewsP, statusP]);
		if (this.#destroyed) return;
		this.recording = status && status.enabled ? Object.keys(status.recorded ?? {}).length : status ? 0 : null;
		if (!views || !status) return;
		const cameraOf = new Map(views.views.map((v) => [v.id, v.cameraId]));
		const rec = new Set<number>();
		for (const viewId of Object.keys(status.recorded ?? {})) {
			const cam = cameraOf.get(Number(viewId));
			if (cam !== undefined) rec.add(cam);
		}
		this.recorded = rec;
		this.#applyRecorded();
	}

	#applyRecorded() {
		const map = this.#scope?.map;
		if (!map?.getSource(SOURCE)) return;
		for (const id of this.recorded) map.setFeatureState({ source: SOURCE, id }, { recorded: true });
	}

	/** Fetch cameras and footprints again (a calibration was saved). */
	async reload(): Promise<void> {
		const scope = this.#scope;
		if (!scope) return;
		const [data, c] = await Promise.all([
			getJson('/api/cameras', { cache: 'no-cache' }).catch(() => null),
			getJson('/api/calibrations', { cache: 'no-cache' }).catch(() => null)
		]);
		if (this.#destroyed || this.#scope !== scope) return;
		if (data) {
			(scope.map.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(data);
			this.#setCameras(data);
			this.#applyRecorded();
			// The open card shows the new status.
			const sel = this.#ctx?.selection.current;
			if (sel?.layer === 'cameras') {
				const cam = this.#byId.get(Number(sel.id));
				if (cam) this.#ctx?.selection.select({ ...sel, fact: STATUS_TEXT[cam.props.status], data: cam.props });
			}
		}
		if (c) this.#setCones(c);
		this.updatedAt = Date.now();
		this.setVisible(this.#visible);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		const map = this.#scope?.map;
		if (!map) return;
		for (const id of ALL_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		this.#models?.setVisible(on);
		this.#onZoom();
		this.#syncBadges();
	}

	// --- selection, windows ---------------------------------------------------------------

	#selection(p: CameraProps, at?: [number, number]): Selection {
		return { kind: 'camera', id: String(p.id), layer: 'cameras', title: p.name, fact: STATUS_TEXT[p.status], source: CREDIT, at, data: p };
	}

	/** The camera's window, as the window manager opens it. */
	#spec(cam: Cam, anchor?: Point): WindowSpec {
		const p = cam.props;
		return {
			key: cameraKey(p.id),
			title: p.name,
			component: CameraWindow,
			props: { cameraId: p.id, name: p.name },
			aspect: 768 / 466,
			anchor,
			status:
				p.status === 'no_image'
					? { shape: '■', word: 'not on 511', color: 'var(--ink-soft)', detail: 'No 511 Idaho image is linked to this camera' }
					: { shape: '◌', word: 'waiting', color: 'var(--ink-soft)', detail: 'Asking for the newest picture…' },
			restore: { kind: 'camera', data: { id: p.id } }
		};
	}

	#closeWindows() {
		const ctx = this.#ctx;
		if (!ctx) return;
		const windows = windowsOf(ctx);
		for (const w of [...windows.list]) if (cameraIdOf(w.key) !== null) windows.close(w.key, { returnFocus: false, forget: false });
	}

	#reopen(data: unknown): WindowSpec | null {
		const id = (data as { id?: unknown } | null)?.id;
		const cam = typeof id === 'number' ? this.#byId.get(id) : undefined;
		return cam ? this.#spec(cam) : null;
	}

	/**
	 * Open a camera's window (or focus it when open). With `fly`, the map flies
	 * to the camera first (a programmatic fly: the view history keeps where it
	 * was) and the window opens beside where the camera lands. Returns whether
	 * a window is open for it now.
	 */
	open(id: number, o: { fly?: boolean; focus?: boolean } = {}): boolean {
		const ctx = this.#ctx;
		const cam = this.#byId.get(id);
		if (!ctx || !cam) return false;
		const map = this.#scope?.map ?? null;
		const windows = windowsOf(ctx);
		const key = cameraKey(id);
		let anchor: Point | undefined;
		if (map) {
			const box = map.getContainer().getBoundingClientRect();
			if (o.fly) {
				// The camera lands where its window fits beside it, clear of the legend and inspect
				// columns, or beside its window when that's open already.
				const open = windows.get(key);
				const land =
					open && windows.layout !== 'phone'
						? landBeside(open.rect, box)
						: landing(box, windows.remembered(key)?.w ?? WIDTH.default, windows.layout);
				anchor = flyToCamera(ctx, map, cam.at, land);
			} else {
				const p = map.project(cam.at);
				if (p.x >= 0 && p.y >= 0 && p.x <= box.width && p.y <= box.height) anchor = { x: box.left + p.x, y: box.top + p.y };
			}
		}
		return windows.open(this.#spec(cam, anchor), { focus: o.focus ?? true }) !== null;
	}

	/** The camera's window number, or null when it has none open. */
	windowOf(id: number): number | null {
		return this.#ctx ? windowsOf(this.#ctx).numberOf(cameraKey(id)) : null;
	}

	#onClick = (e: MapMouseEvent) => {
		const ctx = this.#ctx;
		if (!ctx || !this.#visible || ctx.modes.current !== 'explore') return;
		const touch = (e.originalEvent as PointerEvent | undefined)?.pointerType === 'touch';
		const top = ctx.picker.pickAt(e.point, touch).top;
		const now = performance.now();
		const last = this.#lastClick;
		const second = last !== null && now - last.at < DOUBLE_MS;
		if (top?.kind === 'camera' && top.layer === 'cameras') {
			const id = Number(top.id);
			// The first click of a possible double-click: remember the view before its fly.
			if (!second || last.id !== id) this.#lastClick = { id, at: now, view: ctx.view.current() };
			this.open(id, { fly: true });
		} else if (!second) this.#lastClick = null;
	};

	#onDblClick = (e: MapMouseEvent) => {
		const ctx = this.#ctx;
		const map = this.#scope?.map;
		if (!ctx || !map || !this.#visible || ctx.modes.current !== 'explore') return;
		const top = ctx.picker.pickAt(e.point).top;
		const last = this.#lastClick;
		const recent = last !== null && performance.now() - last.at < 2 * DOUBLE_MS ? last : null;
		// The first click's fly may have moved the camera from under the pointer: it still counts.
		const id = top?.kind === 'camera' && top.layer === 'cameras' ? Number(top.id) : (recent?.id ?? null);
		if (id === null) return;
		// On a camera, MapLibre's double-click zoom is suppressed (§14.6).
		e.preventDefault();
		this.#lastClick = null;
		if (!this.#calibrated(id)) return;
		// Straight in (§14.6, the owner's Q2 answer), from the view before the clicks' fly: stop it and go
		// back first, so Step out returns there, and drop the history entry that fly pushed.
		if (recent && recent.id === id && recent.view) {
			const v = recent.view;
			map.stop();
			map.jumpTo({ center: v.center, zoom: v.zoom, bearing: v.bearing, pitch: v.pitch });
			const h = historyOf(ctx);
			const pushed = h.stack.at(-1);
			if (pushed && sameView(pushed, v)) {
				h.stack = h.stack.slice(0, -1);
				h.dismissChip();
			}
		}
		void this.lookThrough(id);
	};

	#calibrated(id: number): boolean {
		return this.calibrations.some((c) => c.cameraId === id);
	}

	/** Each open camera window's number on its camera (2D, through the overlay). */
	#syncBadges() {
		const ctx = this.#ctx;
		if (!ctx || this.#destroyed) return;
		const instances: OverlayInstance[] = [];
		if (this.#visible) {
			for (const w of windowsOf(ctx).list) {
				const id = cameraIdOf(w.key);
				const cam = id === null ? undefined : this.#byId.get(id);
				if (!cam || w.number < 1 || w.number > 4) continue;
				instances.push({
					id: w.key,
					lng: cam.at[0],
					lat: cam.at[1],
					sprite: badgeKey(w.number),
					offset: [13, -13],
					pick: this.#selection(cam.props, cam.at),
					radius: 12
				});
			}
		}
		this.#badges = new Map(instances.map((i) => [i.id, Number(i.sprite.slice(i.sprite.lastIndexOf('-') + 1))]));
		ctx.overlay.set(BADGES, instances, { z: 55, priority: PRIORITY.camera });
		// From z15 the same number also sits on the camera's 3D head (WP13).
		const heads = this.#visible && this.#models?.drawn ? this.#models.heads() : null;
		const on3d: OverlayInstance[] = [];
		if (heads) {
			for (const i of instances) {
				const id = cameraIdOf(i.id);
				const h = id === null ? undefined : heads.get(id);
				if (!h) continue;
				on3d.push({ ...i, id: `${i.id}:3d`, lng: h.lng, lat: h.lat, altitude: h.above + 0.5, offset: [12, -12] });
			}
		}
		ctx.overlay.set(BADGES_3D, on3d, { z: 56, priority: PRIORITY.camera });
	}

	// --- footprint highlight ---------------------------------------------------------------

	#hover(sel: Selection | null) {
		const id = sel?.kind === 'camera' && sel.layer === 'cameras' ? Number(sel.id) : null;
		if (id === this.#hoverCamera) return;
		this.#hoverCamera = id;
		this.#light();
	}

	/** Light a camera's footprint while the pointer is over its window. */
	highlight(id: number, on: boolean): void {
		if (on) this.#windowCamera = id;
		else if (this.#windowCamera === id) this.#windowCamera = null;
		else return;
		this.#light();
	}

	#light() {
		const map = this.#scope?.map;
		if (!map?.getSource(CONES)) return;
		const cams = new Set([this.#hoverCamera, this.#windowCamera].filter((x): x is number => x !== null));
		const want = this.calibrations.filter((c) => cams.has(c.cameraId)).map((c) => c.calibrationId);
		for (const id of this.#lit) if (!want.includes(id)) map.setFeatureState({ source: CONES, id }, { hover: false });
		for (const id of want) if (!this.#lit.includes(id)) map.setFeatureState({ source: CONES, id }, { hover: true });
		this.#lit = want;
	}

	// --- 3D cameras, the photo in the cone, look-through (WP13) -------------------------------------

	/** The window hooks, the mode strip and frame, the keys, and loading the scene near z15. */
	#install3d(scope: MapScope) {
		const ctx = this.#ctx!;
		const feed = liveOf(ctx);
		cameraHooks.lookThrough = (camera, view) => void this.lookThrough(camera.id, view.id);
		cameraHooks.photo = {
			isOn: (id) => !this.photoOff.has(id),
			set: (id, on) => this.#setPhoto(id, on),
			view: (id, viewId) => this.#viewShown(id, viewId)
		};
		scope.defer(() => {
			cameraHooks.lookThrough = null;
			cameraHooks.photo = null;
		});
		scope.defer(slots.setBanner('look', LookBanner));
		scope.defer(slots.add('windows', { id: 'look-frame', component: LookFrame, order: -10 }));
		scope.defer(
			register([
				{
					id: 'look-through',
					codes: ['Enter', 'NumpadEnter'],
					label: 'Enter',
					description: 'Look through the focused or selected camera (calibrated ones)',
					group: 'Look-through',
					run: () => this.#enterKey()
				},
				{
					id: 'look-previous',
					codes: ['ArrowLeft'],
					label: '←',
					description: 'Previous calibrated camera by distance',
					group: 'Look-through',
					modes: ['look'],
					run: () => void look.actions?.next(-1)
				},
				{
					id: 'look-next',
					codes: ['ArrowRight'],
					label: '→',
					description: 'Next calibrated camera by distance',
					group: 'Look-through',
					modes: ['look'],
					run: () => void look.actions?.next(1)
				}
			])
		);
		scope.defer(
			onEscape(ESC.look, () => {
				if (!look.active) return false;
				look.actions?.stepOut();
				return true;
			})
		);
		scope.on('zoom', () => this.#onZoom());
		// The 3D badges follow the heads' ground; not while a mode's own flights jump the camera every frame.
		scope.on('moveend', () => {
			if (ctx.modes.current === 'explore') this.#syncBadges();
		});
		// New pictures: the photos in the cones and the picture looked through swap them in.
		scope.defer(
			$effect.root(() => {
				$effect(() => {
					const views = feed.views;
					untrack(() => {
						this.#cards?.setFrames(views);
						this.#lookThrough?.setFrames(views);
					});
				});
			})
		);
		scope.defer(() => this.#drop3d());
	}

	/** Zooming: ask for the scene near z15; the photos dither in with the models. */
	#onZoom() {
		const map = this.#scope?.map;
		if (!map) return;
		if (this.#visible && map.getZoom() >= SCENE_FROM_ZOOM) void this.#ensureScene();
		this.#photoVisibility();
	}

	/** The scene engine and the 3D cameras and photo cards in it, loaded once (null when the scene can't start). */
	#ensureScene(): Promise<Scene | null> {
		const ctx = this.#ctx;
		if (!ctx) return Promise.resolve(null);
		this.#scene ??= (async () => {
			const [scene, { Cameras3D }, { PhotoCards }] = await Promise.all([ctx.scene(), import('./scene.js'), import('./card3d.js')]);
			const map = this.#scope?.map;
			if (this.#destroyed || !map) return null;
			if (!scene.ok) throw new Error(scene.error ?? 'WebGL2 is not available');
			this.#models = new Cameras3D(scene, map, {
				selection: (p, at) => this.#selection(p, at),
				exaggeration: () => ctx.exaggeration()
			});
			this.#models.setData([...this.#byId.values()], this.calibrations);
			this.#models.setVisible(this.#visible);
			const cards = (this.#cards = new PhotoCards(scene));
			cards.setCalibrations(this.calibrations);
			for (const id of this.photoOff) cards.set(id, false);
			cards.setFrames(liveOf(ctx).views);
			this.#syncPhotos();
			this.#photoVisibility();
			this.#syncBadges();
			return scene;
		})().catch((e) => {
			// Cameras simply stay icons (and footprints) at every zoom; no 3D photo, no look-through.
			console.warn(`Cameras: 3D cameras are off: ${e instanceof Error ? e.message : e}`);
			cameraHooks.photo = null;
			return null;
		});
		return this.#scene;
	}

	/** The open camera windows, each with the view it shows: their photos in the cones. */
	#syncPhotos() {
		const ctx = this.#ctx;
		const cards = this.#cards;
		if (!ctx || !cards) return;
		const wants: PhotoWant[] = [];
		for (const w of windowsOf(ctx).list) {
			const id = cameraIdOf(w.key);
			const cam = id === null ? undefined : this.#byId.get(id);
			if (!cam) continue;
			const viewId = this.#shownView.get(cam.props.id) ?? this.calibrations.find((c) => c.cameraId === cam.props.id)?.viewId;
			if (viewId !== undefined) wants.push({ cameraId: cam.props.id, viewId, name: cam.props.name });
		}
		cards.setWanted(wants);
	}

	#photoVisibility() {
		const map = this.#scope?.map;
		const ctx = this.#ctx;
		if (!map || !ctx || !this.#cards) return;
		const zoom = map.getZoom();
		this.#cards.setVisible(this.#visible && ctx.modes.current === 'explore' && zoom >= 14.7, modelFade(zoom));
	}

	#setPhoto(id: number, on: boolean) {
		const next = new Set(this.photoOff);
		if (on) next.delete(id);
		else next.add(id);
		this.photoOff = next;
		this.#cards?.set(id, on);
	}

	#viewShown(id: number, viewId: number | null) {
		if (viewId === null) this.#shownView.delete(id);
		else if (this.#shownView.get(id) === viewId) return;
		else this.#shownView.set(id, viewId);
		this.#syncPhotos();
	}

	/**
	 * Look through a calibrated camera (the window's view, else its first
	 * calibrated one); `pose` overrides the saved pose (Check alignment, tests).
	 * Resolves once it's looking, or false.
	 */
	async lookThrough(cameraId: number, viewId?: number | null, pose?: Pose): Promise<boolean> {
		const lt = await this.#ensureLook();
		if (!lt) {
			toasts.show("Look-through needs the 3D view, which couldn't start here", { kind: 'problem', key: 'look-through' });
			return false;
		}
		return lt.enter(cameraId, viewId ?? this.#shownView.get(cameraId) ?? null, { pose });
	}

	#ensureLook(): Promise<LookThrough | null> {
		const ctx = this.#ctx;
		if (!ctx) return Promise.resolve(null);
		this.#look ??= (async () => {
			const [scene, { LookThrough }] = await Promise.all([this.#ensureScene(), import('./lookthrough.js')]);
			const map = this.#scope?.map;
			if (!scene || !map || this.#destroyed) return null;
			const lt = new LookThrough(ctx, map, scene, liveOf(ctx), {
				calibrations: () => this.calibrations,
				nameOf: (id) => this.#byId.get(id)?.props.name ?? `Camera ${id}`,
				exclude: (ids) => this.#models?.setExcluded(ids)
			});
			lt.setFrames(liveOf(ctx).views);
			this.#lookThrough = lt;
			return lt;
		})().catch((e) => {
			console.warn(`Cameras: look-through is off: ${e instanceof Error ? e.message : e}`);
			this.#look = null;
			return null;
		});
		return this.#look;
	}

	/** Enter: look through the camera whose window has focus, else the selected camera (calibrated only). */
	#enterKey(): boolean {
		const ctx = this.#ctx;
		if (!ctx || typeof document === 'undefined') return false;
		const el = document.activeElement as HTMLElement | null;
		let id: number | null = null;
		let viewId: number | null = null;
		const win = el?.closest?.<HTMLElement>('[data-window-key]');
		const host = win ?? el?.closest?.<HTMLElement>('[data-camera-id]') ?? null;
		if (win) id = cameraIdOf(win.dataset.windowKey ?? '');
		else if (host?.dataset.cameraId) id = Number(host.dataset.cameraId);
		if (host) {
			const v = (host.matches('[data-view-id]') ? host : host.querySelector<HTMLElement>('[data-view-id]'))?.dataset.viewId;
			viewId = v ? Number(v) : null;
		}
		if (id === null) {
			const sel = ctx.selection.current;
			if (sel?.kind === 'camera' && sel.layer === 'cameras') id = Number(sel.id);
		}
		if (id === null || !this.#calibrated(id)) return false;
		void this.lookThrough(id, viewId);
		return true;
	}

	#drop3d() {
		this.#lookThrough?.destroy();
		this.#lookThrough = null;
		this.#models?.destroy();
		this.#models = null;
		this.#cards?.destroy();
		this.#cards = null;
	}

	// --- chrome -------------------------------------------------------------------------------

	chips(): Chip[] {
		const c = this.counts;
		if (!c) return [];
		const title = `${CREDIT}: ${c.calibrated + c.uncalibrated + c.no_image} cameras`;
		const out: Chip[] = [];
		if (this.recording !== null) out.push({ id: 'recording', text: `${this.recording} recording`, title: `${title} · views the capture services record` });
		out.push({ id: 'calibrated', text: `${c.calibrated} calibrated`, title: `${title} · ${c.calibrated} calibrated, ${c.uncalibrated} not yet` });
		return out;
	}

	summary(): string | null {
		return this.cameras.length ? `${this.cameras.length} cameras` : null;
	}

	destroy(): void {
		this.#destroyed = true;
		this.#scope?.dispose();
		this.#scope = null;
	}

	// --- debug ----------------------------------------------------------------------------------

	/** A read-only handle for tests and the console: `__tvtCameras`. */
	#installDebug() {
		const ctx = this.#ctx!;
		const feed = liveOf(ctx);
		const windows = windowsOf(ctx);
		const handle = Object.freeze({
			/** Open a camera's window (and fly there with `fly`), as a click does. */
			open: (id: number, fly = false) => this.open(id, { fly }),
			cameras: () =>
				[...this.#byId.values()].map((c) => ({ ...c.props, lng: c.at[0], lat: c.at[1], recorded: this.recorded.has(c.props.id) })),
			/** Open camera windows: key, camera, number and header status. */
			windows: () =>
				windows.list
					.filter((w) => cameraIdOf(w.key) !== null)
					.map((w) => ({ key: w.key, cameraId: cameraIdOf(w.key), number: w.number, status: w.status ? `${w.status.shape} ${w.status.word}` : null })),
			/**
			 * The number badges on cameras: camera, the number its sprite shows, and where the last
			 * frame drew it (CSS px, before the offset; null when it wasn't drawn, e.g. off screen).
			 */
			badges: () => {
				const drawn = new Map(ctx.overlay.positions(BADGES).map((p) => [p.id, p]));
				return [...this.#badges].map(([k, number]) => ({ cameraId: cameraIdOf(k), number, x: drawn.get(k)?.x ?? null, y: drawn.get(k)?.y ?? null }));
			},
			/** The live feed: views polled, whether it runs, its interval and request count. */
			feed: () => ({ watching: feed.watching, running: feed.running, interval: feed.interval, requests: feed.requests }),
			/** Footprints lit up now (calibration ids). */
			lit: () => [...this.#lit]
		});
		Object.defineProperty(globalThis, '__tvtCameras', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#debug = handle;

		// WP13: 3D cameras and look-through, for tests and the console: `__tvtLook`.
		const lookHandle = Object.freeze({
			/** Look through a camera (its window's view or first calibrated one), optionally at another pose; resolves when looking. */
			enter: (cameraId: number, viewId?: number | null, pose?: Pose) => this.lookThrough(cameraId, viewId, pose),
			/** Step out (Esc): resolves back in Explore. */
			stepOut: async () => (await this.#ensureLook())?.stepOut(),
			next: async (dir: 1 | -1) => (await this.#ensureLook())?.next(dir) ?? false,
			endInPlace: async () => (await this.#ensureLook())?.endInPlace(),
			state: () => ({
				phase: look.phase,
				cameraId: look.cameraId,
				viewId: look.viewId,
				name: look.name,
				box: look.box,
				slider: look.slider,
				index: look.index,
				count: look.count,
				reference: look.reference,
				problem: look.problem
			}),
			/** The eye read back (public state and MapLibre's own), the picture's plane, the limits. */
			inspect: () => this.#lookThrough?.inspect() ?? null,
			/** Record the map camera on every animation step: trace(true), then trace(false) returns the samples. */
			trace: (on: boolean) => this.#lookThrough?.trace(on) ?? [],
			setSlider: (v: number) => look.actions?.setSlider(v),
			/** Load the scene and the 3D cameras now (they load by themselves near z15). */
			load3d: async () => Boolean(await this.#ensureScene()),
			models: () => this.#models?.info() ?? null,
			photos: () => this.#cards?.info() ?? null
		});
		Object.defineProperty(globalThis, '__tvtLook', { value: lookHandle, configurable: true, enumerable: false, writable: false });
		this.#lookDebug = lookHandle;
	}

	#uninstallDebug() {
		if ((globalThis as { __tvtCameras?: unknown }).__tvtCameras === this.#debug) Reflect.deleteProperty(globalThis, '__tvtCameras');
		if ((globalThis as { __tvtLook?: unknown }).__tvtLook === this.#lookDebug) Reflect.deleteProperty(globalThis, '__tvtLook');
		this.#debug = null;
		this.#lookDebug = null;
	}
}

export function create(): LayerModule {
	return new CamerasModule();
}
