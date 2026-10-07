import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CadenceClass, CamerasLive, LiveView } from '#lib/contracts/live.js';
import type { VisibilitySource } from '#lib/state/poll.svelte.js';
import { batches, LiveFeed } from './live.svelte.js';

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
		}
	};
	return doc;
}

/** A fake /api/cameras/live: records each request's views; answers after `delay` ms. */
function fakeServer(o: { cadence?: (id: number) => CadenceClass; delay?: number; serverAhead?: number } = {}) {
	const calls: { views: number[]; at: number; aborted: () => boolean }[] = [];
	const fetch = vi.fn(async (url: string, init: RequestInit) => {
		const ids = new URL(url, 'http://x').searchParams.get('views')!.split(',').map(Number);
		const signal = init.signal!;
		calls.push({ views: ids, at: Date.now(), aborted: () => signal.aborted });
		if (o.delay) {
			await new Promise<void>((resolve, reject) => {
				const t = setTimeout(resolve, o.delay);
				signal.addEventListener('abort', () => {
					clearTimeout(t);
					reject(new DOMException('aborted', 'AbortError'));
				});
			});
		}
		const now = (Date.now() + (o.serverAhead ?? 0)) / 1000;
		const views: Record<string, LiveView> = {};
		for (const id of ids) {
			const cadence = o.cadence?.(id) ?? 'key';
			views[id] = {
				viewId: id,
				imageId: id + 600,
				source: 'archive',
				frame: { url: `/camera-frames/${id + 600}/d/s.jpg`, firstSeenAt: now - 30, width: 768, height: 466, sha: 'a'.repeat(64) },
				cadence,
				cadenceS: cadence === 'road_weather' ? 600 : 50,
				state: 'ok'
			};
		}
		const body: CamerasLive = { contract: 1, now, views };
		// Not a real Response: its body is read on Node's own schedule, which fake timers don't drive.
		return { ok: true, status: 200, json: async () => body } as unknown as Response;
	});
	return { fetch, calls };
}

const settle = () => vi.advanceTimersByTimeAsync(0);

describe('LiveFeed', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('splits views into requests of at most 12', () => {
		expect(batches([1, 2, 3])).toEqual([[1, 2, 3]]);
		const ids = Array.from({ length: 25 }, (_, i) => i + 1);
		expect(batches(ids).map((b) => b.length)).toEqual([12, 12, 1]);
	});

	it('polls the watched views at once and every 15 s, in one batched request', async () => {
		const s = fakeServer();
		const doc = fakeDocument();
		const feed = new LiveFeed({ fetch: s.fetch, visibility: doc as VisibilitySource });
		const a = feed.watch([26]);
		const b = feed.watch([7, 26]);
		await settle();
		expect(s.calls.map((c) => c.views)).toEqual([[26], [7, 26]]);
		expect(feed.view(26)?.state).toBe('ok');
		expect(feed.view(7)?.imageId).toBe(607);
		await vi.advanceTimersByTimeAsync(15_000);
		expect(s.calls.at(-1)!.views).toEqual([7, 26]);
		expect(s.calls.length).toBe(3);
		a();
		b();
		expect(feed.running).toBe(false);
		feed.destroy();
	});

	it('stops at once when the last view is released, aborting a request in flight', async () => {
		const s = fakeServer({ delay: 2_000 });
		const feed = new LiveFeed({ fetch: s.fetch, visibility: fakeDocument() as VisibilitySource });
		const release = feed.watch([45]);
		await settle();
		expect(s.calls.length).toBe(1);
		await vi.advanceTimersByTimeAsync(500);
		release();
		expect(s.calls[0].aborted()).toBe(true);
		expect(feed.running).toBe(false);
		await vi.advanceTimersByTimeAsync(120_000);
		expect(s.calls.length).toBe(1);
		expect(feed.view(45)).toBeNull();
	});

	it('asks for a view added while a request is in flight as soon as that one lands', async () => {
		const s = fakeServer({ delay: 1_000 });
		const feed = new LiveFeed({ fetch: s.fetch, visibility: fakeDocument() as VisibilitySource });
		const a = feed.watch([1]);
		await settle();
		const b = feed.watch([2]);
		// The first answer lands at 1 s; the next request follows on the next turn (a few ms).
		await vi.advanceTimersByTimeAsync(1_010);
		expect(s.calls.map((c) => c.views)).toEqual([[1], [1, 2]]);
		await vi.advanceTimersByTimeAsync(1_000);
		expect(feed.view(2)).not.toBeNull();
		a();
		b();
	});

	it('shares a view between watchers, and keeps polling while one remains', async () => {
		const s = fakeServer();
		const feed = new LiveFeed({ fetch: s.fetch, visibility: fakeDocument() as VisibilitySource });
		const a = feed.watch([5]);
		const b = feed.watch([5]);
		await settle();
		a();
		expect(feed.watching).toEqual([5]);
		await vi.advanceTimersByTimeAsync(15_000);
		expect(s.calls.length).toBe(2);
		b();
		expect(feed.watching).toEqual([]);
		await vi.advanceTimersByTimeAsync(60_000);
		expect(s.calls.length).toBe(2);
	});

	it('makes no request while the page is hidden', async () => {
		const s = fakeServer();
		const doc = fakeDocument();
		const feed = new LiveFeed({ fetch: s.fetch, visibility: doc as VisibilitySource });
		const release = feed.watch([26]);
		await settle();
		doc.set('hidden');
		await vi.advanceTimersByTimeAsync(120_000);
		expect(s.calls.length).toBe(1);
		doc.set('visible');
		await settle();
		expect(s.calls.length).toBe(2);
		release();
	});

	it('polls every 60 s when every view is a road-weather one, and every 15 s again when another joins', async () => {
		const s = fakeServer({ cadence: (id) => (id >= 900 ? 'road_weather' : 'key') });
		const feed = new LiveFeed({ fetch: s.fetch, visibility: fakeDocument() as VisibilitySource });
		const rw = feed.watch([900, 901]);
		await settle();
		expect(feed.interval).toBe(60_000);
		await vi.advanceTimersByTimeAsync(59_000);
		expect(s.calls.length).toBe(1);
		await vi.advanceTimersByTimeAsync(1_000);
		expect(s.calls.length).toBe(2);
		const key = feed.watch([26]);
		await settle();
		expect(s.calls.length).toBe(3);
		expect(feed.interval).toBe(15_000);
		await vi.advanceTimersByTimeAsync(15_000);
		expect(s.calls.length).toBe(4);
		key();
		rw();
	});

	it('ages pictures on the server’s clock', async () => {
		const s = fakeServer({ serverAhead: 5_000 });
		const feed = new LiveFeed({ fetch: s.fetch, visibility: fakeDocument() as VisibilitySource });
		const release = feed.watch([26]);
		await settle();
		const f = feed.view(26)!.frame!;
		expect(feed.ageOf(f)).toBeCloseTo(30, 0);
		expect(feed.ageOf(f, Date.now() + 10_000)).toBeCloseTo(40, 0);
		release();
	});

	it('splits more than 12 views into parallel requests', async () => {
		const s = fakeServer();
		const feed = new LiveFeed({ fetch: s.fetch, visibility: fakeDocument() as VisibilitySource });
		const ids = Array.from({ length: 14 }, (_, i) => i + 1);
		const release = feed.watch(ids);
		await settle();
		expect(s.calls.map((c) => c.views.length)).toEqual([12, 2]);
		expect(Object.keys(feed.views).length).toBe(14);
		release();
	});
});
