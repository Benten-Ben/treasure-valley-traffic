import type { Page } from '@playwright/test';
import { writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { tick } from '../../scripts/archive-tick.ts';
import { env, expect, mapReady, screenPath, seeds, test, type Seed } from './fixtures.js';

/**
 * review, WP15 (docs/14 §14.10 "WP15", §14.11): the final integration's own
 * evidence, on the seeded data (map-rendered camera frames only, never a real
 * camera image), in fixture mode.
 *
 * - **The screenshot matrix** (§14.11): views 1–8 at 1280×800 and 390×844,
 *   with an index (`wp15-matrix.json`) that `scripts/review-page.mjs` turns
 *   into the owner's review page (`review.html` beside the screenshots).
 * - **The visual review checklist's automatable lines** (§14.11): only
 *   same-origin requests; the credits (OpenStreetMap, Protomaps, USGS, NAIP,
 *   Overture, Valley Regional Transit, ITD 511, ACHD); the three fonts in use;
 *   no emoji icons; text contrast ≥ 4.5:1 (3:1 for large text and status
 *   shapes) in the chrome and an open window; nothing under the bars; no
 *   horizontal scroll on the phone. The rest of the checklist is judged from
 *   the screenshots (docs/14 §14.11, WP15's results).
 *
 * Buses are replayed at a busy moment of the clone's recorded day (`?at=`),
 * since the copied data ends on Oct 7 at 8:40 AM. The side-by-side ribbons
 * show only where the clone has a ribbon build (`python3 -m ingest
 * transit-ribbons`, as the deploy runbook's step 4 does); without one,
 * Transit draws each route's plain shape, and the matrix says so.
 */

type Size = { width: number; height: number };
const DESKTOP: Size = { width: 1280, height: 800 };
const PHONE: Size = { width: 390, height: 844 };
const ALL = 'transit,streets,cameras,weather';
/** 5:30 PM MDT on Oct 6, the evening peak of the recorded day (42 buses). */
const AT = '2026-10-06T23:30:00Z';

const info = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.layers as { enabled: string[]; status: Record<string, string>; flavor: string });
const mode = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.mode as string);
const seed = (kind: Seed['kind']) => seeds().seeds.find((s) => s.kind === kind)!;

/** Every layer that's switched on has loaded. */
async function allLoaded(page: Page) {
	await expect
		.poll(async () => {
			const i = await info(page);
			return i.enabled.every((id) => i.status[id] === 'ready' || i.status[id] === 'stale');
		}, { timeout: 90_000 })
		.toBe(true);
}

/** Let CSS animations finish (SwiftShader starves them while the map draws), for screenshots. */
async function settle(page: Page) {
	await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'), null, { timeout: 15_000 }).catch(() => {});
}

/** The saved Base look, set on a page of the same origin that doesn't start the map. */
async function baseLook(page: Page, look: 'auto' | 'map' | 'clay') {
	await page.goto('/api/health');
	await page.evaluate((look) => {
		localStorage.clear();
		localStorage.setItem('tvt:v2:base', JSON.stringify({ look, buildings: true, terrain: true, labels: 'full' }));
	}, look);
}

async function openMap(page: Page, hash: string) {
	await page.goto(`/?at=${AT}${hash}`);
	await mapReady(page);
	await allLoaded(page);
	if ((await info(page)).enabled.includes('transit')) {
		// The replayed buses: the chip counts them once the first tracks poll is in.
		await expect.poll(() => page.locator('.chips').innerText(), { timeout: 60_000 }).toMatch(/\b\d+ bus(es)?\b/);
	}
	await mapReady(page);
	await expect(page.getByText('Building the valley…')).toHaveCount(0);
}

/** Whether the clone has a ribbon build (routes side by side) or Transit draws plain shapes. */
const ribbons = (page: Page) => page.evaluate(() => fetch('/api/meta').then((r) => r.json()).then((m) => m.versions?.ribbons ?? 'none'));

const at = (s: Seed, zoom: number, pitch: number, bearing: number, layers = 'cameras') =>
	`#map=${zoom}/${s.pose.lat.toFixed(5)}/${s.pose.lon.toFixed(5)}/${bearing.toFixed(1)}/${pitch}&layers=${layers}`;

test.describe('review', () => {
	test('the screenshot matrix (§14.11): views 1–8 at 1280×800 and 390×844', { tag: '@wp15' }, async ({ page, consoleErrors, offsite }) => {
		test.setTimeout(2_400_000);
		const key = seed('key');
		const entries: { file: string; view: number; size: string; title: string; notes: string[] }[] = [];
		const shot = async (view: number, size: Size, title: string, notes: string[] = []) => {
			await settle(page);
			const file = `wp15-view${view}-${size.width}x${size.height}.png`;
			await page.screenshot({ path: screenPath(file) });
			entries.push({ file, view, size: `${size.width}×${size.height}`, title, notes });
		};
		const MAP_VIEWS = [
			{ n: 1, title: 'Downtown Boise hub, z15, Transit only', hash: '#map=15/43.6155/-116.2037/-12/45&layers=transit', look: 'auto' },
			{ n: 2, title: 'Fairview and Five Mile corridor, z14, Transit and Streets', hash: '#map=14/43.6195/-116.3143/-12/45&layers=transit,streets', look: 'auto' },
			{ n: 3, title: 'Eagle Rd, z16, every layer', hash: `#map=16/43.6195/-116.3545/-12/50&layers=${ALL}`, look: 'auto' },
			{ n: 4, title: 'Valley overview, z11, every layer', hash: `#map=11/43.6/-116.45/0/0&layers=${ALL}`, look: 'auto' },
			{ n: 5, title: 'View 4 with Clay off (Base: Map)', hash: `#map=11/43.6/-116.45/0/0&layers=${ALL}`, look: 'map' }
		] as const;

		for (const size of [DESKTOP, PHONE]) {
			await page.setViewportSize(size);
			// Jumps instead of flights, so each view is exactly where it was asked to be.
			await page.emulateMedia({ reducedMotion: 'reduce' });
			for (const v of MAP_VIEWS) {
				await baseLook(page, v.look);
				await openMap(page, v.hash);
				const i = await info(page);
				const build = await ribbons(page);
				const chips = (await page.locator('.chips').innerText()).replace(/\s+/g, ' ').trim();
				await shot(v.n, size, v.title, [
					`flavor ${i.flavor}`,
					`layers ${i.enabled.join(', ')}`,
					`buses replayed at ${AT}`,
					build === 'none' ? 'no ribbon build: plain route shapes' : `ribbon build ${build}`,
					`chips: ${chips}`
				]);
				expect(await page.evaluate(() => document.documentElement.scrollWidth), `view ${v.n}: no horizontal scroll`).toBeLessThanOrEqual(size.width);
			}

			// 6: the key seed's window (its map-rendered frame) and the photo in its cone at z16, looking back at the camera.
			// A fresh frame in the fake archive first, as the capture service would add, so the window reads "live".
			tick(env().archive, [key.imageId]);
			await baseLook(page, 'auto');
			await openMap(page, at(key, 16.6, 60, key.pose.heading));
			await page.waitForFunction(() => (globalThis as any).__tvtLook && (globalThis as any).__tvtCameras, null, { timeout: 60_000 });
			expect(await page.evaluate(() => (globalThis as any).__tvtLook.load3d())).toBe(true);
			expect(await page.evaluate((id) => (globalThis as any).__tvtCameras.open(id, false), key.cameraId)).toBe(true);
			await expect
				.poll(async () => (await page.evaluate(() => (globalThis as any).__tvtLook.photos())).photos.some((p: { texture: string | null }) => Boolean(p.texture)), { timeout: 90_000 })
				.toBe(true);
			const frameImg = size === PHONE
				? page.getByRole('region', { name: 'Details' }).locator('img[data-frame-url]').last()
				: page.getByRole('dialog', { name: new RegExp(key.name) }).locator('img[data-frame-url]').last();
			await expect(frameImg).toBeVisible({ timeout: 30_000 });
			await mapReady(page);
			await shot(6, size, `A camera window (seeded, map-rendered frame) and the photo in the cone, z16: ${key.name}`, [`seed ${key.kind}, view ${key.viewId}`]);

			// 7: look-through on the same seed.
			expect(await page.evaluate(([c, v]) => (globalThis as any).__tvtLook.enter(c, v), [key.cameraId, key.viewId] as const)).toBe(true);
			await mapReady(page);
			expect((await page.evaluate(() => (globalThis as any).__tvtLook.state())).phase).toBe('looking');
			await shot(7, size, `Look-through on a seeded camera with a map-rendered frame: ${key.name}`);
			await page.evaluate(() => (globalThis as any).__tvtLook.stepOut());
			await mapReady(page);
			await expect.poll(() => mode(page), { timeout: 120_000 }).toBe('explore');

			// 8: Calibrate mode (a phone gets "Calibration needs a larger screen").
			await page.goto(`/calibrate/${key.cameraId}?view=${key.viewId}`);
			await mapReady(page);
			if (size === PHONE) {
				await expect(page.getByRole('alert').filter({ hasText: 'Calibration needs a larger screen' })).toBeVisible();
				await shot(8, size, 'Calibrate on a phone: "Calibration needs a larger screen"');
			} else {
				await page.waitForFunction(() => (globalThis as any).__tvtCalib?.state().entered && (globalThis as any).__tvtCalib.state().frame);
				await mapReady(page);
				expect(await mode(page)).toBe('calibrate');
				await shot(8, size, `Calibrate mode: ${key.name}`);
			}
		}

		writeFileSync(screenPath('wp15-matrix.json'), JSON.stringify({ at: new Date().toISOString(), entries }, null, 2) + '\n');
		// The owner's review page: the screenshots, the checklist and the numbers in one file beside them.
		execFileSync('node', [join(process.cwd(), 'scripts', 'review-page.mjs'), env().screens]);
		// MapLibre's tile errors under SwiftShader load ("map error …") are recorded by other specs; anything else fails.
		expect(consoleErrors.filter((e) => !/^map error|could not be decoded/.test(e))).toEqual([]);
		expect(offsite).toEqual([]);
	});

	test('the checklist: same origin, credits, fonts, no emoji, contrast, nothing under the bars', { tag: '@wp15' }, async ({ page, offsite }) => {
		test.setTimeout(900_000);
		const key = seed('key');
		const findings: Record<string, unknown> = {};
		await page.setViewportSize(DESKTOP);
		await page.emulateMedia({ reducedMotion: 'reduce' });
		await baseLook(page, 'auto');
		await openMap(page, at(key, 16, 50, -12, ALL));

		// Credits: with every layer and the aerial photos on, the attribution names every source.
		await page.getByRole('toolbar', { name: 'Map layers' }).getByRole('button', { name: 'Base' }).click();
		await page.getByRole('dialog', { name: 'Base map' }).getByRole('switch', { name: /Aerial photos/ }).check();
		await page.keyboard.press('Escape');
		await mapReady(page);
		const credits: string = await page.evaluate(() => {
			const el = document.querySelector('.maplibregl-ctrl-attrib-inner');
			return el?.textContent ?? '';
		});
		findings.credits = credits;
		for (const want of [/OpenStreetMap/, /Protomaps/, /USGS/, /NAIP/, /Overture/, /Valley Regional Transit/, /ITD 511/, /ACHD|Ada County Highway District/]) {
			expect.soft(credits, `the attribution credits ${want}`).toMatch(want);
		}

		// A camera window open, so its text is checked too.
		expect(await page.evaluate((id) => (globalThis as any).__tvtCameras.open(id, false), key.cameraId)).toBe(true);
		await expect(page.getByRole('dialog', { name: new RegExp(key.name) }).locator('img[data-frame-url]').last()).toBeVisible({ timeout: 30_000 });
		await mapReady(page);
		await settle(page);

		// Fonts: Fredoka for the nameplate, Overpass for text, Overpass Mono for numbers; all three loaded.
		const fonts = await page.evaluate(async () => {
			await document.fonts.ready;
			const fam = (sel: string) => {
				const el = document.querySelector(sel);
				return el ? getComputedStyle(el).fontFamily : null;
			};
			return {
				loaded: [...new Set([...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/["']/g, '')))].sort(),
				nameplate: fam('.nameplate h1'),
				body: getComputedStyle(document.body).fontFamily,
				clock: fam('.topbar .clock'),
				chip: fam('.chips .chip')
			};
		});
		findings.fonts = fonts;
		for (const f of ['Fredoka', 'Overpass', 'Overpass Mono']) expect.soft(fonts.loaded, `${f} is loaded`).toContain(f);
		expect.soft(fonts.nameplate).toMatch(/^"?Fredoka/);
		expect.soft(fonts.body).toMatch(/^"?Overpass"?,/);
		expect.soft(fonts.clock).toMatch(/^"?Overpass Mono/);

		// No emoji icons: nothing in the page's text, labels or titles renders as a color emoji.
		const emoji = await page.evaluate(() => {
			const re = /\p{Emoji_Presentation}|\u{FE0F}/u;
			const out: string[] = [];
			const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
			for (let n = walker.nextNode(); n; n = walker.nextNode()) if (re.test(n.textContent ?? '')) out.push(`text: ${n.textContent!.trim().slice(0, 60)}`);
			for (const el of document.querySelectorAll('[aria-label],[title],[alt]'))
				for (const a of ['aria-label', 'title', 'alt']) {
					const v = el.getAttribute(a);
					if (v && re.test(v)) out.push(`${a}: ${v.slice(0, 60)}`);
				}
			return out;
		});
		findings.emoji = emoji;
		expect.soft(emoji, 'no emoji in the page').toEqual([]);

		// Contrast of every visible piece of text in the chrome, the open window and the attribution.
		const contrast = await page.evaluate(() => {
			type RGBA = [number, number, number, number];
			const parse = (c: string): RGBA | null => {
				const m = c.match(/^rgba?\(([^)]+)\)$/);
				if (!m) return c === 'transparent' ? [0, 0, 0, 0] : null;
				const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
				return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
			};
			const over = (top: RGBA, under: RGBA): RGBA => {
				const a = top[3] + under[3] * (1 - top[3]);
				if (a === 0) return [0, 0, 0, 0];
				return [0, 1, 2].map((i) => (top[i] * top[3] + under[i] * under[3] * (1 - top[3])) / a).concat(a) as RGBA;
			};
			const lum = (c: RGBA) => {
				const [r, g, b] = c.slice(0, 3).map((v) => {
					const s = v / 255;
					return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
				});
				return 0.2126 * r + 0.7152 * g + 0.0722 * b;
			};
			const ratio = (a: RGBA, b: RGBA) => {
				const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
				return (x + 0.05) / (y + 0.05);
			};
			/** The solid background under an element, or null where the map shows through or an image paints it. */
			const background = (el: Element): RGBA | null => {
				let acc: RGBA = [0, 0, 0, 0];
				for (let e: Element | null = el; e; e = e.parentElement) {
					const s = getComputedStyle(e);
					if (s.backgroundImage !== 'none') return null;
					const bg = parse(s.backgroundColor);
					if (!bg) return null;
					acc = over(acc, bg);
					if (acc[3] >= 0.999) return acc;
				}
				return null;
			};
			const opacity = (el: Element) => {
				let o = 1;
				for (let e: Element | null = el; e; e = e.parentElement) o *= Number(getComputedStyle(e).opacity);
				return o;
			};
			const roots = [...document.querySelectorAll('.chrome, .maplibregl-ctrl-attrib')];
			const seen = new Set<Element>();
			const out: { text: string; ratio: number; need: number; where: string }[] = [];
			let checked = 0;
			let overMap = 0;
			let halos = 0;
			for (const root of roots)
				for (const el of [root, ...root.querySelectorAll('*')]) {
					if (seen.has(el)) continue;
					seen.add(el);
					const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent ?? '').join('').trim();
					if (!own) continue;
					const r = el.getBoundingClientRect();
					if (!r.width || !r.height || el.closest('[aria-hidden="true"], [hidden], .sr-only, :disabled, [aria-disabled="true"]')) continue;
					const s = getComputedStyle(el);
					if (s.visibility !== 'visible' || Number(s.opacity) === 0) continue;
					if (s.textShadow !== 'none') {
						halos++;
						continue;
					}
					const bg = background(el);
					if (!bg) {
						overMap++;
						continue;
					}
					const fg0 = parse(s.color);
					if (!fg0) continue;
					const fg = over([fg0[0], fg0[1], fg0[2], fg0[3] * opacity(el)], bg);
					const size = parseFloat(s.fontSize);
					const bold = Number(s.fontWeight) >= 700;
					const shape = /^[●▲■◌▼◆○□△]$/u.test(own);
					const need = shape || size >= 24 || (bold && size >= 18.66) ? 3 : 4.5;
					checked++;
					const k = ratio(fg, bg);
					if (k < need - 0.005) {
						const cls = (el.getAttribute('class') ?? '').split(/\s+/).filter((c) => c && !c.startsWith('svelte-')).join('.');
						out.push({ text: own.slice(0, 40), ratio: Math.round(k * 100) / 100, need, where: `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''}` });
					}
				}
			return { checked, overMap, halos, failing: out };
		});
		findings.contrast = contrast;
		expect.soft(contrast.checked).toBeGreaterThan(20);
		expect.soft(contrast.failing, 'text below its contrast minimum').toEqual([]);

		// Nothing under the bars: legends, the right column and windows stay clear of the top bar's cards and the toolbar.
		const overlaps = (sel: string[], bars: string[]) =>
			page.evaluate(
				([sel, bars]) => {
					const rects = (q: string) => [...document.querySelectorAll(q)].map((e) => ({ q, r: e.getBoundingClientRect() })).filter((x) => x.r.width && x.r.height);
					const hit = (a: DOMRect, b: DOMRect) => a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5;
					const out: string[] = [];
					for (const p of sel.flatMap(rects)) for (const b of bars.flatMap(rects)) if (hit(p.r, b.r)) out.push(`${p.q} overlaps ${b.q}`);
					return out;
				},
				[sel, bars] as const
			);
		// The credits card open (it is on arrival, until the first drag), at its longest: every layer and Aerial on.
		await page.evaluate(() => {
			const el = document.querySelector('.maplibregl-ctrl-attrib');
			if (el?.classList.contains('maplibregl-compact') && !el.classList.contains('maplibregl-compact-show')) el.querySelector('summary')?.click();
		});
		await expect(page.locator('.maplibregl-ctrl-attrib-inner')).toBeVisible();
		/** The open credits card holds its text (its background reaches below the last line). */
		const creditsHeld = () =>
			page.evaluate(() => {
				const card = document.querySelector('.maplibregl-ctrl-attrib')?.getBoundingClientRect();
				const text = document.querySelector('.maplibregl-ctrl-attrib-inner')?.getBoundingClientRect();
				return card && text && text.height ? { held: text.bottom <= card.bottom + 0.5 && text.top >= card.top - 0.5, card: Math.round(card.height), text: Math.round(text.height) } : null;
			});
		findings.creditsDesktop = await creditsHeld();
		expect.soft(findings.creditsDesktop, 'the open credits card holds its text (desktop)').toMatchObject({ held: true });
		const desktopBars = ['.topbar .nameplate', '.topbar .chips', '.topbar .right', '.toolbar'];
		const desktop = [
			...(await overlaps(['.chrome .left .legend', '.chrome .right .widget', '.chrome .inspect', '[role="dialog"][data-window-key]'], desktopBars)),
			// The credits card, open as it is on arrival, stays clear of the toolbar.
			...(await overlaps(['.maplibregl-ctrl-attrib'], ['.toolbar']))
		];
		findings.desktopOverlaps = desktop;
		expect.soft(desktop, 'nothing under the bars (desktop)').toEqual([]);
		expect(offsite).toEqual([]);

		// The phone: no horizontal scroll, and the sheet stays clear of the tab bar and the chips.
		await page.setViewportSize(PHONE);
		await openMap(page, at(key, 16, 50, -12, ALL));
		expect(await page.evaluate((id) => (globalThis as any).__tvtCameras.open(id, false), key.cameraId)).toBe(true);
		await expect(page.getByRole('region', { name: 'Details' }).locator('img[data-frame-url]').last()).toBeVisible({ timeout: 30_000 });
		await mapReady(page);
		await settle(page);
		await page.evaluate(() => {
			const el = document.querySelector('.maplibregl-ctrl-attrib');
			if (el?.classList.contains('maplibregl-compact') && !el.classList.contains('maplibregl-compact-show')) el.querySelector('summary')?.click();
		});
		const phone = {
			credits: await creditsHeld(),
			scrollWidth: await page.evaluate(() => document.documentElement.scrollWidth),
			overlaps: await overlaps(['.sheet'], ['.tabbar', '.topbar .nameplate']),
			smallTargets: await page.evaluate(() =>
				[...document.querySelectorAll('.tabbar button, .tabbar a, .sheet [role="tab"], .sheet button.tool')]
					.map((e) => ({ e, r: e.getBoundingClientRect() }))
					.filter(({ r }) => r.width && r.height && (r.width < 44 - 0.5 || r.height < 44 - 0.5))
					.map(({ e, r }) => `${e.getAttribute('aria-label') ?? e.textContent?.trim()}: ${Math.round(r.width)}×${Math.round(r.height)}`)
			)
		};
		findings.phone = phone;
		await page.screenshot({ path: screenPath('wp15-checklist-phone.png') });
		writeFileSync(screenPath('wp15-checklist.json'), JSON.stringify({ at: new Date().toISOString(), ...findings }, null, 2) + '\n');
		expect.soft(phone.credits, 'the open credits card holds its text (phone)').toMatchObject({ held: true });
		expect.soft(phone.scrollWidth).toBeLessThanOrEqual(PHONE.width);
		expect.soft(phone.overlaps, 'nothing under the bars (phone)').toEqual([]);
		expect.soft(phone.smallTargets, 'touch targets of at least 44 px').toEqual([]);
		expect(offsite).toEqual([]);
	});
});
