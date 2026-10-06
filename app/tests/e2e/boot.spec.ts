import { mkdirSync } from 'node:fs';
import { expect, env, mapReady, screenPath, test } from './fixtures.js';

/**
 * boot (docs/14 §14.11): the map loads with every request same-origin, no
 * console errors and a working favicon. Once WP1 adds the debug handle, the
 * readiness check is `__tvt.ready`.
 */
test.describe('boot', () => {
	for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
		test(`loads the map same-origin with no console errors at ${viewport.width}×${viewport.height}`,
			{ tag: '@wp0' },
			async ({ page, offsite, consoleErrors, baseURL }) => {
				await page.setViewportSize(viewport);
				const origin = new URL(baseURL!).origin;
				const seen: string[] = [];
				page.on('request', (r) => seen.push(r.url()));
				const res = await page.goto('/');
				expect(res?.status()).toBe(200);
				const how = await mapReady(page);
				test.info().annotations.push({ type: 'ready', description: how });

				expect(offsite, 'requests that would leave the machine').toEqual([]);
				const foreign = seen.filter((u) => !u.startsWith(origin) && !u.startsWith('data:') && !u.startsWith('blob:'));
				expect(foreign).toEqual([]);
				expect(seen.some((u) => u.includes('/tiles/manifest.json'))).toBe(true);
				expect(seen.some((u) => /\/tiles\/.+\.pmtiles/.test(u)), 'basemap tiles requested').toBe(true);
				expect(consoleErrors).toEqual([]);

				// The favicon: Vite inlines a small one as a data: URL; otherwise it must answer 200.
				const icon = await page.locator('link[rel="icon"]').first().getAttribute('href');
				expect(icon).toBeTruthy();
				if (icon!.startsWith('data:')) expect(icon!.length).toBeGreaterThan(40);
				else expect((await page.request.get(new URL(icon!, origin).href)).status()).toBe(200);
				expect(seen.filter((u) => u.endsWith('/favicon.ico')), 'no fallback favicon request').toEqual([]);

				mkdirSync(env().screens, { recursive: true });
				await page.screenshot({ path: screenPath(`boot-${viewport.width}x${viewport.height}.png`), timeout: 180_000 });
			});
	}
});
