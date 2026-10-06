import type { Map, MapGeoJSONFeature, MapMouseEvent } from 'maplibre-gl';
import { PRIORITY, type Interactive, type Selection } from '#lib/layers/types.js';

/**
 * The one picker for the whole map (docs/14 §14.3, "Hover, selection and
 * picking").
 *
 * - It first hit-tests sprites: the overlay's (and later the 3D scene's),
 *   within max(their radius, 14 px) for a mouse and 22 px for touch.
 * - Then MapLibre features in a ±6 px box (±12 px on touch), from the layers
 *   modules registered as interactive.
 * - The highest priority wins (bus > camera > hub > stop > route > lane >
 *   street), then the nearest. Exactly one thing is selected.
 * - Where several routes share the street, the selection lists them all
 *   ("3 routes here: 7 · 8 · 9"), each opening its own card.
 * - Clicks count only while the map is in Explore (a calibration click never
 *   selects a bus); an empty click clears the selection.
 */
export const MOUSE_RADIUS = 14;
export const TOUCH_RADIUS = 22;
export const MOUSE_BOX = 6;
export const TOUCH_BOX = 12;

export interface Hit {
	selection: Selection;
	priority: number;
	/** Screen distance from the point, px (0 for map features under it). */
	distance: number;
}

/** Something drawn outside MapLibre's own layers that can be hit (the overlay, the 3D scene). */
export interface HitSource {
	/** Hits at a screen point; `minRadius` is the least radius any target gets. */
	hits(x: number, y: number, minRadius: number): Hit[];
}

export interface Pick {
	top: Selection | null;
	hits: Hit[];
}

export interface Hover {
	selection: Selection;
	x: number;
	y: number;
}

export interface PickerOptions {
	/** Whether clicks and hover pick now (the map is in Explore). */
	canPick: () => boolean;
	/** Select (or with null, clear). */
	select: (s: Selection | null) => void;
}

/** The best hit, with shared streets folded into one "n routes here" selection. */
export function resolve(hits: Hit[]): Selection | null {
	if (!hits.length) return null;
	const sorted = [...hits].sort((a, b) => b.priority - a.priority || a.distance - b.distance);
	const top = sorted[0];
	if (top.selection.kind !== 'route') return top.selection;
	const routes: Selection[] = [];
	for (const h of sorted) {
		if (h.selection.kind !== 'route' || h.priority !== top.priority) continue;
		if (!routes.some((r) => r.id === h.selection.id && r.layer === h.selection.layer)) routes.push(h.selection);
	}
	if (routes.length < 2) return top.selection;
	routes.sort((a, b) => (a.badge?.text ?? a.title).localeCompare(b.badge?.text ?? b.title, 'en', { numeric: true }));
	const names = routes.map((r) => r.badge?.text ?? r.title);
	return {
		kind: 'routes',
		id: routes.map((r) => `${r.layer}:${r.id}`).join('|'),
		layer: top.selection.layer,
		title: `${routes.length} routes here: ${names.join(' · ')}`,
		fact: 'They share this street',
		source: top.selection.source,
		items: routes
	};
}

export class Picker {
	#map: Map | null = null;
	#sources = new Set<HitSource>();
	#layers = new globalThis.Map<string, Interactive[]>();
	#hoverFns = new Set<(h: Hover | null) => void>();
	#hovered: Hover | null = null;
	#moveFrame = 0;
	#lastMove: MapMouseEvent | null = null;
	#pointer = false;
	#o: PickerOptions;

	constructor(o: PickerOptions) {
		this.#o = o;
	}

	attach(map: Map): void {
		this.#map = map;
		map.on('click', this.#onClick);
		map.on('mousemove', this.#onMove);
		map.on('mouseout', this.#onOut);
	}

	detach(): void {
		const map = this.#map;
		if (!map) return;
		map.off('click', this.#onClick);
		map.off('mousemove', this.#onMove);
		map.off('mouseout', this.#onOut);
		cancelAnimationFrame(this.#moveFrame);
		this.#map = null;
	}

	/** Add a sprite source (the overlay, the scene). Returns its removal. */
	addSource(src: HitSource): () => void {
		this.#sources.add(src);
		return () => this.#sources.delete(src);
	}

	/** Make a module's MapLibre layers clickable. Returns their removal. */
	addLayers(owner: string, interactive: Interactive[]): () => void {
		this.#layers.set(owner, interactive);
		return () => {
			if (this.#layers.get(owner) === interactive) this.#layers.delete(owner);
		};
	}

	/** Everything hit at a screen point, and what a click there selects. */
	pickAt(point: { x: number; y: number }, touch = false): Pick {
		const hits: Hit[] = [];
		const minRadius = touch ? TOUCH_RADIUS : MOUSE_RADIUS;
		for (const src of this.#sources) hits.push(...src.hits(point.x, point.y, minRadius));
		const map = this.#map;
		if (map) {
			const box = touch ? TOUCH_BOX : MOUSE_BOX;
			const byLayer = new globalThis.Map<string, Interactive>();
			for (const list of this.#layers.values())
				for (const it of list) for (const id of it.layerIds) if (map.getLayer(id)) byLayer.set(id, it);
			if (byLayer.size) {
				const features: MapGeoJSONFeature[] = map.queryRenderedFeatures(
					[
						[point.x - box, point.y - box],
						[point.x + box, point.y + box]
					],
					{ layers: [...byLayer.keys()] }
				);
				for (const f of features) {
					const it = byLayer.get(f.layer.id);
					const selection = it?.pick(f);
					if (it && selection) hits.push({ selection, priority: it.priority, distance: 0 });
				}
			}
		}
		return { top: resolve(hits), hits };
	}

	/** Hear about hover changes (for the tooltip); returns the unsubscribe. */
	onHover(fn: (h: Hover | null) => void): () => void {
		this.#hoverFns.add(fn);
		return () => this.#hoverFns.delete(fn);
	}

	get hovered(): Hover | null {
		return this.#hovered;
	}

	/** Listeners hear every move over something (the tooltip follows the cursor) and the leave. */
	#setHover(h: Hover | null) {
		if (!h && !this.#hovered) return;
		this.#hovered = h;
		for (const fn of this.#hoverFns) fn(h);
		const map = this.#map;
		if (map && Boolean(h) !== this.#pointer) {
			this.#pointer = Boolean(h);
			map.getCanvas().style.cursor = h ? 'pointer' : '';
		}
	}

	#onClick = (e: MapMouseEvent) => {
		if (!this.#o.canPick()) return;
		const touch = (e.originalEvent as PointerEvent | undefined)?.pointerType === 'touch';
		this.#o.select(this.pickAt(e.point, touch).top);
	};

	#onMove = (e: MapMouseEvent) => {
		this.#lastMove = e;
		if (this.#moveFrame) return;
		this.#moveFrame = requestAnimationFrame(() => {
			this.#moveFrame = 0;
			const ev = this.#lastMove;
			if (!ev || !this.#map) return;
			if (!this.#o.canPick()) {
				if (this.#hovered) {
					this.#hovered = null;
					this.#pointer = false;
					for (const fn of this.#hoverFns) fn(null);
				}
				return;
			}
			const top = this.pickAt(ev.point).top;
			this.#setHover(top ? { selection: top, x: ev.point.x, y: ev.point.y } : null);
		});
	};

	#onOut = () => {
		cancelAnimationFrame(this.#moveFrame);
		this.#moveFrame = 0;
		if (this.#hovered) this.#setHover(null);
	};
}

export { PRIORITY };
