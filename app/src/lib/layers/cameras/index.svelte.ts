import type { FeatureCollection } from 'geojson';
import type { GeoJSONSource, MapGeoJSONFeature } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import { take } from '../prefetch.js';
import type { AppCtx } from '#lib/app/context.js';
import { addSlotted, ANCHORS } from '#lib/map/order.js';
import { PRIORITY, type Chip, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import {
	ALL_LAYERS,
	CAMERA_LAYERS,
	cameraLayers,
	CONES,
	counts,
	CREDIT,
	SOURCE,
	STATUS_TEXT,
	type Calibration,
	type CameraCounts,
	type CameraProps
} from './cameras.js';
import Card from './Card.svelte';
import def from './def.js';
import Legend from './Legend.svelte';

async function getJson(url: string, init?: RequestInit) {
	const res = await take(url, init);
	if (!res.ok) {
		const msg = (await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`;
		throw new Error(msg);
	}
	return res.json();
}

/**
 * The Cameras module: camera nodes from /api/cameras and calibrated cones
 * from /api/calibrations (both versioned by /api/meta), the drapes on
 * request, and a refresh when a calibration is saved ('cameras' topic).
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
	/** Draped camera images on the map (the legend's checkbox). */
	images = $state(false);
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{
			layerIds: CAMERA_LAYERS,
			priority: PRIORITY.camera,
			pick: (f: MapGeoJSONFeature): Selection | null => {
				const id = Number(f.properties?.id);
				const p = this.cameras.find((c) => c.id === id) ?? (f.properties as CameraProps | undefined);
				if (!p) return null;
				const at = f.geometry.type === 'Point' ? (f.geometry.coordinates.slice(0, 2) as [number, number]) : undefined;
				return { kind: 'camera', id: String(p.id), layer: 'cameras', title: p.name, fact: STATUS_TEXT[p.status], source: CREDIT, at, data: p };
			}
		}
	];
	#ctx: AppCtx | null = null;
	#scope: MapScope | null = null;
	#drapes: MapScope | null = null;
	#visible = false;
	#draped = false;
	#destroyed = false;

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		const cameras = ctx.dataUrl('/api/cameras', 'cameras').then((u) => getJson(u));
		const cones = ctx
			.dataUrl('/api/calibrations', 'calibrations')
			.then((u) => getJson(u))
			.catch(() => null);
		void this.#status();
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
		scope.addSource(SOURCE, { type: 'geojson', data });
		scope.addSource(CONES, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
		addSlotted(map, cameraLayers(), def.order, (l, before) => scope.addLayer(l, before));
		this.#setCameras(data);
		const c = await cones;
		if (this.#destroyed) return;
		this.#setCones(c ?? { type: 'FeatureCollection', features: [] });
		// A calibration was saved: statuses, counts and cones change.
		scope.defer(ctx.subscribe('cameras', () => void this.reload()));
		this.status = 'ready';
		this.updatedAt = Date.now();
		this.setVisible(this.#visible);
	}

	#setCameras(data: FeatureCollection) {
		this.cameras = (data.features as unknown as { properties: CameraProps }[]).map((f) => f.properties);
		this.counts = counts(this.cameras);
	}

	#setCones(c: FeatureCollection) {
		this.calibrations = c.features.map((f) => f.properties as Calibration);
		(this.#scope?.map.getSource(CONES) as GeoJSONSource | undefined)?.setData(c);
	}

	async #status() {
		try {
			const s = await getJson('/api/cameras/status');
			this.recording = Object.keys(s?.recorded ?? {}).length;
		} catch {
			this.recording = null;
		}
	}

	/** Fetch cameras and cones again (a calibration was saved); the drapes are redone when shown. */
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
			// The open card shows the new status.
			const sel = this.#ctx?.selection.current;
			if (sel?.layer === 'cameras') {
				const p = this.cameras.find((x) => String(x.id) === sel.id);
				if (p) this.#ctx?.selection.select({ ...sel, fact: STATUS_TEXT[p.status], data: p });
			}
		}
		if (c) {
			this.#setCones(c);
			this.#drapes?.dispose();
			this.#drapes = null;
			this.#draped = false;
		}
		this.updatedAt = Date.now();
		this.setVisible(this.#visible);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		const map = this.#scope?.map;
		if (!map) return;
		for (const id of ALL_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		for (const c of this.calibrations)
			if (map.getLayer(`drape-${c.calibrationId}`))
				map.setLayoutProperty(`drape-${c.calibrationId}`, 'visibility', on && this.images ? 'visible' : 'none');
		if (on && this.images && !this.#draped) void this.#drapeAll();
	}

	/** Show or hide the camera images draped on the ground. */
	setImages(on: boolean): void {
		this.images = on;
		this.setVisible(this.#visible);
	}

	/** Drape each calibrated camera's reference frame onto the ground under its cone (once). */
	async #drapeAll() {
		if (!this.#scope || this.#draped || !this.calibrations.length) return;
		this.#draped = true;
		const scope = (this.#drapes = new MapScope(this.#scope.map));
		// The projection code loads only when someone asks for the images.
		const [{ drape, imageData }, { footprint }] = await Promise.all([import('#lib/calibration/drape.js'), import('#lib/calibration/solver.js')]);
		if (this.#drapes !== scope) return;
		for (const c of this.calibrations) {
			const pixels = await imageData(`/frames/${c.frame}`).catch(() => null);
			if (!pixels || this.#destroyed || this.#drapes !== scope) return;
			const d = drape(c.pose, c.size, pixels, c.groundZ, footprint(c.pose, c.size, c.groundZ, 200));
			if (!d) continue;
			const id = `drape-${c.calibrationId}`;
			scope.addSource(id, { type: 'image', url: d.url, coordinates: d.coordinates });
			const map = scope.map;
			scope.addLayer(
				{ id, type: 'raster', source: id, paint: { 'raster-fade-duration': 0 }, layout: { visibility: this.#visible && this.images ? 'visible' : 'none' } },
				map.getLayer('cones-fill') ? 'cones-fill' : map.getLayer(ANCHORS.footprints) ? ANCHORS.footprints : undefined
			);
		}
	}

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
		this.#drapes?.dispose();
		this.#drapes = null;
		this.#scope?.dispose();
		this.#scope = null;
	}
}

export function create(): LayerModule {
	return new CamerasModule();
}
