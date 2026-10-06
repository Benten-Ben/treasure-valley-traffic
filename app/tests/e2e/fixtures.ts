/**
 * Shared test fixtures and helpers for every e2e spec (WP0). Import `test` and
 * `expect` from here, not from @playwright/test, so the data check runs.
 *
 * - **Data check** (automatic): the basemap manifest, the package's seeded
 *   frames and archive, and a working database clone. When something is
 *   missing the spec skips with a message, or fails when
 *   TVT_E2E_REQUIRE_DATA=1 (the workflow).
 * - **Same-origin guard** (automatic): any request that would leave the
 *   machine is aborted and recorded; `offsite` lists them.
 * - `consoleErrors`: console errors and uncaught page errors.
 * - `mapReady(page)`: `__tvt.ready` once WP1 provides it; until then, the map
 *   canvas plus a quiet network.
 */
import { test as base, expect, type Page } from '@playwright/test';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

export { expect };

export const env = () => ({
	tilesDir: process.env.TILES_DIR ?? '',
	framesDir: process.env.FRAMES_DIR ?? '',
	archive: process.env.TVT_ARCHIVE ?? '',
	screens: process.env.TVT_SCREENS ?? '',
	wp: process.env.TVT_WP ?? '',
	requireData: process.env.TVT_E2E_REQUIRE_DATA === '1'
});

export interface Seed {
	kind: 'key' | 'roll' | 'low-tilt' | 'hd';
	viewId: number;
	imageId: number;
	cameraId: number;
	name: string;
	size: { width: number; height: number };
	pose: { lon: number; lat: number; alt: number; heading: number; tilt: number; roll: number; vfov: number };
	frame: string;
	visual: boolean;
	registration: { maxPx: number; rmsPx: number; mapRollSign: 1 | -1 } | null;
}

/** The seeds written by `npm run seed` (data/dev/<wp>/seed.json). */
export function seeds(): { seeds: Seed[]; archive: { day: string; imageIds: number[] } } {
	return JSON.parse(readFileSync(join(resolve(env().framesDir, '..'), 'seed.json'), 'utf8'));
}

/** What's missing for the specs to mean anything; empty when all is there. */
export function missingData(): string[] {
	const e = env();
	const missing: string[] = [];
	if (!e.tilesDir || !existsSync(join(e.tilesDir, 'manifest.json'))) missing.push(`no basemap manifest in TILES_DIR (${e.tilesDir || 'unset'})`);
	if (!e.framesDir || !existsSync(join(e.framesDir, '_fixture'))) missing.push(`no seeded frames in FRAMES_DIR (${e.framesDir || 'unset'}): run npm run seed`);
	const jpeg = join(e.archive, 'cameras', 'jpeg');
	if (!e.archive || !existsSync(jpeg) || readdirSync(jpeg).length === 0) missing.push(`no fake archive in TVT_ARCHIVE (${e.archive || 'unset'}): run npm run seed`);
	if (!existsSync(join(resolve(e.framesDir || '.', '..'), 'seed.json'))) missing.push('no seed.json next to FRAMES_DIR: run npm run seed');
	return missing;
}

let databaseChecked: string | null | undefined;

export const test = base.extend<{ dataCheck: void; offsite: string[]; consoleErrors: string[] }>({
	dataCheck: [
		async ({ request }, use, testInfo) => {
			const missing = missingData();
			if (databaseChecked === undefined) {
				const meta = await request.get('/api/meta').then((r) => r.json()).catch(() => null);
				databaseChecked = meta?.database === 'ok' ? null : `the database clone isn't answering (/api/meta: ${meta?.database ?? 'no answer'})`;
			}
			if (databaseChecked) missing.push(databaseChecked);
			if (missing.length) {
				const msg = `Missing seeded data: ${missing.join('; ')}`;
				if (env().requireData) throw new Error(`${msg}. TVT_E2E_REQUIRE_DATA=1, so this fails instead of skipping.`);
				testInfo.skip(true, msg);
			}
			await use();
		},
		{ auto: true }
	],
	offsite: [
		async ({ page, baseURL }, use) => {
			const origin = new URL(baseURL!).origin;
			const offsite: string[] = [];
			await page.context().route(
				(url) => !['data:', 'blob:'].includes(url.protocol) && url.origin !== origin,
				(route) => {
					offsite.push(route.request().url());
					return route.abort('blockedbyclient');
				}
			);
			await use(offsite);
		},
		{ auto: true }
	],
	consoleErrors: async ({ page }, use) => {
		const errors: string[] = [];
		page.on('console', (m) => {
			if (m.type() === 'error') errors.push(m.text());
		});
		page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
		await use(errors);
	}
});

/** Kinds of request that mean the map is still loading (not the 15 s polls). */
const LOADING = /\/tiles\/|\/api\/(?!transit\/vehicles|transit\/tracks|cameras\/live)/;

/**
 * Wait until the map has loaded: `__tvt.ready` when the app provides it
 * (WP1), else the map canvas and no map request in flight for `quietMs`.
 */
export async function mapReady(page: Page, { timeout = 180_000, quietMs = 2500 } = {}) {
	const start = Date.now();
	let inflight = 0;
	let last = Date.now();
	const onReq = (r: { url(): string }) => {
		if (LOADING.test(r.url())) {
			inflight++;
			last = Date.now();
		}
	};
	const onDone = (r: { url(): string }) => {
		if (LOADING.test(r.url())) {
			inflight = Math.max(0, inflight - 1);
			last = Date.now();
		}
	};
	page.on('request', onReq);
	page.on('requestfinished', onDone);
	page.on('requestfailed', onDone);
	try {
		await page.waitForFunction(
			() => (globalThis as any).__tvt || document.querySelector('.maplibregl-canvas'),
			null,
			{ timeout }
		);
		if (await page.evaluate(() => Boolean((globalThis as any).__tvt?.ready))) {
			await page.evaluate(() => (globalThis as any).__tvt.ready);
			return 'tvt';
		}
		while (inflight > 0 || Date.now() - last < quietMs) {
			if (Date.now() - start > timeout) throw new Error(`the map didn't settle in ${timeout} ms (${inflight} in flight)`);
			await page.waitForTimeout(250);
		}
		return 'quiet';
	} finally {
		page.off('request', onReq);
		page.off('requestfinished', onDone);
		page.off('requestfailed', onDone);
	}
}

/** Where a spec's evidence goes: data/dev/screens/<wp>/<name>. */
export const screenPath = (name: string) => join(env().screens, name);
