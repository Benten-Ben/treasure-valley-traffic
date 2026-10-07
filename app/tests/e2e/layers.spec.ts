import type { Page } from '@playwright/test';
import { appendFileSync } from 'node:fs';
import postgres from 'postgres';
import { recordNetwork } from '../../scripts/net.mjs';
import { expect, mapReady, screenPath, test } from './fixtures.js';

/**
 * layers (docs/14 §14.10, WP2 acceptance; §14.11): the layer system and the
 * chrome. Any combination of layers toggles cleanly and keeps one draped
 * run; the set survives a reload and travels in the hash; the keys behave;
 * the picker gives a bus over a road the bus card and lists every route where
 * several share a street; one base flavor (WP4: Valley or Clay, no wash layer),
 * whatever is on; labels under the buses;
 * a loaded toggle makes no request; loading and error states show; the
 * overlay draws 1,000 sprites where map.project says, picks them and moves
 * them without setData; Space on a focused button only presses it.
 */

type Info = {
	enabled: string[];
	shown: string[];
	status: Record<string, string>;
	errors: Record<string, string | null>;
	clay: boolean;
	flavor: 'valley' | 'clay';
	selection: { kind: string; id: string; layer: string; title: string } | null;
	keys: string[];
	overlay: { ok: boolean; frames: number };
};

const info = (page: Page): Promise<Info> => page.evaluate(() => (globalThis as any).__tvt.layers);
const enabled = async (page: Page) => [...(await info(page)).enabled].sort();
const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'Map layers' });
const layerButton = (page: Page, name: string) => toolbar(page).getByRole('button', { name, exact: true });
const ALL = ['cameras', 'streets', 'transit'];
const TITLE: Record<string, string> = { streets: 'Streets', transit: 'Transit', cameras: 'Cameras' };

/** Every layer loaded (the first idle prefetches the ones that are off). */
async function allLoaded(page: Page) {
	await expect.poll(async () => Object.values((await info(page)).status).every((s) => s === 'ready' || s === 'stale'), { timeout: 60_000 }).toBe(true);
}

/** Draped runs (MapLibre's render-to-texture stacks) in the live style, as rttStacks counts them. */
const liveRuns = (page: Page) =>
	page.evaluate(() => {
		const map = (globalThis as any).__tvt.map;
		const z = map.getZoom();
		const draped = new Set(['background', 'fill', 'line', 'raster', 'hillshade', 'color-relief']);
		const runs: string[][] = [];
		let open = false;
		for (const id of map.getLayersOrder() as string[]) {
			const l = map.getLayer(id);
			if (map.getLayoutProperty(id, 'visibility') === 'none') continue;
			if ((l.minzoom && z < l.minzoom) || (l.maxzoom && z >= l.maxzoom)) continue;
			if (draped.has(l.type)) {
				if (!open) runs.push([]);
				runs[runs.length - 1].push(id);
				open = true;
			} else open = false;
		}
		return runs;
	});

/** One pixel of the drawn map (read inside a render, while the drawing buffer is valid). */
const pixel = (page: Page, x: number, y: number) =>
	page.evaluate(
		([x, y]) =>
			new Promise<number[]>((resolve) => {
				const map = (globalThis as any).__tvt.map;
				map.once('render', () => {
					const gl = map.getCanvas().getContext('webgl2') as WebGL2RenderingContext;
					const k = gl.drawingBufferWidth / map.getCanvas().clientWidth;
					const out = new Uint8Array(4);
					gl.readPixels(Math.round(x * k), Math.round(gl.drawingBufferHeight - y * k), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, out);
					resolve([...out]);
				});
				map.triggerRepaint();
			}),
		[x, y]
	);

test.describe('layers', () => {
	test('any subset of the three layers toggles with no console errors and one draped run', { tag: '@wp2' }, async ({ page, consoleErrors, offsite }) => {
		test.setTimeout(400_000);
		await page.goto('/#map=14/43.615/-116.2023/0/45&layers=none');
		await mapReady(page);
		await allLoaded(page);
		expect(await enabled(page)).toEqual([]);
		const subsets = [[], ['streets'], ['transit'], ['cameras'], ['streets', 'transit'], ['streets', 'cameras'], ['transit', 'cameras'], ['streets', 'transit', 'cameras'], []];
		for (const want of subsets) {
			const now = await enabled(page);
			for (const id of ALL) if (now.includes(id) !== want.includes(id)) await layerButton(page, TITLE[id]).click();
			await mapReady(page);
			const i = await info(page);
			expect([...i.enabled].sort(), `enabled for [${want}]`).toEqual([...want].sort());
			expect([...i.shown].sort(), `shown for [${want}]`).toEqual([...want].sort());
			for (const id of ALL) await expect(layerButton(page, TITLE[id])).toHaveAttribute('aria-pressed', String(want.includes(id)));
			const runs = await liveRuns(page);
			expect(runs.length, `draped runs for [${want}]: ${JSON.stringify(runs)}`).toBeLessThanOrEqual(1);
			if (want.length === 3) await page.screenshot({ path: screenPath('layers-all-on.png') });
		}
		expect(consoleErrors).toEqual([]);
		expect(offsite).toEqual([]);
	});

	test('a reload, a #…&layers= link and the old lens restore the set', { tag: '@wp2' }, async ({ page, browser, baseURL }) => {
		test.setTimeout(300_000);
		await page.goto('/#map=13/43.6/-116.3/0/30');
		await mapReady(page);
		expect(await enabled(page), 'a first visit').toEqual(['cameras', 'transit']);
		await layerButton(page, 'Streets').click();
		await layerButton(page, 'Cameras').click();
		await expect.poll(() => page.evaluate(() => location.hash)).toMatch(/&layers=transit,streets$/);
		await page.reload();
		await mapReady(page);
		expect(await enabled(page), 'after a reload').toEqual(['streets', 'transit']);

		const other = await browser.newContext({ baseURL });
		const p2 = await other.newPage();
		await p2.goto('/#map=13/43.6/-116.3/0/30&layers=cameras,streets');
		await mapReady(p2);
		expect(await enabled(p2), 'from the hash').toEqual(['cameras', 'streets']);
		await other.close();

		const old = await browser.newContext({ baseURL });
		await old.addInitScript(() => {
			if (!sessionStorage.getItem('seeded')) {
				localStorage.setItem('tvt-lens', 'streets');
				sessionStorage.setItem('seeded', '1');
			}
		});
		const p3 = await old.newPage();
		await p3.goto('/');
		await mapReady(p3);
		expect(await enabled(p3), 'the old lens').toEqual(['streets']);
		expect(await p3.evaluate(() => [localStorage.getItem('tvt-lens'), localStorage.getItem('tvt:v2:layers')])).toEqual([null, '["streets"]']);
		await old.close();
	});

	test('2/4/7 toggle, Shift+4 solos and 1 turns all off, each again to restore', { tag: '@wp2' }, async ({ page }) => {
		await page.goto('/');
		await mapReady(page);
		expect(await enabled(page)).toEqual(['cameras', 'transit']);
		await page.keyboard.press('2');
		expect(await enabled(page)).toEqual(['cameras', 'streets', 'transit']);
		await page.keyboard.press('4');
		expect(await enabled(page)).toEqual(['cameras', 'streets']);
		await page.keyboard.press('7');
		expect(await enabled(page)).toEqual(['streets']);
		await page.keyboard.press('7');
		await page.keyboard.press('Shift+Digit4');
		expect(await enabled(page), 'Shift+4 solos Transit').toEqual(['transit']);
		await page.keyboard.press('Shift+Digit4');
		expect(await enabled(page), 'again restores').toEqual(['cameras', 'streets']);
		await page.keyboard.press('1');
		expect(await enabled(page), '1: all off').toEqual([]);
		await page.keyboard.press('1');
		expect(await enabled(page), 'again restores').toEqual(['cameras', 'streets']);
		expect((await info(page)).keys.slice(-8), 'the bindings that ran').toEqual([
			'layer-streets',
			'layer-transit',
			'layer-cameras',
			'layer-cameras',
			'solo-transit',
			'solo-transit',
			'all-layers',
			'all-layers'
		]);
	});

	test('a click on a bus over a road opens only the bus card', { tag: '@wp2' }, async ({ page }) => {
		test.setTimeout(300_000);
		const sql = postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });
		const [road] = await sql`
			select ST_X(p) as lng, ST_Y(p) as lat from (
				select ST_ClosestPoint(geom, ST_Centroid(geom)) as p from core.road_segment
				where functional_class in ('Principal Arterial', 'Minor Arterial') and ST_Length(geom::geography) > 150
				  and geom && ST_MakeEnvelope(-116.215, 43.605, -116.195, 43.62, 4326)
				order by functional_class desc, id limit 1) s`;
		await sql.end();
		expect(road, 'an arterial downtown').toBeTruthy();
		const [lng, lat] = [Number(road.lng), Number(road.lat)];
		// One bus, reporting now, right on the road (the local positions are from this morning). WP8: the
		// tracks API replaced the vehicles one; the bus's newest fix is 10 s before the playhead (now − 90 s).
		await page.route('**/api/transit/tracks**', (r) => {
			const now = Date.now() / 1000;
			r.fulfill({
				json: {
					contract: 1,
					now,
					vehicles: { 'test-bus': { label: '2213', routeId: '9', routeSource: 'feed', shortName: '9', color: '#2a78d6', textColor: '#ffffff', halo: true, headsign: null } },
					steps: [['test-bus', now - 100, null, null, lng, lat, 90, null, null]],
					routeRuns: { '9': [[now - 100, now - 100]] },
					lastFix: now - 100
				}
			});
		});
		await page.goto(`/#map=17/${lat}/${lng}/0/0&layers=streets,transit`);
		await mapReady(page);
		await expect.poll(async () => (await info(page)).status.transit).toBe('ready');
		await page.waitForTimeout(1500);
		const pt = await page.evaluate(([lng, lat]) => (globalThis as any).__tvt.map.project([lng, lat]), [lng, lat]);
		// With Transit on, streets draw on the slate ramp (WP4: 'streets-speed-under').
		const onRoad = await page.evaluate((p) => (globalThis as any).__tvt.map.queryRenderedFeatures([[p.x - 3, p.y - 3], [p.x + 3, p.y + 3]], { layers: ['streets-speed', 'streets-speed-under'] }).length, pt);
		expect(onRoad, 'the bus sits on a drawn road').toBeGreaterThan(0);
		// Hover first: the tooltip names the bus (not the road), with its source.
		await page.mouse.move(pt.x, pt.y);
		await expect(page.getByRole('tooltip')).toContainText('bus 2213');
		await expect(page.getByRole('tooltip')).toContainText('Valley Regional Transit');
		await page.mouse.click(pt.x, pt.y);
		await expect(page.getByRole('region', { name: 'Selected bus' })).toBeVisible();
		await expect(page.getByRole('region', { name: 'Selected road' })).toHaveCount(0);
		expect((await info(page)).selection).toMatchObject({ kind: 'bus', id: 'test-bus' });
		await page.screenshot({ path: screenPath('layers-bus-over-road.png') });
		// The same spot without the bus is the road, outlined while selected.
		await page.keyboard.press('4');
		await mapReady(page);
		await page.mouse.click(pt.x, pt.y);
		await expect(page.getByRole('region', { name: 'Selected road' })).toBeVisible();
		const road2 = (await info(page)).selection!;
		expect(road2.kind).toBe('street');
		expect(JSON.stringify(await page.evaluate(() => (globalThis as any).__tvt.map.getFilter('streets-selected')))).toContain(`,${road2.id}]`);
	});

	test('a click where routes overlap lists them all', { tag: '@wp2' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto('/#map=15.5/43.6152/-116.2035/0/0&layers=transit');
		await mapReady(page);
		await expect.poll(async () => (await info(page)).status.transit).toBe('ready');
		await mapReady(page);
		// A spot where at least two routes overlap, with no stop or bus there.
		const spot = await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			const c = map.getCanvas();
			let best: { x: number; y: number; ids: string[] } | null = null;
			for (let y = 120; y < c.clientHeight - 120; y += 6)
				for (let x = 320; x < c.clientWidth - 400; x += 6) {
					const box = [[x - 6, y - 6], [x + 6, y + 6]];
					const routes = map.queryRenderedFeatures(box, { layers: ['transit-routes'] });
					const ids = [...new Set(routes.map((f: any) => f.properties.routeId))] as string[];
					if (ids.length < 2) continue;
					if (map.queryRenderedFeatures([[x - 14, y - 14], [x + 14, y + 14]], { layers: ['transit-stops'] }).length) continue;
					if (!best || ids.length > best.ids.length) best = { x, y, ids };
				}
			return best;
		});
		expect(spot, 'somewhere downtown, routes share a street').not.toBeNull();
		await page.mouse.click(spot!.x, spot!.y);
		const card = page.getByRole('region', { name: 'Routes here' });
		await expect(card).toBeVisible();
		await expect(card.getByRole('heading')).toHaveText(`${spot!.ids.length} routes here`);
		await expect(card.getByRole('listitem')).toHaveCount(spot!.ids.length);
		const sel = (await info(page)).selection!;
		expect(sel.kind).toBe('routes');
		expect(sel.title).toMatch(new RegExp(`^${spot!.ids.length} routes here: `));
		await page.screenshot({ path: screenPath('layers-routes-here.png') });
		// Each opens its own route card.
		await card.getByRole('listitem').first().getByRole('button').click();
		await expect(page.getByRole('region', { name: 'Selected route' })).toBeVisible();
		expect((await info(page)).selection?.kind).toBe('route');
	});

	test('a park pixel is unchanged when a second layer turns on (one base flavor)', { tag: '@wp2' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto('/#map=14.5/43.6075/-116.2058/0/0&layers=cameras');
		await mapReady(page);
		await allLoaded(page);
		await mapReady(page);
		expect((await info(page)).clay, 'Auto: clay with a layer on').toBe(true);
		// Candidate park pixels (Ann Morrison and Julia Davis parks): inside a park, away from every camera.
		const candidates = await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			const c = map.getCanvas();
			const data = map.getLayersOrder().filter((id: string) => /^(cameras|cones|transit|streets)/.test(id));
			const out: { x: number; y: number }[] = [];
			for (let y = 140; y < c.clientHeight - 140; y += 10)
				for (let x = 330; x < c.clientWidth - 420; x += 10) {
					if (!map.queryRenderedFeatures([x, y], { layers: ['landuse_park'] }).length) continue;
					if (map.queryRenderedFeatures([[x - 16, y - 16], [x + 16, y + 16]], { layers: data }).length) continue;
					out.push({ x, y });
				}
			return out;
		});
		expect(candidates.length, 'park pixels in view').toBeGreaterThan(0);
		const before = await Promise.all(candidates.slice(0, 40).map((p) => pixel(page, p.x, p.y)));
		await page.keyboard.press('2');
		await mapReady(page);
		// Only spots the second layer doesn't draw over.
		const clear = await page.evaluate((pts) => {
			const map = (globalThis as any).__tvt.map;
			return pts.map((p) => map.queryRenderedFeatures([[p.x - 16, p.y - 16], [p.x + 16, p.y + 16]], { layers: ['streets-speed', 'streets-casing', 'streets-oneway', 'streets-speed-labels'] }).length === 0);
		}, candidates.slice(0, 40));
		const after = await Promise.all(candidates.slice(0, 40).map((p) => pixel(page, p.x, p.y)));
		let compared = 0;
		for (let i = 0; i < before.length; i++) {
			if (!clear[i]) continue;
			compared++;
			for (let k = 0; k < 3; k++) expect(Math.abs(before[i][k] - after[i][k]), `pixel ${JSON.stringify(candidates[i])} channel ${k}: ${before[i]} → ${after[i]}`).toBeLessThanOrEqual(2);
		}
		expect(compared, 'park pixels clear of the streets').toBeGreaterThan(0);
		// WP4 replaced the wash with the Clay flavor: no wash layer at all, and the ground is clay.
		const washes = await page.evaluate(() => ((globalThis as any).__tvt.map.getLayersOrder() as string[]).filter((id) => id.includes('wash')));
		expect(washes).toEqual([]);
		expect((await info(page)).flavor).toBe('clay');
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getPaintProperty('earth', 'fill-color'))).toBe('#f3ede2');
	});

	test('base labels sit below the bus layers', { tag: '@wp2' }, async ({ page }) => {
		await page.goto('/#map=13/43.6/-116.3/0/30&layers=streets,transit,cameras');
		await mapReady(page);
		await allLoaded(page);
		const order = await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			return (map.getLayersOrder() as string[]).map((id) => ({ id, type: map.getLayer(id).type }));
		});
		const at = (id: string) => order.findIndex((l) => l.id === id);
		expect(at('overlay'), 'the overlay (bus discs and plates)').toBeGreaterThan(0);
		const symbols = order.filter((l) => l.type === 'symbol');
		expect(symbols.length).toBeGreaterThan(5);
		for (const s of symbols) expect(at(s.id), `${s.id} under the buses`).toBeLessThan(at('overlay'));
		if (at('transit-buses') !== -1) for (const s of symbols.filter((x) => !x.id.startsWith('transit-bus'))) expect(at(s.id)).toBeLessThan(at('transit-buses'));
	});

	test('toggling a loaded layer makes no request', { tag: '@wp2' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto('/#map=14/43.615/-116.2023/0/45&layers=streets,transit,cameras');
		await mapReady(page);
		await allLoaded(page);
		await mapReady(page);
		const toggleAll = async () => {
			for (const name of ['Transit', 'Cameras', 'Streets']) {
				await layerButton(page, name).click();
				await mapReady(page);
				await layerButton(page, name).click();
				await mapReady(page);
			}
		};
		// A first round shows every legend and tooltip once, so their fonts are in.
		await toggleAll();
		// Then right after a tracks poll, so its 10 s interval is seldom due while Transit is back on;
		// Transit stays off for the rest, so its regular poll can't land in the count either.
		const isTracks = (url: string) => url.includes('/api/transit/tracks');
		const tracksAt: number[] = [];
		page.on('request', (r) => {
			if (isTracks(r.url())) tracksAt.push(Date.now());
		});
		await (await page.waitForRequest((r) => isTracks(r.url()), { timeout: 30_000 })).response();
		const net = await recordNetwork(page, { bodies: false });
		const mark = net.mark();
		const polls = tracksAt.length;
		await layerButton(page, 'Transit').click();
		await mapReady(page);
		await layerButton(page, 'Transit').click();
		await mapReady(page);
		await layerButton(page, 'Transit').click();
		const transitOff = Date.now();
		for (const name of ['Cameras', 'Streets']) {
			await layerButton(page, name).click();
			await mapReady(page);
			await layerButton(page, name).click();
			await mapReady(page);
		}
		const during = net.since(mark).map((x: { url: string }) => x.url);
		await net.detach();
		expect(during.filter((url: string) => !isTracks(url)), 'requests while toggling loaded layers').toEqual([]);
		// Under a loaded SwiftShader a toggle with its map settling can outlast the interval. A tracks
		// poll a full interval (POLL_MS, 10 s) after the one before is Transit's regular poll, not the
		// toggle's; one sooner than that, or once Transit is off, is a request the toggle made.
		const early = tracksAt
			.map((t, i) => ({ t, gap: i ? t - tracksAt[i - 1] : Infinity }))
			.slice(polls)
			.filter((p) => p.gap < 10_000 - 500 || p.t > transitOff + 1000);
		expect(early, 'tracks polls the toggles brought forward').toEqual([]);
	});

	test('a slow routes request shows the ring and "Loading routes…"; a 500 shows ▲ and Retry', { tag: '@wp2' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.route('**/api/transit/network**', async (r) => {
			await new Promise((res) => setTimeout(res, 3000));
			await r.continue();
		});
		await page.goto('/');
		const transit = layerButton(page, 'Transit');
		await expect(transit).toHaveAttribute('aria-busy', 'true', { timeout: 20_000 });
		await expect(page.getByRole('region', { name: 'Transit legend' }).getByText('Loading routes…')).toBeVisible();
		await page.screenshot({ path: screenPath('layers-loading.png') });
		await expect(transit).toHaveAttribute('aria-busy', 'false', { timeout: 30_000 });
		await expect(page.getByRole('region', { name: 'Transit legend' }).getByText('Loading routes…')).toHaveCount(0);

		await page.unroute('**/api/transit/network**');
		await page.route('**/api/transit/network**', (r) => r.fulfill({ status: 500, json: { message: 'the database is resting' } }));
		await page.reload();
		await mapReady(page);
		await expect(transit.locator('.warn')).toHaveText('▲');
		const legend = page.getByRole('region', { name: 'Transit legend' });
		await expect(legend.getByRole('alert')).toContainText('the database is resting');
		await transit.hover();
		await expect(page.getByRole('tooltip')).toContainText('▲');
		await page.screenshot({ path: screenPath('layers-error-retry.png') });
		await page.unroute('**/api/transit/network**');
		await legend.getByRole('button', { name: 'Retry' }).click();
		await expect.poll(async () => (await info(page)).status.transit, { timeout: 30_000 }).toBe('ready');
		await expect(transit.locator('.warn')).toHaveCount(0);
	});

	test('the overlay draws 1,000 sprites where map.project says, picks them, and moves them without setData', { tag: '@wp2' }, async ({ page }) => {
		test.setTimeout(400_000);
		// The Boise foothills, tilted: the terrain under the sprites varies by hundreds of metres.
		await page.goto('/?overlay-test#map=13.2/43.632/-116.175/25/55&layers=none');
		await mapReady(page);
		await page.waitForFunction(() => (globalThis as any).__tvtOverlayTest, null, { timeout: 60_000 });
		const t = await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			const c = map.getCenter();
			return { ok: (globalThis as any).__tvtOverlayTest.ok(), terrain: Boolean(map.getTerrain()), ground: map.queryTerrainElevation([c.lng, c.lat]) };
		});
		expect(t.ok, 'the overlay is running').toBe(true);
		expect(t.terrain, 'terrain on').toBe(true);
		expect(t.ground, 'ground elevation at the centre (m, exaggerated)').toBeGreaterThan(500);
		await mapReady(page);
		const check = () =>
			page.evaluate(
				() =>
					new Promise<{ n: number; max: number; spread: number }>((resolve) => {
						const map = (globalThis as any).__tvt.map;
						map.once('render', () => {
							const pos = (globalThis as any).__tvtOverlayTest.positions();
							let max = 0;
							const elev = pos.map((p: any) => map.queryTerrainElevation([p.lng, p.lat]) ?? 0);
							for (const p of pos) {
								const q = map.project([p.lng, p.lat]);
								max = Math.max(max, Math.hypot(q.x - p.x, q.y - p.y));
							}
							resolve({ n: pos.length, max, spread: Math.max(...elev) - Math.min(...elev) });
						});
						map.triggerRepaint();
					})
			);
		const r = await check();
		const placed = `${r.n} sprites, max ${r.max.toFixed(4)} px from map.project, ground spread ${r.spread.toFixed(0)} m`;
		test.info().annotations.push({ type: 'overlay', description: placed });
		appendFileSync(screenPath('layers-overlay.txt'), `${new Date().toISOString()} placement: ${placed}\n`);
		expect(r.n).toBe(1000);
		expect(r.spread, 'sprites over varied terrain').toBeGreaterThan(50);
		expect(r.max).toBeLessThanOrEqual(0.5);
		await page.screenshot({ path: screenPath('layers-overlay-1000.png') });

		// Picking: a sprite in the lower middle of the grid (40 columns, 25 rows).
		const target = await page.evaluate(() => (globalThis as any).__tvtOverlayTest.positions()[20 * 40 + 20]);
		await page.mouse.click(target.x, target.y);
		await expect.poll(async () => (await info(page)).selection).toMatchObject({ kind: 'sprite', id: target.id, layer: 'overlay-test' });
		await expect(page.getByRole('region', { name: 'Selected marker' })).toBeVisible();

		// Moving: frames come, positions change, and no source gets setData.
		await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			(globalThis as any).__setData = 0;
			for (const id of Object.keys(map.getStyle().sources)) {
				const src = map.getSource(id);
				if (typeof src?.setData !== 'function') continue;
				const orig = src.setData.bind(src);
				src.setData = (...a: unknown[]) => {
					(globalThis as any).__setData++;
					return orig(...a);
				};
			}
		});
		const frames0 = await page.evaluate(() => (globalThis as any).__tvtOverlayTest.frames());
		const p0 = await page.evaluate(() => (globalThis as any).__tvtOverlayTest.positions().slice(0, 50));
		await page.evaluate(() => (globalThis as any).__tvtOverlayTest.setMoving(true));
		await page.waitForTimeout(3000);
		const frames1 = await page.evaluate(() => (globalThis as any).__tvtOverlayTest.frames());
		const p1 = await page.evaluate(() => (globalThis as any).__tvtOverlayTest.positions().slice(0, 50));
		await page.evaluate(() => (globalThis as any).__tvtOverlayTest.setMoving(false));
		const setData = await page.evaluate(() => (globalThis as any).__setData);
		const moved = p0.filter((p: any, i: number) => Math.hypot(p.x - p1[i].x, p.y - p1[i].y) > 0.05).length;
		const motion = `${frames1 - frames0} frames in 3 s, ${moved}/50 sprites moved, ${setData} setData calls`;
		test.info().annotations.push({ type: 'moving', description: motion });
		appendFileSync(screenPath('layers-overlay.txt'), `${new Date().toISOString()} moving: ${motion}\n`);
		expect(frames1 - frames0, 'frames while moving').toBeGreaterThan(3);
		expect(moved, 'sprites that moved').toBeGreaterThan(40);
		expect(setData, 'setData calls while moving').toBe(0);
	});

	test('Space or Enter on a focused toolbar button presses only the button', { tag: '@wp2' }, async ({ page }) => {
		await page.goto('/');
		await mapReady(page);
		const streets = layerButton(page, 'Streets');
		await streets.focus();
		const keys0 = (await info(page)).keys.length;
		await page.keyboard.press('Space');
		await expect(streets).toHaveAttribute('aria-pressed', 'true');
		expect(await enabled(page)).toEqual(['cameras', 'streets', 'transit']);
		await page.keyboard.press('Enter');
		await expect(streets).toHaveAttribute('aria-pressed', 'false');
		expect((await info(page)).keys.length, 'no shortcut ran').toBe(keys0);
		// Other shortcuts still work from a focused button; ← and → move along the toolbar.
		await page.keyboard.press('4');
		expect(await enabled(page)).toEqual(['cameras']);
		await page.keyboard.press('ArrowRight');
		await expect(layerButton(page, 'Transit')).toBeFocused();
		await page.keyboard.press('ArrowLeft');
		await page.keyboard.press('ArrowLeft');
		await expect(toolbar(page).getByRole('button', { name: 'Base' })).toBeFocused();
	});

	test('the Base popover drives the flavor, buildings, terrain and labels; Help and Esc', { tag: '@wp2' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto('/#map=15/43.6152/-116.2035/0/45&layers=none');
		await mapReady(page);
		const vis = (id: string) => page.evaluate((id) => (globalThis as any).__tvt.map.getLayoutProperty(id, 'visibility') ?? 'visible', id);
		// The look is the basemap flavor now (WP4), not a wash layer.
		expect((await info(page)).flavor, 'Auto with no layer: the map look').toBe('valley');
		await toolbar(page).getByRole('button', { name: 'Base' }).click();
		const pop = page.getByRole('dialog', { name: 'Base map' });
		await expect(pop).toBeVisible();
		await pop.getByRole('radio', { name: 'Clay' }).check();
		expect((await info(page)).flavor).toBe('clay');
		await pop.getByRole('radio', { name: 'Map' }).check();
		expect((await info(page)).flavor).toBe('valley');
		await pop.getByRole('switch', { name: '3D buildings' }).uncheck();
		// Both tones: measured heights and estimated ones.
		expect(await vis('buildings-3d')).toBe('none');
		expect(await vis('buildings-3d-estimated')).toBe('none');
		await pop.getByRole('switch', { name: 'Terrain' }).uncheck();
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getTerrain())).toBeNull();
		await pop.getByRole('radio', { name: 'Fewer' }).check();
		expect(await vis('pois')).toBe('none');
		await page.screenshot({ path: screenPath('layers-base-popover.png') });
		await pop.getByRole('switch', { name: 'Terrain' }).check();
		expect(await page.evaluate(() => Boolean((globalThis as any).__tvt.map.getTerrain()))).toBe(true);
		// Esc closes the popover first.
		await page.keyboard.press('Escape');
		await expect(pop).toHaveCount(0);
		// Help opens with ?, lists the keys, and Esc closes it before anything else.
		await page.keyboard.press('2');
		await mapReady(page);
		await page.keyboard.press('Shift+Slash');
		const help = page.getByRole('dialog', { name: 'Keys' });
		await expect(help).toBeVisible();
		await expect(help.getByText('Toggle Transit')).toBeVisible();
		await expect(help.getByText('Home: over Meridian')).toBeVisible();
		await page.screenshot({ path: screenPath('layers-help.png') });
		await page.keyboard.press('Escape');
		await expect(help).toHaveCount(0);
		// The settings stay after a reload.
		await page.reload();
		await mapReady(page);
		expect(await vis('buildings-3d')).toBe('none');
		expect(await vis('buildings-3d-estimated')).toBe('none');
		expect(await vis('pois')).toBe('none');
	});

	test('the phone layout: a tab bar and a sheet, no horizontal scroll', { tag: '@wp2' }, async ({ page }) => {
		await page.setViewportSize({ width: 390, height: 844 });
		await page.goto('/');
		await mapReady(page);
		const tabs = page.getByRole('navigation', { name: 'Map layers' });
		await expect(tabs).toBeVisible();
		await expect(page.getByRole('toolbar', { name: 'Map layers' })).toHaveCount(0);
		await expect(page.getByRole('region', { name: 'Details' })).toBeVisible();
		expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
		for (const b of await tabs.getByRole('button').all()) expect((await b.boundingBox())!.height).toBeGreaterThanOrEqual(44);
		await tabs.getByRole('button', { name: 'Streets' }).click();
		expect(await enabled(page)).toEqual(['cameras', 'streets', 'transit']);
		await page.screenshot({ path: screenPath('layers-phone.png') });
	});
});
