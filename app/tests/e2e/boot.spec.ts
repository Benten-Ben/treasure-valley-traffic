import { mkdirSync } from 'node:fs';
import { expect, env, mapReady, screenPath, test } from './fixtures.js';

/**
 * boot (docs/14 §14.11): the map loads with every request same-origin, no
 * console errors and a working favicon, and the shell paints before the
 * map's first frame (§14.9 "Shell paint": the `tvt:shell` mark). Once WP1
 * adds the debug handle, the readiness check is `__tvt.ready`.
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

				// The shell (top bar and toolbar, or the phone's tab bar) paints before the map's first frame.
				const marks = await page.evaluate(() => {
					const out: Record<string, number> = {};
					for (const m of performance.getEntriesByType('mark')) if (m.name.startsWith('tvt:') && !(m.name in out)) out[m.name] = Math.round(m.startTime);
					return out;
				});
				test.info().annotations.push({ type: 'shell / first frame (ms)', description: `${marks['tvt:shell']} / ${marks['tvt:first-frame']}` });
				expect(marks['tvt:shell'], 'the shell mark').toBeGreaterThan(0);
				expect(marks['tvt:shell'], "the shell paints no later than the map's first frame").toBeLessThanOrEqual(marks['tvt:first-frame']);

				mkdirSync(env().screens, { recursive: true });
				await page.screenshot({ path: screenPath(`boot-${viewport.width}x${viewport.height}.png`), timeout: 180_000 });
			});
	}
});
