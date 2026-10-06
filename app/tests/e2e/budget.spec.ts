import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Page } from '@playwright/test';
import { firstAt, MB, recordNetwork, summarize } from '../../scripts/net.mjs';
import { env, expect, mapReady, test } from './fixtures.js';

/**
 * budget (docs/14 §14.9 "Targets", §14.11): what a cold first load at the
 * default view costs, measured the way perf.mjs --budget does (25 Mbps,
 * 40 ms; JS and JSON counted at their gzip size).
 *
 * The first test records the numbers and holds today. The others are later
 * packages' targets, marked expected-to-fail until they're met; the package
 * that meets one removes its test.fail line.
 */
async function coldLoad(page: Page, baseURL: string) {
	const net = await recordNetwork(page, { throttle: { latencyMs: 40, mbps: 25 } });
	await page.goto('/');
	await mapReady(page);
	await net.settle();
	const summary = summarize(net.entries, new URL(baseURL).origin);
	const t0 = Math.min(...net.entries.map((x) => x.start));
	const timing = {
		firstDataStart: firstAt(net.entries, (x) => x.kind === 'api' && !x.url.includes('/api/meta'), t0),
		firstDemResponse: firstAt(net.entries, (x) => x.kind === 'terrain', t0, 'responseAt')
	};
	await net.detach();
	return { summary, timing };
}

test.describe('budget', () => {
	test('records the cold first load at the default view', { tag: '@wp0' }, async ({ page, baseURL }) => {
		const { summary, timing } = await coldLoad(page, baseURL!);
		const record = { at: new Date().toISOString(), view: 'default (manifest centre, z10, pitch 45)', ...summary, timing };
		const dir = join(process.env.TVT_MAIN!, 'data', 'dev', env().wp || 'local');
		mkdirSync(dir, { recursive: true });
		writeFileSync(join(dir, 'budget-first-load.json'), JSON.stringify(record, null, 2));
		await test.info().attach('first-load.json', { body: JSON.stringify(record, null, 2), contentType: 'application/json' });
		test.info().annotations.push({
			type: 'first load',
			description: `${summary.requests} requests, ${MB(summary.bytes)} MB (terrain ${MB(summary.byKind.terrain?.bytes ?? 0)} MB), ${summary.duplicates} duplicate ranges`
		});
		expect(summary.foreign).toEqual([]);
		expect(summary.failed).toBe(0);
		expect(summary.requests).toBeGreaterThan(10);
		expect(summary.byKind.basemap?.bytes ?? 0).toBeGreaterThan(0);
	});

	test('cold first load ≤ 6 MB, ≤ 50 requests, 0 duplicate ranges (WP5)', { tag: ['@wp0', '@wp5'] }, async ({ page, baseURL }) => {
		test.fail(true, 'WP5 target (§14.9): today two DEM sources fetch 8–13 MB of terrain.');
		const { summary } = await coldLoad(page, baseURL!);
		expect(summary.bytes).toBeLessThanOrEqual(6e6);
		expect(summary.requests).toBeLessThanOrEqual(50);
		expect(summary.duplicates).toBe(0);
	});

	test('data API requests start before the first DEM tile response (WP1)', { tag: ['@wp0', '@wp1'] }, async ({ page, baseURL }) => {
		test.fail(true, "WP1 target (§14.8 Boot): today the data layers wait for the map's load event.");
		const { timing } = await coldLoad(page, baseURL!);
		expect(timing.firstDataStart).not.toBeNull();
		expect(timing.firstDemResponse).not.toBeNull();
		expect(timing.firstDataStart!).toBeLessThan(timing.firstDemResponse!);
	});
});
