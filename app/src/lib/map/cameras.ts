import type { FeatureCollection } from 'geojson';
import type { GeoJSONSource, MapGeoJSONFeature, MapLayerMouseEvent } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { drape, imageData } from '#lib/calibration/drape.js';
import { footprint, type ImageSize, type Pose } from '#lib/calibration/solver.js';

export type CameraStatus = 'calibrated' | 'uncalibrated' | 'no_image';
export interface CameraProps {
	id: number;
	name: string;
	achdCamId: number | null;
	views: number;
	status: CameraStatus;
}

/** A calibrated view's cone, as /api/calibrations reports it. */
export interface Calibration {
	calibrationId: number;
	pose: Pose;
	size: ImageSize;
	groundZ: number;
	frame: string;
}

const SOURCE = 'cameras';
export const CAMERA_LAYERS = ['cameras-no-image', 'cameras-uncalibrated', 'cameras-calibrated'];
/** Every layer the Cameras lens shows, besides the drapes. */
const ALL_LAYERS = [...CAMERA_LAYERS, 'cameras-calibrated-check', 'cones-fill', 'cones-line'];

export type CameraCounts = Record<CameraStatus, number>;

type Handlers = {
	onSelect: (c: CameraProps) => void;
	onCounts: (c: CameraCounts) => void;
	onCalibrations: (c: Calibration[]) => void;
	onError: (message: string) => void;
};

async function getJson(url: string) {
	const res = await fetch(url);
	if (!res.ok) {
		const msg = (await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`;
		throw new Error(msg);
	}
	return res.json();
}

/**
 * The Cameras lens: camera nodes, told apart by shape as well as color
 * (never color alone):
 *  - calibrated: solid teal dot with a white ring and a check
 *  - uncalibrated: hollow amber ring
 *  - no image yet: small gray dot
 * plus the view cones of calibrated cameras and, on request, each one's
 * reference frame draped on the ground under its cone.
 *
 * Adapted to the app context (WP1): both fetches start at boot, versioned by
 * /api/meta; the layers attach on `style.load`; clicks count only in Explore;
 * `destroy()` removes everything it added. WP2 ports this to
 * `#lib/layers/cameras/`.
 */
export class CameraLayer {
	calibrations: Calibration[] = [];
	cameras: CameraProps[] = [];
	private scope: MapScope | null = null;
	private drapes: MapScope | null = null;
	private visible = false;
	private images = false;
	private draped = false;
	private destroyed = false;

	constructor(
		private app: AppCtx,
		private on: Handlers
	) {}

	/** False when cameras aren't available (the reason goes to onError) or the map isn't. */
	async load(): Promise<boolean> {
		const camerasUrl = this.app.dataUrl('/api/cameras', 'cameras');
		const conesUrl = this.app.dataUrl('/api/calibrations', 'calibrations');
		const cameras = camerasUrl.then(getJson);
		const cones = conesUrl.then(getJson).catch(() => null);
		let data: FeatureCollection;
		try {
			data = await cameras;
		} catch (e) {
			this.on.onError(`Cameras unavailable: ${e instanceof Error ? e.message : e}`);
			return false;
		}
		const map = await this.app.styleReady.catch(() => null);
		if (!map || this.destroyed) return false;
		const scope = (this.scope = new MapScope(map));
		const hidden = { visibility: 'none' as const };
		scope.addSource(SOURCE, { type: 'geojson', data });
		const radius = ['interpolate', ['linear'], ['zoom'], 10, 4, 14, 7, 18, 11] as unknown as number;
		scope.addLayer({
			id: 'cameras-no-image', type: 'circle', source: SOURCE, filter: ['==', ['get', 'status'], 'no_image'], layout: hidden,
			paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 18, 6], 'circle-color': '#9a958c',
				'circle-stroke-color': '#fffbf4', 'circle-stroke-width': 1 }
		});
		scope.addLayer({
			id: 'cameras-uncalibrated', type: 'circle', source: SOURCE, filter: ['==', ['get', 'status'], 'uncalibrated'], layout: hidden,
			paint: { 'circle-radius': radius, 'circle-color': 'rgba(255,251,244,0.85)', 'circle-stroke-color': '#f2a20c',
				'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 2, 16, 3.5] }
		});
		scope.addLayer({
			id: 'cameras-calibrated', type: 'circle', source: SOURCE, filter: ['==', ['get', 'status'], 'calibrated'], layout: hidden,
			paint: { 'circle-radius': radius, 'circle-color': '#2c8c99', 'circle-stroke-color': '#fffbf4',
				'circle-stroke-width': 2 }
		});
		scope.addLayer({
			id: 'cameras-calibrated-check', type: 'symbol', source: SOURCE, filter: ['==', ['get', 'status'], 'calibrated'],
			minzoom: 12,
			layout: { ...hidden, 'text-field': '✓', 'text-size': 11, 'text-font': ['Noto Sans Medium'], 'text-allow-overlap': true },
			paint: { 'text-color': '#fffbf4' }
		});
		const exploring = () => this.app.modes.current === 'explore';
		for (const id of CAMERA_LAYERS) {
			scope.onLayer('mouseenter', id, () => {
				if (exploring()) map.getCanvas().style.cursor = 'pointer';
			});
			scope.onLayer('mouseleave', id, () => {
				if (exploring()) map.getCanvas().style.cursor = '';
			});
			scope.onLayer('click', id, (e: MapLayerMouseEvent) => {
				if (!exploring()) return;
				const f = e.features?.[0] as MapGeoJSONFeature | undefined;
				if (f) this.on.onSelect(f.properties as CameraProps);
			});
		}
		this.setCameras(data);

		// View cones for calibrated cameras, under the camera nodes.
		const c = await cones;
		if (!this.destroyed) this.setCones(c ?? { type: 'FeatureCollection', features: [] });
		this.setVisible(this.visible, this.images);
		return true;
	}

	private setCameras(data: FeatureCollection) {
		this.cameras = (data.features as unknown as { properties: CameraProps }[]).map((f) => f.properties);
		const counts: CameraCounts = { calibrated: 0, uncalibrated: 0, no_image: 0 };
		for (const p of this.cameras) counts[p.status]++;
		this.on.onCounts(counts);
	}

	private setCones(c: FeatureCollection) {
		const scope = this.scope;
		if (!scope) return;
		this.calibrations = c.features.map((f) => f.properties as Calibration);
		this.on.onCalibrations(this.calibrations);
		const src = scope.map.getSource('cones') as GeoJSONSource | undefined;
		if (src) return void src.setData(c);
		const hidden = { visibility: 'none' as const };
		scope.addSource('cones', { type: 'geojson', data: c });
		scope.addLayer({ id: 'cones-fill', type: 'fill', source: 'cones', layout: hidden,
			paint: { 'fill-color': '#2c8c99', 'fill-opacity': 0.14 } }, 'cameras-no-image');
		scope.addLayer({ id: 'cones-line', type: 'line', source: 'cones', layout: hidden,
			paint: { 'line-color': '#2c8c99', 'line-width': 1.5, 'line-opacity': 0.8 } }, 'cameras-no-image');
	}

	/**
	 * Fetch cameras and cones again (a calibration was saved): statuses, counts
	 * and cones update in place, and the drapes are redone when shown.
	 */
	async reload(): Promise<void> {
		const scope = this.scope;
		if (!scope) return;
		const [data, c] = await Promise.all([
			fetch('/api/cameras', { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null)),
			fetch('/api/calibrations', { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null))
		]).catch(() => [null, null]);
		if (this.destroyed || this.scope !== scope) return;
		if (data) {
			(scope.map.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(data);
			this.setCameras(data);
		}
		if (c) {
			this.setCones(c);
			this.drapes?.dispose();
			this.drapes = null;
			this.draped = false;
		}
		this.setVisible(this.visible, this.images);
	}

	/** Show or hide the lens, and with it (when asked) the draped camera images. */
	setVisible(on: boolean, images = this.images) {
		this.visible = on;
		this.images = images;
		const map = this.scope?.map;
		if (!map) return;
		for (const id of ALL_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
		for (const c of this.calibrations)
			if (map.getLayer(`drape-${c.calibrationId}`))
				map.setLayoutProperty(`drape-${c.calibrationId}`, 'visibility', on && images ? 'visible' : 'none');
		if (on && images && !this.draped) void this.drapeAll();
	}

	/** Drape each calibrated camera's reference frame onto the ground under its cone (once). */
	private async drapeAll() {
		if (!this.scope || this.draped || !this.calibrations.length) return;
		this.draped = true;
		const scope = (this.drapes = new MapScope(this.scope.map));
		for (const c of this.calibrations) {
			const pixels = await imageData(`/frames/${c.frame}`).catch(() => null);
			if (!pixels || this.destroyed || this.drapes !== scope) return;
			const d = drape(c.pose, c.size, pixels, c.groundZ, footprint(c.pose, c.size, c.groundZ, 200));
			if (!d) continue;
			const id = `drape-${c.calibrationId}`;
			scope.addSource(id, { type: 'image', url: d.url, coordinates: d.coordinates });
			scope.addLayer({ id, type: 'raster', source: id, paint: { 'raster-fade-duration': 0 },
				layout: { visibility: this.visible && this.images ? 'visible' : 'none' } }, 'cones-fill');
		}
	}

	destroy() {
		this.destroyed = true;
		this.drapes?.dispose();
		this.drapes = null;
		this.scope?.dispose();
		this.scope = null;
	}
}
