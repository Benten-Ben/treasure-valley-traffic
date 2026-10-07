import { describe, expect, it } from 'vitest';
import type { NetworkRoute, NetworkStop } from '#lib/contracts/network.js';
import { metresPerPx } from './bus3d.js';
import { flagColors, NAME_ZOOM, POST_HEIGHT_M, POST_MAX_SCALE, POST_PX, POST_ZOOM, postFade, postScale, StopPosts, stopNameLayer } from './stops3d.js';

const LAT = 43.6;
const route = (id: string, color: string, ghost: string): NetworkRoute => ({ id, rid: Number(id) || 1, shortName: id, longName: null, color, ghost, textColor: '#ffffff', halo: false, sortOrder: null });
const ROUTES = [route('1', '#2a78d6', '#b1c6e2'), route('2', '#eb6834', '#f5b59a'), route('3', '#1baf7a', '#a4d2b2'), route('4', '#eda100', '#f1c17b'), route('5', '#e87ba4', '#f1b3c2')];
const byId = new Map(ROUTES.map((r) => [r.id, r]));
const stop = (id: string, lon: number, lat: number, routes: string[]): NetworkStop => ({ id, name: `Stop ${id}`, lon, lat, routes, segment: null, n: 1, bearing: 90 });

describe('stop posts (§14.4 "Buses and stops")', () => {
	it('dither in over 15.7–16', () => {
		expect(postFade(15.6)).toBe(0);
		expect(postFade(POST_ZOOM - 0.15)).toBeCloseTo(0.5, 6);
		expect(postFade(POST_ZOOM)).toBe(1);
	});

	it('are drawn about 26 px tall until their true size is taller', () => {
		const px = (z: number) => (POST_HEIGHT_M * postScale(z, LAT)) / metresPerPx(z, LAT);
		expect(postScale(POST_ZOOM, LAT)).toBe(POST_MAX_SCALE);
		expect(px(POST_ZOOM)).toBeGreaterThan(18);
		for (let z = 16.5; z <= 19; z += 0.25) expect(px(z), `z${z}`).toBeGreaterThanOrEqual(POST_PX - 1e-9);
		expect(postScale(19.5, LAT)).toBe(1);
	});

	it('fly a flag per route: running ones first in route color, then ghosts, four at most', () => {
		expect(flagColors(['1', '2'], new Set(['2']), byId)).toEqual(['#eb6834', '#b1c6e2', null, null]);
		expect(flagColors(['1', '2', '3', '4', '5'], new Set(['5']), byId)).toEqual(['#e87ba4', '#b1c6e2', '#f5b59a', '#a4d2b2']);
		expect(flagColors(['9'], new Set(['9']), byId)).toEqual([null, null, null, null]);
	});

	it('hand the scene only the posts near the view, sized and faded in place', () => {
		const posts = new StopPosts();
		const stops = [stop('a', -116.2, 43.6, ['1']), stop('b', -116.21, 43.605, ['1', '2']), stop('c', -116.5, 43.7, ['3'])];
		posts.build(stops, (i) => ({ kind: 'stop', id: stops[i].id, layer: 'transit', title: stops[i].name! }));
		expect(posts.all.map((p) => p.id)).toEqual(['stop:a', 'stop:b', 'stop:c']);
		expect(posts.all[1]).toMatchObject({ mesh: 'stop', heading: 90, pick: { kind: 'stop', id: 'b' } });
		const near = posts.near;
		posts.setNear({ getWest: () => -116.22, getEast: () => -116.19, getSouth: () => 43.59, getNorth: () => 43.61 });
		expect(near.map((p) => p.id)).toEqual(['stop:a', 'stop:b']);
		expect(posts.near).toBe(near);
		// In a tilted view the bounds reach far; a radius around the centre keeps it to what can be seen.
		posts.setNear({ getWest: () => -116.3, getEast: () => -116.1, getSouth: () => 43.5, getNorth: () => 43.7 }, [-116.2, 43.6], 500);
		expect(near.map((p) => p.id)).toEqual(['stop:a']);
		posts.setNear({ getWest: () => -116.22, getEast: () => -116.19, getSouth: () => 43.59, getNorth: () => 43.61 });
		expect(posts.setZoom(15.5, LAT)).toBe(false);
		expect(posts.setZoom(17, LAT)).toBe(true);
		expect(near[0].scale).toBeCloseTo(postScale(17, LAT), 9);
		expect(near[0].opacity).toBe(1);
		posts.setRunning(new Set(['2']), byId);
		expect(posts.all[1].slots).toEqual(['#eb6834', '#b1c6e2', null, null]);
	});

	it('name stops from z17, above the base labels', () => {
		const l = stopNameLayer('transit-stops');
		expect(l.slot).toBe('labels');
		expect(l.layer).toMatchObject({ id: 'transit-stop-names', type: 'symbol', source: 'transit-stops', minzoom: NAME_ZOOM });
	});
});
