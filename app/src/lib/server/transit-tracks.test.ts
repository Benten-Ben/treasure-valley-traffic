import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
	assemble,
	badge,
	contrast,
	DEFAULT_WINDOW_S,
	fallbackStep,
	flatPath,
	MAX_WINDOW_S,
	parseAt,
	parseWindow,
	resetTracksCache,
	routeRuns,
	runningAt,
	toStep,
	tracks,
	UNKNOWN_ROUTE,
	type StepRow,
	type TracksBody
} from './transit-tracks.js';
import { TRACKS_CONTRACT } from '#lib/contracts/tracks.js';

const row = (over: Partial<StepRow>): StepRow => ({
	vid: '706',
	t0: 1000,
	t1: 1030,
	lon: -116.2149,
	lat: 43.62143,
	bearing: 305,
	step: null,
	speed: null,
	chord: null,
	path: null,
	...over
});

describe('parameters', () => {
	it('reads window: default 120, capped at 900, whole seconds only', () => {
		expect(parseWindow(null)).toBe(DEFAULT_WINDOW_S);
		expect(parseWindow('')).toBe(DEFAULT_WINDOW_S);
		expect(parseWindow('450')).toBe(450);
		expect(parseWindow('5000')).toBe(MAX_WINDOW_S);
		for (const bad of ['0', '-5', '12.5', 'abc', '1e3']) expect(parseWindow(bad), bad).toBeNull();
	});

	it('reads at: a past ISO time pins the window; a future one is live; junk is an error', () => {
		const now = Date.parse('2026-10-06T17:00:00Z') / 1000;
		expect(parseAt(null, now)).toBeNull();
		expect(parseAt('2026-10-05T20:30:00Z', now)).toBe(Date.parse('2026-10-05T20:30:00Z') / 1000);
		expect(parseAt('2026-10-06T14:30:00.900Z', now)).toBe(Date.parse('2026-10-06T14:30:00Z') / 1000);
		expect(parseAt('2026-10-07T00:00:00Z', now)).toBeNull();
		expect(parseAt('yesterday', now)).toBeUndefined();
	});
});

describe('the badge rule (§14.3)', () => {
	it('flags blue, orange, red and unknown gray for a halo, and not aqua or violet', () => {
		expect(badge('#2a78d6', '#ffffff')).toEqual({ color: '#2a78d6', textColor: '#ffffff', halo: true });
		expect(badge('#eb6834', '#2b2a33').halo).toBe(true);
		expect(badge('#e34948', '#ffffff').halo).toBe(true);
		expect(badge(null, null)).toEqual({ color: UNKNOWN_ROUTE, textColor: '#2b2a33', halo: true });
		expect(badge('#1baf7a', '#2b2a33').halo).toBe(false);
		expect(badge('#4a3aa7', '#ffffff').halo).toBe(false);
	});

	it('matches the contrast table in §14.4', () => {
		expect(contrast('#2a78d6', '#ffffff')).toBeCloseTo(4.42, 2);
		expect(contrast('#8a857c', '#2b2a33')).toBeCloseTo(3.86, 2);
		expect(contrast('#1baf7a', '#2b2a33')).toBeCloseTo(5.03, 2);
	});

	it('picks the better numeral color when the stored one is missing or odd', () => {
		expect(badge('#4a3aa7', null).textColor).toBe('#ffffff');
		expect(badge('#EDA100', 'black').textColor).toBe('#2b2a33');
		expect(badge('#EDA100', 'black').color).toBe('#eda100');
	});
});

describe('steps', () => {
	it('classifies unmatched steps from time and distance', () => {
		expect(fallbackStep(200, 900)).toEqual(['gap', null]);
		expect(fallbackStep(30, 8)).toEqual(['still', 0]);
		expect(fallbackStep(30, 300)).toEqual(['straight', 10]);
	});

	it("gives a bus's newest fix no kind, speed or path", () => {
		expect(toStep(row({ t1: null, step: 'along', speed: 9 }))).toEqual(['706', 1000, null, null, -116.2149, 43.62143, 305, null, null]);
	});

	it('carries an along step with its path, flat lon,lat including the ends', () => {
		const path = JSON.stringify({ type: 'LineString', coordinates: [[-116.2150001, 43.6214], [-116.2149, 43.6215], [-116.2148, 43.6216]] });
		expect(toStep(row({ step: 'along', speed: 7.46, chord: 220, path }))).toEqual([
			'706', 1000, 1030, 'along', -116.2149, 43.62143, 305, 7.5, [-116.215, 43.6214, -116.2149, 43.6215, -116.2148, 43.6216]
		]);
	});

	it('plays an along step without a drawable path as straight', () => {
		const point = JSON.stringify({ type: 'Point', coordinates: [-116.2149, 43.6215] });
		expect(flatPath(point)).toBeNull();
		const s = toStep(row({ step: 'along', speed: 0, chord: 15, path: point }));
		expect([s[3], s[7], s[8]]).toEqual(['straight', 0.5, null]);
	});

	it('joins the two pieces of a path across a loop seam without repeating a point', () => {
		const multi = JSON.stringify({ type: 'MultiLineString', coordinates: [[[0, 0], [1, 0]], [[1, 0], [2, 0]]] });
		expect(flatPath(multi)).toEqual([0, 0, 1, 0, 2, 0]);
	});

	it('falls back for fixes the matcher has not reached, so playback never goes blank', () => {
		expect(toStep(row({ chord: 300 })).slice(3, 9)).toEqual(['straight', -116.2149, 43.62143, 305, 10, null]);
		expect(toStep(row({ t1: 1300, chord: 2000 }))[3]).toBe('gap');
		expect(toStep(row({ chord: 4 }))[3]).toBe('still');
		expect(toStep(row({ step: 'still', speed: 0.3, chord: 4 }))[7]).toBe(0);
		expect(toStep(row({ step: 'gap', speed: 3, t1: 1400 }))[7]).toBeNull();
	});
});

describe('running routes', () => {
	/** A fix every 30 s from `from` to `to`, both included. */
	const every = (route: string, from: number, to: number) => {
		const out = [];
		for (let t = from; t < to; t += 30) out.push({ route, t });
		out.push({ route, t: to });
		return out;
	};
	// A: two runs; B: an early one; C: a run, then a fix after the second playhead;
	// D: only a fix after it; E: an early run and a fix after it.
	const rows = [
		...every('A', 1000, 2000),
		...every('A', 3000, 3600),
		...every('B', 1000, 1500),
		...every('C', 1500, 1800),
		{ route: 'C', t: 3500 },
		{ route: 'D', t: 3500 },
		...every('E', 1000, 1200),
		{ route: 'E', t: 3500 }
	].reverse();
	const runs = routeRuns(rows);

	it('splits a route where its fixes are more than 15 min apart', () => {
		expect(runs).toEqual({
			A: [[1000, 2000], [3000, 3600]],
			B: [[1000, 1500]],
			C: [[1500, 1800], [3500, 3500]],
			D: [[3500, 3500]],
			E: [[1000, 1200], [3500, 3500]]
		});
	});

	it('gives the right running set at three playheads', () => {
		expect([...runningAt(runs, 1200)].sort()).toEqual(['A', 'B', 'E']);
		// C's and E's newest fixes are after this playhead: C ran within 15 min of it, E didn't.
		expect([...runningAt(runs, 2600)].sort()).toEqual(['A', 'C']);
		expect([...runningAt(runs, 3550)].sort()).toEqual(['A', 'C', 'D', 'E']);
	});
});

describe('assemble', () => {
	it('builds vehicles from each bus newest fix, and the contract fields', () => {
		const body = assemble(
			[
				row({ vid: '706', t0: 1000, t1: 1030, chord: 200 }),
				row({
					vid: '706', t0: 1030, t1: null, label: '706', route_id: '9', route_source: 'trip', short_name: '9',
					color: '#eda100', text_color: '#2b2a33', headsign: 'Toward Gary & State'
				}),
				row({ vid: '755', t0: 1010, t1: null, route_id: null })
			],
			[{ route: '9', t: 1030 }],
			1030
		);
		expect(body.contract).toBe(TRACKS_CONTRACT);
		expect(body.steps).toHaveLength(3);
		expect(body.vehicles['706']).toEqual({
			label: '706', routeId: '9', routeSource: 'trip', shortName: '9', color: '#eda100', textColor: '#2b2a33',
			halo: false, headsign: 'Toward Gary & State'
		});
		expect(body.vehicles['755']).toMatchObject({ routeId: null, routeSource: null, color: UNKNOWN_ROUTE, halo: true });
		expect(body.routeRuns).toEqual({ '9': [[1030, 1030]] });
		expect(body.lastFix).toBe(1030);
	});
});

describe('the micro-cache', () => {
	const body: TracksBody = { contract: TRACKS_CONTRACT, vehicles: {}, steps: [], routeRuns: {}, lastFix: 1 };
	beforeEach(() => resetTracksCache());

	it('serves N viewers within 5 s from one query, with a fresh now each time', async () => {
		const load = vi.fn(async () => body);
		const t = 1_791_297_000_000;
		const a = await tracks(load, 120, null, t);
		const b = await tracks(load, 120, null, t + 4_000);
		expect(load).toHaveBeenCalledTimes(1);
		expect(load).toHaveBeenCalledWith(1_791_297_000, 120);
		expect([a.hit, b.hit]).toEqual([false, true]);
		expect(b.body.now).toBe((t + 4_000) / 1000);
		await tracks(load, 120, null, t + 5_001);
		expect(load).toHaveBeenCalledTimes(2);
		await tracks(load, 300, null, t + 5_002);
		expect(load).toHaveBeenCalledTimes(3);
	});

	it('pins now to at, and caches each at on its own', async () => {
		const load = vi.fn(async () => body);
		const at = 1_791_297_000;
		const r = await tracks(load, 120, at, 1_791_308_000_000);
		expect(r.body.now).toBe(at);
		expect(load).toHaveBeenCalledWith(at, 120);
		await tracks(load, 120, at + 1, 1_791_308_000_000);
		expect(load).toHaveBeenCalledTimes(2);
	});

	it('shares one query between concurrent requests and does not keep a failure', async () => {
		let calls = 0;
		const load = vi.fn(async () => {
			calls++;
			if (calls === 1) throw new Error('database down');
			return body;
		});
		const t = 1_791_297_000_000;
		const [x, y] = await Promise.allSettled([tracks(load, 120, null, t), tracks(load, 120, null, t + 10)]);
		expect([x.status, y.status]).toEqual(['rejected', 'rejected']);
		expect(load).toHaveBeenCalledTimes(1);
		const z = await tracks(load, 120, null, t + 20);
		expect(z.hit).toBe(false);
		expect(load).toHaveBeenCalledTimes(2);
	});
});
