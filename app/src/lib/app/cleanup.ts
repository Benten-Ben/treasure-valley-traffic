import type { Map, MapEventType, MapLayerEventType } from 'maplibre-gl';

/**
 * Bookkeeping so a map module can clean up after itself (docs/14 §14.8:
 * "every source, layer, handler and marker a module adds is removed in its
 * cleanup"). Each `add…` both does the thing and remembers how to undo it;
 * `dispose()` undoes everything in reverse order and tolerates a map that is
 * already gone.
 */
export class MapScope {
	#undo: (() => void)[] = [];

	constructor(readonly map: Map) {}

	addSource(id: string, source: Parameters<Map['addSource']>[1]): void {
		this.map.addSource(id, source);
		this.#undo.push(() => {
			if (this.map.getSource(id)) this.map.removeSource(id);
		});
	}

	addLayer(layer: Parameters<Map['addLayer']>[0], before?: string): void {
		this.map.addLayer(layer, before);
		this.#undo.push(() => {
			if (this.map.getLayer(layer.id)) this.map.removeLayer(layer.id);
		});
	}

	addImage(id: string, image: Parameters<Map['addImage']>[1], options?: Parameters<Map['addImage']>[2]): void {
		if (this.map.hasImage(id)) return;
		this.map.addImage(id, image, options);
		this.#undo.push(() => {
			if (this.map.hasImage(id)) this.map.removeImage(id);
		});
	}

	/** A handler on one layer's features. */
	onLayer<T extends keyof MapLayerEventType>(
		type: T,
		layerId: string,
		listener: (ev: MapLayerEventType[T] & object) => void
	): void {
		this.map.on(type, layerId, listener);
		this.#undo.push(() => this.map.off(type, layerId, listener));
	}

	/** A handler on the whole map. */
	on<T extends keyof MapEventType>(type: T, listener: (ev: MapEventType[T] & object) => void): void {
		this.map.on(type, listener);
		this.#undo.push(() => this.map.off(type, listener));
	}

	/** Anything else to undo (a marker's remove, a cursor reset). */
	defer(fn: () => void): void {
		this.#undo.push(fn);
	}

	/** Undo everything, newest first. */
	dispose(): void {
		for (const f of this.#undo.splice(0).reverse()) {
			try {
				f();
			} catch {
				// The map may already be removed (leaving the map routes); nothing left to undo then.
			}
		}
	}
}
