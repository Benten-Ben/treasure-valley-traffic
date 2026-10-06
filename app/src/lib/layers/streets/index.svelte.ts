import type { MapGeoJSONFeature } from 'maplibre-gl';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { addSlotted } from '#lib/map/order.js';
import { PRIORITY, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import def from './def.js';
import Legend from './Legend.svelte';
import { chevron, CHEVRON, L, ROADS_SOURCE, STREET_LAYERS, streetLayers, type StreetProps } from './streets.js';

export const SOURCE = 'ACHD road centerlines';

/** The Streets module (docs/14 §14.5 until WP4's ramp): road tiles cut by PostGIS, versioned by /api/meta. */
export class StreetsModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{
			layerIds: [L.speed],
			priority: PRIORITY.street,
			pick: (f: MapGeoJSONFeature): Selection => {
				const p = { ...f.properties, id: Number(f.id ?? f.properties?.id) } as StreetProps;
				return {
					kind: 'street',
					id: String(p.id),
					layer: 'streets',
					title: p.name ?? 'Unnamed road',
					fact: p.speed ? `${p.speed} mph posted` : 'Speed not posted',
					source: SOURCE,
					data: p
				};
			}
		}
	];
	#scope: MapScope | null = null;
	#visible = false;
	#destroyed = false;

	async mount(ctx: AppCtx): Promise<void> {
		const tiles = await ctx.dataUrl(`${location.origin}/api/tiles/roads/{z}/{x}/{y}`, 'roads');
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		const scope = (this.#scope = new MapScope(map));
		scope.addSource(ROADS_SOURCE, {
			type: 'vector',
			tiles: [tiles],
			minzoom: 8,
			maxzoom: 16,
			attribution: 'Ada County Highway District'
		});
		scope.addImage(CHEVRON, chevron(), { pixelRatio: 2 });
		addSlotted(map, streetLayers(), def.order, (l, before) => scope.addLayer(l, before));
		this.status = 'ready';
		this.updatedAt = Date.now();
		this.setVisible(this.#visible);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		const map = this.#scope?.map;
		if (!map) return;
		for (const id of STREET_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
	}

	summary(): string | null {
		return 'Ada County roads';
	}

	destroy(): void {
		this.#destroyed = true;
		this.#scope?.dispose();
		this.#scope = null;
	}
}

export function create(): LayerModule {
	return new StreetsModule();
}
