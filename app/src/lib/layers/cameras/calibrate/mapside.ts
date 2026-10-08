import type { FeatureCollection } from 'geojson';
import { Marker, type GeoJSONSource, type ImageSource, type Map, type MapMouseEvent, type PaddingOptions } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { drape, imageData } from '#lib/calibration/drape.js';
import { groundMetres } from '#lib/calibration/frustum.js';
import { footprint, type ImageSize, type LngLatZ, type Pose } from '#lib/calibration/solver.js';
import { beforeSlot } from '#lib/map/order.js';
import { BUILDINGS_LAYER } from '#lib/map/style.js';
import type { Scene } from '#lib/scene/index.js';
import type { Selection } from '../../types.js';
import { INK, TEAL } from '../cameras.js';
import { trueHeight, type DraftPair } from './draft.js';

/**
 * The map side of Calibrate mode (docs/14 §14.6, "Calibrating on the map";
 * WP14). On the one shared map:
 *
 * - **Entering** pushes the view snapshot (`modes.enter('calibrate')`), turns
 *   Aerial on (in full color: the flavor stays, so no basemap tile is laid
 *   out again), puts buildings at 0.25 and terrain at true scale, and sets a
 *   crosshair. The layer manager hides Transit, Streets and the other
 *   cameras; this camera's pole and live cone stay, drawn here.
 * - **Aiming** jumps (no flight, so no tiles load for the zooms in between)
 *   to pitch 0, bearing = the solved heading (north when there's none), zoom
 *   19, centred on the worked footprint or the pole, with the panel's width as
 *   the map's left padding.
 * - **Clicks** belong to the calibrator: each gives a ground point, its
 *   height read from the drawn terrain and divided by the exaggeration in
 *   force *now* (true scale here, but a height picked at 1.3 agrees).
 * - **What it draws:** ACHD's pole point; numbered, draggable pair markers;
 *   the live cone's footprint in teal (a camera's color), with the 3D pole,
 *   head, cone and frustum edges from the scene engine when it's loaded; a
 *   faint line from the pole to the solved position when they're more than
 *   3 m apart; and, as a check, the reference frame draped on the ground.
 * - **Leaving** removes all of it, restores the buildings' opacity and the
 *   cursor, and pops the snapshot (`modes.leave`), which puts the view,
 *   limits, terrain, layers, aerial and windows back with `jumpTo`.
 */
export const CONE_SOURCE = 'calib-cone';
export const CONE_FILL = 'calib-cone-fill';
export const CONE_LINE = 'calib-cone-line';
export const MOVE_SOURCE = 'calib-move';
export const MOVE_LINE = 'calib-move-line';
export const DRAPE = 'calib-drape';
export const GROUP_3D = 'calibrate-3d';
export const CALIBRATE_LAYERS = [DRAPE, CONE_FILL, CONE_LINE, MOVE_LINE] as const;
/** Buildings while calibrating (§14.6): faint, so the ground points under them can be seen. */
export const BUILDINGS_OPACITY = 0.25;
export const CALIBRATE_ZOOM = 19;
/** A solved camera further than this from ACHD's point gets a line to it (§14.6, "Moved camera"). */
export const MOVED_M = 3;

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };

export interface Aim {
	center: [number, number];
	bearing: number;
}

export interface Solved {
	pose: Pose;
	size: ImageSize;
	groundZ: number;
}

export interface DrapeWant extends Solved {
	url: string;
}

export interface CalibrateMapOptions {
	cameraId: number;
	viewId: number;
	name: string;
	/** ACHD's point for the camera. */
	pole: [number, number];
	/** A click on the map (in Calibrate mode): its ground point, or null with the reason. */
	onGround(g: LngLatZ | null, why?: string): void;
	/** A pair's marker was clicked (select it). */
	onPick(index: number): void;
	/** A pair's marker was dragged to a new ground point. */
	onMoveGround(index: number, g: LngLatZ): void;
}

/** What the map side shows now (tests and the console). */
export interface CalibrateMapInfo {
	entered: boolean;
	hidden: boolean;
	markers: { n: number; selected: boolean; pending: boolean; lng: number; lat: number }[];
	cone: boolean;
	drape: boolean;
	moved: boolean;
	scene: { instances: number; cones: number; lines: number } | null;
	buildingsOpacity: unknown;
}

export class CalibrateMap {
	#app: AppCtx;
	#o: CalibrateMapOptions;
	#map: Map | null = null;
	#scope: MapScope | null = null;
	#markers: Marker[] = [];
	#pairs: readonly DraftPair[] = [];
	#selected: number | null = null;
	#solved: Solved | null = null;
	#drape: DrapeWant | null = null;
	#drapeTimer: ReturnType<typeof setTimeout> | undefined;
	#drapeShown = false;
	#pixels: { url: string; data: Promise<ImageData> } | null = null;
	#hidden = false;
	#scene: Scene | null = null;
	#build3d: typeof import('../scene.js').build3d | null = null;
	#built = { instances: 0, cones: 0, lines: 0 };
	#gone = false;

	constructor(app: AppCtx, o: CalibrateMapOptions) {
		this.#app = app;
		this.#o = o;
	}

	get entered(): boolean {
		return this.#scope !== null;
	}

	/** Enter Calibrate mode on the shared map, aimed at `aim`. False when there's no map. */
	enter(aim: Aim, padding: PaddingOptions): boolean {
		const app = this.#app;
		const map = app.map;
		if (!map || this.#scope || this.#gone) return false;
		this.#map = map;
		this.#hidden = false;
		map.stop();
		app.modes.enter('calibrate');
		app.setAerial(true);
		app.setExaggeration(1);
		const s = (this.#scope = new MapScope(map));

		// Buildings faint, back as they were on leaving.
		if (map.getLayer(BUILDINGS_LAYER)) {
			const before = map.getPaintProperty(BUILDINGS_LAYER, 'fill-extrusion-opacity');
			map.setPaintProperty(BUILDINGS_LAYER, 'fill-extrusion-opacity', BUILDINGS_OPACITY);
			s.defer(() => {
				if (map.getLayer(BUILDINGS_LAYER)) map.setPaintProperty(BUILDINGS_LAYER, 'fill-extrusion-opacity', before);
			});
		}

		// The live cone's footprint and the moved line, with the camera footprints (draped, one run).
		const at = beforeSlot(map, 'footprints', 99);
		s.addSource(CONE_SOURCE, { type: 'geojson', data: EMPTY });
		s.addSource(MOVE_SOURCE, { type: 'geojson', data: EMPTY });
		s.addLayer({ id: CONE_FILL, type: 'fill', source: CONE_SOURCE, paint: { 'fill-color': TEAL, 'fill-opacity': 0.12 } }, at);
		s.addLayer({ id: CONE_LINE, type: 'line', source: CONE_SOURCE, paint: { 'line-color': TEAL, 'line-width': 2, 'line-opacity': 0.9 } }, at);
		s.addLayer(
			{ id: MOVE_LINE, type: 'line', source: MOVE_SOURCE, paint: { 'line-color': INK, 'line-width': 1.5, 'line-opacity': 0.6, 'line-dasharray': [2, 2] } },
			at
		);

		// ACHD's point for the camera.
		const pole = document.createElement('div');
		pole.className = 'calib-pole';
		pole.title = `${this.#o.name}: ACHD's location (±25 m)`;
		const poleMarker = new Marker({ element: pole }).setLngLat(this.#o.pole).addTo(map);
		s.defer(() => poleMarker.remove());
		s.defer(() => this.#clearMarkers());

		s.on('click', this.#onClick);
		const canvas = map.getCanvas();
		canvas.style.cursor = 'crosshair';
		s.defer(() => (canvas.style.cursor = ''));
		s.on('zoomend', () => this.#push3d());

		this.aim(aim, padding);
		this.#syncMarkers();
		this.#syncSolved();
		void this.#load3d();
		return true;
	}

	/** Jump (never fly) to the camera's working view. */
	aim(aim: Aim, padding: PaddingOptions): void {
		const map = this.#map;
		if (!map || !this.#scope) return;
		map.stop();
		map.jumpTo({ center: aim.center, zoom: CALIBRATE_ZOOM, pitch: 0, bearing: aim.bearing, padding });
	}

	setPadding(padding: PaddingOptions): void {
		const map = this.#map;
		if (!map || !this.#scope || this.#hidden) return;
		const p = map.getPadding();
		if (p.top === padding.top && p.right === padding.right && p.bottom === padding.bottom && p.left === padding.left) return;
		map.setPadding(padding);
	}

	/** The true ground point under a map position, or null (no terrain yet). */
	groundAt(lngLat: { lng: number; lat: number }): LngLatZ | null {
		const map = this.#map;
		if (!map) return null;
		const z = map.queryTerrainElevation([lngLat.lng, lngLat.lat]);
		if (z === null) return null;
		return [lngLat.lng, lngLat.lat, trueHeight(z, this.#app.exaggeration())];
	}

	#onClick = (e: MapMouseEvent) => {
		if (this.#hidden || this.#app.modes.current !== 'calibrate') return;
		// A click on a pair's marker selects it (the marker's own handler).
		const t = e.originalEvent?.target as Element | null;
		if (t && typeof t.closest === 'function' && t.closest('.calib-pair')) return;
		const g = this.groundAt(e.lngLat);
		if (!g) {
			this.#o.onGround(null, this.#map?.getTerrain() ? 'No ground height here yet (terrain still loading). Try again in a moment.' : 'Terrain is off, so there is no ground height to read.');
			return;
		}
		this.#o.onGround(g);
	};

	// --- pairs ---------------------------------------------------------------------------

	setPairs(pairs: readonly DraftPair[], selected: number | null): void {
		this.#pairs = pairs;
		this.#selected = selected;
		this.#syncMarkers();
	}

	#clearMarkers() {
		for (const m of this.#markers) m.remove();
		this.#markers = [];
	}

	#syncMarkers() {
		const map = this.#map;
		this.#clearMarkers();
		if (!map || !this.#scope) return;
		const last = this.#pairs.length - 1;
		this.#pairs.forEach((p, i) => {
			if (!p.ground) return;
			const el = document.createElement('button');
			el.type = 'button';
			el.className = 'calib-pair';
			el.textContent = String(i + 1);
			el.title = `Pair ${i + 1}: drag to move its ground point`;
			el.setAttribute('aria-label', `Pair ${i + 1} on the map`);
			el.dataset.pair = String(i + 1);
			if (i === this.#selected) el.classList.add('selected');
			if (i === last && !p.pixel) el.classList.add('pending');
			if (this.#hidden) el.style.display = 'none';
			el.addEventListener('click', (ev) => {
				ev.stopPropagation();
				this.#o.onPick(i);
			});
			const m = new Marker({ element: el, draggable: true }).setLngLat([p.ground[0], p.ground[1]]).addTo(map);
			m.on('dragend', () => {
				const g = this.groundAt(m.getLngLat());
				if (g) this.#o.onMoveGround(i, g);
				else m.setLngLat([p.ground![0], p.ground![1]]);
			});
			this.#markers.push(m);
		});
	}

	// --- the live cone ---------------------------------------------------------------------

	setSolved(s: Solved | null): void {
		this.#solved = s;
		this.#syncSolved();
	}

	#syncSolved() {
		const map = this.#map;
		if (!map || !this.#scope) return;
		const s = this.#solved;
		const cone = map.getSource(CONE_SOURCE) as GeoJSONSource | undefined;
		const move = map.getSource(MOVE_SOURCE) as GeoJSONSource | undefined;
		if (!s) {
			cone?.setData(EMPTY);
			move?.setData(EMPTY);
		} else {
			const ring = footprint(s.pose, s.size, s.groundZ);
			cone?.setData({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } });
			const at: [number, number] = [s.pose.lon, s.pose.lat];
			const moved = groundMetres(this.#o.pole, at) > MOVED_M;
			move?.setData(moved ? { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [this.#o.pole, at] } } : EMPTY);
		}
		this.#push3d();
	}

	/** The scene engine and the 3D cameras' builder (pole, head, cone, edges), loaded once. */
	async #load3d() {
		try {
			const [scene, mod] = await this.#app.track(Promise.all([this.#app.scene(), import('../scene.js')]));
			if (this.#gone || !this.#scope || !scene.ok) return;
			this.#scene = scene;
			this.#build3d = mod.build3d;
			this.#push3d();
		} catch {
			// No 3D here: the footprint and the markers still show the cone.
		}
	}

	#push3d() {
		const scene = this.#scene;
		const build = this.#build3d;
		const map = this.#map;
		if (!scene || !build || !map) return;
		const s = this.#solved;
		if (!s || this.#hidden || !this.#scope) {
			scene.set(GROUP_3D, []);
			scene.setCones(GROUP_3D, []);
			scene.setLines(GROUP_3D, []);
			this.#built = { instances: 0, cones: 0, lines: 0 };
			return;
		}
		const o = this.#o;
		const pick: Selection = { kind: 'camera', id: String(o.cameraId), layer: 'cameras', title: o.name };
		const built = build(
			[{ props: { id: o.cameraId, name: o.name, achdCamId: null, views: 1, status: 'calibrated' }, at: o.pole }],
			[{ calibrationId: -1, viewId: o.viewId, cameraId: o.cameraId, pose: s.pose, size: s.size, groundZ: s.groundZ, frame: '' }],
			{
				zoom: map.getZoom(),
				lat: map.getCenter().lat,
				ground: (lng, lat) => {
					const z = map.getTerrain() ? map.queryTerrainElevation([lng, lat]) : null;
					return z === null ? null : trueHeight(z, this.#app.exaggeration());
				},
				selection: () => pick
			}
		);
		for (const i of built.instances) i.pick = null;
		scene.set(GROUP_3D, built.instances);
		scene.setCones(GROUP_3D, built.cones);
		scene.setLines(GROUP_3D, built.lines);
		scene.show(GROUP_3D, true);
		this.#built = { instances: built.instances.length, cones: built.cones.length, lines: built.lines.length };
	}

	// --- the drape (a check) -----------------------------------------------------------------

	/** Drape the reference frame on the ground under the cone (null: off). Debounced. */
	setDrape(want: DrapeWant | null): void {
		this.#drape = want;
		clearTimeout(this.#drapeTimer);
		const map = this.#map;
		if (!map || !this.#scope) return;
		if (!want || this.#hidden) {
			this.#showDrape(false);
			return;
		}
		this.#drapeTimer = setTimeout(() => void this.#makeDrape(want), 250);
	}

	async #makeDrape(want: DrapeWant) {
		const map = this.#map;
		const scope = this.#scope;
		if (!map || !scope) return;
		if (this.#pixels?.url !== want.url) this.#pixels = { url: want.url, data: imageData(want.url) };
		let pixels: ImageData;
		try {
			pixels = await this.#pixels.data;
		} catch {
			this.#pixels = null;
			return;
		}
		if (this.#drape !== want || this.#scope !== scope || this.#hidden) return;
		const d = drape(want.pose, want.size, pixels, want.groundZ, footprint(want.pose, want.size, want.groundZ, 200));
		if (!d) return this.#showDrape(false);
		const src = map.getSource(DRAPE) as ImageSource | undefined;
		if (src) src.updateImage({ url: d.url, coordinates: d.coordinates });
		else {
			scope.addSource(DRAPE, { type: 'image', url: d.url, coordinates: d.coordinates });
			scope.addLayer({ id: DRAPE, type: 'raster', source: DRAPE, paint: { 'raster-fade-duration': 0, 'raster-opacity': 0.9 } }, CONE_FILL);
		}
		this.#showDrape(true);
	}

	#showDrape(on: boolean) {
		const map = this.#map;
		this.#drapeShown = on;
		if (map?.getLayer(DRAPE)) map.setLayoutProperty(DRAPE, 'visibility', on ? 'visible' : 'none');
	}

	// --- look-through over it ------------------------------------------------------------------

	/** Hide everything this draws (while Check alignment looks through), or show it again. */
	setHidden(hidden: boolean): void {
		if (hidden === this.#hidden) return;
		this.#hidden = hidden;
		const map = this.#map;
		if (!map || !this.#scope) return;
		for (const id of [CONE_FILL, CONE_LINE, MOVE_LINE]) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', hidden ? 'none' : 'visible');
		for (const m of this.#markers) m.getElement().style.display = hidden ? 'none' : '';
		map.getCanvas().style.cursor = hidden ? '' : 'crosshair';
		this.#push3d();
		if (hidden) this.#showDrape(false);
		else this.setDrape(this.#drape);
	}

	// --- leaving ---------------------------------------------------------------------------------

	/** Remove everything and pop the snapshot (restores the view exactly, with jumpTo). */
	leave(): void {
		clearTimeout(this.#drapeTimer);
		const scope = this.#scope;
		this.#scope = null;
		this.#scene?.remove(GROUP_3D);
		scope?.dispose();
		this.#drapeShown = false;
		if (scope) this.#app.modes.leave('calibrate');
	}

	/** For good: leave, and never enter again. */
	destroy(): void {
		this.#gone = true;
		this.leave();
		this.#map = null;
	}

	info(): CalibrateMapInfo {
		const map = this.#map;
		return {
			entered: this.entered,
			hidden: this.#hidden,
			markers: this.#markers.map((m) => {
				const el = m.getElement();
				const ll = m.getLngLat();
				return { n: Number(el.dataset.pair), selected: el.classList.contains('selected'), pending: el.classList.contains('pending'), lng: ll.lng, lat: ll.lat };
			}),
			cone: !!this.#solved,
			drape: this.#drapeShown,
			moved: !!this.#solved && groundMetres(this.#o.pole, [this.#solved.pose.lon, this.#solved.pose.lat]) > MOVED_M,
			scene: this.#scene ? { ...this.#built } : null,
			buildingsOpacity: map?.getLayer(BUILDINGS_LAYER) ? map.getPaintProperty(BUILDINGS_LAYER, 'fill-extrusion-opacity') : null
		};
	}
}
