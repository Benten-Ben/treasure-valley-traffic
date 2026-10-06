import type { ExpressionSpecification, Map, MapGeoJSONFeature, MapLayerMouseEvent } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { firstBasemapLabel } from '#lib/map/style.js';

/**
 * The Streets lens: every Ada County road from ACHD's centerlines, colored by
 * posted speed (one hue, light to dark as speed rises), widened by road class,
 * with arrows on one-way streets and speed numbers along the bigger roads.
 * Tiles are cut by PostGIS on request (/api/tiles/roads/{z}/{x}/{y}).
 */

export interface StreetProps {
	id: number;
	name: string | null;
	class: string | null;
	speed: number | null;
	one_way: 'both' | 'forward' | 'backward';
	private: boolean | null;
	elevated: boolean;
	community: string | null;
}

/** Posted-speed bins and colors: a validated single-hue ramp on the cream map. */
export const SPEED_BINS: { label: string; from: number; color: string }[] = [
	{ label: '20 mph or less', from: 0, color: '#6da7ec' },
	{ label: '25–30 mph', from: 25, color: '#3987e5' },
	{ label: '35–40 mph', from: 35, color: '#256abf' },
	{ label: '45–50 mph', from: 45, color: '#184f95' },
	{ label: '55 mph and up', from: 55, color: '#0d366b' }
];

export function speedColor(mph: number | null): string {
	let color = SPEED_BINS[0].color;
	for (const b of SPEED_BINS) if ((mph ?? 0) >= b.from) color = b.color;
	return color;
}

/** Line width at zoom 14, by road class. */
const CLASS_WIDTH: Record<string, number> = {
	Interstate: 5,
	'Principal Arterial': 4.5,
	'Minor Arterial': 3.5,
	Ramp: 2.5,
	Collector: 2.5,
	Local: 1.4
};

const L = {
	wash: 'streets-wash',
	casing: 'streets-casing',
	speed: 'streets-speed',
	labels: 'streets-speed-labels',
	oneway: 'streets-oneway'
};
export const STREET_LAYERS = Object.values(L);

const classWidth: ExpressionSpecification = [
	'match',
	['get', 'class'],
	...Object.entries(CLASS_WIDTH).flat(),
	1
] as unknown as ExpressionSpecification;

const width = (extra = 0): ExpressionSpecification => [
	'interpolate',
	['linear'],
	['zoom'],
	9,
	['+', ['*', classWidth, 0.35], extra * 0.5],
	14,
	['+', classWidth, extra],
	17,
	['+', ['*', classWidth, 2], extra]
];

/** A chevron pointing right (the line's direction), ink with a cream outline. */
function chevron(): ImageData {
	const w = 24;
	const h = 20;
	const c = document.createElement('canvas');
	c.width = w;
	c.height = h;
	const g = c.getContext('2d')!;
	g.beginPath();
	g.moveTo(5, 3);
	g.lineTo(19, 10);
	g.lineTo(5, 17);
	g.lineJoin = 'round';
	g.lineCap = 'round';
	g.lineWidth = 7;
	g.strokeStyle = '#fffbf4';
	g.stroke();
	g.lineWidth = 3.5;
	g.strokeStyle = '#2b2a33';
	g.stroke();
	return g.getImageData(0, 0, w, h);
}


/**
 * The Streets lens on the shared map, adapted to the app context (WP1): the
 * roads source and its hidden layers attach on `style.load`, the tile URL
 * carries the roads version from /api/meta, clicks count only in Explore, and
 * `destroy()` removes everything it added. WP2 ports this to
 * `#lib/layers/streets/`.
 */
export class StreetsLayer {
	private scope: MapScope | null = null;
	private visible = false;
	private destroyed = false;

	constructor(
		private app: AppCtx,
		private onSelect: (s: StreetProps | null) => void
	) {}

	async load(): Promise<boolean> {
		const tiles = await this.app.dataUrl(`${location.origin}/api/tiles/roads/{z}/{x}/{y}`, 'roads');
		const map = await this.app.styleReady.catch(() => null);
		if (!map || this.destroyed) return false;
		const scope = (this.scope = new MapScope(map));
		scope.addSource('roads', {
			type: 'vector',
			tiles: [tiles],
			minzoom: 8,
			maxzoom: 16,
			attribution: 'Ada County Highway District'
		});
		scope.addSource('streets-wash', {
			type: 'geojson',
			data: { type: 'Polygon', coordinates: [[[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]]] }
		});
		scope.addImage('oneway-chevron', chevron(), { pixelRatio: 2 });
		const firstLabel = firstBasemapLabel(map);
		const hidden = { visibility: 'none' as const };
		const speedStep = [
			'step',
			['coalesce', ['get', 'speed'], 0],
			SPEED_BINS[0].color,
			...SPEED_BINS.slice(1).flatMap((b) => [b.from, b.color])
		] as unknown as ExpressionSpecification;

		scope.addLayer({ id: L.wash, type: 'fill', source: 'streets-wash', layout: hidden,
			paint: { 'fill-color': '#f6f0e6', 'fill-opacity': 0.5 } }, firstLabel);
		scope.addLayer({ id: L.casing, type: 'line', source: 'roads', 'source-layer': 'roads',
			layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' },
			paint: { 'line-color': '#fffbf4', 'line-width': width(2), 'line-opacity': 0.9 } }, firstLabel);
		scope.addLayer({ id: L.speed, type: 'line', source: 'roads', 'source-layer': 'roads',
			layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' },
			paint: { 'line-color': speedStep, 'line-width': width() } }, firstLabel);
		scope.addLayer({ id: L.oneway, type: 'symbol', source: 'roads', 'source-layer': 'roads', minzoom: 14,
			filter: ['!=', ['get', 'one_way'], 'both'],
			layout: { ...hidden, 'symbol-placement': 'line', 'symbol-spacing': 90, 'icon-image': 'oneway-chevron',
				'icon-rotate': ['case', ['==', ['get', 'one_way'], 'backward'], 180, 0],
				'icon-rotation-alignment': 'map', 'icon-allow-overlap': true } });
		scope.addLayer({ id: L.labels, type: 'symbol', source: 'roads', 'source-layer': 'roads', minzoom: 13,
			filter: ['in', ['get', 'class'], ['literal', ['Interstate', 'Principal Arterial', 'Minor Arterial', 'Collector']]],
			layout: { ...hidden, 'symbol-placement': 'line', 'symbol-spacing': 280, 'text-field': ['to-string', ['get', 'speed']],
				'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-rotation-alignment': 'viewport' },
			paint: { 'text-color': '#2b2a33', 'text-halo-color': '#fffbf4', 'text-halo-width': 2 } });

		const exploring = () => this.app.modes.current === 'explore';
		scope.onLayer('click', L.speed, (e: MapLayerMouseEvent) => {
			if (!exploring()) return;
			const f = e.features?.[0] as MapGeoJSONFeature | undefined;
			this.onSelect(f ? ({ ...f.properties, id: Number(f.id ?? f.properties?.id) } as StreetProps) : null);
		});
		scope.onLayer('mouseenter', L.speed, () => {
			if (exploring()) map.getCanvas().style.cursor = 'pointer';
		});
		scope.onLayer('mouseleave', L.speed, () => {
			if (exploring()) map.getCanvas().style.cursor = '';
		});
		if (this.visible) this.setVisible(true);
		return true;
	}

	setVisible(on: boolean) {
		this.visible = on;
		const map = this.scope?.map;
		if (map) setStreetsVisible(map, on);
	}

	destroy() {
		this.destroyed = true;
		this.scope?.dispose();
		this.scope = null;
	}
}

export function setStreetsVisible(map: Map, on: boolean) {
	for (const id of STREET_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
}

export function oneWayText(s: Pick<StreetProps, 'one_way'>): string {
	return s.one_way === 'both' ? 'Two-way' : 'One-way (arrows show direction)';
}
