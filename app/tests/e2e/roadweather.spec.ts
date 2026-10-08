import type { Locator, Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import { cleanRoadWeather, seedRoadWeather, STATIONS, waitForSeeded } from './roadweather-seed.js';

/**
 * road weather (docs/14 §14.10, WP16 acceptance; §14.6 "Road weather"):
 * toggling Road weather draws the seeded stations; clicking one opens a
 * window whose tabs show the seeded archive frames with their ages, on the
 * road-weather freshness thresholds; a station whose views are all
 * placeholders ("no live feed") is drawn hollow. Also: the Cameras layer
 * doesn't list the stations, key 9 toggles the layer, and on a phone a
 * station opens as a sheet tab. The inspect card says each view's status in
 * the window's words, and a station clicked under the inspect card pans into
 * the free middle first.
 *
 * The spec sets up its own stations (roadweather-seed.ts: the real loader on
 * the plugin's synthetic list, test-pattern frames at chosen ages, a running
 * capture status) and removes them afterwards. No real camera image is used.
 */

type Drawn = { id: number; name: string; provider: string; hollow: boolean; views: number; x: number | null; y: number | null };

/** Every seeded station on screen, clear of the legend column and the toolbar. */
const VIEW = '#map=9/43.64/-116.62/0/0';
/** The same zoom further west: Example Grade sits under the inspect column, where the card opens (about x 1000). */
const UNDER_CARD = '#map=9/43.64/-116.82/0/0';
const NAMES: string[] = Object.values(STATIONS).map((s) => s.name);

const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'Map layers' });
const button = (page: Page) => toolbar(page).getByRole('button', { name: 'Road weather', exact: true });
const drawn = (page: Page): Promise<Drawn[]> => page.evaluate(() => (globalThis as any).__tvtRoadWeather?.stations() ?? []);

let seeded: ReturnType<typeof waitForSeeded> | null = null;

/**
 * Seed once for the spec, then wait until the server knows the new stations and their views (its
 * lists are cached; the review's checklist, which has Road weather on, runs just before this one).
 */
function ensureSeeded(request: import('@playwright/test').APIRequestContext) {
	seeded ??= (async () => {
		seedRoadWeather();
		return waitForSeeded(request);
	})();
	return seeded;
}

test.afterAll(async () => {
	if (seeded) await cleanRoadWeather();
});

async function openMap(page: Page, layers: string, view = VIEW) {
	await page.goto(`/${view}&layers=${layers}`);
	await mapReady(page);
}

/** The seeded stations as drawn, once all three are. */
async function seededDrawn(page: Page): Promise<Record<string, Drawn>> {
	const ours = async () => (await drawn(page)).filter((s) => NAMES.includes(s.name));
	await expect.poll(async () => (await ours()).length, { timeout: 60_000 }).toBe(3);
	await mapReady(page);
	return Object.fromEntries((await ours()).map((s) => [s.name, s]));
}

async function clickStation(page: Page, s: Drawn) {
	const box = (await page.locator('canvas.maplibregl-canvas').boundingBox())!;
	await page.mouse.click(box.x + s.x!, box.y + s.y!);
}

/** The newest picture the window's frame shows (the top layer). */
const pictureSrc = (win: Locator) => win.locator('img[data-frame-url]').last().getAttribute('src');

const escapeRe = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** The legend and inspect columns on a desktop (windows.svelte.ts, §14.3): the free middle is between them. */
const LEFT_COLUMN = 312;
const RIGHT_COLUMN = 392;

type Box = { x: number; y: number; width: number; height: number } | null;
const inside = (b: Box, x: number, y: number) => !!b && x >= b.x && x <= b.x + b.width && y >= b.y && y <= b.y + b.height;

test.describe('road weather', () => {
	test('toggling Road weather draws the seeded stations, hollow where every view has no live feed', { tag: '@wp16' }, async ({ page, request, consoleErrors, offsite }) => {
		test.setTimeout(300_000);
		const stations = await ensureSeeded(request);
		const byName = Object.fromEntries(stations.map((s) => [s.name, s]));
		expect(stations.map((s) => s.views.length).sort()).toEqual([2, 2, 4]);
		expect(byName[STATIONS.summit.name].hollow).toBe(true);
		expect(byName[STATIONS.grade.name].hollow).toBe(false);
		expect(byName[STATIONS.bridge.name].hollow).toBe(false);
		// The stations aren't ACHD's traffic cameras: the Cameras layer doesn't list them.
		const cams = await (await request.get('/api/cameras')).json();
		expect(cams.features.filter((f: { properties: { name: string } }) => NAMES.includes(f.properties.name))).toEqual([]);

		await openMap(page, 'none');
		await expect(button(page)).toHaveAttribute('aria-pressed', 'false');
		await button(page).click();
		await expect(button(page)).toHaveAttribute('aria-pressed', 'true');
		await mapReady(page);
		const on = await seededDrawn(page);
		expect(on[STATIONS.summit.name].hollow).toBe(true);
		expect([on[STATIONS.grade.name].hollow, on[STATIONS.bridge.name].hollow]).toEqual([false, false]);
		// All on screen, none under the legend (so each can be seen and clicked).
		const legendBox = (await page.getByRole('region', { name: 'Road weather legend' }).boundingBox())!;
		for (const s of Object.values(on)) {
			expect(s.x!, s.name).toBeGreaterThan(20);
			expect(s.x!, s.name).toBeLessThan(1280 - 80);
			expect(s.y!, s.name).toBeGreaterThan(80);
			expect(s.y!, s.name).toBeLessThan(800 - 120);
			const under = s.x! >= legendBox.x && s.x! <= legendBox.x + legendBox.width && s.y! >= legendBox.y && s.y! <= legendBox.y + legendBox.height;
			expect(under, `${s.name} under the legend`).toBe(false);
		}
		// Drawn on the map: one badge per station, the hollow one with the hollow image.
		const rendered = await page.evaluate((ids) => {
			const map = (globalThis as any).__tvt.map;
			return map
				.queryRenderedFeatures({ layers: ['roadweather-badges'] })
				.filter((f: any) => ids.includes(f.properties.id))
				.map((f: any) => ({ id: f.properties.id, hollow: f.properties.hollow, image: f.layer.layout?.['icon-image'] ?? null }));
		}, Object.values(on).map((s) => s.id));
		expect(rendered.map((r: { id: number }) => r.id).sort()).toEqual(Object.values(on).map((s) => s.id).sort());
		for (const r of rendered as { id: number; hollow: boolean; image: unknown }[]) {
			const want = r.id === on[STATIONS.summit.name].id;
			expect(r.hollow, `station ${r.id}`).toBe(want);
			if (typeof r.image === 'string' || (r.image && typeof r.image === 'object' && 'name' in (r.image as object)))
				expect(String((r.image as { name?: string }).name ?? r.image)).toBe(want ? 'roadweather-badge-hollow' : 'roadweather-badge');
		}
		// The legend shows both badges with their counts.
		const legend = page.getByRole('region', { name: 'Road weather legend' });
		const hollowCount = (await drawn(page)).filter((s) => s.hollow).length;
		await expect(legend.getByText('No live feed on any view')).toContainText(`(${hollowCount})`);
		await page.screenshot({ path: screenPath('roadweather-stations.png'), animations: 'disabled' });

		// Off hides it (the layer stays loaded); key 9 turns it back on.
		await button(page).click();
		await expect(button(page)).toHaveAttribute('aria-pressed', 'false');
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getLayoutProperty('roadweather-badges', 'visibility'))).toBe('none');
		await page.keyboard.press('9');
		await expect(button(page)).toHaveAttribute('aria-pressed', 'true');
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getLayoutProperty('roadweather-badges', 'visibility'))).toBe('visible');
		expect(consoleErrors).toEqual([]);
		expect(offsite).toEqual([]);
	});

	test('clicking a station opens a window whose tabs show the seeded archive frames with their ages', { tag: '@wp16' }, async ({ page, request, consoleErrors, offsite }) => {
		test.setTimeout(360_000);
		const stations = await ensureSeeded(request);
		const grade = stations.find((s) => s.name === STATIONS.grade.name)!;
		const live: string[] = [];
		page.on('request', (r) => {
			if (r.url().includes('/api/cameras/live')) live.push(r.url());
		});
		await openMap(page, 'weather', UNDER_CARD);
		const on = await seededDrawn(page);

		// At this view Example Grade sits under the inspect column, where the card opens: the click pans it clear.
		// The map already spans its bounds from side to side here, so a pan alone can't move it: it zooms in just enough.
		const before = on[STATIONS.grade.name];
		expect(before.x!).toBeGreaterThan(1280 - RIGHT_COLUMN);
		const zoom = () => page.evaluate(() => (globalThis as any).__tvt.map.getZoom() as number);
		const zoomBefore = await zoom();
		await clickStation(page, before);
		const win = page.getByRole('dialog', { name: STATIONS.grade.name });
		await expect(win).toBeVisible();
		const card = page.getByRole('region', { name: 'Selected station' });
		await expect(card.getByRole('heading', { name: STATIONS.grade.name })).toBeVisible();
		// The pan runs 450 ms: read where it ends.
		await page.waitForFunction(() => !(globalThis as any).__tvt.map.isMoving());
		await mapReady(page);
		const canvas = (await page.locator('canvas.maplibregl-canvas').boundingBox())!;
		const landed = (await seededDrawn(page))[STATIONS.grade.name];
		const at = { x: canvas.x + landed.x!, y: canvas.y + landed.y! };
		expect(at.x, 'the station in the free middle').toBeGreaterThan(LEFT_COLUMN);
		expect(at.x, 'the station in the free middle').toBeLessThan(1280 - RIGHT_COLUMN);
		expect(inside(await card.boundingBox(), at.x, at.y), 'the inspect card leaves the station in view').toBe(false);
		expect(inside(await win.boundingBox(), at.x, at.y), 'its window leaves the station in view').toBe(false);
		expect(await zoom()).toBeGreaterThan(zoomBefore);
		expect(await zoom()).toBeLessThan(zoomBefore + 2);
		const tabs = win.getByRole('tab');
		await expect(tabs).toHaveCount(4);
		await expect(tabs.locator('.label')).toHaveText([...STATIONS.grade.labels]);
		// The first live view is chosen: its newest archive frame, and how long ago our capture saw it.
		await expect(tabs.nth(0)).toHaveAttribute('aria-selected', 'true');
		const day = /\/\d{4}-\d{2}-\d{2}\/\d{8}T\d{6}Z\.jpg$/;
		await expect.poll(() => pictureSrc(win), { timeout: 60_000 }).toMatch(new RegExp(`^/camera-frames/990011${day.source}`));
		const seen = win.locator('.seen');
		// 511's refresh, not our 10-minute capture.
		await expect(seen).toHaveText(/^seen \d+:\d\d ago · 511 updates these pictures about every 15 minutes$/);
		const age = async (i: number) => Number(await tabs.nth(i).getAttribute('data-age'));
		const elapsed = 15 * 60; // the spec's own running time, at most
		expect(await age(0)).toBeGreaterThanOrEqual(4 * 60 - 5);
		expect(await age(0)).toBeLessThan(4 * 60 + elapsed);
		await expect(tabs.nth(0)).toHaveAttribute('data-state', 'fresh');
		await expect(tabs.nth(0)).toContainText(/\d+ min/);
		await expect(win.getByText('live', { exact: true }).first()).toBeVisible();
		// The poll asks for the station's three pictures (not the view 511 lists as disabled).
		const want = grade.views.filter((v) => !v.disabled).map((v) => v.id).sort((a, b) => a - b).join(',');
		expect(live.some((u) => new URL(u).searchParams.get('views') === want), live.join('\n')).toBe(true);
		await page.screenshot({ path: screenPath('roadweather-window.png'), animations: 'disabled' });

		// 40 min: late (road-weather thresholds: live within 30 min, late within 60, stale after).
		await tabs.nth(1).click();
		await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true');
		await expect.poll(() => pictureSrc(win), { timeout: 30_000 }).toMatch(new RegExp(`^/camera-frames/990012${day.source}`));
		await expect(tabs.nth(1)).toHaveAttribute('data-state', 'late');
		expect(await age(1)).toBeGreaterThanOrEqual(40 * 60 - 5);
		expect(await age(1)).toBeLessThan(60 * 60);
		// 70 min: stale, and 511 is probably showing its "no live feed" picture.
		await tabs.nth(2).click();
		await expect.poll(() => pictureSrc(win), { timeout: 30_000 }).toMatch(new RegExp(`^/camera-frames/990013${day.source}`));
		await expect(tabs.nth(2)).toHaveAttribute('data-state', 'stale');
		await expect(win.getByText(/probably showing its “no live feed” picture/)).toBeVisible();
		// Disabled in 511's list: no live feed, and no picture asked for. (The arrow keys move along the tabs.)
		await tabs.nth(2).press('ArrowRight');
		await expect(tabs.nth(3)).toHaveAttribute('aria-selected', 'true');
		await expect(tabs.nth(3)).toBeFocused();
		await expect(tabs.nth(3)).toHaveAttribute('data-state', 'offline');
		await expect(seen).toHaveText('no live feed · 511 lists this view as disabled');
		await expect(win.getByText('No live feed: 511 has no picture from this camera now')).toBeVisible();

		// The inspect card says each view's status in the window's words: live, late, stale, no live feed.
		const states = ['fresh', 'late', 'stale', 'offline'];
		const items = card.locator('.views li');
		await expect(items).toHaveCount(4);
		for (let i = 0; i < 4; i++) {
			await expect(tabs.nth(i)).toHaveAttribute('data-state', states[i]);
			await expect(items.nth(i)).toHaveAttribute('data-state', states[i]);
		}
		await expect(items).toHaveText([/^● Looking East: live · \d+ min$/, /^▲ Looking West: late · \d+ min$/, /^■ Pavement: stale · 1 h$/, /^■ View 4: no live feed$/]);
		await expect(card.locator('.meta')).toHaveText(/1 of 4 views live · ITD RWIS/);
		await page.screenshot({ path: screenPath('roadweather-card.png'), animations: 'disabled' });
		await win.getByRole('button', { name: `Close ${STATIONS.grade.name}` }).click();
		await expect(win).toHaveCount(0);

		// The hollow station: every view without a live feed, and the window says so. (Back to the first
		// view, where it's in the free middle, so the click doesn't move the map.)
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ center: [-116.62, 43.64], zoom: 9 }));
		await mapReady(page);
		const summit = (await seededDrawn(page))[STATIONS.summit.name];
		await clickStation(page, summit);
		const hollow = page.getByRole('dialog', { name: STATIONS.summit.name });
		await expect(hollow).toBeVisible();
		await expect(hollow.getByRole('tab')).toHaveCount(2);
		for (let i = 0; i < 2; i++) await expect(hollow.getByRole('tab').nth(i)).toHaveAttribute('data-state', 'offline');
		await expect(hollow.locator('header .status')).toHaveText(/no live feed/);
		await expect(hollow.locator('.seen')).toHaveText('no live feed · no picture recorded lately');
		await expect(card.locator('.views li')).toHaveText([/^■ View 1: no live feed$/, /^■ View 2: no live feed$/]);
		await expect(card.locator('.meta')).toHaveText(/No live feed on any of 2 views/);
		await page.screenshot({ path: screenPath('roadweather-window-hollow.png'), animations: 'disabled' });
		expect(consoleErrors).toEqual([]);
		expect(offsite).toEqual([]);
	});

	test('at 390×844 a station opens as a sheet tab with its view tabs', { tag: '@wp16' }, async ({ page, request, consoleErrors, offsite }) => {
		test.setTimeout(240_000);
		await ensureSeeded(request);
		await page.setViewportSize({ width: 390, height: 844 });
		await page.goto('/#map=10/43.56/-116.24/0/0&layers=weather');
		await mapReady(page);
		const grade = (await seededDrawn(page))[STATIONS.grade.name];
		await clickStation(page, grade);
		const sheet = page.getByRole('region', { name: 'Details' });
		const name = new RegExp(escapeRe(STATIONS.grade.name));
		await expect(sheet.getByRole('tab', { name })).toHaveAttribute('aria-selected', 'true');
		await expect(page.getByRole('dialog')).toHaveCount(0);
		const panel = sheet.getByRole('tabpanel', { name });
		await expect(panel.getByRole('tab')).toHaveCount(4);
		await expect.poll(() => pictureSrc(panel), { timeout: 60_000 }).toMatch(/^\/camera-frames\/990011\//);
		await expect(panel.locator('img[data-frame-url]').last()).toBeVisible();
		expect(await page.evaluate(() => document.documentElement.scrollWidth), 'no horizontal scroll').toBeLessThanOrEqual(390);
		await page.screenshot({ path: screenPath('roadweather-phone.png'), animations: 'disabled' });
		expect(consoleErrors).toEqual([]);
		expect(offsite).toEqual([]);
	});
});
