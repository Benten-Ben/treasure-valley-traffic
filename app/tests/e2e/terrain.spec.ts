import type { Page, Route } from '@playwright/test';
import { mkdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { openCheck, startCheckServer } from '../../scripts/terrain-check.mjs';
import { env, expect, mapReady, screenPath, test } from './fixtures.js';

/**
 * terrain (docs/14 §14.10, WP17 acceptance): terrain-RGB re-encoded as
 * lossless WebP by basemap/terrain_reencode.py works in the browser.
 *
 * - The bare terrain page (scripts/terrain-check.mjs) reads the same
 *   synthetic terrain as PNG and as WebP and gets identical elevations,
 *   which match the formula they were made from.
 * - The app draws the synthetic WebP terrain with no console errors (its
 *   manifest's terrain entry is pointed at it).
 * - The terrain the served manifest lists loads with no console errors, in
 *   3D over the foothills. That is today's PNG on a fresh checkout, and the
 *   WebP file when TILES_DIR holds the re-encoded copy and its manifest.
 *
 * The fixture is synthetic (basemap/test_terrain_reencode.py
 * --write-e2e-fixture), not elevation data. Before/after screenshots of the
 * real terrain come from scripts/terrain-compare.mjs.
 */

const FIXTURE = fileURLToPath(new URL('./terrain-fixture', import.meta.url));
type Fixture = {
	png: string;
	webp: string;
	tileSize: number;
	center: [number, number];
	zoom: number;
	points: [number, number, number][];
};
const info: Fixture = JSON.parse(readFileSync(join(FIXTURE, 'synthetic.json'), 'utf8'));

/** The pmtiles header's tile type (byte 99): 2 PNG, 4 WebP. */
const TILE_TYPES: Record<number, string> = { 1: 'mvt', 2: 'png', 3: 'jpg', 4: 'webp', 5: 'avif' };

/** Answer a byte-range request from a local file, as the tiles server would. */
async function fulfilFile(route: Route, file: string) {
	const body = readFileSync(file);
	const m = /^bytes=(\d+)-(\d*)$/.exec(route.request().headers()['range'] ?? '');
	if (!m) return route.fulfill({ status: 200, body, headers: { 'Accept-Ranges': 'bytes', 'Content-Type': 'application/octet-stream' } });
	const start = Number(m[1]);
	const end = m[2] === '' ? body.length - 1 : Math.min(Number(m[2]), body.length - 1);
	return route.fulfill({
		status: 206,
		body: body.subarray(start, end + 1),
		headers: {
			'Accept-Ranges': 'bytes',
			'Content-Range': `bytes ${start}-${end}/${body.length}`,
			'Content-Type': 'application/octet-stream',
			ETag: `"${statSync(file).mtimeMs.toString(36)}"`
		}
	});
}

/** Tile requests (pmtiles ranges) with their statuses. */
function watchTiles(page: Page) {
	const seen: { url: string; status: number }[] = [];
	page.on('response', (r) => {
		if (/\/tiles\/.+\.pmtiles/.test(r.url())) seen.push({ url: r.url(), status: r.status() });
	});
	return seen;
}

test.describe('terrain', () => {
	test('the browser decodes WebP terrain-RGB exactly like PNG', { tag: '@wp17' }, async ({ page }) => {
		const server = await startCheckServer({ roots: { fixture: FIXTURE } });
		try {
			const [lon, lat] = info.center;
			const sample = async (file: string) => {
				const errors = await openCheck(page, server, {
					dem: `fixture/${file}`,
					tileSize: info.tileSize,
					mode: 'terrain',
					lon,
					lat,
					z: info.zoom
				});
				const heights = await page.evaluate((pts) => (globalThis as any).__check.sample(pts), info.points);
				return { errors, heights: heights as (number | null)[] };
			};
			const png = await sample(info.png);
			const webp = await sample(info.webp);
			expect(png.errors).toEqual([]);
			expect(webp.errors).toEqual([]);
			const webpRanges = server.requests.filter(([, path]) => path.endsWith(info.webp));
			expect(webpRanges.length, 'WebP archive read').toBeGreaterThan(1);
			expect(webpRanges.every(([status]) => status === 206), 'ranges answered').toBe(true);

			const rows = info.points.map(([plon, plat, want], i) => ({
				lon: plon,
				lat: plat,
				want,
				png: png.heights[i],
				webp: webp.heights[i]
			}));
			test.info().annotations.push({ type: 'heights', description: JSON.stringify(rows.slice(0, 5)) });
			for (const r of rows) {
				expect(r.png, `PNG at ${r.lon},${r.lat}`).not.toBeNull();
				// Same decoded values, so the same sample, to the last bit.
				expect(r.webp, `WebP at ${r.lon},${r.lat}`).toBe(r.png);
				// And they are the terrain the fixture was made from: a channel decoded wrong would
				// be off by 25.6 m (green) or 6,553.6 m (red); sampling between pixels is within 3 m.
				expect(Math.abs(r.webp! - r.want), `WebP vs formula at ${r.lon},${r.lat}`).toBeLessThan(3);
			}
			mkdirSync(env().screens, { recursive: true });
			await page.screenshot({ path: screenPath('terrain-fixture-check.png') });
		} finally {
			await server.close();
		}
	});

	test('the app draws WebP terrain with no console errors', { tag: '@wp17' }, async ({ page, consoleErrors, offsite }) => {
		// The app's manifest, with the terrain entry pointed at the synthetic WebP archive.
		await page.route('**/tiles/manifest.json', async (route) => {
			const res = await route.fetch();
			const m = await res.json();
			m.terrain = { ...m.terrain, file: `__wp17/${info.webp}`, tileSize: info.tileSize, format: 'webp' };
			await route.fulfill({ response: res, json: m });
		});
		await page.route(`**/tiles/__wp17/${info.webp}`, (route) => fulfilFile(route, join(FIXTURE, info.webp)));
		const tiles = watchTiles(page);
		const [lon, lat] = info.center;
		await page.goto(`/#12.5/${lat}/${lon}/30/55`);
		await mapReady(page);

		const fixture = tiles.filter((t) => t.url.includes(`/__wp17/${info.webp}`));
		expect(fixture.length, 'the WebP terrain was read').toBeGreaterThan(1);
		expect(fixture.every((t) => t.status === 206)).toBe(true);
		expect(tiles.filter((t) => t.status >= 400)).toEqual([]);
		expect(offsite).toEqual([]);
		expect(consoleErrors).toEqual([]);
		mkdirSync(env().screens, { recursive: true });
		await page.screenshot({ path: screenPath('terrain-app-fixture.png'), timeout: 180_000 });
	});

	test('the terrain the manifest lists loads in 3D with no console errors', { tag: '@wp17' }, async ({ page, request, consoleErrors, offsite }) => {
		const manifest = await (await request.get('/tiles/manifest.json')).json();
		expect(manifest.terrain?.file, 'the manifest lists terrain').toBeTruthy();
		const head = await request.get(`/tiles/${manifest.terrain.file}`, { headers: { Range: 'bytes=0-126' } });
		expect(head.status()).toBe(206);
		const type = TILE_TYPES[(await head.body())[99]] ?? 'unknown';
		test.info().annotations.push({ type: 'terrain', description: `${manifest.terrain.file} (${type})` });
		expect(['png', 'webp']).toContain(type);

		const tiles = watchTiles(page);
		// The Boise foothills, tilted, at the zoom where the 0.5 m rounding applies.
		await page.goto('/#13/43.6478/-116.1750/25/60');
		await mapReady(page);
		const terrain = tiles.filter((t) => t.url.includes(`/tiles/${manifest.terrain.file}`));
		expect(terrain.length, 'terrain tiles requested').toBeGreaterThan(1);
		expect(tiles.filter((t) => t.status >= 400)).toEqual([]);
		expect(offsite).toEqual([]);
		expect(consoleErrors).toEqual([]);
		mkdirSync(env().screens, { recursive: true });
		await page.screenshot({ path: screenPath(`terrain-app-${type}.png`), timeout: 180_000 });
	});
});
