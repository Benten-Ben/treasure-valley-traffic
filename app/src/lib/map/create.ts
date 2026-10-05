import {
	AttributionControl,
	Map,
	NavigationControl,
	ScaleControl,
	addProtocol,
	setWorkerUrl,
	type LngLatLike
} from 'maplibre-gl';
// MapLibre looks for its worker next to its own module, which bundling breaks,
// so Vite builds the worker and MapLibre gets its URL.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { Protocol } from 'pmtiles';
import { buildStyle, loadManifest, type BasemapManifest } from './style.js';

let protocolAdded = false;

export interface MapOptions {
	aerial?: boolean;
	center?: LngLatLike;
	zoom?: number;
	pitch?: number;
	bearing?: number;
	hash?: boolean;
	/** Degrees of slack around the valley that the view may pan into. */
	pad?: number;
}

export class MapUnavailable extends Error {}

/** A MapLibre map on our self-hosted basemap. Throws MapUnavailable if the basemap isn't built. */
export async function createMap(container: HTMLElement, o: MapOptions = {}): Promise<{ map: Map; manifest: BasemapManifest }> {
	const result = await loadManifest();
	if (!result.ok) throw new MapUnavailable(result.reason);
	const m = result.manifest;
	if (!protocolAdded) {
		setWorkerUrl(workerUrl);
		addProtocol('pmtiles', new Protocol({ metadata: true }).tile);
		protocolAdded = true;
	}
	const [w, s, e, n] = m.bounds;
	// Terrain covers the valley plus a 0.2 degree ring; stay inside it.
	const pad = o.pad ?? 0.15;
	const map = new Map({
		container,
		style: buildStyle(m, location.origin, o.aerial ?? false),
		center: o.center ?? m.center,
		zoom: o.zoom ?? m.zoom,
		pitch: o.pitch ?? (m.terrain ? 45 : 0),
		bearing: o.bearing ?? 0,
		maxPitch: 75,
		maxBounds: [
			[w - pad, s - pad],
			[e + pad, n + pad]
		],
		hash: o.hash ?? false,
		attributionControl: false
	});
	map.addControl(new NavigationControl({ visualizePitch: true }), 'top-right');
	map.addControl(new ScaleControl({ unit: 'imperial' }), 'bottom-left');
	map.addControl(new AttributionControl({ compact: true }), 'bottom-right');
	map.on('error', (ev) => console.error('map error', ev.error));
	return { map, manifest: m };
}
