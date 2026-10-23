import { describe, expect, it } from 'vitest';
import { layerShown, suppressGroups, releaseGroups, type SuppressMap } from '#lib/map/flavors.js';
import type { BaseState } from '#lib/base/types.js';
import { PROTOMAPS_GROUPS } from '#lib/map/style.js';
import paving from './paving.base.js';

/** A map with the basemap's layers (only what suppression reads). */
function fakeMap(ids: string[]): SuppressMap & { layers: Map<string, { visibility: string; minzoom: number; maxzoom: number }> } {
	const layers = new Map(ids.map((id) => [id, { visibility: 'visible', minzoom: 0, maxzoom: 24 }]));
	return {
		layers,
		getLayer: (id: string) => (layers.has(id) ? ({ minzoom: layers.get(id)!.minzoom, maxzoom: layers.get(id)!.maxzoom } as never) : undefined),
		getLayoutProperty: (id: string) => layers.get(id)?.visibility as never,
		setLayoutProperty: (id: string, _k: string, v: string) => void (layers.get(id)!.visibility = v),
		setLayerZoomRange: (id: string, min: number, max: number) => void Object.assign(layers.get(id)!, { minzoom: min, maxzoom: max })
	} as never;
}

const state = (over: Partial<BaseState> = {}): BaseState => ({ flavor: 'valley', aerial: false, layers: new Set(), ...over });

describe('the paving base contribution', () => {
	it('is the roads.paving contribution, with its three source layers and the Lanes cards', () => {
		expect(paving.id).toBe('roads.paving');
		expect(paving.source).toEqual({
			kind: 'landscape',
			sourceLayers: ['roads.paving_lots', 'roads.paving_ways', 'roads.paving_stalls']
		});
		expect(paving.cardsWhen).toBe('lanes');
		expect(paving.looks).toBe('both');
		expect(paving.credit).toContain('OpenStreetMap');
	});

	it('draws its surfaces in the surfaces slot, lots and ways at rank 10, and hides under Aerial', () => {
		for (const l of paving.layers) {
			expect(l.slot).toBe('surfaces');
			expect(l.aerial).toBe('hide');
		}
		expect(paving.layers.find((l) => l.id === 'roads.paving_lots')?.rank).toBe(10);
		expect(paving.layers.find((l) => l.id === 'roads.paving_ways')?.rank).toBe(10);
	});

	it('starts its layers at the plan zooms: lots z14, ways z15.5, stalls z17.5, edges z16.5', () => {
		const min = (id: string) => paving.layers.find((l) => l.id === id)?.minzoom;
		expect(min('roads.paving_lots')).toBe(14);
		expect(min('roads.paving_ways')).toBe(15.5);
		expect(min('roads.paving_edges')).toBe(16.5);
		expect(min('roads.paving_stalls')).toBe(17.5);
	});

	it('hides under Aerial and shows otherwise', () => {
		const lots = paving.layers.find((l) => l.id === 'roads.paving_lots')!;
		expect(layerShown(paving, lots, state({ aerial: false }))).toBe(true);
		expect(layerShown(paving, lots, state({ aerial: true }))).toBe(false);
	});

	it('suppresses the basemap service and paths groups from z15.5', () => {
		expect(paving.suppresses).toEqual({ groups: ['service', 'paths'], fromZoom: 15.5 });
		for (const g of paving.suppresses!.groups) expect(PROTOMAPS_GROUPS[g].length).toBeGreaterThan(0);
	});

	it('keeps paths hidden while another owner (Trails) lets go of it', () => {
		const ids = [...PROTOMAPS_GROUPS.service, ...PROTOMAPS_GROUPS.paths];
		const map = fakeMap(ids);
		suppressGroups(map, paving.id, paving.suppresses!.groups, paving.suppresses!.fromZoom);
		suppressGroups(map, 'roads.trails', ['paths']);
		expect(map.layers.get('roads_other')?.visibility).toBe('none');
		releaseGroups(map, 'roads.trails');
		const other = map.layers.get('roads_other')!;
		expect(other.visibility).toBe('visible');
		expect(other.maxzoom).toBe(15.5);
		releaseGroups(map, paving.id);
		expect(other.maxzoom).toBe(24);
	});

	it('orders its layers as the plan has them: lots and ways at rank 10, edges 11, stalls 12', () => {
		const rank = (id: string) => paving.layers.find((l) => l.id === id)?.rank;
		expect(rank('roads.paving_ways')).toBe(10);
		expect(rank('roads.paving_edges')).toBe(11);
		expect(rank('roads.paving_stalls')).toBe(12);
		expect(rank('roads.paving_ways')!).toBeLessThan(rank('roads.paving_edges')!);
		expect(rank('roads.paving_edges')!).toBeLessThan(rank('roads.paving_stalls')!);
	});
});
