import type { FeatureCollection } from 'geojson';
import type { GeoJSONSource, MapGeoJSONFeature, MapMouseEvent } from 'maplibre-gl';
import { untrack } from 'svelte';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import type { CamerasStatus } from '#lib/contracts/live.js';
import { addSlotted } from '#lib/map/order.js';
import { discSprite, type OverlayInstance } from '#lib/overlay/index.js';
import { WIDTH, windowsOf, type Point, type WindowSpec } from '#lib/state/windows.svelte.js';
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
import Card from './Card.svelte';
import def from './def.js';
import type { CameraViewRow } from './detail.js';
import Legend from './Legend.svelte';
import { liveOf } from './live.svelte.js';
import { flyToCamera } from './fly.js';
import { cameraIdOf, cameraKey, landBeside, landing } from './place.js';

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
 *   50) and opens its window beside it (the owner's Q2 answer); MapLibre's
 *   double-click zoom is suppressed on a camera (WP13 makes the double-click
 *   look through);
 * - each open window's number badge drawn on its camera (the overlay);
 * - hovering a camera (or its window) lights its footprint up;
 * - pinned camera windows reopen on the next visit ('camera' window kind);
 * - while a mode (calibrate, look-through) is active, camera windows step
 *   aside; the mode's view snapshot brings them back when it ends.
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
		scope.defer(windows.listen(() => this.#syncBadges()));
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
	}

	#setCones(c: FeatureCollection) {
		this.calibrations = c.features.map((f) => f.properties as Calibration);
		const map = this.#scope?.map;
		(map?.getSource(CONES) as GeoJSONSource | undefined)?.setData(c);
		const poles = new Map([...this.#byId].map(([id, cam]) => [id, cam.at] as const));
		(map?.getSource(MOVES) as GeoJSONSource | undefined)?.setData(movedLines(poles, this.calibrations));
		this.#light();
	}

	/** The notch: cameras with a view the capture services record. */
	async #setRecorded(viewsP: Promise<{ views: CameraViewRow[] } | null>, statusP: Promise<CamerasStatus | null>) {
		const [views, status] = await Promise.all([viewsP, statusP]);
		if (this.#destroyed) return;
		const cameraOf = views ? new Map(views.views.map((v) => [v.id, v.cameraId])) : null;
		// The road-weather views are recorded too (WP16), but they aren't this layer's: count the views it shows.
		const recordedViews = Object.keys(status?.recorded ?? {}).filter((v) => !cameraOf || cameraOf.has(Number(v)));
		this.recording = status && status.enabled ? recordedViews.length : status ? 0 : null;
		if (!cameraOf || !status) return;
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
		if (top?.kind === 'camera' && top.layer === 'cameras') this.open(Number(top.id), { fly: true });
	};

	#onDblClick = (e: MapMouseEvent) => {
		const ctx = this.#ctx;
		if (!ctx || !this.#visible || ctx.modes.current !== 'explore') return;
		const top = ctx.picker.pickAt(e.point).top;
		// On a camera, MapLibre's double-click zoom is suppressed (§14.6).
		if (top?.kind === 'camera' && top.layer === 'cameras') e.preventDefault();
	};

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
	}

	#uninstallDebug() {
		if ((globalThis as { __tvtCameras?: unknown }).__tvtCameras === this.#debug) Reflect.deleteProperty(globalThis, '__tvtCameras');
		this.#debug = null;
	}
}

export function create(): LayerModule {
	return new CamerasModule();
}
