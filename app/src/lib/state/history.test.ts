import { describe, expect, it, vi } from 'vitest';
import type { Map } from 'maplibre-gl';
import { CHIP_MS, HISTORY_DEPTH, pushView, sameView, ViewHistory } from './history.svelte.js';
import type { CameraView } from './view.svelte.js';

const view = (zoom: number, lng = -116.2): CameraView => ({ center: [lng, 43.6], zoom, bearing: 0, pitch: 0 });

/** A map with a camera, a fake flyTo that animates until `finish()`, and moveend. */
function fakeMap() {
	let cam = view(10);
	let moving = false;
	let target: CameraView | null = null;
	const handlers = new Set<() => void>();
	const fire = () => {
		for (const h of [...handlers]) h();
	};
	const map = {
		getCenter: () => ({ lng: cam.center[0], lat: cam.center[1] }),
		getZoom: () => cam.zoom,
		getBearing: () => cam.bearing,
		getPitch: () => cam.pitch,
		isMoving: () => moving,
		on: (t: string, h: () => void) => void (t === 'moveend' && handlers.add(h)),
		off: (t: string, h: () => void) => void handlers.delete(h),
		jumpTo: vi.fn((o: Partial<CameraView>) => {
			cam = { ...cam, ...o } as CameraView;
			fire();
		}),
		flyTo(o: Partial<CameraView>) {
			// Interrupting a flight ends it first (MapLibre's stop()).
			if (moving) {
				moving = false;
				fire();
			}
			target = { ...cam, ...o } as CameraView;
			moving = true;
			return map;
		}
	};
	return {
		map,
		get cam() {
			return cam;
		},
		/** Part of the way there. */
		step(f = 0.5) {
			if (!target) return;
			cam = { ...cam, zoom: cam.zoom + (target.zoom - cam.zoom) * f, center: [cam.center[0] + (target.center[0] - cam.center[0]) * f, cam.center[1]] };
		},
		finish() {
			if (!target) return;
			cam = target;
			target = null;
			moving = false;
			fire();
		}
	};
}

describe('view history', () => {
	it('compares views and keeps at most 10', () => {
		expect(sameView(view(10), { ...view(10), bearing: 360 })).toBe(true);
		expect(sameView(view(10), view(10.01))).toBe(false);
		expect(pushView([view(1)], view(1))).toBeNull();
		let s: CameraView[] = [];
		for (let i = 0; i < 15; i++) s = pushView(s, view(i))!;
		expect(s).toHaveLength(HISTORY_DEPTH);
		expect(s[0].zoom).toBe(5);
	});

	it('a programmatic fly pushes the view it left; Backspace flies back', () => {
		const f = fakeMap();
		let now = 1000;
		const h = new ViewHistory({ reducedMotion: () => false, now: () => now });
		h.attach(f.map as unknown as Map);
		f.map.flyTo({ zoom: 15, center: [-116.3, 43.6] });
		expect(h.stack).toEqual([view(10)]);
		expect(h.chipUntil).toBe(1000 + CHIP_MS);
		f.finish();
		now = 2000;
		expect(h.back()).toBe(true);
		expect(h.stack).toEqual([]);
		expect(h.chipUntil).toBe(0);
		f.finish();
		expect(f.cam).toEqual(view(10));
		// Flying back pushed nothing; there's nothing more to go back to.
		expect(h.stack).toEqual([]);
		expect(h.back()).toBe(false);
	});

	it('a fly that interrupts another keeps the view the first one left', () => {
		const f = fakeMap();
		const h = new ViewHistory({ reducedMotion: () => false });
		h.attach(f.map as unknown as Map);
		f.map.flyTo({ zoom: 15 });
		f.step();
		f.map.flyTo({ zoom: 17 });
		f.finish();
		expect(h.stack).toEqual([view(10)]);
		// A later, separate fly pushes where that one ended.
		f.map.flyTo({ zoom: 12 });
		f.finish();
		expect(h.stack.map((v) => v.zoom)).toEqual([10, 17]);
	});

	it('nothing is pushed outside Explore, and a jump is not a fly', () => {
		const f = fakeMap();
		let explore = false;
		const h = new ViewHistory({ canPush: () => explore, reducedMotion: () => false });
		h.attach(f.map as unknown as Map);
		f.map.flyTo({ zoom: 15 });
		f.finish();
		f.map.jumpTo({ zoom: 3 });
		expect(h.stack).toEqual([]);
		explore = true;
		h.fly({ zoom: 8 });
		expect(h.stack.map((v) => v.zoom)).toEqual([3]);
	});

	it('under reduced motion fly() jumps and still pushes; back() jumps', () => {
		const f = fakeMap();
		const h = new ViewHistory({ reducedMotion: () => true });
		h.attach(f.map as unknown as Map);
		h.fly({ zoom: 14 });
		expect(f.map.jumpTo).toHaveBeenCalledWith(expect.objectContaining({ zoom: 14 }));
		expect(f.cam.zoom).toBe(14);
		expect(h.back()).toBe(true);
		expect(f.cam).toEqual(view(10));
	});

	it('detach puts the map’s own flyTo back', () => {
		const f = fakeMap();
		const own = f.map.flyTo;
		const h = new ViewHistory();
		h.attach(f.map as unknown as Map);
		expect(f.map.flyTo).not.toBe(own);
		h.detach();
		expect(f.map.flyTo).toBe(own);
	});
});
