import { describe, expect, it } from 'vitest';
import { clampFps, Loop } from './loop.js';

/** A fake clock, rAF queue and visibility. */
function harness() {
	let now = 0;
	let next = 1;
	const frames = new Map<number, (t: number) => void>();
	const vis = {
		visibilityState: 'visible',
		fns: new Set<() => void>(),
		addEventListener: (_: 'visibilitychange', f: () => void) => vis.fns.add(f),
		removeEventListener: (_: 'visibilitychange', f: () => void) => vis.fns.delete(f)
	};
	const repaints: number[] = [];
	const map = {
		triggerRepaint: () => repaints.push(now),
		on: () => {},
		off: () => {}
	};
	const loop = new Loop({
		now: () => now,
		raf: (fn) => {
			const id = next++;
			frames.set(id, fn);
			return id;
		},
		caf: (id) => void frames.delete(id),
		visibility: vis
	});
	/** Run animation frames every `step` ms for `ms`. */
	const run = (ms: number, step = 1000 / 60) => {
		const end = now + ms;
		while (now < end) {
			now += step;
			const due = [...frames.entries()];
			frames.clear();
			for (const [, fn] of due) fn(now);
		}
	};
	const setVisible = (v: boolean) => {
		vis.visibilityState = v ? 'visible' : 'hidden';
		for (const f of vis.fns) f();
	};
	return { loop, map, run, repaints, frames, setVisible };
}

describe('Loop', () => {
	it('clamps the rate to 2–60 fps', () => {
		expect(clampFps(0.5)).toBe(2);
		expect(clampFps(400)).toBe(60);
		expect(clampFps(12)).toBe(12);
	});

	it('asks for nothing while nothing is wanted', () => {
		const h = harness();
		h.loop.attach(h.map);
		h.run(1000);
		expect(h.repaints).toEqual([]);
		expect(h.loop.running).toBe(false);
	});

	it('repaints at the highest rate asked for, and stops when withdrawn', () => {
		const h = harness();
		h.loop.attach(h.map);
		h.loop.want('buses', 5);
		h.run(2000);
		// 5 fps for 2 s: about 10 repaints.
		expect(h.repaints.length).toBeGreaterThanOrEqual(9);
		expect(h.repaints.length).toBeLessThanOrEqual(11);
		h.repaints.length = 0;
		h.loop.want('fast', 30);
		h.run(1000);
		expect(h.repaints.length).toBeGreaterThanOrEqual(28);
		expect(h.repaints.length).toBeLessThanOrEqual(31);
		h.loop.want('fast', null);
		h.loop.want('buses', null);
		h.repaints.length = 0;
		h.run(1000);
		expect(h.repaints.length).toBeLessThanOrEqual(1);
		expect(h.loop.running).toBe(false);
	});

	it('runs tweens at full rate for their duration only', () => {
		const h = harness();
		h.loop.attach(h.map);
		h.loop.tween('fly', 500);
		h.run(1000);
		expect(h.repaints.length).toBeGreaterThanOrEqual(28);
		expect(h.repaints.length).toBeLessThanOrEqual(32);
		expect(h.loop.running).toBe(false);
	});

	it('stops while the tab is hidden and resumes when shown', () => {
		const h = harness();
		h.loop.attach(h.map);
		h.loop.want('buses', 10);
		h.run(500);
		h.setVisible(false);
		h.repaints.length = 0;
		h.run(2000);
		expect(h.repaints).toEqual([]);
		expect(h.frames.size).toBe(0);
		h.setVisible(true);
		h.run(1000);
		expect(h.repaints.length).toBeGreaterThanOrEqual(9);
	});
});
