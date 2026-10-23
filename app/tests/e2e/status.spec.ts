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

test.describe('status chip, narrow top bar', () => {
	test('below 1024 px the chip shows its shape and count, and its name is the whole sentence', { tag: '@status' }, async ({ page }) => {
		await page.setViewportSize({ width: 800, height: 800 });
		await stubStatus(page, { sources: { fresh: 1, late: 0, stale: 0, never: 3, failing: 0 }, attention: [], builds: [] });
		await page.goto('/');
		await mapReady(page);

		const chip = page.locator('.status .chip');
		await expect(chip).toBeVisible();
		// The accessible name carries the headline; the visible text is only the shape and the number.
		const name = (await chip.getAttribute('aria-label')) ?? '';
		expect(name).toMatch(/\S/);
		expect(name).toMatch(/\d/);
		const visible = (await chip.innerText()).trim();
		expect(visible).toMatch(/^[●▲■◌]\s*\d+$/);
		expect(visible).not.toContain(name);
		await expect(page.getByRole('button', { name })).toBeVisible();
	});

	test('the "+N" chip stays whole and clear of the right side from 600 to 800 px', { tag: '@status' }, async ({ page }) => {
		await stubStatus(page, FRESH);
		await page.setViewportSize({ width: 800, height: 800 });
		await page.goto('/');
		await mapReady(page);
		for (const width of [800, 768, 700, 600]) {
			await page.setViewportSize({ width, height: 800 });
			const right = (await page.locator('.topbar .right').boundingBox())!;
			// Nothing on the right side runs off the screen.
			expect(right.x + right.width, `${width} px: the right side fits`).toBeLessThanOrEqual(width);
			const more = page.locator('.topbar .chip.more');
			if (await more.count()) {
				const box = (await more.boundingBox())!;
				expect(box.x + box.width, `${width} px: "+N" ends before the right side starts`).toBeLessThanOrEqual(right.x);
			}
		}
	});
});
