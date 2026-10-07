import { describe, expect, it, vi } from 'vitest';
import type { Map } from 'maplibre-gl';
import { Follow, FOLLOW_FPS } from './follow.svelte.js';

/** A flat map: 1 px per 0.0001° around the centre; render/dragstart/moveend events by hand. */
function fakeMap() {
	let center = { lng: -116.2, lat: 43.6 };
	const handlers: Record<string, Set<() => void>> = {};
	const on = (t: string, h: () => void) => void (handlers[t] ??= new Set()).add(h);
	const off = (t: string, h: () => void) => void handlers[t]?.delete(h);
	const fire = (t: string) => [...(handlers[t] ?? [])].forEach((h) => h());
	const zoom = { scroll: { around: false, on: true }, touch: { around: false, on: true } };
	const handler = (z: { around: boolean; on: boolean }) => ({
		isEnabled: () => z.on,
		enable: (o?: { around?: string }) => {
			z.on = true;
			z.around = o?.around === 'center';
		}
	});
	const map = {
		getCenter: () => center,
		project: (p: [number, number] | { lng: number; lat: number }) => {
			const [lng, lat] = Array.isArray(p) ? p : [p.lng, p.lat];
			return { x: (lng + 116.2) * 10000, y: (43.6 - lat) * 10000 };
		},
		jumpTo: vi.fn((o: { center: [number, number] }) => void (center = { lng: o.center[0], lat: o.center[1] })),
		easeTo: vi.fn((o: { center: [number, number] }) => void (center = { lng: o.center[0], lat: o.center[1] })),
		on,
		off,
		once: (t: string, h: () => void) => {
			const w = () => {
				off(t, w);
				h();
			};
			on(t, w);
		},
		scrollZoom: handler(zoom.scroll),
		touchZoomRotate: handler(zoom.touch)
	};
	return { map, fire, zoom, get center() { return center; } };
}

describe('follow', () => {
	it('eases to the target, then keeps it centred after each frame', () => {
		const f = fakeMap();
		const loop = { want: vi.fn() };
		const follow = new Follow({ reducedMotion: () => false });
		follow.attach(f.map as unknown as Map, loop);
		let pos: [number, number] = [-116.3, 43.65];
		expect(follow.start({ kind: 'bus', id: '2213', label: 'bus 2213', position: () => pos })).toBe(true);
		expect(f.map.easeTo).toHaveBeenCalledWith(expect.objectContaining({ center: [-116.3, 43.65] }));
		expect(loop.want).toHaveBeenCalledWith('follow', FOLLOW_FPS);
		expect(f.zoom.scroll.around && f.zoom.touch.around).toBe(true);
		// While the ease runs, frames don't jump.
		pos = [-116.31, 43.65];
		f.fire('render');
		expect(f.map.jumpTo).not.toHaveBeenCalled();
		f.fire('moveend');
		f.fire('render');
		expect(f.map.jumpTo).toHaveBeenLastCalledWith({ center: [-116.31, 43.65] });
		// Under half a pixel of movement: left alone.
		pos = [-116.31 + 0.00002, 43.65];
		f.fire('render');
		expect(f.map.jumpTo).toHaveBeenCalledTimes(1);
		expect(follow.is('bus', '2213')).toBe(true);
	});

	it('a drag ends it, and puts zooming back as it was', () => {
		const f = fakeMap();
		const loop = { want: vi.fn() };
		const follow = new Follow({ reducedMotion: () => true });
		follow.attach(f.map as unknown as Map, loop);
		follow.start({ kind: 'bus', id: '1', label: 'bus 1', position: () => [-116.25, 43.6] });
		expect(f.map.jumpTo).toHaveBeenCalledWith({ center: [-116.25, 43.6] });
		f.fire('dragstart');
		expect(follow.current).toBeNull();
		expect(loop.want).toHaveBeenLastCalledWith('follow', null);
		expect(f.zoom.scroll.around || f.zoom.touch.around).toBe(false);
		f.fire('render');
		expect(f.map.jumpTo).toHaveBeenCalledTimes(1);
	});

	it('stops when the map leaves Explore, and won’t start outside it', () => {
		const f = fakeMap();
		let explore = true;
		const follow = new Follow({ canFollow: () => explore, reducedMotion: () => true });
		follow.attach(f.map as unknown as Map, null);
		follow.start({ kind: 'bus', id: '1', label: 'bus 1', position: () => [-116.25, 43.6] });
		explore = false;
		f.fire('render');
		expect(follow.current).toBeNull();
		expect(follow.start({ kind: 'bus', id: '1', label: 'bus 1', position: () => null })).toBe(false);
	});
});
