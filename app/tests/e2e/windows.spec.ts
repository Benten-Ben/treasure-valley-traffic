import type { Locator, Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';

/**
 * windows (docs/14 §14.10, WP3 acceptance; §14.11), with the dev-only test
 * window (`?window-test`, which also gives `__tvtWindows`):
 *
 * - 4 windows open, and a 5th replaces the least recently used; with every
 *   window pinned a toast says so;
 * - windows can't go under the bars, and positions persist after a reload
 *   (pinned windows reopen by themselves); docking and keyboard resizing;
 * - Esc closes the focused window, or with focus outside every window the
 *   top one;
 * - a window docked right stops beside the camera widget and the Map /
 *   Aerial switch;
 * - the map's padding follows the fixed chrome, and H, O and Back land in
 *   the visible area (under reduced motion too, through the history); the
 *   inspect card moves nothing, flat or tilted, while a move started with it
 *   open lands left of it, and a click it would cover pans clear;
 * - at 390×844: a tab bar and a sheet (windows as its tabs), no horizontal
 *   scroll, targets ≥ 44 px;
 * - Backspace returns to the view before a programmatic fly;
 * - the camera widget replaces MapLibre's controls; follow tracks and ends.
 *
 * WP12 adds the camera windows' own checks to this spec.
 */

type Rect = { x: number; y: number; w: number; h: number };
type Info = {
	layout: string;
	limit: number;
	safe: { left: number; top: number; right: number; bottom: number };
	pending: { key: string }[];
	list: { key: string; number: number; rect: Rect; pinned: boolean; z: number }[];
};

const VIEW = '#map=14/43.615/-116.2023/0/45&layers=cameras';
/** The map's padding in Explore at 1280×800: the bars, the legend column and the camera widget's (§14.3 "Regions"). */
const CHROME = { top: 76, right: 72, bottom: 104, left: 312 };
const MERIDIAN: [number, number] = [-116.3915, 43.6121];
/**
 * MapLibre's error details, from the start of a test: create.ts warns "map error detail: …" (the error's
 * name and message, its source and tile) beside each "map error" it logs, which the console shows as a
 * bare "map error Error" whatever went wrong.
 */
function mapErrorDetails(page: Page): string[] {
	const details: string[] = [];
	page.on('console', (m) => {
		if (m.type() === 'warning' && m.text().startsWith('map error detail:')) details.push(m.text());
	});
	return details;
}
/** A tile's fetch that failed in transport: "map error detail: Error: Failed to fetch · source … · tile …". */
const FETCH_FAILED = /^map error detail: \w*Error: Failed to fetch( ·|$)/;
/**
 * Console errors less MapLibre's bare "map error Error"s, as long as each of those was a fetch that failed in
 * transport: closer in than the basemap's z15, a range fetch for a tile two overscaled tiles share now and
 * then does ("Failed to fetch"), which no chrome code touches. Any other map error (a source, the style, a
 * layer) stays, by its detail.
 */
const realErrors = (errors: string[], details: string[]) => [...errors.filter((e) => e !== 'map error Error'), ...details.filter((d) => !FETCH_FAILED.test(d))];

async function openTest(page: Page, hash = VIEW) {
	await page.goto(`/?window-test${hash}`);
	await mapReady(page);
	await page.waitForFunction(() => (globalThis as any).__tvtWindows, null, { timeout: 60_000 });
}

/** Let CSS animations and transitions finish (SwiftShader starves them while the map draws), for screenshots. */
async function settle(page: Page) {
	await page
		.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'), null, { timeout: 15_000 })
		.catch(() => {});
}

const info = (page: Page): Promise<Info> => page.evaluate(() => (globalThis as any).__tvtWindows.info());
const open = (page: Page, n: number) => page.evaluate((n) => (globalThis as any).__tvtWindows.open(n), n);
const win = (page: Page, n: number) => page.getByRole('dialog', { name: `Test window ${n}` });
const box = async (l: Locator) => (await l.boundingBox())!;

/** Drag a window by its header (grabbed left of its buttons) so the grab point lands at (mx, my). */
async function dragHeader(page: Page, n: number, mx: number, my: number) {
	const b = await box(win(page, n).locator('header'));
	const gx = b.x + 60;
	const gy = b.y + b.height / 2;
	await page.mouse.move(gx, gy);
	await page.mouse.down();
	await page.mouse.move((gx + mx) / 2, (gy + my) / 2, { steps: 4 });
	await page.mouse.move(mx, my, { steps: 4 });
	await page.mouse.up();
}

/** Drag a window by its header to put its top left at (x, y). */
async function dragTo(page: Page, n: number, x: number, y: number) {
	const b = await box(win(page, n).locator('header'));
	const w = await box(win(page, n));
	await dragHeader(page, n, b.x + 60 + (x - w.x), b.y + b.height / 2 + (y - w.y));
}

test.describe('windows', () => {
	test('4 windows open, and a 5th replaces the least recently used; all pinned → a toast', { tag: '@wp3' }, async ({ page, consoleErrors, offsite }) => {
		test.setTimeout(300_000);
		await openTest(page);
		for (let n = 1; n <= 4; n++) expect(await open(page, n)).toBe(true);
		for (let n = 1; n <= 4; n++) await expect(win(page, n)).toBeVisible();
		let i = await info(page);
		expect(i.layout).toBe('desktop');
		expect(i.list.map((w) => w.number)).toEqual([1, 2, 3, 4]);
		// Number badges, and focus raises: the newest is on top.
		for (let n = 1; n <= 4; n++) await expect(win(page, n)).toHaveAttribute('data-window-number', String(n));
		expect(Math.max(...i.list.map((w) => w.z))).toBe(i.list.find((w) => w.key === 'test:4')!.z);
		// Use window 1 (the oldest), so window 2 becomes the least recently used.
		await win(page, 1).locator('header h2').click();
		i = await info(page);
		expect(i.list.find((w) => w.key === 'test:1')!.z, 'a click raises it').toBe(Math.max(...i.list.map((w) => w.z)));
		await settle(page);
		await page.screenshot({ path: screenPath('windows-four.png') });
		expect(await open(page, 5)).toBe(true);
		await expect(win(page, 2)).toHaveCount(0);
		for (const n of [1, 3, 4, 5]) await expect(win(page, n)).toBeVisible();
		i = await info(page);
		expect(i.list.map((w) => w.key)).toEqual(['test:1', 'test:3', 'test:4', 'test:5']);
		expect(i.list.find((w) => w.key === 'test:5')!.number, 'the newcomer takes the freed badge').toBe(2);
		// Pin all four (from the keyboard: the cascade overlaps their headers): a sixth can't open, and a toast says why.
		for (const n of [1, 3, 4, 5]) {
			await win(page, n).getByRole('button', { name: 'Pin' }).focus();
			await page.keyboard.press('Enter');
		}
		for (const n of [1, 3, 4, 5]) await expect(win(page, n).getByRole('button', { name: 'Unpin' })).toHaveAttribute('aria-pressed', 'true');
		expect(await open(page, 6)).toBe(false);
		await expect(page.getByRole('status').filter({ hasText: 'All 4 windows are pinned' })).toBeVisible();
		expect((await info(page)).list).toHaveLength(4);
		await settle(page);
		await page.screenshot({ path: screenPath('windows-pinned-toast.png') });
		expect(consoleErrors).toEqual([]);
		expect(offsite).toEqual([]);
	});

	test('windows stay between the bars, dock and resize, and keep their place after a reload', { tag: '@wp3' }, async ({ page }) => {
		test.setTimeout(300_000);
		await openTest(page);
		await open(page, 1);
		const w1 = win(page, 1);
		await expect(w1).toBeVisible();
		const topBar = await box(page.locator('header.topbar'));
		const toolbar = await box(page.getByRole('toolbar', { name: 'Map layers' }));
		// Dragged up over the top bar, then down over the toolbar: it stops at the bars.
		await dragHeader(page, 1, 640, 2);
		let b = await box(w1);
		expect(b.y, 'below the top bar').toBeGreaterThanOrEqual(topBar.y + topBar.height);
		await dragHeader(page, 1, 640, 798);
		b = await box(w1);
		expect(b.y + b.height, 'above the toolbar').toBeLessThanOrEqual(toolbar.y);
		// And sideways off the screen: it stays on it.
		await dragHeader(page, 1, 2, 400);
		b = await box(w1);
		expect(b.x).toBeGreaterThanOrEqual(0);
		const safe = (await info(page)).safe;
		expect(b.x, 'snapped to the safe area’s left edge').toBe(safe.left);
		await settle(page);
		await page.screenshot({ path: screenPath('windows-clamped.png') });

		// Dock right, without dragging: beside the camera widget and the Map / Aerial switch, not over them.
		await w1.getByRole('button', { name: 'Dock right' }).click();
		b = await box(w1);
		expect(Math.round(b.x + b.width)).toBe(safe.right);
		const widget = await box(page.getByRole('group', { name: 'Map camera' }));
		const views = page.getByRole('group', { name: 'Map view' });
		const clearOf = (await views.count()) ? Math.min(widget.x, (await box(views)).x) : widget.x;
		expect(b.x + b.width, 'clear of the widget and the switch').toBeLessThanOrEqual(clearOf - 11.5);
		for (const name of ['Pin', 'Dock left', 'Dock right', 'Close Test window 1']) {
			const btn = await box(w1.getByRole('button', { name, exact: true }));
			const hit = await page.evaluate(([x, y]) => Boolean(document.elementFromPoint(x, y)?.closest('[data-window-key="test:1"]')), [btn.x + btn.width / 2, btn.y + btn.height / 2]);
			expect(hit, `${name} is on top`).toBe(true);
		}
		await settle(page);
		await page.screenshot({ path: screenPath('windows-docked-right.png') });
		// Resize from the keyboard: the grip, → wider; the picture keeps 16:9.
		const before = await box(w1.getByRole('img'));
		await w1.getByRole('button', { name: /^Resize/ }).focus();
		await page.keyboard.press('ArrowLeft');
		await page.keyboard.press('ArrowLeft');
		const after = await box(w1.getByRole('img'));
		expect(Math.round(before.width - after.width)).toBe(40);
		expect(after.width / after.height).toBeCloseTo(16 / 9, 1);

		// Put it somewhere particular, open a second and pin it, then reload.
		await dragTo(page, 1, 520, 260);
		const placed = (await info(page)).list.find((w) => w.key === 'test:1')!.rect;
		expect(placed).toMatchObject({ x: 520, y: 260 });
		await open(page, 2);
		await dragTo(page, 2, 700, 120);
		await win(page, 2).getByRole('button', { name: 'Pin' }).click();
		const pinnedAt = (await info(page)).list.find((w) => w.key === 'test:2')!.rect;
		await page.reload();
		await mapReady(page);
		await page.waitForFunction(() => (globalThis as any).__tvtWindows, null, { timeout: 60_000 });
		// Only the pinned window reopens by itself, where it was.
		await expect(win(page, 2)).toBeVisible();
		await expect(win(page, 1)).toHaveCount(0);
		let i = await info(page);
		expect(i.list.map((w) => [w.key, w.pinned])).toEqual([['test:2', true]]);
		expect(i.list[0].rect).toMatchObject({ x: pinnedAt.x, y: pinnedAt.y, w: pinnedAt.w });
		// Opening window 1 again puts it where it was left.
		await open(page, 1);
		i = await info(page);
		expect(i.list.find((w) => w.key === 'test:1')!.rect).toMatchObject({ x: placed.x, y: placed.y, w: placed.w });
		await settle(page);
		await page.screenshot({ path: screenPath('windows-after-reload.png') });
	});

	test('Esc closes the focused window, and focus goes back', { tag: '@wp3' }, async ({ page }) => {
		test.setTimeout(300_000);
		await openTest(page);
		await open(page, 1);
		await expect(win(page, 1)).toBeFocused();
		await open(page, 2);
		await expect(win(page, 2)).toBeFocused();
		await page.keyboard.press('Escape');
		await expect(win(page, 2)).toHaveCount(0);
		await expect(win(page, 1), 'focus went back to where it was').toBeFocused();
		// A control inside a window counts as the window having focus.
		await open(page, 3);
		await win(page, 1).getByRole('button', { name: 'Dock left' }).focus();
		await page.keyboard.press('Escape');
		await expect(win(page, 1)).toHaveCount(0);
		await expect(win(page, 3)).toBeVisible();
		// With focus outside every window, Esc closes the top one (the most recently focused), one per press.
		// Window 4 opens on top (over window 3's header); focusing window 3 raises it.
		await open(page, 4);
		await expect(win(page, 4)).toBeVisible();
		await win(page, 3).focus();
		expect((await info(page)).list.find((w) => w.key === 'test:3')!.z, 'window 3 is on top').toBeGreaterThan((await info(page)).list.find((w) => w.key === 'test:4')!.z);
		await page.locator('canvas.maplibregl-canvas').focus();
		await page.keyboard.press('Escape');
		await expect(win(page, 3)).toHaveCount(0);
		await expect(win(page, 4)).toBeVisible();
		expect((await info(page)).list.map((w) => w.key)).toEqual(['test:4']);
		// The close button closes too.
		await win(page, 4).getByRole('button', { name: 'Close Test window 4' }).click();
		await expect(win(page, 4)).toHaveCount(0);
		// Popovers close before windows: Help first, then the window.
		await open(page, 5);
		await page.locator('canvas.maplibregl-canvas').focus();
		await page.keyboard.press('Shift+Slash');
		await expect(page.getByRole('dialog', { name: 'Keys' })).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(page.getByRole('dialog', { name: 'Keys' })).toHaveCount(0);
		await expect(win(page, 5)).toBeVisible();
		await page.locator('canvas.maplibregl-canvas').focus();
		await page.keyboard.press('Escape');
		await expect(win(page, 5)).toHaveCount(0);
	});

	test('at 390×844: a tab bar and a sheet with the windows as tabs, no horizontal scroll, targets ≥ 44 px', { tag: '@wp3' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		await page.setViewportSize({ width: 390, height: 844 });
		await openTest(page, '#map=12/43.615/-116.2023/0/30');
		const tabbar = page.getByRole('navigation', { name: 'Map layers' });
		await expect(tabbar).toBeVisible();
		await expect(page.getByRole('toolbar', { name: 'Map layers' })).toHaveCount(0);
		const sheet = page.getByRole('region', { name: 'Details' });
		await expect(sheet).toBeVisible();
		// The sheet's three sizes: 25%, then 55% and 90% of the screen, tapping the handle.
		const handle = sheet.getByRole('button', { name: /^Panel size/ });
		const heights: number[] = [];
		for (let k = 0; k < 3; k++) {
			await page.waitForTimeout(400);
			heights.push(Math.round((await box(sheet)).height));
			await handle.click();
		}
		expect(heights[0]).toBeCloseTo(0.25 * 844, -1);
		expect(heights[1]).toBeCloseTo(0.55 * 844, -1);
		expect(heights[2]).toBeGreaterThan(0.75 * 844);
		await page.waitForTimeout(400);
		expect(Math.round((await box(sheet)).height), 'back to 25%').toBeCloseTo(0.25 * 844, -1);

		// Windows open as tabs of the sheet, never floating; at most 3.
		for (let n = 1; n <= 4; n++) await open(page, n);
		const i = await info(page);
		expect(i.layout).toBe('phone');
		expect(i.list.map((w) => w.key)).toEqual(['test:2', 'test:3', 'test:4']);
		await expect(page.getByRole('dialog')).toHaveCount(0);
		const tabs = sheet.getByRole('tab');
		await expect(tabs).toHaveCount(4);
		await expect(sheet.getByRole('tab', { name: /Test window 4/ })).toHaveAttribute('aria-selected', 'true');
		await expect(sheet.getByRole('tabpanel', { name: /Test window 4/ }).getByRole('img')).toBeVisible();
		await page.waitForTimeout(400);
		expect((await box(sheet)).height, 'a window lifts the sheet to 55%').toBeGreaterThanOrEqual(0.55 * 844 - 2);
		await settle(page);
		await page.screenshot({ path: screenPath('windows-phone.png') });

		expect(await page.evaluate(() => document.documentElement.scrollWidth), 'no horizontal scroll').toBeLessThanOrEqual(390);
		// Every visible control is at least 44 px. Links inside the attribution's sentence are inline
		// text (WCAG 2.5.8's inline exception).
		const small = await page.evaluate(() => {
			const sel = 'button, a[href], summary, input, select, [role="button"], [role="tab"], [role="switch"]';
			const out: string[] = [];
			for (const el of document.querySelectorAll<HTMLElement>(sel)) {
				const r = el.getBoundingClientRect();
				if (r.width === 0 || r.height === 0 || getComputedStyle(el).visibility === 'hidden') continue;
				if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
				if (el.matches('.maplibregl-ctrl-attrib-inner a')) continue;
				// A checkbox's target is its label.
				const label = el.matches('input') ? el.closest('label')?.getBoundingClientRect() : null;
				if (label && label.height >= 44 && label.width >= 44) continue;
				if (r.height < 44 || r.width < 44) out.push(`${(el.getAttribute('aria-label') || el.textContent || el.tagName).trim().slice(0, 40)}: ${Math.round(r.width)}×${Math.round(r.height)}`);
			}
			return out;
		});
		expect(small).toEqual([]);
		// Each tab shows its window; the Map tab shows the legends.
		await sheet.getByRole('tab', { name: 'Map' }).click();
		await expect(sheet.getByRole('region', { name: 'Cameras legend' })).toBeVisible();
		await sheet.getByRole('tab', { name: /Test window 2/ }).click();
		await expect(sheet.getByRole('tabpanel', { name: /Test window 2/ })).toBeVisible();
		await sheet.getByRole('tabpanel', { name: /Test window 2/ }).getByRole('button', { name: 'Close Test window 2' }).click();
		await expect(tabs).toHaveCount(3);
		await tabbar.getByRole('button', { name: 'Streets' }).click();
		expect(consoleErrors).toEqual([]);
	});

	test('Backspace returns to the view before a programmatic fly', { tag: '@wp3' }, async ({ page }) => {
		test.setTimeout(300_000);
		await openTest(page, '#map=12.5/43.6/-116.25/-20/40&layers=none');
		const start = await page.evaluate(() => (globalThis as any).__tvt.view);
		// A drag is the viewer's own move: nothing goes on the history.
		const c = await box(page.locator('canvas.maplibregl-canvas'));
		await page.mouse.move(c.x + c.width / 2, c.y + c.height / 2);
		await page.mouse.down();
		await page.mouse.move(c.x + c.width / 2 + 120, c.y + c.height / 2 + 40, { steps: 6 });
		await page.mouse.up();
		await mapReady(page);
		expect(await page.evaluate(() => (globalThis as any).__tvtWindows.history())).toBe(0);
		await expect(page.getByRole('button', { name: /Back to previous view/ })).toHaveCount(0);
		const before = await page.evaluate(() => (globalThis as any).__tvt.view);
		expect(Math.abs(before.center[0] - start.center[0])).toBeGreaterThan(1e-4);

		// H flies home: the chip offers the way back, and Backspace takes it.
		await page.keyboard.press('KeyH');
		await expect(page.getByRole('button', { name: /Back to previous view/ })).toBeVisible();
		await page.waitForFunction(() => !(globalThis as any).__tvt.map.isMoving(), null, { timeout: 60_000 });
		await mapReady(page);
		const home = await page.evaluate(() => (globalThis as any).__tvt.view);
		expect(home.zoom).toBeCloseTo(13, 3);
		await settle(page);
		await page.screenshot({ path: screenPath('windows-back-chip.png') });
		await page.keyboard.press('Backspace');
		await page.waitForFunction(() => !(globalThis as any).__tvt.map.isMoving(), null, { timeout: 60_000 });
		await mapReady(page);
		const back = await page.evaluate(() => (globalThis as any).__tvt.view);
		expect(Math.abs(back.center[0] - before.center[0])).toBeLessThan(1e-6);
		expect(Math.abs(back.center[1] - before.center[1])).toBeLessThan(1e-6);
		expect(Math.abs(back.zoom - before.zoom)).toBeLessThan(0.01);
		expect(Math.abs(back.bearing - before.bearing)).toBeLessThan(0.01);
		expect(Math.abs(back.pitch - before.pitch)).toBeLessThan(0.01);
		await expect(page.getByRole('button', { name: /Back to previous view/ })).toHaveCount(0);

		// The camera widget's Overview is a fly too, with the chip; Backspace goes back the same way. (Not the
		// chip after the flight: it hides 8 s after the push, which a loaded laptop's flight can outlast. The
		// reduced-motion test below clicks it.)
		await page.getByRole('button', { name: 'Overview: the whole valley' }).click();
		const chip = page.getByRole('button', { name: /Back to previous view/ });
		await expect(chip).toBeVisible();
		await page.waitForFunction(() => !(globalThis as any).__tvt.map.isMoving(), null, { timeout: 60_000 });
		expect((await page.evaluate(() => (globalThis as any).__tvt.view)).pitch).toBeCloseTo(0, 3);
		await page.keyboard.press('Backspace');
		await page.waitForFunction(() => !(globalThis as any).__tvt.map.isMoving(), null, { timeout: 60_000 });
		const again = await page.evaluate(() => (globalThis as any).__tvt.view);
		expect(Math.abs(again.center[0] - before.center[0])).toBeLessThan(1e-6);
		expect(Math.abs(again.zoom - before.zoom)).toBeLessThan(0.01);
		// Nothing left: Backspace does nothing.
		await page.keyboard.press('Backspace');
		await page.waitForTimeout(500);
		const still = await page.evaluate(() => (globalThis as any).__tvt.view);
		expect(still.center).toEqual(again.center);
	});

	test('the camera widget replaces MapLibre’s controls; follow tracks and a drag or Esc ends it', { tag: '@wp3' }, async ({ page }) => {
		test.setTimeout(300_000);
		await openTest(page, '#map=13/43.6/-116.25/30/40&layers=none');
		await expect(page.locator('.maplibregl-ctrl-group')).toHaveCount(0);
		await expect(page.locator('.maplibregl-ctrl-scale')).toBeVisible();
		await expect(page.locator('.maplibregl-ctrl-attrib')).toBeVisible();
		const widget = page.getByRole('group', { name: 'Map camera' });
		await expect(widget).toBeVisible();
		for (const b of await widget.getByRole('button').all()) {
			const r = await box(b);
			expect(Math.round(Math.min(r.width, r.height)), 'widget buttons: 40 px targets').toBeGreaterThanOrEqual(40);
		}
		const view = () => page.evaluate(() => (globalThis as any).__tvt.view);
		const settled = () => page.waitForFunction(() => !(globalThis as any).__tvt.map.isMoving(), null, { timeout: 60_000 });
		await widget.getByRole('button', { name: /Turn back to north/ }).click();
		await settled();
		expect((await view()).bearing).toBeCloseTo(0, 3);
		const z0 = (await view()).zoom;
		await widget.getByRole('button', { name: 'Zoom in' }).click();
		await settled();
		expect((await view()).zoom).toBeCloseTo(z0 + 1, 3);
		await widget.getByRole('button', { name: 'Zoom out' }).click();
		await settled();
		const threeD = widget.getByRole('button', { name: '3D view' });
		await expect(threeD).toHaveAttribute('aria-pressed', 'true');
		await threeD.click();
		await settled();
		expect((await view()).pitch).toBeCloseTo(0, 3);
		await expect(threeD).toHaveAttribute('aria-pressed', 'false');
		await threeD.click();
		await settled();
		expect((await view()).pitch).toBeCloseTo(40, 3);
		await settle(page);
		await page.screenshot({ path: screenPath('windows-camera-widget.png') });

		// Follow: the view keeps the moving target at its centre; Esc ends it.
		expect(await page.evaluate(() => (globalThis as any).__tvtWindows.followTest())).toBe(true);
		await expect(page.getByRole('status').filter({ hasText: 'Following the test target' })).toBeVisible();
		const lng0 = (await view()).center[0];
		await page.waitForTimeout(2500);
		await expect.poll(async () => (await view()).center[0] - lng0, { timeout: 20_000 }).toBeGreaterThan(0.0004);
		await settle(page);
		await page.screenshot({ path: screenPath('windows-follow.png') });
		await page.locator('canvas.maplibregl-canvas').focus();
		await page.keyboard.press('Escape');
		expect(await page.evaluate(() => (globalThis as any).__tvtWindows.following())).toBeNull();
		await expect(page.getByRole('status').filter({ hasText: 'Following' })).toHaveCount(0);
		// And a drag ends it too.
		expect(await page.evaluate(() => (globalThis as any).__tvtWindows.followTest())).toBe(true);
		const c = await box(page.locator('canvas.maplibregl-canvas'));
		await page.mouse.move(c.x + c.width / 2, c.y + c.height / 2);
		await page.mouse.down();
		await page.mouse.move(c.x + c.width / 2 - 80, c.y + c.height / 2, { steps: 5 });
		await page.mouse.up();
		expect(await page.evaluate(() => (globalThis as any).__tvtWindows.following())).toBeNull();
	});
	test('the map padding follows the fixed chrome: H lands in the visible area; the inspect card moves nothing, flat or tilted', { tag: '@wp3' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		const details = mapErrorDetails(page);
		await openTest(page, '#map=13/43.6/-116.25/0/0&layers=none');
		const map = () =>
			page.evaluate(() => {
				const m = (globalThis as any).__tvt.map;
				const c = m.getContainer().getBoundingClientRect();
				return { padding: m.getPadding(), w: c.width, h: c.height, view: (globalThis as any).__tvt.view };
			});
		const at = (lngLat: [number, number]) => page.evaluate((ll) => (globalThis as any).__tvt.map.project(ll), lngLat);
		const settled = () => page.waitForFunction(() => !(globalThis as any).__tvt.map.isMoving(), null, { timeout: 60_000 });
		const card = page.getByRole('region', { name: 'Selected marker' });
		// Below the top bar, above the toolbar, right of the legends, left of the camera widget.
		await expect.poll(async () => (await map()).padding, { timeout: 30_000 }).toEqual(CHROME);
		let m = await map();
		// The link's centre is where it said, drawn in the middle of the visible area.
		expect(Math.abs(m.view.center[0] - -116.25)).toBeLessThan(1e-6);
		expect(Math.abs(m.view.center[1] - 43.6)).toBeLessThan(1e-6);
		const mid = { x: 312 + (m.w - 312 - 72) / 2, y: 76 + (m.h - 76 - 104) / 2 };
		let p = await at([-116.25, 43.6]);
		expect(Math.abs(p.x - mid.x)).toBeLessThan(1.5);
		expect(Math.abs(p.y - mid.y)).toBeLessThan(1.5);

		// The inspect card opens and closes: the padding stays the chrome's, and the picture stays put.
		const fixed: [number, number] = [-116.24, 43.605];
		const before = await at(fixed);
		await page.evaluate(() => (globalThis as any).__tvtWindows.select('A test thing'));
		await expect(card).toBeVisible();
		await page.waitForTimeout(500);
		await settled();
		expect((await map()).padding, 'the card takes no padding').toEqual(CHROME);
		let after = await at(fixed);
		expect(Math.hypot(after.x - before.x, after.y - before.y), 'the map didn’t move').toBeLessThan(1.5);
		await page.keyboard.press('Escape');
		await expect(card).toHaveCount(0);
		await page.waitForTimeout(500);
		await settled();
		expect((await map()).padding).toEqual(CHROME);
		after = await at(fixed);
		expect(Math.hypot(after.x - before.x, after.y - before.y), 'nor when it closes').toBeLessThan(1.5);

		// Tilted and close in, where a new padding would move the perspective and skew the 3D scene (about
		// 65 px at z19.5, pitch 65): ground points across the screen, some under the card, stay within 1.5 px.
		// (The North End, as the trees spec: one downtown z15 basemap tile fails to load from the local tiles.)
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ center: [-116.20892, 43.62755], zoom: 19.5, pitch: 65, bearing: -12 }));
		await mapReady(page);
		const spots: [number, number][] = [
			[400, 260],
			[mid.x, mid.y],
			[860, 600],
			[m.w - 200, 300],
			[m.w - 120, 640]
		];
		const ground = await page.evaluate((s) => s.map(([x, y]) => (globalThis as any).__tvt.map.unproject([x, y]).toArray() as [number, number]), spots);
		const drawn = () => page.evaluate((g) => g.map((ll) => (globalThis as any).__tvt.map.project(ll) as { x: number; y: number }), ground);
		const flat = await drawn();
		for (const [i, q] of flat.entries()) expect(Math.hypot(q.x - spots[i][0], q.y - spots[i][1]), 'the spots are on the ground').toBeLessThan(1);
		await page.evaluate(() => (globalThis as any).__tvtWindows.select('A test thing'));
		await expect(card).toBeVisible();
		await page.waitForTimeout(500);
		await settled();
		await mapReady(page);
		for (const [i, q] of (await drawn()).entries()) expect(Math.hypot(q.x - flat[i].x, q.y - flat[i].y), `spot ${i} as the card opens`).toBeLessThan(1.5);
		await page.keyboard.press('Escape');
		await expect(card).toHaveCount(0);
		await page.waitForTimeout(500);
		await settled();
		for (const [i, q] of (await drawn()).entries()) expect(Math.hypot(q.x - flat[i].x, q.y - flat[i].y), `spot ${i} as it closes`).toBeLessThan(1.5);

		// H: Meridian lands in the middle of the visible area, not of the whole screen.
		await page.keyboard.press('KeyH');
		await settled();
		await mapReady(page);
		m = await map();
		p = await at(MERIDIAN);
		expect(Math.abs(p.x - mid.x)).toBeLessThan(2);
		expect(Math.abs(p.y - mid.y)).toBeLessThan(2);

		// A reload opens at the same view: the padding never drifts the saved centre (a drift would be
		// half the columns' difference, about 2 km here; the hash keeps about a metre).
		await page.waitForTimeout(1500);
		const hash = await page.evaluate(() => location.hash);
		const saved = (await map()).view;
		await page.reload();
		await mapReady(page);
		await expect.poll(async () => (await map()).padding).toEqual(CHROME);
		const again = (await map()).view;
		expect(Math.abs(again.center[0] - saved.center[0])).toBeLessThan(2e-5);
		expect(Math.abs(again.center[1] - saved.center[1])).toBeLessThan(2e-5);
		await page.waitForTimeout(1500);
		expect(await page.evaluate(() => location.hash), 'the hash reads the same').toBe(hash);
		expect(realErrors(consoleErrors, details)).toEqual([]);
	});

	test('with the inspect card open, H, O and Back land left of it, and the padding, view and hash keep none of it', { tag: '@wp3' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		const details = mapErrorDetails(page);
		await openTest(page, '#map=13/43.6/-116.25/0/0&layers=none');
		const map = () =>
			page.evaluate(() => {
				const m = (globalThis as any).__tvt.map;
				const c = m.getContainer().getBoundingClientRect();
				return { padding: m.getPadding(), w: c.width, h: c.height, view: (globalThis as any).__tvt.view };
			});
		const at = (lngLat: [number, number]) => page.evaluate((ll) => (globalThis as any).__tvt.map.project(ll), lngLat);
		const settled = () => page.waitForFunction(() => !(globalThis as any).__tvt.map.isMoving(), null, { timeout: 60_000 });
		const card = page.getByRole('region', { name: 'Selected marker' });
		await expect.poll(async () => (await map()).padding).toEqual(CHROME);
		const { w, h } = await map();
		const mid = { x: 312 + (w - 312 - 72) / 2, y: 76 + (h - 76 - 104) / 2 };
		// The middle of the area the card leaves: right of the legends, left of the card's column.
		const clear = { x: 312 + (w - 312 - 392) / 2, y: mid.y };
		const near = (q: { x: number; y: number }, r: { x: number; y: number }, what: string, px = 2) => {
			expect(Math.abs(q.x - r.x), `${what} (x)`).toBeLessThan(px);
			expect(Math.abs(q.y - r.y), `${what} (y)`).toBeLessThan(px);
		};
		await page.evaluate(() => (globalThis as any).__tvtWindows.select('A test thing'));
		await expect(card).toBeVisible();

		// H lands Meridian left of the card. The map keeps the chrome's padding, and its centre (the view, the
		// hash) is still the place drawn in the middle of that padding.
		await page.keyboard.press('KeyH');
		await settled();
		await mapReady(page);
		near(await at(MERIDIAN), clear, 'H: Meridian in the middle of the area the card leaves');
		let m = await map();
		expect(m.padding, 'the fly took no padding').toEqual(CHROME);
		near(await at(m.view.center), mid, 'the view’s centre is the map’s own', 1.5);
		const box = (await card.boundingBox())!;
		expect((await at(MERIDIAN)).x).toBeLessThan(box.x);

		// A reload with that hash opens the same picture (the card closed now): Meridian where it was.
		await page.waitForTimeout(1500);
		await page.reload();
		await mapReady(page);
		await expect.poll(async () => (await map()).padding).toEqual(CHROME);
		near(await at(MERIDIAN), clear, 'after a reload, the hash held no card');
		const reloaded = (await map()).view;

		// O with the card open: the valley is fitted to the area the card leaves, and lands as far left as the
		// map's bounds allow. (MapLibre keeps the padded view inside maxBounds, the terrain's ring: at Overview's
		// zoom that stops the valley short, so its east end can stay under the card, §14.3 "Regions".)
		await page.evaluate(() => (globalThis as any).__tvtWindows.select('A test thing'));
		await expect(card).toBeVisible();
		await page.keyboard.press('KeyO');
		await settled();
		await mapReady(page);
		const sw = await at([-116.72, 43.47]);
		const ne = await at([-116.08, 43.73]);
		for (const q of [sw, ne]) {
			expect(q.x).toBeGreaterThanOrEqual(312 - 1);
			expect(q.y).toBeGreaterThanOrEqual(76 - 1);
			expect(q.y).toBeLessThanOrEqual(h - 104 + 1);
		}
		const across = (ne.x - sw.x) / (w - 312 - 392 - 80);
		expect(across, 'fitted to the area the card leaves, less the 40 px margins').toBeGreaterThan(0.97);
		expect(across).toBeLessThan(1.03);
		// Where the bounds' east edge is drawn: at the padded view's right edge when they stop it.
		const bound = await page.evaluate(([y]) => {
			const m = (globalThis as any).__tvt.map;
			return m.project([m.getMaxBounds().getEast(), m.unproject([0, y]).lat]).x as number;
		}, [mid.y]);
		if (ne.x > w - 392 + 1) expect(Math.abs(bound - (w - 72)), 'only the bounds stop it short of the card').toBeLessThan(6);
		expect((await map()).padding).toEqual(CHROME);

		// Back, to the view O left: its centre lands left of the card too.
		await page.keyboard.press('Backspace');
		await settled();
		await mapReady(page);
		m = await map();
		expect(Math.abs(m.view.zoom - reloaded.zoom)).toBeLessThan(0.01);
		expect(Math.abs(m.view.pitch - reloaded.pitch)).toBeLessThan(0.01);
		near(await at(reloaded.center), clear, 'Back: the previous centre in the middle of the area the card leaves');
		expect(m.padding).toEqual(CHROME);
		expect(realErrors(consoleErrors, details)).toEqual([]);
	});

	test('a click the open inspect card would cover pans it clear without skewing a tilted map; one already clear moves nothing', { tag: '@wp3' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		const details = mapErrorDetails(page);
		await page.goto('/?window-test&overlay-test#map=16/43.62755/-116.20892/-20/50&layers=none');
		await mapReady(page);
		await page.waitForFunction(() => (globalThis as any).__tvtWindows && (globalThis as any).__tvtOverlayTest, null, { timeout: 60_000 });
		type Sprite = { id: string; x: number; y: number };
		const sprites = (): Promise<Sprite[]> => page.evaluate(() => (globalThis as any).__tvtOverlayTest.positions());
		const camera = () =>
			page.evaluate(() => {
				const m = (globalThis as any).__tvt.map;
				const c = m.getCenter();
				return { center: [c.lng, c.lat], zoom: m.getZoom(), pitch: m.getPitch(), bearing: m.getBearing(), padding: m.getPadding(), w: m.getContainer().clientWidth };
			});
		const selected = () => page.evaluate(() => (globalThis as any).__tvt.layers?.selection?.id ?? null);
		const history = () => page.evaluate(() => (globalThis as any).__tvtWindows.history());
		const settled = () => page.waitForFunction(() => !(globalThis as any).__tvt.map.isMoving(), null, { timeout: 60_000 });
		const card = page.getByRole('region', { name: 'Selected marker' });
		await expect.poll(async () => (await camera()).padding).toEqual(CHROME);
		const c0 = await camera();
		// The inspect card's column: 360 px, 16 px from the right edge, from below the camera widget to the toolbar's line.
		const slot = (await page.locator('.inspect-slot').boundingBox())!;
		const cardLeft = slot.x;
		expect(cardLeft).toBe(c0.w - 16 - 360);
		const underCard = (s: Sprite) => s.x > cardLeft + 30 && s.x < c0.w - 60 && s.y > slot.y + 30 && s.y < 800 - 104 - 30;
		const all = await sprites();
		const covered = all.find(underCard);
		const free = all.find((s) => s.x > 520 && s.x < 700 && s.y > 300 && s.y < 500);
		expect(covered && free, 'sprites under the card and in the free middle').toBeTruthy();
		const h0 = await history();

		// Under the card: selected, and the map pans it just clear, at the same height.
		await page.mouse.click(covered!.x, covered!.y);
		await expect.poll(selected).toBe(covered!.id);
		await expect(card).toBeVisible();
		await page.waitForTimeout(300);
		await settled();
		await mapReady(page);
		const c1 = await camera();
		const moved = (await sprites()).find((s) => s.id === covered!.id)!;
		expect(moved.x, 'clear of the card').toBeLessThan(cardLeft - 16);
		expect(Math.abs(moved.x - (cardLeft - 40)), 'just far enough').toBeLessThan(2);
		expect(Math.abs(moved.y - covered!.y), 'sideways').toBeLessThan(2);
		expect(moved.x).toBeLessThan((await card.boundingBox())!.x);
		// A plain pan: the same zoom, tilt, heading and padding (so no skew), and nothing on the view history.
		expect(c1.zoom).toBeCloseTo(c0.zoom, 6);
		expect(c1.pitch).toBeCloseTo(c0.pitch, 6);
		expect(c1.bearing).toBeCloseTo(c0.bearing, 6);
		expect(c1.padding).toEqual(CHROME);
		expect(await history()).toBe(h0);
		await page.screenshot({ path: screenPath('windows-reveal-pan.png') });

		// Already clear: selected, and nothing moves.
		const freeNow = (await sprites()).find((s) => s.id === free!.id)!;
		await page.mouse.click(freeNow.x, freeNow.y);
		await expect.poll(selected).toBe(free!.id);
		await page.waitForTimeout(800);
		await settled();
		const c2 = await camera();
		expect(Math.abs(c2.center[0] - c1.center[0])).toBeLessThan(1e-9);
		expect(Math.abs(c2.center[1] - c1.center[1])).toBeLessThan(1e-9);
		const still = (await sprites()).find((s) => s.id === free!.id)!;
		expect(Math.hypot(still.x - freeNow.x, still.y - freeNow.y), 'nothing moved').toBeLessThan(0.5);

		// Under reduced motion the pan is a jump.
		await page.emulateMedia({ reducedMotion: 'reduce' });
		await page.keyboard.press('Escape');
		await expect(card).toHaveCount(0);
		const next = (await sprites()).find((s) => s.id !== covered!.id && underCard(s));
		expect(next, 'another sprite under where the card goes').toBeTruthy();
		const c3 = await camera();
		await page.mouse.click(next!.x, next!.y);
		await expect.poll(selected).toBe(next!.id);
		// Moved already, and not moving: no animation.
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.isMoving())).toBe(false);
		expect(Math.abs((await camera()).center[0] - c3.center[0]), 'panned at once').toBeGreaterThan(1e-6);
		// (The overlay reports where it drew each sprite: the next frame.)
		await expect.poll(async () => Math.abs((await sprites()).find((s) => s.id === next!.id)!.x - (cardLeft - 40))).toBeLessThan(2);
		const jumped = (await sprites()).find((s) => s.id === next!.id)!;
		expect(Math.abs(jumped.y - next!.y)).toBeLessThan(2);
		expect(realErrors(consoleErrors, details)).toEqual([]);
	});

	test('under reduced motion H and O still go on the view history; Overview frames the valley', { tag: '@wp3' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.emulateMedia({ reducedMotion: 'reduce' });
		await openTest(page, '#map=12.5/43.6/-116.25/-20/40&layers=none');
		const view = () => page.evaluate(() => (globalThis as any).__tvt.view);
		const history = () => page.evaluate(() => (globalThis as any).__tvtWindows.history());
		const chip = page.getByRole('button', { name: /Back to previous view/ });
		const start = await view();
		const same = (a: any, b: any) => {
			expect(Math.abs(a.center[0] - b.center[0])).toBeLessThan(1e-6);
			expect(Math.abs(a.center[1] - b.center[1])).toBeLessThan(1e-6);
			expect(Math.abs(a.zoom - b.zoom)).toBeLessThan(0.01);
			expect(Math.abs(a.bearing - b.bearing)).toBeLessThan(0.01);
			expect(Math.abs(a.pitch - b.pitch)).toBeLessThan(0.01);
		};

		// H jumps (no flight) and pushes; the chip comes back. It hides 8 s after the push, and a click's wait
		// for a stable element took 14 s on a loaded laptop (SwiftShader starves animation frames, Oct 15), so
		// the click is dispatched on it.
		await page.keyboard.press('KeyH');
		await chip.waitFor({ state: 'attached', timeout: 5_000 });   // H shows the Back chip (its fade-in may lag under load)
		expect(await history()).toBe(1);
		const home = await view();
		expect(home.zoom).toBeCloseTo(13, 3);
		expect(home.pitch).toBeCloseTo(50, 3);
		// The click does not wait on the chip's 8 s lifetime: it is dispatched on whatever is there now. If the
		// chip has already hidden, Backspace takes the same step back.
		if (await chip.count()) await chip.dispatchEvent('click');
		else await page.keyboard.press('Backspace');
		await mapReady(page);
		same(await view(), start);
		expect(await history()).toBe(0);

		// O the same way, framing the valley (Caldwell to east Boise, Kuna to Eagle) in the visible area.
		await page.keyboard.press('KeyO');
		await expect(chip).toBeVisible();
		expect(await history()).toBe(1);
		const o = await view();
		expect(o.pitch).toBeCloseTo(0, 3);
		expect(o.bearing).toBeCloseTo(0, 3);
		const frame = await page.evaluate(() => {
			const m = (globalThis as any).__tvt.map;
			const c = m.getContainer().getBoundingClientRect();
			const pad = m.getPadding();
			const sw = m.project([-116.72, 43.47]);
			const ne = m.project([-116.08, 43.73]);
			return { sw, ne, pad, w: c.width, h: c.height };
		});
		const area = { left: frame.pad.left, right: frame.w - frame.pad.right, top: frame.pad.top, bottom: frame.h - frame.pad.bottom };
		for (const pt of [frame.sw, frame.ne]) {
			expect(pt.x).toBeGreaterThanOrEqual(area.left - 1);
			expect(pt.x).toBeLessThanOrEqual(area.right + 1);
			expect(pt.y).toBeGreaterThanOrEqual(area.top - 1);
			expect(pt.y).toBeLessThanOrEqual(area.bottom + 1);
		}
		// Snug: the valley fills the visible area across or down (less the 40 px margin).
		const fill = Math.max((frame.ne.x - frame.sw.x) / (area.right - area.left), (frame.sw.y - frame.ne.y) / (area.bottom - area.top));
		expect(fill, 'the valley fills the visible area').toBeGreaterThan(0.7);
		await mapReady(page);
		await page.screenshot({ path: screenPath('windows-overview-valley.png') });
		// Backspace comes back (the chip may have hidden by now).
		await page.keyboard.press('Backspace');
		await mapReady(page);
		same(await view(), start);
		expect(await history()).toBe(0);
	});
});
