import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveFetcher, imageUrl } from './live511.js';
import { RobotsCache, type RobotsVerdict } from './robots.js';
import { GRAY_16x8, TEAL_24x8, sha, variant } from './live-fixtures.test-util.js';

const ALLOW: RobotsVerdict = { allowed: true, decision: 'allowed', crawlDelayS: null };

/** A fake 511: each request gets a new picture (different bytes), logged with the fake clock's time. */
function fake511() {
	const calls: { image: number; at: number }[] = [];
	let n = 0;
	const fetchImage = vi.fn(async (image: number) => {
		calls.push({ image, at: Date.now() });
		return variant(GRAY_16x8, n++);
	});
	return { calls, fetchImage };
}

beforeEach(() => {
	vi.useFakeTimers({ now: Date.parse('2026-10-06T18:00:00Z') });
});
afterEach(() => {
	vi.useRealTimers();
});

describe('LiveFetcher', () => {
	it('lets N clients polling one view cause at most 1 upstream request per 55 s', async () => {
		const up = fake511();
		const f = new LiveFetcher({ fetchImage: up.fetchImage, robots: async () => ALLOW });
		// 20 clients ask at once: one fetch, shared.
		const first = await Promise.all(Array.from({ length: 20 }, () => f.request(656, 26)));
		expect(up.calls).toHaveLength(1);
		expect(new Set(first.map((o) => o.frame?.sha)).size).toBe(1);
		expect(first.every((o) => o.state === 'ok')).toBe(true);
		// Then 5 clients each poll every 15 s for 10 minutes, at staggered times.
		for (let t = 0; t < 600; t += 3) {
			await vi.advanceTimersByTimeAsync(3_000);
			if (t % 15 < 3 || t % 15 === 6 || t % 15 === 12) await Promise.all([f.request(656, 26), f.request(656, 26)]);
		}
		const gaps = up.calls.slice(1).map((c, i) => c.at - up.calls[i].at);
		expect(Math.min(...gaps)).toBeGreaterThanOrEqual(55_000);
		expect(up.calls.length).toBeLessThanOrEqual(Math.floor(600 / 55) + 1);
		f.stop();
	});

	it('keeps at most 2 upstream requests in flight', async () => {
		const resolvers: (() => void)[] = [];
		let active = 0;
		let most = 0;
		const f = new LiveFetcher({
			robots: async () => ALLOW,
			fetchImage: (image) =>
				new Promise<Uint8Array>((r) => {
					active++;
					most = Math.max(most, active);
					resolvers.push(() => {
						active--;
						r(variant(GRAY_16x8, image));
					});
				})
		});
		const all = Promise.all([1, 2, 3, 4, 5, 6].map((i) => f.request(600 + i, i, 0)));
		await vi.advanceTimersByTimeAsync(0);
		expect(most).toBe(2);
		while (resolvers.length) {
			resolvers.shift()!();
			await vi.advanceTimersByTimeAsync(0);
		}
		await all;
		expect(most).toBe(2);
		expect(f.counts.upstream).toBe(6);
		f.stop();
	});

	it('takes at most 12 distinct images per 10 minutes', async () => {
		const up = fake511();
		const f = new LiveFetcher({ fetchImage: up.fetchImage, robots: async () => ALLOW });
		for (let i = 0; i < 12; i++) expect((await f.request(700 + i, i)).state).toBe('ok');
		const capped = await f.request(800, 99);
		expect(capped).toMatchObject({ state: 'capped', frame: null });
		expect(capped.reason).toMatch(/12 cameras per 10 minutes/);
		expect(up.calls.some((c) => c.image === 800)).toBe(false);
		// Images already in the window keep refreshing.
		await vi.advanceTimersByTimeAsync(60_000);
		expect((await f.request(700, 0)).state).toBe('ok');
		expect(up.calls.filter((c) => c.image === 700)).toHaveLength(2);
		// Refreshing keeps their slots for 3 minutes after the last ask (image 700's, at 1 minute).
		// Once every image's last request is 10 minutes old, the 13th gets its turn.
		await vi.advanceTimersByTimeAsync(9 * 60_000);
		expect((await f.request(800, 99)).state).toBe('capped');
		await vi.advanceTimersByTimeAsync(5 * 60_000);
		const later = await f.request(800, 99);
		expect(later.state).toBe('ok');
		expect(up.calls.filter((c) => c.image === 800)).toHaveLength(1);
		f.stop();
	});

	it('makes no request and answers "blocked" when robots.txt disallows it', async () => {
		const up = fake511();
		const robots = new RobotsCache({ fetch: async () => new Response('User-agent: *\nDisallow: /map/Cctv/\n') });
		const f = new LiveFetcher({ fetchImage: up.fetchImage, robots: (u) => robots.check(u) });
		const o = await f.request(656, 26);
		expect(o).toMatchObject({ state: 'blocked', frame: null, reason: "robots.txt doesn't allow it right now" });
		await vi.advanceTimersByTimeAsync(5 * 60_000);
		expect((await f.request(656, 26)).state).toBe('blocked');
		expect(up.calls).toHaveLength(0);
		f.stop();
	});

	it('counts an unreadable robots.txt as blocked for now', async () => {
		const up = fake511();
		const robots = new RobotsCache({ fetch: async () => new Response('', { status: 502 }) });
		const f = new LiveFetcher({ fetchImage: up.fetchImage, robots: (u) => robots.check(u) });
		expect((await f.request(656, 26)).state).toBe('blocked');
		expect(up.calls).toHaveLength(0);
		f.stop();
	});

	it('checks robots.txt for the 511 image URL', async () => {
		const checked: string[] = [];
		const f = new LiveFetcher({ fetchImage: fake511().fetchImage, robots: async (u) => (checked.push(u), ALLOW) });
		await f.request(656, 26);
		expect(checked).toEqual([imageUrl(656)]);
		expect(imageUrl(656)).toBe('https://511.idaho.gov/map/Cctv/656');
		f.stop();
	});

	it('keeps refreshing for 3 minutes after the last ask, then stops', async () => {
		const up = fake511();
		const f = new LiveFetcher({ fetchImage: up.fetchImage, robots: async () => ALLOW });
		const t0 = Date.now();
		await f.request(656, 26);
		await vi.advanceTimersByTimeAsync(10 * 60_000);
		const at = up.calls.map((c) => (c.at - t0) / 1000);
		expect(at.length).toBeGreaterThanOrEqual(4); // 0, ~55, ~110, ~165 s
		expect(Math.max(...at)).toBeLessThanOrEqual(180);
		f.stop();
	});

	it("keeps a repeat's first seen time, and gives new bytes a new one", async () => {
		let bytes = GRAY_16x8;
		const f = new LiveFetcher({ fetchImage: async () => bytes, robots: async () => ALLOW });
		const a = (await f.request(656, 26)).frame!;
		expect(a).toMatchObject({ sha: sha(GRAY_16x8), width: 16, height: 8, firstSeenAt: Date.now() / 1000 });
		await vi.advanceTimersByTimeAsync(60_000);
		const b = (await f.request(656, 26)).frame!;
		expect(b.sha).toBe(a.sha);
		expect(b.firstSeenAt).toBe(a.firstSeenAt);
		bytes = TEAL_24x8;
		await vi.advanceTimersByTimeAsync(60_000);
		const c = (await f.request(656, 26)).frame!;
		expect(c).toMatchObject({ sha: sha(TEAL_24x8), width: 24 });
		// Seen when the refresher got it, after the change and no later than now.
		expect(c.firstSeenAt).toBeGreaterThan(b.firstSeenAt + 60);
		expect(c.firstSeenAt).toBeLessThanOrEqual(Date.now() / 1000);
		f.stop();
	});

	it('keeps 64 frames in memory, least recently used out first', async () => {
		let n = 0;
		const f = new LiveFetcher({
			fetchImage: async () => variant(GRAY_16x8, n++),
			robots: null,
			limits: { capImages: 1000, minIntervalMs: 0 }
		});
		const first = (await f.request(1, 1)).frame!.sha;
		for (let i = 0; i < 64; i++) await f.request(1000 + i, 1000 + i);
		expect(f.frame(first)).toBeNull();
		f.stop();
	});

	it('reports a failed or broken picture as an error, then retries after 55 s', async () => {
		let answer: () => Uint8Array = () => {
			throw new Error('511 Idaho answered 503');
		};
		const f = new LiveFetcher({ fetchImage: async () => answer(), robots: null });
		expect(await f.request(656, 26)).toMatchObject({ state: 'error', frame: null });
		answer = () => GRAY_16x8.subarray(0, 40);
		await vi.advanceTimersByTimeAsync(30_000);
		expect((await f.request(656, 26)).state).toBe('error'); // not retried yet
		await vi.advanceTimersByTimeAsync(30_000);
		expect((await f.request(656, 26)).reason).toMatch(/not a complete JPEG/);
		answer = () => GRAY_16x8;
		await vi.advanceTimersByTimeAsync(60_000);
		expect((await f.request(656, 26)).state).toBe('ok');
		f.stop();
	});
});
