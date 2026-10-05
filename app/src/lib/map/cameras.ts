import type { Map, MapGeoJSONFeature } from 'maplibre-gl';

export type CameraStatus = 'calibrated' | 'uncalibrated' | 'no_image';
export interface CameraProps {
	id: number;
	name: string;
	achdCamId: number | null;
	views: number;
	status: CameraStatus;
}

const SOURCE = 'cameras';
export const CAMERA_LAYERS = ['cameras-no-image', 'cameras-uncalibrated', 'cameras-calibrated'];

export type CameraCounts = Record<CameraStatus, number>;

/**
 * Camera nodes, told apart by shape as well as color (never color alone):
 *  - calibrated: solid teal dot with a white ring and a check
 *  - uncalibrated: hollow amber ring
 *  - no image yet: small gray dot
 */
export async function addCameraLayer(
	map: Map,
	onSelect: (c: CameraProps) => void
): Promise<{ error: string } | { counts: CameraCounts }> {
	const res = await fetch('/api/cameras');
	if (!res.ok) {
		const msg = (await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`;
		return { error: `Cameras unavailable: ${msg}` };
	}
	const data = await res.json();
	map.addSource(SOURCE, { type: 'geojson', data });
	const radius = ['interpolate', ['linear'], ['zoom'], 10, 4, 14, 7, 18, 11] as unknown as number;
	map.addLayer({
		id: 'cameras-no-image', type: 'circle', source: SOURCE, filter: ['==', ['get', 'status'], 'no_image'],
		paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 18, 6], 'circle-color': '#9a958c',
			'circle-stroke-color': '#fffbf4', 'circle-stroke-width': 1 }
	});
	map.addLayer({
		id: 'cameras-uncalibrated', type: 'circle', source: SOURCE, filter: ['==', ['get', 'status'], 'uncalibrated'],
		paint: { 'circle-radius': radius, 'circle-color': 'rgba(255,251,244,0.85)', 'circle-stroke-color': '#f2a20c',
			'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 2, 16, 3.5] }
	});
	map.addLayer({
		id: 'cameras-calibrated', type: 'circle', source: SOURCE, filter: ['==', ['get', 'status'], 'calibrated'],
		paint: { 'circle-radius': radius, 'circle-color': '#2c8c99', 'circle-stroke-color': '#fffbf4',
			'circle-stroke-width': 2 }
	});
	map.addLayer({
		id: 'cameras-calibrated-check', type: 'symbol', source: SOURCE, filter: ['==', ['get', 'status'], 'calibrated'],
		minzoom: 12,
		layout: { 'text-field': '✓', 'text-size': 11, 'text-font': ['Noto Sans Medium'], 'text-allow-overlap': true },
		paint: { 'text-color': '#fffbf4' }
	});
	for (const id of CAMERA_LAYERS) {
		map.on('mouseenter', id, () => (map.getCanvas().style.cursor = 'pointer'));
		map.on('mouseleave', id, () => (map.getCanvas().style.cursor = ''));
		map.on('click', id, (e) => {
			const f = e.features?.[0] as MapGeoJSONFeature | undefined;
			if (f) onSelect(f.properties as CameraProps);
		});
	}
	const counts: CameraCounts = { calibrated: 0, uncalibrated: 0, no_image: 0 };
	for (const f of data.features as { properties: CameraProps }[]) counts[f.properties.status]++;
	return { counts };
}
