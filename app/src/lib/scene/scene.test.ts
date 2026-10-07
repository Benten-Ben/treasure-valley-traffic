import { describe, expect, it } from 'vitest';
import { along, GroundTracker, renderedZ, slopePitch, TWEEN_MS } from './ground.js';
import { pickLayer } from './textures.js';
import { PickIndex, priorityOf, selectionKey } from './pick.js';
import { hprBasis, packColor } from './index.js';
import { PRIORITY, type Selection } from '#lib/layers/types.js';

describe('ground', () => {
	it('renderedZ follows the plan: exag·groundTrue + (trueZ − groundTrue)', () => {
		// A camera 12 m up a pole on 800 m ground, terrain drawn at 1.3×.
		expect(renderedZ(812, 800, 1.3)).toBeCloseTo(1052, 9);
		// At true scale (look-through) nothing changes.
		expect(renderedZ(812, 800, 1)).toBe(812);
		// Terrain off: flat ground at 0, so only the height above the ground is left.
		expect(renderedZ(812, 800, 0)).toBe(12);
		// Something on the ground sits on the drawn ground.
		expect(renderedZ(800, 800, 1.3)).toBeCloseTo(1040, 9);
	});

	it('a still object eases to refined DEM heights over 200 ms; a moving one follows at once', () => {
		const g = new GroundTracker();
		g.begin();
		expect(g.sample('a', -116, 43, 1300, 1.3, 0)).toBeCloseTo(1000, 9);
		// The DEM under it refines by 13 m drawn (10 m true).
		g.begin();
		expect(g.sample('a', -116, 43, 1313, 1.3, 1000)).toBeCloseTo(1000, 6);
		expect(g.tweening).toBe(true);
		g.begin();
		const mid = g.sample('a', -116, 43, 1313, 1.3, 1000 + TWEEN_MS / 2);
		expect(mid).toBeGreaterThan(1000);
		expect(mid).toBeLessThan(1010);
		g.begin();
		expect(g.sample('a', -116, 43, 1313, 1.3, 1000 + TWEEN_MS)).toBeCloseTo(1010, 9);
		expect(g.tweening).toBe(false);
		// Moving: no easing.
		g.begin();
		expect(g.sample('a', -116.001, 43, 1326, 1.3, 2000)).toBeCloseTo(1020, 9);
		expect(g.tweening).toBe(false);
	});

	it('an exaggeration change keeps the true ground, so nothing eases', () => {
		const g = new GroundTracker();
		g.begin();
		g.sample('a', -116, 43, 1300, 1.3, 0);
		g.begin();
		expect(g.sample('a', -116, 43, 1000, 1, 10)).toBeCloseTo(1000, 9);
		expect(g.tweening).toBe(false);
	});

	it('within one terrain epoch a still object isn’t queried again; a new epoch, a move or a frame off screen queries it', () => {
		const g = new GroundTracker();
		let queries = 0;
		const q = (v: number) => () => (queries++, v);
		g.begin();
		g.sample('a', -116, 43, q(1300), 1.3, 0, false, 7);
		g.begin();
		expect(g.sample('a', -116, 43, q(9999), 1.3, 16, false, 7)).toBeCloseTo(1000, 9);
		expect(queries).toBe(1);
		expect(g.queries).toBe(0);
		// The camera moved (a new epoch): queried, and a refined value eases in.
		g.begin();
		g.sample('a', -116, 43, q(1313), 1.3, 32, false, 8);
		expect(queries).toBe(2);
		expect(g.tweening).toBe(true);
		// Not drawn for a frame (off screen), then back: queried and taken at once.
		g.begin();
		g.begin();
		expect(g.sample('a', -116, 43, q(1326), 1.3, 48, false, 8)).toBeCloseTo(1020, 9);
		expect(queries).toBe(3);
		expect(g.peek('a')).toBeCloseTo(1020, 9);
	});

	it('a height from older terrain data isn’t trusted for culling: the next frame queries it again', () => {
		const g = new GroundTracker();
		let queries = 0;
		const q = (v: number) => () => (queries++, v);
		// Queried before the DEM tile under it arrived: MapLibre answers 0.
		g.begin();
		expect(g.sample('a', -116, 43, q(0), 1.3, 0, false, 3, 1)).toBe(0);
		// The same terrain data: the height stands (a still camera queries nothing).
		expect(g.peek('a', 1)).toBe(0);
		g.begin();
		g.sample('a', -116, 43, q(9999), 1.3, 16, false, 3, 1);
		expect(queries).toBe(1);
		// The tile arrived (a new data epoch): no height to cull with, so it's drawn and queried again.
		expect(g.peek('a', 2)).toBeUndefined();
		expect(g.peek('a')).toBe(0);
		g.begin();
		expect(g.sample('a', -116, 43, q(1300), 1.3, 32, false, 4, 2)).toBe(0);
		expect(queries).toBe(2);
		// While it eases up, culling uses where it's going, not the eased height (or it could freeze off screen).
		expect(g.tweening).toBe(true);
		expect(g.peek('a', 2)).toBeCloseTo(1000, 9);
		g.begin();
		expect(g.sample('a', -116, 43, q(1300), 1.3, 32 + TWEEN_MS, false, 4, 2)).toBeCloseTo(1000, 9);
		expect(queries).toBe(2);
	});

	it('under reduced motion heights jump', () => {
		const g = new GroundTracker();
		g.begin();
		g.sample('a', -116, 43, 1300, 1.3, 0);
		g.begin();
		expect(g.sample('a', -116, 43, 1313, 1.3, 1, true)).toBeCloseTo(1010, 9);
	});

	it('slopePitch reads the drawn slope 6 m ahead and behind', () => {
		// A 10% grade rising to the north.
		const src = { queryTerrainElevation: ([, lat]: [number, number]) => (lat - 43) * 111195 * 0.1 + 900 };
		expect(slopePitch(src, -116, 43, 0)).toBeCloseTo((Math.atan(0.1) * 180) / Math.PI, 1);
		expect(slopePitch(src, -116, 43, 180)).toBeCloseTo((-Math.atan(0.1) * 180) / Math.PI, 1);
		expect(slopePitch({ queryTerrainElevation: () => null }, -116, 43, 0)).toBe(0);
		const [lng, lat] = along(-116, 43, 90, 100);
		expect(lat).toBeCloseTo(43, 9);
		expect(lng).toBeGreaterThan(-116);
	});
});

describe('model axes', () => {
	const close = (a: number[], b: number[]) => a.forEach((x, i) => expect(x).toBeCloseTo(b[i], 9));
	it('heading turns +y to the compass bearing; pitch lifts the nose; the axes stay right-handed', () => {
		const [r, f, u] = hprBasis(90, 0, 0);
		close(f, [1, 0, 0]);
		close(r, [0, -1, 0]);
		close(u, [0, 0, 1]);
		const [, f2, u2] = hprBasis(0, 10, 0);
		expect(f2[2]).toBeCloseTo(Math.sin((10 * Math.PI) / 180), 9);
		expect(u2[1]).toBeLessThan(0);
		for (const [h, p, ro] of [
			[37, 5, 0],
			[200, -8, 3]
		]) {
			const [a, b, c] = hprBasis(h, p, ro);
			const cross = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
			close(cross, c);
		}
	});

	it('slot colors pack as RGBA8 with alpha 255, and empty slots as 0', () => {
		expect(packColor('#d1495b')).toBe(0xd1495bff);
		expect(packColor(null)).toBe(0);
	});
});

describe('picking', () => {
	const bus: Selection = { kind: 'bus', id: '2213', layer: 'transit', title: 'Bus 2213' };
	const route: Selection = { kind: 'route', id: '7', layer: 'transit', title: 'Route 7' };

	it('hits within max(radius, the picker’s minimum), with the kind’s priority', () => {
		const p = new PickIndex();
		p.begin();
		p.add({ x: 100, y: 100, r: 6, w: 1, pick: bus, priority: priorityOf(bus) });
		p.commit();
		expect(p.hits(113, 100, 14)).toHaveLength(1);
		expect(p.hits(115, 100, 14)).toHaveLength(0);
		expect(p.hits(121, 100, 22)).toHaveLength(1);
		expect(p.hits(100, 100, 14)[0].priority).toBe(PRIORITY.bus);
		expect(priorityOf(route)).toBe(PRIORITY.route);
		expect(priorityOf(route, 99)).toBe(99);
	});

	it('only a committed frame is hit-tested', () => {
		const p = new PickIndex();
		p.begin();
		p.add({ x: 0, y: 0, r: 30, w: 1, pick: bus, priority: 1 });
		expect(p.hits(0, 0, 14)).toHaveLength(0);
		p.commit();
		expect(p.hits(0, 0, 14)).toHaveLength(1);
	});

	it('a selection key names kind, layer and id', () => {
		expect(selectionKey(bus)).not.toBe(selectionKey({ ...bus, layer: 'other' }));
		expect(selectionKey(null)).toBe('');
	});
});

describe('photo textures', () => {
	it('fills free layers first, then reuses the least recently used', () => {
		expect(pickLayer([], 4)).toBe(0);
		expect(
			pickLayer(
				[
					{ layer: 0, used: 5 },
					{ layer: 2, used: 1 }
				],
				4
			)
		).toBe(1);
		expect(
			pickLayer(
				[
					{ layer: 0, used: 5 },
					{ layer: 1, used: 2 },
					{ layer: 2, used: 9 },
					{ layer: 3, used: 3 }
				],
				4
			)
		).toBe(1);
	});
});
