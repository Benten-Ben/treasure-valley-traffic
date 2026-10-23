import { expect, mapReady, test } from './fixtures.js';

/**
 * The status chip (landscape sprint, M1): visible in the top bar, its shape
 * and words match its level, and "Status unknown" when /api/meta has no
 * status. /api/meta is answered by the real server and its `status` is
 * replaced here, so the spec doesn't depend on seeded data.
 */
const FRESH = { sources: { fresh: 1, late: 0, stale: 0, never: 0, failing: 0 }, attention: [], builds: [] };

async function stubStatus(page: import('@playwright/test').Page, status: unknown) {
	await page.route('**/api/meta', async (route) => {
		const res = await route.fetch();
		const body = (await res.json()) as Record<string, unknown>;
		await route.fulfill({ response: res, json: { ...body, status } });
	});
}

test.describe('status chip', () => {
	test('shows the level by shape and words in the top bar', { tag: '@status' }, async ({ page }) => {
		await page.setViewportSize({ width: 1280, height: 800 });
		await stubStatus(page, FRESH);
		await page.goto('/');
		await mapReady(page);

		const chip = page.locator('.status .chip');
		await expect(chip).toBeVisible();
		const text = (await chip.innerText()).trim();
		expect(text.charAt(0)).toMatch(/[●▲■◌]/);
		expect(text).toContain('Data fresh');
		expect(text.charAt(0)).toBe('●');
	});

	test('says "Status unknown" when /api/meta has no status', { tag: '@status' }, async ({ page }) => {
		await page.setViewportSize({ width: 1280, height: 800 });
		await stubStatus(page, null);
		await page.goto('/');
		await mapReady(page);

		const chip = page.locator('.status .chip');
		await expect(chip).toBeVisible();
		const text = (await chip.innerText()).trim();
		expect(text.charAt(0)).toBe('◌');
		expect(text).toContain('Status unknown');
	});
});
