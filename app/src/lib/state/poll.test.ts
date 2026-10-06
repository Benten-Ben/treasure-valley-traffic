import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Poller, type VisibilitySource } from './poll.svelte.js';

/** A document stand-in whose visibility the test flips. */
function fakeDocument() {
	let listeners: (() => void)[] = [];
	const doc = {
		visibilityState: 'visible' as string,
		addEventListener: (_: 'visibilitychange', f: () => void) => void listeners.push(f),
		removeEventListener: (_: 'visibilitychange', f: () => void) => void (listeners = listeners.filter((g) => g !== f)),
		set(state: 'visible' | 'hidden') {
			doc.visibilityState = state;
			for (const f of [...listeners]) f();
		},
		get listeners() {
			return listeners.length;
		}
	};
	return doc;
}

/** Let the poll's promise chain run (fake timers don't touch microtasks). */
const settle = () => vi.advanceTimersByTimeAsync(0);

describe('Poller', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('polls at once, then on its interval', async () => {
		const doc = fakeDocument();
		const fn = vi.fn(async () => {});
		const p = new Poller(fn, { interval: 15_000, visibility: doc as VisibilitySource });
		p.start();
		await settle();
		expect(fn).toHaveBeenCalledTimes(1);
		expect(p.status).toBe('ok');
		await vi.advanceTimersByTimeAsync(14_999);
		expect(fn).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1);
		expect(fn).toHaveBeenCalledTimes(2);
		p.stop();
		await vi.advanceTimersByTimeAsync(60_000);
		expect(fn).toHaveBeenCalledTimes(2);
		expect(doc.listeners).toBe(0);
	});

	it('makes no request while hidden, and polls at once when shown if one is due', async () => {
		const doc = fakeDocument();
		const fn = vi.fn(async () => {});
		const p = new Poller(fn, { interval: 15_000, visibility: doc as VisibilitySource });
		p.start();
		await settle();
		doc.set('hidden');
		await vi.advanceTimersByTimeAsync(60_000);
		expect(fn).toHaveBeenCalledTimes(1);
		doc.set('visible');
		await settle();
		expect(fn).toHaveBeenCalledTimes(2);
		p.stop();
	});

	it('waits out the rest of the interval when shown again early', async () => {
		const doc = fakeDocument();
		const fn = vi.fn(async () => {});
		const p = new Poller(fn, { interval: 15_000, visibility: doc as VisibilitySource });
		p.start();
		await settle();
		await vi.advanceTimersByTimeAsync(5_000);
		doc.set('hidden');
		await vi.advanceTimersByTimeAsync(5_000);
		doc.set('visible');
		await settle();
		expect(fn).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(4_999);
		expect(fn).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1);
		expect(fn).toHaveBeenCalledTimes(2);
		p.stop();
	});

	it("doesn't start while hidden, and starts when shown", async () => {
		const doc = fakeDocument();
		doc.visibilityState = 'hidden';
		const fn = vi.fn(async () => {});
		const p = new Poller(fn, { interval: 15_000, visibility: doc as VisibilitySource });
		p.start();
		await vi.advanceTimersByTimeAsync(60_000);
		expect(fn).not.toHaveBeenCalled();
		doc.set('visible');
		await settle();
		expect(fn).toHaveBeenCalledTimes(1);
		p.stop();
	});

	it('backs off after failures, doubling up to the cap, and recovers', async () => {
		const doc = fakeDocument();
		let fail = true;
		const fn = vi.fn(async () => {
			if (fail) throw new Error('HTTP 500');
		});
		const p = new Poller(fn, { interval: 10_000, maxBackoff: 50_000, visibility: doc as VisibilitySource });
		p.start();
		await settle();
		expect(p.status).toBe('error');
		expect(p.error).toBe('HTTP 500');
		expect(p.delay).toBe(20_000);
		await vi.advanceTimersByTimeAsync(20_000);
		expect(fn).toHaveBeenCalledTimes(2);
		expect(p.delay).toBe(40_000);
		await vi.advanceTimersByTimeAsync(40_000);
		expect(fn).toHaveBeenCalledTimes(3);
		expect(p.delay).toBe(50_000);
		fail = false;
		await vi.advanceTimersByTimeAsync(50_000);
		expect(fn).toHaveBeenCalledTimes(4);
		expect(p.status).toBe('ok');
		expect(p.failures).toBe(0);
		expect(p.delay).toBe(10_000);
		p.stop();
	});

	it('never overlaps a slow poll', async () => {
		const doc = fakeDocument();
		let release: () => void = () => {};
		const fn = vi.fn(() => new Promise<void>((r) => (release = r)));
		const p = new Poller(fn, { interval: 1_000, visibility: doc as VisibilitySource });
		p.start();
		p.poke();
		doc.set('hidden');
		doc.set('visible');
		await vi.advanceTimersByTimeAsync(5_000);
		expect(fn).toHaveBeenCalledTimes(1);
		release();
		await settle();
		await vi.advanceTimersByTimeAsync(1_000);
		expect(fn).toHaveBeenCalledTimes(2);
		p.stop();
	});

	it("a restart right after a poll doesn't poll again at once", async () => {
		const doc = fakeDocument();
		const fn = vi.fn(async () => {});
		const p = new Poller(fn, { interval: 15_000, visibility: doc as VisibilitySource });
		p.start();
		await settle();
		p.stop();
		await vi.advanceTimersByTimeAsync(3_000);
		p.start();
		await settle();
		expect(fn).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(12_000);
		expect(fn).toHaveBeenCalledTimes(2);
		p.stop();
	});

	it('aborts the request in flight when stopped', async () => {
		const doc = fakeDocument();
		let signal: AbortSignal | undefined;
		const fn = vi.fn((s: AbortSignal) => {
			signal = s;
			return new Promise<void>(() => {});
		});
		const p = new Poller(fn, { interval: 15_000, visibility: doc as VisibilitySource });
		p.start();
		p.stop();
		expect(signal?.aborted).toBe(true);
	});
});
