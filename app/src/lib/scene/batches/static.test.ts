import { describe, expect, it } from 'vitest';
import type { Selection } from '#lib/layers/types.js';
import { circumferenceAt, mercatorX, mercatorY } from '../rtc.js';
import { selectionKey } from '../pick.js';
import { boxesFor, PANEL_SHARE, POST_SPACING_M, RAIL_M, StaticData, type Projector, type StaticSegment } from './static.js';
import { INSTANCE_FLOATS } from './mesh.js';

const LNG = -116.2;
const LAT = 43.6;
/** Degrees of longitude / latitude per metre here. */
const DLNG = 1 / (111195.08 * Math.cos((LAT * Math.PI) / 180));
const DLAT = 1 / 111195.08;

const sel = (id: string): Selection => ({ kind: 'sprite', id, layer: 'fences', title: id });

/** A segment `len` metres east of (east, north) metres from (LNG, LAT). */
function seg(id: string, east: number, north: number, len: number, over: Partial<StaticSegment> = {}): StaticSegment {
	return {
		id,
		from: [LNG + east * DLNG, LAT + north * DLAT],
		to: [LNG + (east + len) * DLNG, LAT + north * DLAT],
		height: 1.8,
		thickness: 0.15,
		look: 'solid',
		color: '#c9b79c',
		pick: sel(id),
		...over
	};
}

const box = (d: StaticData, i: number) => {
	const o = i * INSTANCE_FLOATS;
	return { offset: [...d.f32.slice(o, o + 3)], bx: [...d.f32.slice(o + 3, o + 6)], by: [...d.f32.slice(o + 6, o + 9)], bz: [...d.f32.slice(o + 9, o + 12)], hover: d.f32[o + 20] };
};

describe('static batch: building', () => {
	it('a solid segment is one box, an open one a post every 2.5 m or less, a rail and a panel', () => {
		expect(boxesFor(seg('a', 0, 0, 30))).toBe(1);
		expect(boxesFor(seg('b', 0, 0, 30, { look: 'open' }))).toBe(12 + 1 + 2);
		expect(boxesFor(seg('c', 0, 0, 1, { look: 'open' }))).toBe(1 + 1 + 2);
		const d = new StaticData([seg('a', 0, 0, 10), seg('b', 0, 5, 10, { look: 'open' })]);
		expect(d.boxes).toBe(1 + (4 + 1 + 2));
		expect(d.first[1]).toBe(1);
		expect(d.count[1]).toBe(7);
	});

	it('lays a solid box over its segment: centred, as long as the segment, as thick and as tall as asked', () => {
		const d = new StaticData([seg('a', 0, 0, 20, { thickness: 0.3, height: 2.4 })]);
		const b = box(d, 0);
		expect(Math.hypot(b.by[0], b.by[1])).toBeCloseTo(20, 2);
		expect(Math.hypot(b.bx[0], b.bx[1])).toBeCloseTo(0.3, 5);
		expect(b.bz).toEqual([0, 0, expect.closeTo(2.4, 5)]);
		// Centred on the batch origin: the segment is the whole box.
		expect(b.offset[0]).toBeCloseTo(0, 3);
		expect(b.offset[1]).toBeCloseTo(0, 3);
		// Right-handed (across × along is up), so back faces cull the right way.
		const z = b.bx[0] * b.by[1] - b.bx[1] * b.by[0];
		expect(z).toBeGreaterThan(0);
	});

	it('an open fence: posts along it, a rail at the top and a quarter-height panel under the rail', () => {
		const d = new StaticData([seg('a', 0, 0, 10, { look: 'open', height: 1.6 })]);
		const posts = d.count[0] - 2;
		expect(posts).toBe(5);
		const xs = Array.from({ length: posts }, (_, i) => box(d, i).offset[0]);
		for (let i = 1; i < posts; i++) expect(xs[i] - xs[i - 1]).toBeCloseTo(2.5, 2);
		expect(xs[0]).toBeCloseTo(-5, 2);
		expect(xs[posts - 1]).toBeCloseTo(5, 2);
		for (let i = 0; i < posts; i++) expect(box(d, i).bz[2]).toBeCloseTo(1.6, 5);
		const rail = box(d, posts);
		expect(rail.bz[2]).toBeCloseTo(RAIL_M, 5);
		expect(rail.offset[2]).toBeCloseTo(1.6 - RAIL_M, 5);
		expect(Math.hypot(rail.by[0], rail.by[1])).toBeCloseTo(10, 2);
		const panel = box(d, posts + 1);
		expect(panel.bz[2]).toBeCloseTo(PANEL_SHARE * 1.6, 5);
		expect(panel.offset[2] + panel.bz[2]).toBeCloseTo(rail.offset[2], 5);
	});

	it('has its own origin: the middle of its bounding box, so offsets stay small far from anywhere', () => {
		const d = new StaticData([seg('a', -3000, -2000, 10), seg('b', 3000, 2000, 10)]);
		expect(d.origin.lng).toBeCloseTo(LNG + 5 * DLNG, 6);
		expect(d.origin.lat).toBeCloseTo(LAT, 6);
		expect(d.origin.mx).toBeCloseTo(mercatorX(d.origin.lng), 12);
		expect(d.origin.k).toBeCloseTo(1 / circumferenceAt(LAT), 12);
		const [a, b] = [box(d, 0), box(d, 1)];
		expect(a.offset[0]).toBeCloseTo(-3000, 0);
		expect(b.offset[0]).toBeCloseTo(3000, 0);
		expect(a.offset[1]).toBeCloseTo(-2000, 0);
		expect(b.offset[1]).toBeCloseTo(2000, 0);
		// The batch matrix with an identity map matrix: the origin as Mercator, and metres scaled by k (y flipped).
		const out64 = new Float64Array(16);
		const out32 = new Float32Array(16);
		const id = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
		d.matrix(id, out64, out32);
		expect(out64[12]).toBeCloseTo(mercatorX(d.origin.lng), 12);
		expect(out64[13]).toBeCloseTo(mercatorY(d.origin.lat), 12);
		expect(out64[0]).toBeCloseTo(d.origin.k, 15);
		expect(out64[5]).toBeCloseTo(-d.origin.k, 15);
		expect(out32[12]).toBeCloseTo(out64[12], 6);
	});

	it('is built once per call: reading the matrix and hovering never build it again', () => {
		const d = new StaticData([seg('a', 0, 0, 10), seg('b', 0, 5, 10)]);
		expect(d.builds).toBe(1);
		const v = d.version;
		d.matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], new Float64Array(16), new Float32Array(16));
		d.hits(() => false, 0, 0, 14);
		expect(d.builds).toBe(1);
		expect(d.version).toBe(v);
	});
});

describe('static batch: the ground', () => {
	it('re-grounds from the DEM only when asked, lifting the boxes by the exaggerated ground above the origin’s', () => {
		const d = new StaticData([seg('a', 0, 0, 10, { look: 'open', height: 1.5 }), seg('b', 0, 20, 10)]);
		expect(d.groundedEpoch).toBe(-1);
		let queries = 0;
		// A slope rising 2 m per 10 m east, plus 800 m of ground.
		const slope = (lng: number) => 800 + (lng - LNG) / DLNG / 5;
		d.ground((lng) => (queries++, slope(lng)), 1.3, 7);
		expect(queries).toBe(4);
		expect(d.groundedEpoch).toBe(7);
		expect(d.grounds).toBe(1);
		// Built flat at the start, and again for the terrain's exaggeration; the ground itself rewrites boxes in place.
		expect(d.builds).toBe(2);
		const v = d.version;
		// First post (west end) is lower than the last (east end) by 1.3 × 2 m; the rail slopes the same.
		const first = box(d, 0);
		const last = box(d, 4);
		expect(last.offset[2] - first.offset[2]).toBeCloseTo(1.3 * 2, 2);
		const rail = box(d, 5);
		expect(rail.by[2]).toBeCloseTo(1.3 * 2, 2);
		// Posts stay upright.
		expect(first.bz[0]).toBe(0);
		expect(first.bz[1]).toBe(0);
		// The origin sits on the mean ground: the matrix lifts by exag × that ground.
		const m64 = new Float64Array(16);
		d.matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], m64, new Float32Array(16));
		expect(m64[14]).toBeCloseTo(1.3 * d.gOrigin * d.origin.k, 9);
		// The DEM refines (new tiles): a second grounding moves the boxes, one more build, one version more.
		d.ground((lng) => slope(lng) + 3, 1.3, 8);
		expect(d.grounds).toBe(2);
		expect(d.version).toBeGreaterThan(v);
		expect(d.groundedEpoch).toBe(8);
		expect(box(d, 4).offset[2] - box(d, 0).offset[2]).toBeCloseTo(1.3 * 2, 2);
		// A changed exaggeration rebuilds from the ground it holds, without reading the DEM again.
		queries = 0;
		d.rebuild(2);
		expect(queries).toBe(0);
		expect(box(d, 4).offset[2] - box(d, 0).offset[2]).toBeCloseTo(2 * 2, 2);
		// Terrain off (exaggeration 0): flat, and heights above ground only.
		d.rebuild(0);
		expect(box(d, 4).offset[2]).toBeCloseTo(0, 6);
		expect(box(d, 0).bz[2]).toBeCloseTo(1.5, 6);
	});
});

describe('static batch: grounding in slices', () => {
	it('reads a slice of the segments per call and finishes the pass over the next calls, grounding the same boxes as one go', () => {
		const segs = Array.from({ length: 20 }, (_, i) => seg(`s${i}`, 0, i * 5, 10));
		const ground = (_lng: number, lat: number) => 800 + (lat - LAT) / DLAT / 10;
		const sliced = new StaticData(segs);
		let queries = 0;
		let calls = 0;
		// Stop at the first check of each call: 8 segments (16 reads).
		const stopAlways = () => true;
		const q = (lng: number, lat: number) => (queries++, ground(lng, lat));
		while (!sliced.step(q, 1, 4, 0, stopAlways)) {
			calls++;
			expect(sliced.groundedEpoch).toBe(-1);
		}
		expect(calls).toBe(2);
		expect(queries).toBe(40);
		expect(sliced.groundedEpoch).toBe(4);
		expect(sliced.grounds).toBe(1);
		// Done and current: asking again for the same epoch reads nothing.
		expect(sliced.step(q, 1, 4, 0, stopAlways)).toBe(true);
		expect(queries).toBe(40);
		const whole = new StaticData(segs);
		whole.ground(ground, 1, 4);
		// The slices zeroed the heights on the first 8 segments' ground; the boxes then differ from the whole pass's only by that zero.
		const shift = whole.gOrigin - sliced.gOrigin;
		for (let i = 0; i < whole.boxes; i++) expect(box(sliced, i).offset[2] - box(whole, i).offset[2]).toBeCloseTo(shift, 3);
		// A new epoch starts a new pass; a slice of it leaves the earlier heights drawn for the rest.
		const before = box(sliced, 19).offset[2];
		expect(sliced.step((lng, lat) => ground(lng, lat) + 5, 1, 5, 0, stopAlways)).toBe(false);
		expect(sliced.groundedEpoch).toBe(4);
		expect(box(sliced, 0).offset[2]).toBeGreaterThan(box(whole, 0).offset[2] - shift + 4);
		expect(box(sliced, 19).offset[2]).toBe(before);
	});
});

describe('static batch: lazy picking', () => {
	/** A top-down orthographic screen: 1 px per metre east and north of the segment origin, height lifts by 0.1 px per metre. */
	function ortho(calls: { n: number }): Projector {
		const m = (LAT * Math.PI) / 180;
		const k = 1 / circumferenceAt(LAT);
		const ox = mercatorX(LNG);
		const oy = mercatorY(LAT);
		void m;
		return (mx, my, z, out) => {
			calls.n++;
			out.x = 400 + (mx - ox) / k;
			out.y = 300 + (my - oy) / k - z * 0.1;
			out.w = 1;
			return true;
		};
	}

	it('projects nothing until a pointer event asks, then hits the segments near the pointer, nearest first', () => {
		const calls = { n: 0 };
		const d = new StaticData([seg('far', 0, 80, 20), seg('near', 0, 0, 20), seg('none', 0, 0, 20, { pick: null })]);
		expect(calls.n).toBe(0);
		const project = ortho(calls);
		const hits = d.hits(project, 410, 303, 14);
		expect(calls.n).toBeGreaterThan(0);
		expect(hits.map((h) => h.selection.id)).toEqual(['near']);
		expect(hits[0].distance).toBeLessThan(14);
		expect(d.hits(project, 410, 360, 14)).toEqual([]);
		// The farther one is hit when the pointer is by it; the pick-less segment never is.
		expect(d.hits(project, 410, 223, 14).map((h) => h.selection.id)).toEqual(['far']);
		// A group priority overrides the pick's.
		expect(d.hits(project, 410, 300, 14, 77)[0].priority).toBe(77);
	});

	it('skips segments behind the camera', () => {
		const d = new StaticData([seg('a', 0, 0, 20)]);
		expect(d.hits(() => false, 400, 300, 14)).toEqual([]);
	});

	it('tints the hovered segment’s boxes and only those, and says when the buffer changed', () => {
		const d = new StaticData([seg('a', 0, 0, 10, { look: 'open' }), seg('b', 0, 20, 10)]);
		const key = selectionKey(sel('a'));
		const v = d.version;
		expect(d.setHover(key)).toBe(true);
		expect(d.version).toBeGreaterThan(v);
		for (let i = 0; i < d.count[0]; i++) expect(box(d, i).hover).toBe(1);
		expect(box(d, d.first[1]).hover).toBe(0);
		expect(d.setHover(key)).toBe(false);
		expect(d.setHover(selectionKey(sel('b')))).toBe(true);
		expect(box(d, 0).hover).toBe(0);
		expect(box(d, d.first[1]).hover).toBe(1);
		expect(d.setHover('')).toBe(true);
		expect(box(d, d.first[1]).hover).toBe(0);
		// A hover that survives a re-ground.
		d.setHover(key);
		d.ground(() => 0, 1, 1);
		expect(box(d, 0).hover).toBe(1);
	});
});
