import type { Locator, Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import { cleanRoadWeather, seedRoadWeather, STATIONS } from './roadweather-seed.js';

/**
 * road weather (docs/14 §14.10, WP16 acceptance; §14.6 "Road weather"):
 * toggling Road weather draws the seeded stations; clicking one opens a
 * window whose tabs show the seeded archive frames with their ages, on the
 * road-weather freshness thresholds; a station whose views are all
 * placeholders ("no live feed") is drawn hollow. Also: the Cameras layer
 * doesn't list the stations, key 9 toggles the layer, and on a phone a
 * station opens as a sheet tab.
 *
 * The spec sets up its own stations (roadweather-seed.ts: the real loader on
 * the plugin's synthetic list, test-pattern frames at chosen ages, a running
 * capture status) and removes them afterwards. No real camera image is used.
 */

type Drawn = { id: number; name: string; provider: string; hollow: boolean; views: number; x: number | null; y: number | null };
type RwView = { id: number; imageId: number; label: string; disabled: boolean; ageS: number | null; feed: string };
type RwStation = { id: number; name: string; hollow: boolean; views: RwView[] };

/** Every seeded station on screen, clear of the legend column and the toolbar. */
const VIEW = '#map=9/43.64/-116.62/0/0';
const NAMES: string[] = Object.values(STATIONS).map((s) => s.name);

const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'Map layers' });
const button = (page: Page) => toolbar(page).getByRole('button', { name: 'Road weather', exact: true });
const drawn = (page: Page): Promise<Drawn[]> => page.evaluate(() => (globalThis as any).__tvtRoadWeather?.stations() ?? []);

let seeded: Promise<RwStation[]> | null = null;

/** Seed once for the spec, then wait until the server knows the new stations and their views (its lists are cached). */
function ensureSeeded(request: import('@playwright/test').APIRequestContext): Promise<RwStation[]> {
	seeded ??= (async () => {
		seedRoadWeather();
		let stations: RwStation[] = [];
		await expect
			.poll(
				async () => {
					const rw = await (await request.get('/api/roadweather')).json();
					stations = (rw.stations as RwStation[]).filter((s) => NAMES.includes(s.name));
					return stations.length;
				},
				{ timeout: 60_000, intervals: [1000, 2000] }
			)
			.toBe(3);
		const ids = stations.flatMap((s) => s.views.map((v) => v.id));
		// /api/cameras/live keeps its view list for a minute: wait until it serves the new views from the archive.
		await expect
			.poll(
				async () => {
					const live = await (await request.get(`/api/cameras/live?views=${ids.join(',')}`)).json();
					return Object.values(live.views as Record<string, { cadence: string }>).filter((v) => v.cadence === 'road_weather').length;
				},
				{ timeout: 90_000, intervals: [2000, 5000] }
			)
			.toBe(ids.length);
		return stations;
	})();
	return seeded;
}

test.afterAll(async () => {
	if (seeded) await cleanRoadWeather();
});

async function openMap(page: Page, layers: string) {
	await page.goto(`/${VIEW}&layers=${layers}`);
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
		await openMap(page, 'weather');
		const on = await seededDrawn(page);

		await clickStation(page, on[STATIONS.grade.name]);
		const win = page.getByRole('dialog', { name: STATIONS.grade.name });
		await expect(win).toBeVisible();
		const tabs = win.getByRole('tab');
		await expect(tabs).toHaveCount(4);
		await expect(tabs.locator('.label')).toHaveText([...STATIONS.grade.labels]);
		// The first live view is chosen: its newest archive frame, and how long ago our capture saw it.
		await expect(tabs.nth(0)).toHaveAttribute('aria-selected', 'true');
		const day = /\/\d{4}-\d{2}-\d{2}\/\d{8}T\d{6}Z\.jpg$/;
		await expect.poll(() => pictureSrc(win), { timeout: 60_000 }).toMatch(new RegExp(`^/camera-frames/990011${day.source}`));
		const seen = win.locator('.seen');
		await expect(seen).toHaveText(/^seen \d+:\d\d ago · updates about every 10 minutes$/);
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

		// 30 min: late (road-weather thresholds: live under 20 min, stale over 45).
		await tabs.nth(1).click();
		await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true');
		await expect.poll(() => pictureSrc(win), { timeout: 30_000 }).toMatch(new RegExp(`^/camera-frames/990012${day.source}`));
		await expect(tabs.nth(1)).toHaveAttribute('data-state', 'late');
		expect(await age(1)).toBeGreaterThanOrEqual(30 * 60 - 5);
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
		await win.getByRole('button', { name: `Close ${STATIONS.grade.name}` }).click();
		await expect(win).toHaveCount(0);

		// The hollow station: every view without a live feed, and the window says so.
		await clickStation(page, on[STATIONS.summit.name]);
		const hollow = page.getByRole('dialog', { name: STATIONS.summit.name });
		await expect(hollow).toBeVisible();
		await expect(hollow.getByRole('tab')).toHaveCount(2);
		for (let i = 0; i < 2; i++) await expect(hollow.getByRole('tab').nth(i)).toHaveAttribute('data-state', 'offline');
		await expect(hollow.locator('header .status')).toHaveText(/no live feed/);
		await expect(hollow.locator('.seen')).toHaveText('no live feed · no picture recorded lately');
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
