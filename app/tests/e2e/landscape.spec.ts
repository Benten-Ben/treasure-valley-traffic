import type { Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';

/**
 * landscape (landscape sprint plan §4.2 S3b, §5): a few stacks of the base and the Landscape tray, sampled
 * with the fixture's tiles (`TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted)`):
 *
 * 1. the Clay default (Transit and Cameras): Clay, the tray closed and uncounted;
 * 2. Valley with Trees (a layer that keeps the valley look): the tray's count, the one Landscape legend, the
 *    Base menu's rows and Look hint;
 * 3. Valley with Aerial and a tray layer on, where the manifest has imagery;
 * 4. the tray on a phone: a tab in the sheet, rows 44 px tall, the Map tab gives the legends back.
 *
 * What a stack draws from the ground and the contributions is checked by the packages that add them (their
 * own specs toggle their layers through the URL hash); this spec checks the chrome around them.
 */

type Info = { enabled: string[]; flavor: 'valley' | 'clay'; status: Record<string, string> };
const info = (page: Page): Promise<Info> => page.evaluate(() => (globalThis as any).__tvt.layers);
const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'Map layers' });
const HOME = '/#map=15/43.62755/-116.20892/0/45';

test.describe('landscape', () => {
	test('stack 1, the Clay default: Transit and Cameras on Clay, and the tray is closed with no count', { tag: '@landscape' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		await page.goto('/');
		await mapReady(page);
		const i = await info(page);
		expect([...i.enabled].sort()).toEqual(['cameras', 'transit']);
		expect(i.flavor).toBe('clay');
		const landscape = toolbar(page).getByRole('button', { name: 'Landscape', exact: true });
		await expect(landscape).toHaveAttribute('aria-expanded', 'false');
		await expect(landscape.locator('.count')).toHaveCount(0);
		await expect(page.getByRole('region', { name: 'Landscape legend' })).toHaveCount(0);
		await page.screenshot({ path: screenPath('landscape-1-clay-default.png') });
		expect(consoleErrors.filter((e) => !e.startsWith('map error'))).toEqual([]);
	});

	test('stack 2, Valley with Trees: the count, one Landscape legend, and the Base menu says what Auto keeps', { tag: '@landscape' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto(`${HOME}&layers=trees`);
		await mapReady(page);
		expect((await info(page)).flavor, 'Trees keep the valley look under Auto').toBe('valley');
		const landscape = toolbar(page).getByRole('button', { name: 'Landscape', exact: true });
		await expect(landscape.locator('.count')).toHaveText('1');
		// One legend for the tray, a section per layer on.
		const legend = page.getByRole('region', { name: 'Landscape legend' });
		await expect(legend).toBeVisible();
		await expect(legend.getByRole('region', { name: 'Trees legend' })).toBeVisible();
		await expect(page.getByRole('region', { name: 'Trees legend' })).toHaveCount(1);
		// The Base menu: the Look hint names the layers that keep the valley look.
		await toolbar(page).getByRole('button', { name: 'Base' }).click();
		const pop = page.getByRole('dialog', { name: 'Base map' });
		await expect(pop.getByText('Now Map: no data layer is on')).toBeVisible();
		await expect(pop.locator('label[title*="Trees, Fences, Water and Lanes"]')).toHaveCount(1);
		// A row per base contribution, built or with its reason (none, or the fixture's, depending on what is registered).
		for (const row of await pop.locator('[data-contribution]').all()) {
			const built = await row.getAttribute('data-built');
			await expect(row.locator('small')).toContainText(built === 'true' ? 'Built' : 'Not built: ');
		}
		await page.screenshot({ path: screenPath('landscape-2-valley-trees.png') });
	});

	test('stack 3, Valley with Aerial and a tray layer on: the photo and Trees together, still Valley', { tag: '@landscape' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto(`${HOME}&layers=trees`);
		await mapReady(page);
		await toolbar(page).getByRole('button', { name: 'Base' }).click();
		const pop = page.getByRole('dialog', { name: 'Base map' });
		const aerial = pop.getByRole('switch', { name: /Aerial photos/ });
		test.skip((await aerial.count()) === 0, 'the tiles folder has no aerial photos');
		await aerial.check();
		await mapReady(page);
		const i = await info(page);
		expect(i.enabled).toEqual(['trees']);
		expect(i.flavor).toBe('valley');
		await page.screenshot({ path: screenPath('landscape-3-valley-aerial.png') });
	});

	test('stack 4, the tray on a phone: a tab of the sheet, rows 44 px tall, the Map tab gives the legends back', { tag: '@landscape' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.setViewportSize({ width: 390, height: 844 });
		await page.goto(`${HOME}&layers=none`);
		await mapReady(page);
		const tabs = page.getByRole('navigation', { name: 'Map layers' });
		const tab = tabs.getByRole('button', { name: 'Landscape', exact: true });
		await expect(tab).toBeVisible();
		expect((await tab.boundingBox())!.height).toBeGreaterThanOrEqual(44);
		await tab.click();
		await expect(tab).toHaveAttribute('aria-expanded', 'true');
		const sheetTab = page.getByRole('tab', { name: 'Landscape' });
		await expect(sheetTab).toHaveAttribute('aria-selected', 'true');
		const panel = page.getByRole('tabpanel', { name: 'Landscape' });
		const rows = panel.getByRole('button');
		const n = await rows.count();
		expect(n).toBeGreaterThanOrEqual(1);
		for (const row of await rows.all()) expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(44);
		await panel.getByRole('button', { name: /^Trees/ }).click();
		await expect(tab.locator('.count')).toHaveText('1');
		expect(await info(page).then((i) => i.enabled)).toEqual(['trees']);
		expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
		await page.screenshot({ path: screenPath('landscape-4-phone-tray.png') });
		// The Map tab closes the tray tab and shows the Landscape legend.
		await page.getByRole('tab', { name: 'Map' }).click();
		await expect(sheetTab).toHaveCount(0);
		await expect(tab).toHaveAttribute('aria-expanded', 'false');
		await expect(page.getByRole('region', { name: 'Landscape legend' })).toBeVisible();
	});
});
