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
import { dev } from '$app/env';
import { buildStyle, loadManifest, type BasemapManifest } from './style.js';

let setUp = false;

/**
 * The worker URL and the PMTiles protocol, once per page. The boot calls this
 * before MapLibre's `prewarm()`, which starts the workers, so it must come
 * first; `createMap` calls it too.
 *
 * The protocol runs with `metadata: false`: the attribution comes from the
 * manifest, so the metadata section is never fetched (docs/14 §14.8).
 */
export function setupMapLibre(): void {
	if (setUp) return;
	setUp = true;
	setWorkerUrl(workerUrl);
	addProtocol('pmtiles', new Protocol({ metadata: false }).tile);
}

/**
 * Out-of-view tiles kept per source, as zoom levels' worth of a viewport.
 * MapLibre's own default is 5; a calibrate or look-through round trip must
 * find the original view's tiles still cached (the `persistent` spec), so
 * this never goes lower. (`maxTileCacheSize` could only lower the cache:
 * MapLibre takes the smaller of the two.) WP5's memory soak checks the cost.
 */
export const TILE_CACHE_ZOOM_LEVELS = 5;

export interface MapOptions {
	aerial?: boolean;
	center?: LngLatLike;
	zoom?: number;
	pitch?: number;
	bearing?: number;
	/** Degrees of slack around the valley that the view may pan into. */
	pad?: number;
	/** The manifest, when the caller already has it (the boot fetched it). */
	manifest?: BasemapManifest;
}

export class MapUnavailable extends Error {}

/**
 * A MapLibre map on our self-hosted basemap. Throws MapUnavailable if the
 * basemap isn't built. Map options follow docs/14 §14.8: no MapLibre hash
 * (the view module owns the URL), no hourly tile refresh, a tile cache that
 * survives a mode round trip, pixel ratio at most 2, and style validation in
 * development only.
 */
export async function createMap(container: HTMLElement, o: MapOptions = {}): Promise<{ map: Map; manifest: BasemapManifest }> {
	let m = o.manifest;
	if (!m) {
		const result = await loadManifest();
		if (!result.ok) throw new MapUnavailable(result.reason);
		m = result.manifest;
	}
	setupMapLibre();
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
		hash: false,
		attributionControl: false,
		refreshExpiredTiles: false,
		maxTileCacheZoomLevels: TILE_CACHE_ZOOM_LEVELS,
		pixelRatio: Math.min(globalThis.devicePixelRatio || 1, 2),
		validateStyle: dev
	});
	map.addControl(new NavigationControl({ visualizePitch: true }), 'top-right');
	map.addControl(new ScaleControl({ unit: 'imperial' }), 'bottom-left');
	map.addControl(new AttributionControl({ compact: true }), 'bottom-right');
	map.on('error', (ev) => console.error('map error', ev.error));
	return { map, manifest: m };
}
