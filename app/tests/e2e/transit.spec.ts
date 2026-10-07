import type { Page, Route } from '@playwright/test';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import type { TransitNetwork } from '../../src/lib/contracts/network.js';
import type { Tracks } from '../../src/lib/contracts/tracks.js';

/**
 * transit (docs/14 §14.10 WP8, §14.11): the Transit client on a replay.
 *
 * The local clone holds the morning of Oct 6 (fixes 11:23–15:00 UTC), not
 * the Oct 5 20:17–20:34 minutes the plan names, so the replay is pinned at
 * 14:30 UTC (8:30 AM MDT), as WP7's tracks spec does.
 *
 * - buses move between two screenshots 5 s apart at the default view (z10),
 *   without the 3D scene chunk;
 * - a change in which routes run makes 0 `setData` on the ribbon source, and
 *   bus positions make none at all; with trails on, at most one a second;
 * - with no input at z ≤ 12 the map renders at 5 fps or less, and the loop
 *   stops when the tab is hidden or the layer is off;
 * - the time pill's states, Space and L (Space on a focused button presses
 *   only the button);
 * - the bus, route and stop cards, spotlight and follow.
 */
const AT = '2026-10-06T14:30:00Z';
const AT_S = Date.parse(AT) / 1000;
const MINUS = '\u2212';
const APP = resolve(import.meta.dirname, '..', '..');

interface BusDebug {
	id: string;
	lng: number;
	lat: number;
	state: string | null;
	opacity: number;
	x: number | null;
	y: number | null;
}

const transit = <T>(page: Page, fn: string): Promise<T> => page.evaluate((f) => (globalThis as any).__tvtTransit[f](), fn);
const buses = (page: Page) => transit<BusDebug[]>(page, 'buses');
const drawn = async (page: Page) => (await buses(page)).filter((b) => b.x !== null && b.opacity > 0);
const pill = (page: Page) => page.locator('.pill-button');
const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'Map layers' });
const layerButton = (page: Page, name: string) => toolbar(page).getByRole('button', { name, exact: true });

async function transitReady(page: Page) {
	await mapReady(page);
	await page.waitForFunction(() => (globalThis as any).__tvtTransit, null, { timeout: 120_000 });
	await expect.poll(async () => (await drawn(page)).length, { timeout: 60_000 }).toBeGreaterThan(0);
}

/** The 3D scene chunk's file in the build (WP9), or null when the build has none. */
function sceneChunk(): string | null {
	const file = resolve(APP, '.svelte-kit', 'output', 'client', '.vite', 'manifest.json');
	if (!existsSync(file)) return null;
	const manifest = JSON.parse(readFileSync(file, 'utf8')) as Record<string, { src?: string; file: string }>;
	return Object.values(manifest).find((v) => v.src === 'src/lib/scene/index.ts')?.file ?? null;
}

/** Count setData / updateData per GeoJSON source from now on (`__setData`). */
async function countSetData(page: Page) {
	await page.evaluate(() => {
		const g = globalThis as any;
		g.__setData = {};
		if (g.__setDataWrapped) return;
		const proto = Object.getPrototypeOf(g.__tvt.map.getSource('transit-ribbons'));
		for (const name of ['setData', 'updateData']) {
			const orig = proto[name];
			proto[name] = function (this: { id: string }, ...args: unknown[]) {
				g.__setData[this.id] = (g.__setData[this.id] ?? 0) + 1;
				return orig.apply(this, args);
			};
		}
		g.__setDataWrapped = true;
	});
}
const setDataCounts = (page: Page): Promise<Record<string, number>> => page.evaluate(() => ({ ...(globalThis as any).__setData }));

/** Rendered frames (map 'render' events) over `ms`. */
async function framesOver(page: Page, ms: number): Promise<number> {
	return page.evaluate(async (ms) => {
		const map = (globalThis as any).__tvt.map;
		let n = 0;
		const on = () => n++;
		map.on('render', on);
		await new Promise((r) => setTimeout(r, ms));
		map.off('render', on);
		return n;
	}, ms);
}

async function setVisibility(page: Page, state: 'hidden' | 'visible') {
	await page.evaluate((state) => {
		Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
		Object.defineProperty(document, 'hidden', { configurable: true, get: () => state === 'hidden' });
		document.dispatchEvent(new Event('visibilitychange'));
	}, state);
}

/** §14.4 "Running", as the client decides it. */
function runningAt(runs: Record<string, [number, number][]>, T: number): string[] {
	return Object.entries(runs)
		.filter(([, spans]) => spans.some(([a, b]) => a <= T && b >= T - 900))
		.map(([r]) => r)
		.sort();
}

/**
 * Serve the replay as if it were live: the real answer at AT, every time
 * shifted to now (minus `stallS`, to make the feed look stalled).
 */
function liveFromReplay(base: string, stallS = () => 0) {
	return async (route: Route) => {
		const url = new URL(route.request().url());
		const w = url.searchParams.get('window') ?? '120';
		const res = await route.fetch({ url: `${base}/api/transit/tracks?window=${w}&at=${AT}` });
		const t: Tracks = await res.json();
		const now = Date.now() / 1000;
		const shift = now - AT_S - stallS();
		t.now = now;
		t.steps = t.steps.map((s) => [s[0], s[1] + shift, s[2] === null ? null : s[2] + shift, ...s.slice(3)] as Tracks['steps'][number]);
		t.routeRuns = Object.fromEntries(Object.entries(t.routeRuns).map(([r, spans]) => [r, spans.map(([a, b]) => [a + shift, b + shift] as [number, number])]));
		t.lastFix = t.lastFix === null ? null : t.lastFix + shift;
		await route.fulfill({ json: t, headers: { 'cache-control': 'no-store' } });
	};
}

test.describe('transit', () => {
	test('a replay moves buses between two screenshots 5 s apart at the default view, without the scene chunk', { tag: '@wp8' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		const chunk = sceneChunk();
		const sceneRequests: string[] = [];
		page.on('request', (r) => {
			if (chunk && r.url().includes(chunk)) sceneRequests.push(r.url());
		});
		// Once WP9 is merged it prefetches the chunk after the first idle when Transit is on: block it,
		// so the buses provably move without it.
		if (chunk) await page.route(`**/${chunk}`, (r) => r.abort());
		await page.goto(`/?at=${AT}`);
		await transitReady(page);
		await expect.poll(async () => (await drawn(page)).length, { timeout: 60_000 }).toBeGreaterThanOrEqual(15);
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getZoom())).toBeCloseTo(10, 1);
		await expect(pill(page)).toContainText('REPLAY');
		const t0 = await transit<number>(page, 'playhead');
		const a = await drawn(page);
		const shotA = await page.screenshot({ path: screenPath('transit-replay-z10-a.png') });
		await page.waitForTimeout(5000);
		const b = await drawn(page);
		const shotB = await page.screenshot({ path: screenPath('transit-replay-z10-b.png') });
		const t1 = await transit<number>(page, 'playhead');
		expect(t1 - t0, 'the playhead runs in real time').toBeGreaterThan(4);
		// Each SwiftShader screenshot takes a second or two.
		expect(t1 - t0).toBeLessThan(20);
		// The replay starts at `at` minus the 90 s delay.
		expect(t0).toBeGreaterThan(AT_S - 90);
		expect(t0).toBeLessThan(AT_S - 60);
		const before = new Map(a.map((x) => [x.id, x]));
		const moved = b.filter((x) => {
			const p = before.get(x.id);
			return p && (p.lng !== x.lng || p.lat !== x.lat) && Math.hypot(x.x! - p.x!, x.y! - p.y!) > 0.2;
		});
		console.log(`buses drawn ${a.length} → ${b.length}; moved ${moved.length}; scene chunk ${chunk ?? '(none in this build)'} requested ${sceneRequests.length}×`);
		expect(moved.length, 'buses that moved in 5 s').toBeGreaterThanOrEqual(3);
		expect(shotA.equals(shotB), 'the two screenshots differ').toBe(false);
		// Drawn by the overlay, not a symbol layer.
		expect(await transit<boolean>(page, 'overlay')).toBe(true);
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getLayer('transit-buses'))).toBeUndefined();
		if (!chunk) expect(sceneRequests).toEqual([]);
		expect(consoleErrors.filter((e) => !e.includes('net::ERR_FAILED'))).toEqual([]);
	});

	test('running changes make 0 setData on the ribbon source; bus motion none; trails at most one a second', { tag: '@wp8' }, async ({ page, request }) => {
		test.setTimeout(300_000);
		// A replay time X when the 1-minute and 5-minute delays see different routes running (service
		// starting up), and still the same two sets 30 s later (the replay runs on while the test does).
		// The spans at 13:00 cover 11:45–13:00, enough to decide for X from 12:00.
		const runs: Tracks = await (await request.get('/api/transit/tracks?at=2026-10-06T13:00:00Z&window=60')).json();
		const same = (a: string[], b: string[]) => JSON.stringify(a) === JSON.stringify(b);
		let at: string | null = null;
		let sets: [string[], string[]] = [[], []];
		for (let X = Date.parse('2026-10-06T12:00:00Z') / 1000; X < runs.now - 30; X += 30) {
			const one = runningAt(runs.routeRuns, X - 60);
			const five = runningAt(runs.routeRuns, X - 300);
			if (same(one, five) || !same(one, runningAt(runs.routeRuns, X - 30)) || !same(five, runningAt(runs.routeRuns, X - 270))) continue;
			at = new Date(X * 1000).toISOString();
			sets = [one, five];
			break;
		}
		expect(at, 'a replay time when the running set changes').not.toBeNull();
		console.log(`replay at ${at}: running with a 1-min delay ${sets[0].join(' ')}; with 5 min ${sets[1].join(' ')}`);
		const net: TransitNetwork = await (await request.get('/api/transit/network')).json();
		const rid = Object.fromEntries(net.routes.map((r) => [r.id, r.rid]));

		await page.goto(`/?at=${at}#map=11/43.61/-116.3/0/0&layers=transit`);
		await transitReady(page);
		await countSetData(page);
		const active = (id: string) =>
			page.evaluate((id) => Boolean((globalThis as any).__tvt.map.getFeatureState({ source: 'transit-ribbons', id })?.active), rid[id]);

		// The 1-minute delay, then the 5-minute one: the playhead jumps back 4 minutes.
		await pill(page).click();
		await page.getByRole('radio', { name: /^1 min/ }).check();
		await expect.poll(() => transit<string[]>(page, 'running'), { timeout: 10_000 }).toEqual(sets[0]);
		for (const id of sets[0]) expect(await active(id), `route ${id} drawn running`).toBe(true);
		await page.getByRole('radio', { name: /^5 min/ }).check();
		await page.keyboard.press('Escape');
		await expect.poll(() => transit<string[]>(page, 'running'), { timeout: 10_000 }).toEqual(sets[1]);
		for (const id of net.routes.map((r) => r.id)) expect(await active(id), `route ${id}`).toBe(sets[1].includes(id));
		await expect(page.getByRole('region', { name: 'Transit legend' })).toContainText(`Running now`);
		// Buses keep moving for a while: still nothing but the shields (on the running change) was set.
		await page.waitForTimeout(5000);
		const counts = await setDataCounts(page);
		console.log('setData while running changed and buses moved:', JSON.stringify(counts));
		expect(counts['transit-ribbons'] ?? 0, 'ribbon source').toBe(0);
		expect(counts['transit-shields'] ?? 0, 'shields: once per running change').toBeLessThanOrEqual(2);
		const others = Object.entries(counts).filter(([id]) => id.startsWith('transit-') && id !== 'transit-shields');
		expect(others, 'no other Transit setData (bus positions included)').toEqual([]);
		await page.screenshot({ path: screenPath('transit-running-changed.png') });

		// Trails on: one line source, at most once a second.
		await page.getByRole('checkbox', { name: /Trails/ }).check();
		await countSetData(page);
		const t0 = Date.now();
		await page.waitForTimeout(10_000);
		const trails = await setDataCounts(page);
		const seconds = (Date.now() - t0) / 1000;
		const total = Object.entries(trails).filter(([id]) => id.startsWith('transit-')).reduce((a, [, b]) => a + b, 0);
		console.log(`with trails on, ${total} setData in ${seconds.toFixed(1)} s:`, JSON.stringify(trails));
		expect(trails['transit-trails'] ?? 0).toBeGreaterThan(0);
		expect(total).toBeLessThanOrEqual(Math.ceil(seconds) + 1);
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getLayoutProperty('transit-trails', 'visibility'))).toBe('visible');
		await page.screenshot({ path: screenPath('transit-trails.png') });
	});

	test('with no input at z ≤ 12 the map renders at 5 fps or less; the loop stops when hidden or off', { tag: '@wp8' }, async ({ page }) => {
		test.setTimeout(300_000);
		const results: string[] = [];
		for (const view of ['10/43.6/-116.4/0/45', '12/43.61/-116.25/0/0']) {
			await page.goto(`/?at=${AT}#map=${view}&layers=transit`);
			await transitReady(page);
			await mapReady(page);
			await page.waitForTimeout(2000);
			const frames = await framesOver(page, 10_000);
			results.push(`${view}: ${frames} frames in 10 s`);
			expect(frames / 10, `fps at ${view}`).toBeLessThanOrEqual(5);
			expect(frames, 'buses are moving, so some frames come').toBeGreaterThan(0);
		}
		// Hidden: no frames at all.
		await setVisibility(page, 'hidden');
		await page.waitForTimeout(500);
		const hiddenFrames = await framesOver(page, 4000);
		expect(hiddenFrames, 'frames while hidden').toBe(0);
		await setVisibility(page, 'visible');
		await expect.poll(() => framesOver(page, 1500), { timeout: 10_000 }).toBeGreaterThan(0);
		// The layer off: no frames, and the buses stop asking for them.
		await page.keyboard.press('4');
		await expect(layerButton(page, 'Transit')).toHaveAttribute('aria-pressed', 'false');
		await page.waitForTimeout(1000);
		const offFrames = await framesOver(page, 4000);
		expect(offFrames, 'frames with Transit off').toBe(0);
		expect(await transit<boolean>(page, 'animating')).toBe(false);
		results.push(`hidden: ${hiddenFrames}; off: ${offFrames}`);
		console.log(results.join('\n'));
	});

	test('the time pill: live, delay, pause, stalled and replay; Space and L', { tag: '@wp8' }, async ({ page, baseURL }) => {
		test.setTimeout(300_000);
		let stall = 0;
		await page.route('**/api/transit/tracks**', liveFromReplay(baseURL!, () => stall));
		await page.goto('/#map=12/43.61/-116.25/0/0&layers=transit');
		await transitReady(page);
		await expect(pill(page)).toHaveText(`LIVE ${MINUS}1:30`);
		await expect(pill(page)).toHaveClass(/\blive\b/);
		await pill(page).click();
		const pop = page.getByRole('dialog', { name: 'Playback' });
		await expect(pop).toContainText('buses may pause');
		await pop.getByRole('radio', { name: /^3 min/ }).check();
		await expect(pill(page)).toHaveText(`LIVE ${MINUS}3:00`);
		await page.screenshot({ path: screenPath('transit-pill-popover.png') });
		await page.keyboard.press('Escape');
		await expect(pop).toHaveCount(0);
		await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

		// Space pauses (the playhead freezes), Space plays on behind, L goes back to live.
		await page.keyboard.press('Space');
		await expect(pill(page)).toContainText(`PAUSED ${MINUS}3:0`);
		const p0 = await transit<number>(page, 'playhead');
		await page.waitForTimeout(2500);
		expect(await transit<number>(page, 'playhead')).toBe(p0);
		await expect(pill(page)).toContainText(`PAUSED ${MINUS}3:0`);
		await page.screenshot({ path: screenPath('transit-pill-paused.png'), clip: { x: 640, y: 0, width: 640, height: 70 } });
		await page.keyboard.press('Space');
		await expect(pill(page)).toContainText(`BEHIND ${MINUS}3:0`);
		await page.keyboard.press('KeyL');
		await expect(pill(page)).toHaveText(`LIVE ${MINUS}3:00`);

		// Space on a focused button presses only the button.
		await layerButton(page, 'Transit').focus();
		await page.keyboard.press('Space');
		await expect(layerButton(page, 'Transit')).toHaveAttribute('aria-pressed', 'false');
		await expect(pill(page)).toHaveText(`LIVE ${MINUS}3:00`);
		await page.keyboard.press('Space');
		await expect(layerButton(page, 'Transit')).toHaveAttribute('aria-pressed', 'true');
		await expect(pill(page)).toHaveText(`LIVE ${MINUS}3:00`);

		// The feed stalls: no new GPS for minutes.
		stall = 200;
		await page.reload();
		await transitReady(page);
		await expect(pill(page)).toHaveText(/^LIVE · no new GPS for \d+ min$/, { timeout: 30_000 });
		await expect(pill(page)).toHaveClass(/\bstalled\b/);
		await page.screenshot({ path: screenPath('transit-pill-stalled.png'), clip: { x: 640, y: 0, width: 640, height: 70 } });

		// A replay link, then L: back to live, and `?at=` leaves the address.
		await page.unroute('**/api/transit/tracks**');
		await page.goto(`/?at=${AT}#map=12/43.61/-116.25/0/0&layers=transit`);
		await transitReady(page);
		await expect(pill(page)).toHaveText(/REPLAY · Oct 6/);
		await page.keyboard.press('KeyL');
		await expect(pill(page)).not.toContainText('REPLAY');
		await expect.poll(() => new URL(page.url()).searchParams.has('at')).toBe(false);
	});

	test('the bus, route and stop cards; spotlight; follow', { tag: '@wp8' }, async ({ page, request }) => {
		test.setTimeout(300_000);
		const net: TransitNetwork = await (await request.get('/api/transit/network')).json();
		await page.goto(`/?at=${AT}#map=13.5/43.6125/-116.235/0/0&layers=transit`);
		await transitReady(page);
		// A moving bus clear of the panels.
		const pick = async () => {
			const list = await drawn(page);
			return list.find((b) => b.state === 'moving' && b.x! > 340 && b.x! < 860 && b.y! > 120 && b.y! < 640) ?? null;
		};
		await expect.poll(pick, { timeout: 60_000 }).not.toBeNull();
		const bus = (await pick())!;
		const now = (await buses(page)).find((b) => b.id === bus.id)!;
		await page.mouse.click(now.x!, now.y!);
		const card = page.getByRole('region', { name: 'Selected bus' });
		await expect(card).toBeVisible();
		await expect(card).toContainText('Bus ');
		await expect(card).toContainText('Valley Regional Transit (CC BY 3.0)');
		await expect(card).toContainText(/Last fix \d+:\d\d:\d\d [AP]M/);
		await expect(card).toContainText(/between reported positions|At its reported position|waiting for GPS/i);
		await page.screenshot({ path: screenPath('transit-bus-card.png') });

		// Follow: the view keeps the bus at its centre; a drag ends it.
		await card.getByRole('button', { name: 'Follow', exact: true }).click();
		await expect(card.getByRole('button', { name: /Following/ })).toBeVisible();
		await page.waitForTimeout(3000);
		const off = await page.evaluate((id) => {
			const map = (globalThis as any).__tvt.map;
			const b = (globalThis as any).__tvtTransit.buses().find((x: { id: string }) => x.id === id);
			const p = map.project([b.lng, b.lat]);
			const c = map.project(map.getCenter());
			return Math.hypot(p.x - c.x, p.y - c.y);
		}, bus.id);
		expect(off, 'px between the bus and the centre while following').toBeLessThan(3);
		await page.screenshot({ path: screenPath('transit-follow.png') });
		await page.mouse.move(700, 500);
		await page.mouse.down();
		await page.mouse.move(760, 540, { steps: 6 });
		await page.mouse.up();
		await expect(card.getByRole('button', { name: 'Follow', exact: true })).toBeVisible();

		// A route from the legend: its card, and the spotlight (every other route takes its ghost).
		const legend = page.getByRole('region', { name: 'Transit legend' });
		const running = await transit<string[]>(page, 'running');
		const r = net.routes.find((x) => x.id === running[0])!;
		await legend.getByRole('button', { name: new RegExp(`^${r.shortName}\\b`) }).first().click();
		const routeCard = page.getByRole('region', { name: 'Selected route' });
		await expect(routeCard).toContainText('Running now');
		await expect(routeCard.getByRole('button', { name: /Spotlight/ })).toHaveAttribute('aria-pressed', 'true');
		const states = await page.evaluate(
			(ids) => ids.map((id) => (globalThis as any).__tvt.map.getFeatureState({ source: 'transit-ribbons', id })),
			net.routes.map((x) => x.rid)
		);
		net.routes.forEach((x, i) => {
			expect(Boolean(states[i].spot), `route ${x.id} spot`).toBe(x.id === r.id);
			expect(Boolean(states[i].dim), `route ${x.id} dim`).toBe(x.id !== r.id);
		});
		await page.screenshot({ path: screenPath('transit-route-spotlight.png') });
		await page.keyboard.press('Escape');

		// A stop: zoom in, click a capsule.
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ center: [-116.2035, 43.6152], zoom: 15.5 }));
		await mapReady(page);
		const stop = await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			const c = map.getCanvas();
			const fs = map.queryRenderedFeatures([[340, 120], [c.clientWidth - 420, c.clientHeight - 160]], { layers: ['transit-stops'] });
			for (const f of fs) {
				const p = map.project(f.geometry.coordinates);
				const busy = map.queryRenderedFeatures([[p.x - 16, p.y - 16], [p.x + 16, p.y + 16]], { layers: ['transit-hubs'] }).length;
				const near = (globalThis as any).__tvtTransit.buses().some((b: { x: number | null; y: number | null }) => b.x !== null && Math.hypot(b.x - p.x, b.y! - p.y) < 30);
				if (!busy && !near) return { x: p.x, y: p.y, name: f.properties.name };
			}
			return null;
		});
		expect(stop, 'a stop capsule downtown').not.toBeNull();
		await page.mouse.click(stop!.x, stop!.y);
		const stopCard = page.getByRole('region', { name: 'Selected stop' });
		await expect(stopCard).toContainText('Routes that stop here');
		await expect(stopCard).toContainText(/running|not running/);
		await page.screenshot({ path: screenPath('transit-stop-card.png') });
	});

	test('screenshots: downtown hub and the Fairview–Five Mile corridor, desktop and phone', { tag: '@wp8' }, async ({ page }) => {
		test.setTimeout(400_000);
		const shots: [string, string, { width: number; height: number }][] = [
			['transit-1-downtown-hub-z15', '15/43.6152/-116.2035/0/0&layers=transit', { width: 1280, height: 800 }],
			['transit-2-fairview-five-mile-z14', '14/43.6175/-116.3125/0/0&layers=streets,transit', { width: 1280, height: 800 }],
			['transit-1-downtown-hub-z15-phone', '15/43.6152/-116.2035/0/0&layers=transit', { width: 390, height: 844 }],
			['transit-2-fairview-five-mile-z14-phone', '14/43.6175/-116.3125/0/0&layers=streets,transit', { width: 390, height: 844 }]
		];
		for (const [name, hash, size] of shots) {
			await page.setViewportSize(size);
			await page.goto(`/?at=${AT}#map=${hash}`);
			await transitReady(page);
			await page.waitForTimeout(2500);
			await mapReady(page);
			// The corridor outline is drawn wherever ribbons are.
			const counts = await page.evaluate(() => {
				const map = (globalThis as any).__tvt.map;
				return {
					ribbons: map.queryRenderedFeatures({ layers: ['transit-routes'] }).length,
					outline: map.queryRenderedFeatures({ layers: ['transit-corridor-outline'] }).length
				};
			});
			expect(counts.ribbons).toBeGreaterThan(0);
			expect(counts.outline).toBeGreaterThan(0);
			await page.screenshot({ path: screenPath(`${name}.png`) });
		}
	});
});
