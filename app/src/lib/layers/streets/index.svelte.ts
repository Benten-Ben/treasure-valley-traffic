import type { MapGeoJSONFeature } from 'maplibre-gl';
import { untrack } from 'svelte';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import { addSlotted } from '#lib/map/order.js';
import type { PaddingMove } from '#lib/ui/padding.js';
import { PRIORITY, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import def from './def.js';
import Legend from './Legend.svelte';
import type { RampName } from './ramp.js';
import { chevron, CHEVRON, KEEPER, L, ROADS_SOURCE, selectedFilter, STREET_LAYERS, streetLayers, visibleStreetLayers, type StreetProps } from './streets.js';

export const SOURCE = 'ACHD road centerlines';

/**
 * The Streets module (docs/14 §14.5): road tiles cut by PostGIS, versioned by
 * /api/meta, drawn on the stepped speed ramp. While Transit is on, the pale
 * slate ramp at 70% width replaces the blue one (§14.3 "The color budget"):
 * the two are separate layers on the same source, so switching only changes
 * visibility and fetches no tile.
 *
 * Turning Streets off and on again in the same view fetches no tile either:
 * the keeper layer (KEEPER in streets.ts) holds the road tiles while Streets
 * is hidden, until the map moves (the padding's own jumps don't count:
 * PADDING_MOVE in ui/padding.ts).
 */
export class StreetsModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	/** The ramp drawn now: 'under' while Transit is on. The legend and card follow it. */
	ramp = $state<RampName>('alone');
	Legend = Legend;
	Card = Card;
	interactive: Interactive[] = [
		{
			layerIds: [L.speed, L.speedUnder],
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
	/** The keeper is holding the road tiles: from the first show until the map moves with Streets off. */
	#keeping = false;
	#destroyed = false;
	#stopEffects: (() => void) | null = null;

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
		// A road tile that fails puts ▲ on the button until Retry (§14.3: map source errors go to their layer's status).
		scope.on('error', (e) => {
			if ((e as { sourceId?: string }).sourceId !== ROADS_SOURCE) return;
			this.status = 'stale';
			this.error = `Some road tiles failed to load: ${e.error?.message ?? 'unknown error'}`;
		});
		// Hidden and moving: let the tiles go, so a hidden Streets fetches nothing for the new view. The map's
		// padding following the inspect card isn't a move (its jumpTo fires movestart all the same).
		scope.on('movestart', (e) => {
			if (this.#visible || !this.#keeping || (e as Partial<PaddingMove>).tvtPadding === true) return;
			this.#keeping = false;
			this.#show();
		});
		// The ramp follows Transit: slate while it's on (whether or not its routes have loaded yet).
		this.#stopEffects = $effect.root(() => {
			$effect(() => {
				const ramp: RampName = ctx.layers?.isOn('transit') ? 'under' : 'alone';
				untrack(() => {
					this.ramp = ramp;
					this.#show();
				});
			});
		});
		this.status = 'ready';
		this.updatedAt = Date.now();
		this.#show();
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		this.#show();
	}

	/** Layout visibility only: the layer's on/off, which ramp pair is drawn, and the keeper. */
	#show(): void {
		const map = this.#scope?.map;
		if (!map) return;
		if (this.#visible) this.#keeping = true;
		const shown = visibleStreetLayers(this.#visible, this.ramp);
		if (this.#keeping) shown.add(KEEPER);
		for (const id of [KEEPER, ...STREET_LAYERS]) {
			const want = shown.has(id) ? 'visible' : 'none';
			if (map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== want) map.setLayoutProperty(id, 'visibility', want);
		}
	}

	summary(): string | null {
		return 'Ada County roads';
	}

	/** Outline the selected road (a filter change on its two layers, not new data). */
	selected(s: Selection | null): void {
		const map = this.#scope?.map;
		if (!map) return;
		const id = s?.layer === 'streets' && s.kind === 'street' ? Number(s.id) : null;
		for (const layer of [L.selectedHalo, L.selected]) if (map.getLayer(layer)) map.setFilter(layer, selectedFilter(id));
	}

	destroy(): void {
		this.#destroyed = true;
		this.#stopEffects?.();
		this.#stopEffects = null;
		this.#scope?.dispose();
		this.#scope = null;
	}
}

export function create(): LayerModule {
	return new StreetsModule();
}
