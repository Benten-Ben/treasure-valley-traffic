import { describe, expect, it } from 'vitest';
import type { TrackStep } from '#lib/contracts/tracks.js';
import { Clock } from '#lib/state/clock.svelte.js';
import {
	bearingTo,
	busAt,
	buildTracks,
	FADE_S,
	Feed,
	HIDE_S,
	metres,
	positionAt,
	runningAt,
	smoothAngle,
	speedText,
	trail,
	WAIT_S,
	type Track
} from './playback.js';

/**
 * docs/14 §14.4 "Playback", the client's tests: positionAt at t0, mid-step
 * and t1, the waiting, stale and hidden transitions, and a ±60 s clock
 * offset that doesn't change positions; plus the feed, running routes,
 * heading and the per-frame budget.
 */

// A bus going east along a street at 43.6° N: 0.001° of longitude is about 80.6 m.
const LAT = 43.6;
const X0 = -116.2;
const dx = (m: number) => m / (111_320 * Math.cos((LAT * Math.PI) / 180));

/** An along step from x metres to y metres east, t0 → t1, with a path that bends through the middle. */
function along(vid: string, t0: number, t1: number, x0: number, x1: number): TrackStep {
	const mid = (x0 + x1) / 2;
	const path = [X0 + dx(x0), LAT, X0 + dx(mid), LAT, X0 + dx(x1), LAT];
	return [vid, t0, t1, 'along', path[0], path[1], 90, (x1 - x0) / (t1 - t0), path];
}

const fix = (vid: string, t0: number, x: number, t1: number | null = null, kind: TrackStep[3] = null, bearing: number | null = 90): TrackStep => [
	vid,
	t0,
	t1,
	kind,
	X0 + dx(x),
	LAT,
	bearing,
	kind === 'still' ? 0 : null,
	null
];

const track = (...steps: TrackStep[]): Track => buildTracks(steps).get(steps[0][0])!;
const east = (lon: number) => (lon - X0) * 111_320 * Math.cos((LAT * Math.PI) / 180);

describe('positionAt', () => {
	const t = track(along('a', 1000, 1010, 0, 100), fix('a', 1010, 100, 1040, 'straight'), fix('a', 1040, 400, 1050, 'still'), fix('a', 1050, 400));

	it('plays an along step at constant speed between t0 and t1', () => {
		const at = positionAt(t, 1000);
		expect(east(at.lon)).toBeCloseTo(0, 3);
		expect(at.state).toBe('moving');
		expect(east(positionAt(t, 1002.5).lon)).toBeCloseTo(25, 1);
		expect(east(positionAt(t, 1005).lon)).toBeCloseTo(50, 1);
		expect(east(positionAt(t, 1009.999).lon)).toBeCloseTo(100, 0);
		expect(positionAt(t, 1005).speed).toBeCloseTo(10, 5);
		expect(positionAt(t, 1005).heading).toBeCloseTo(90, 3);
	});

	it('plays a straight step linearly between the fixes, at t1 the next step begins', () => {
		expect(east(positionAt(t, 1010).lon)).toBeCloseTo(100, 3);
		expect(east(positionAt(t, 1025).lon)).toBeCloseTo(250, 3);
		const at = positionAt(t, 1025);
		expect(at.kind).toBe('straight');
		expect(at.speed).toBeCloseTo(10, 3);
		expect(east(positionAt(t, 1040).lon)).toBeCloseTo(400, 3);
		expect(positionAt(t, 1040).state).toBe('still');
	});

	it('holds a still step at its fix, with the feed bearing', () => {
		const at = positionAt(t, 1045);
		expect(east(at.lon)).toBeCloseTo(400, 3);
		expect(at.speed).toBe(0);
		expect(at.heading).toBe(90);
	});

	it('waits at the newest fix, never extrapolating: waiting, then stale, then hidden', () => {
		const w = positionAt(t, 1050 + WAIT_S - 1);
		expect(w.state).toBe('waiting');
		expect(east(w.lon)).toBeCloseTo(400, 3);
		expect(w.speed).toBe(0);
		const s = positionAt(t, 1050 + WAIT_S + 1);
		expect(s.state).toBe('stale');
		expect(east(s.lon)).toBeCloseTo(400, 3);
		expect(positionAt(t, 1050 + HIDE_S - 1).state).toBe('stale');
		const h = positionAt(t, 1050 + HIDE_S + 1);
		expect(h.state).toBe('hidden');
		expect(h.opacity).toBe(0);
	});

	it('is hidden before its first fix', () => {
		expect(positionAt(t, 999).state).toBe('hidden');
	});

	it('waits at the end of an along step whose next fix has not arrived', () => {
		const only = track(along('b', 1000, 1010, 0, 100));
		const at = positionAt(only, 1020);
		expect(east(at.lon)).toBeCloseTo(100, 3);
		expect(at.state).toBe('waiting');
		expect(at.fix).toBe(1010);
	});

	it('holds through a gap, then fade-jumps in its last 300 ms', () => {
		const g = track(fix('c', 1000, 0, 1200, 'gap'), fix('c', 1200, 900));
		const held = positionAt(g, 1100);
		expect(held.state).toBe('gap');
		expect(east(held.lon)).toBeCloseTo(0, 3);
		expect(held.opacity).toBe(1);
		const out = positionAt(g, 1200 - FADE_S * 0.75);
		expect(east(out.lon)).toBeCloseTo(0, 3);
		expect(out.opacity).toBeCloseTo(0.5, 5);
		const inn = positionAt(g, 1200 - FADE_S * 0.25);
		expect(east(inn.lon)).toBeCloseTo(900, 3);
		expect(inn.opacity).toBeCloseTo(0.5, 5);
		expect(positionAt(g, 1200).state).toBe('waiting');
	});

	it('finds the right step from any hint, forwards and backwards', () => {
		const at = busAt();
		for (const T of [1045, 1001, 1030, 1009, 1049, 1000]) {
			const fresh = positionAt({ ...t, hint: 0 }, T);
			positionAt(t, T, at);
			expect(at.lon).toBe(fresh.lon);
		}
	});
});

describe('the clock', () => {
	it('a client clock ±60 s off gives the same playhead, so the same positions', () => {
		const server = 1_800_000_000; // server time at the first poll
		const playheads = [-60, 0, 60].map((skew) => {
			let wall = (server + skew) * 1000;
			const c = new Clock({ now: () => wall, ticking: false, delay: 90 });
			// Five polls, 10 s apart, 120 ms round trips.
			for (let i = 0; i < 5; i++) {
				const send = wall;
				wall += 120;
				c.sample(server + i * 10 + 0.06, send, wall);
				wall += 10_000 - 120;
			}
			return c.playhead();
		});
		expect(playheads[0]).toBeCloseTo(playheads[1], 6);
		expect(playheads[2]).toBeCloseTo(playheads[1], 6);
		const t = track(along('a', playheads[1] - 5, playheads[1] + 5, 0, 100));
		const [a, b, c] = playheads.map((T) => east(positionAt(t, T).lon));
		expect(a).toBeCloseTo(b, 6);
		expect(c).toBeCloseTo(b, 6);
		expect(b).toBeCloseTo(50, 3);
	});

	it('pauses, plays on behind, and goes back to live', () => {
		let wall = 1_000_000_000_000;
		const c = new Clock({ now: () => wall, ticking: false, delay: 90 });
		expect(c.playhead()).toBeCloseTo(wall / 1000 - 90, 6);
		expect(c.state).toBe('live');
		c.pause();
		const p = c.playhead();
		wall += 95_000;
		expect(c.playhead()).toBe(p);
		c.tick = wall;
		expect(c.label).toBe('PAUSED −3:05');
		c.play();
		expect(c.state).toBe('behind');
		wall += 10_000;
		expect(c.playhead()).toBeCloseTo(p + 10, 6);
		c.goLive();
		expect(c.playhead()).toBeCloseTo(wall / 1000 - 90, 6);
		c.setDelay(180);
		c.tick = wall;
		expect(c.label).toBe('LIVE −3:00');
		expect(c.playhead()).toBeCloseTo(wall / 1000 - 180, 6);
		c.setDelay(45); // not offered: ignored
		expect(c.delay).toBe(180);
	});

	it('says when the feed has stalled, and replays a pinned time from `at` minus the delay', () => {
		let wall = 1_000_000_000_000;
		const c = new Clock({ now: () => wall, ticking: false, delay: 90 });
		c.feed = { lastFix: wall / 1000 - 200, ok: true, at: wall };
		c.tick = wall;
		expect(c.state).toBe('stalled');
		expect(c.label).toBe('LIVE · no new GPS for 3 min');
		const at = Date.parse('2026-10-06T14:30:00Z') / 1000;
		const r = new Clock({ now: () => wall, ticking: false, delay: 90, at });
		expect(r.playhead()).toBeCloseTo(at - 90, 6);
		wall += 5000;
		expect(r.playhead()).toBeCloseTo(at - 85, 6);
		r.tick = wall;
		expect(r.label).toBe('REPLAY · Oct 6');
		r.sample(at + 1000, wall, wall); // a replay keeps its own clock
		expect(r.playhead()).toBeCloseTo(at - 85, 6);
	});
});

describe('the feed', () => {
	it("merges by (bus, t0): a later poll replaces a bus's newest fix", () => {
		const f = new Feed();
		const veh = { a: { label: '1', routeId: '9', routeSource: 'feed' as const, shortName: '9', color: '#2a78d6', textColor: '#ffffff', halo: true, headsign: null } };
		f.merge({ now: 1100, vehicles: veh, steps: [along('a', 1000, 1010, 0, 100), fix('a', 1010, 100)], routeRuns: {}, lastFix: 1010 });
		expect(f.tracks.get('a')!.steps.map((s) => s.t1)).toEqual([1010, null]);
		f.merge({ now: 1110, vehicles: veh, steps: [fix('a', 1010, 100, 1020, 'straight'), fix('a', 1020, 200)], routeRuns: {}, lastFix: 1020 });
		expect(f.tracks.get('a')!.steps.map((s) => [s.t0, s.t1])).toEqual([
			[1000, 1010],
			[1010, 1020],
			[1020, null]
		]);
		expect(f.lastFix).toBe(1020);
	});

	it('prunes steps that ended more than 6 min before the playhead, and buses with none left', () => {
		const f = new Feed();
		f.merge({ now: 2000, vehicles: {}, steps: [along('a', 1000, 1010, 0, 100), fix('a', 1010, 100, 1500, 'gap'), fix('a', 1500, 100), fix('b', 1000, 0)], routeRuns: {}, lastFix: 1500 });
		f.prune(1500 + 300);
		expect(f.tracks.get('a')!.steps.map((s) => s.t0)).toEqual([1010, 1500]);
		f.prune(1000 + HIDE_S + 361);
		expect(f.tracks.has('b')).toBe(false);
	});

	it('replaces everything after a reload', () => {
		const f = new Feed();
		f.merge({ now: 1100, vehicles: {}, steps: [fix('a', 1000, 0)], routeRuns: {}, lastFix: 1000 });
		f.merge({ now: 5000, vehicles: {}, steps: [fix('b', 4900, 0)], routeRuns: {}, lastFix: 4900 }, true);
		expect([...f.tracks.keys()]).toEqual(['b']);
	});
});

describe('running routes', () => {
	const runs: Record<string, [number, number][]> = {
		'9': [[1000, 2000]],
		// Its newest fix is after the playhead; it also had one in the window.
		'10': [[1500, 1600], [2600, 3000]],
		'11': [[100, 200]],
		'12': [[2500, 2600]]
	};

	it('runs at T iff some span starts by T and ends at or after T − 15 min', () => {
		expect([...runningAt(runs, 2000)].sort()).toEqual(['10', '9']);
		// Route 10's newest fix (3000) is after the playhead, but it had none in [T − 900, T]: not running.
		expect([...runningAt(runs, 2550)].sort()).toEqual(['12', '9']);
		expect([...runningAt(runs, 3000)].sort()).toEqual(['10', '12']);
		expect([...runningAt(runs, 1000)].sort()).toEqual(['11', '9']);
	});
});

describe('heading and trails', () => {
	it('turns through the short way round with a 300 ms low-pass', () => {
		expect(smoothAngle(null, 90, 16)).toBe(90);
		expect(smoothAngle(80, null, 16)).toBe(80);
		const h = smoothAngle(350, 10, 300)!;
		// 1 − e^−1 of the way from 350 toward 370.
		expect(h).toBeCloseTo((350 + 20 * (1 - Math.exp(-1))) % 360, 6);
		expect(smoothAngle(10, 350, 1e6)).toBeCloseTo(350, 3);
	});

	it('measures distances and bearings', () => {
		expect(metres(X0, LAT, X0 + dx(100), LAT)).toBeCloseTo(100, 3);
		expect(bearingTo(X0, LAT, X0 + 0.001, LAT)).toBeCloseTo(90, 6);
		expect(bearingTo(X0, LAT, X0, LAT - 0.001)).toBeCloseTo(180, 6);
	});

	it('draws a trail along the paths of the last 5 minutes, up to where the bus is now', () => {
		const t = track(along('a', 1000, 1010, 0, 100), fix('a', 1010, 100, 1040, 'straight'), fix('a', 1040, 400));
		const T = 1025;
		const lines = trail(t, T, positionAt(t, T));
		expect(lines).toHaveLength(1);
		const l = lines[0];
		expect(east(l[0])).toBeCloseTo(0, 3);
		expect(east(l[l.length - 2])).toBeCloseTo(250, 3);
		// From only 5 s back: it starts mid-way through the straight step.
		const short = trail(t, T, positionAt(t, T), 5)[0];
		expect(east(short[0])).toBeCloseTo(100, 3);
	});

	it('says speeds in mph', () => {
		expect(speedText(8)).toBe('18 mph');
		expect(speedText(0.2)).toBe('stopped');
		expect(speedText(null)).toBeNull();
	});
});

describe('the per-frame budget', () => {
	it('places 42 buses in well under 2 ms a frame', () => {
		const steps: TrackStep[] = [];
		for (let b = 0; b < 42; b++) {
			const vid = `bus${b}`;
			for (let i = 0; i < 40; i++) {
				const t0 = 1000 + i * 10;
				const path: number[] = [];
				for (let k = 0; k <= 30; k++) path.push(X0 + dx(i * 100 + (k * 100) / 30) + b * 0.01, LAT + Math.sin(k) * 1e-5);
				steps.push([vid, t0, t0 + 10, 'along', path[0], path[1], 90, 10, path]);
			}
			steps.push([vid, 1400, null, null, X0, LAT, 90, null, null]);
		}
		const tracks = [...buildTracks(steps).values()];
		const at = busAt();
		const frames = 600;
		let heading: number | null = null;
		const start = performance.now();
		for (let f = 0; f < frames; f++) {
			const T = 1000 + (f / frames) * 400;
			for (const t of tracks) {
				positionAt(t, T, at);
				heading = smoothAngle(heading, at.heading, 16);
			}
		}
		const perFrame = (performance.now() - start) / frames;
		expect(perFrame).toBeLessThan(2);
	});
});
