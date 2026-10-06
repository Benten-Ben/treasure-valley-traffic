import type { Page } from '@playwright/test';
import { expect, mapReady, test } from './fixtures.js';

/**
 * polling (docs/14 §14.11; WP1 acceptance): with a fake clock and the page
 * hidden, the app makes no /api request for 60 s; once visible again, a
 * poll goes out within 1 s.
 */
async function setVisibility(page: Page, state: 'hidden' | 'visible') {
	await page.evaluate((state) => {
		Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
		Object.defineProperty(document, 'hidden', { configurable: true, get: () => state === 'hidden' });
		document.dispatchEvent(new Event('visibilitychange'));
	}, state);
}

test.describe('polling', () => {
	test('stops while hidden and resumes within 1 s of becoming visible', { tag: '@wp1' }, async ({ page }) => {
		const api: string[] = [];
		page.on('request', (r) => {
			if (new URL(r.url()).pathname.startsWith('/api/')) api.push(new URL(r.url()).pathname);
		});
		// Fake timers from the start; time flows normally until we move it by hand.
		await page.clock.install();
		await page.goto('/');
		await mapReady(page);

		// The Transit lens polls the live buses.
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvt.layers?.transit)).toBe(true);
		await page.keyboard.press('4');
		await expect.poll(() => api.filter((p) => p === '/api/transit/vehicles').length).toBeGreaterThan(0);

		await setVisibility(page, 'hidden');
		// Let anything already in flight land, then watch a quiet minute.
		await page.waitForTimeout(500);
		const hiddenFrom = api.length;
		await page.clock.runFor(60_000);
		await page.waitForTimeout(500);
		expect(api.slice(hiddenFrom), 'requests to /api while hidden').toEqual([]);

		const shownFrom = api.length;
		await setVisibility(page, 'visible');
		await page.clock.runFor(1_000);
		await expect.poll(() => api.slice(shownFrom).filter((p) => p === '/api/transit/vehicles').length, { timeout: 5_000 }).toBe(1);

		// And it keeps polling on its interval while visible.
		await page.clock.runFor(15_000);
		await expect.poll(() => api.slice(shownFrom).filter((p) => p === '/api/transit/vehicles').length, { timeout: 5_000 }).toBe(2);
	});
});
