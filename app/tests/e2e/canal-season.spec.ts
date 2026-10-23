import type { Page } from '@playwright/test';
import postgres from 'postgres';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import { cleanWater, GAUGE, seedWater, type Seeded } from './water-seed.js';

/**
 * The canal season (landscape sprint plan v3 §4.2 P5, P5-app): each canal draws filled when on, hollow when off and
 * as a thin centre line when unknown, from its lifecycles, with the basis on its card. It runs on the synthetic
 * landscape fixture (`TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted)`: a main canal 7001 of canal 1,
 * a lateral 7002 and a piped lateral 7004 of canal 2, a ditch 7003 and an NHD-only stream with no canal) and on
 * made-up lifecycles in `evt.event` over the water seed's rows (`water-seed.ts`), all named "Fixture":
 *
 * - canal 1 is off by its gauge (and was on before; an ended span must not count), canal 2 is on by IDWR's legal
 *   window (internal), and a later test makes canal 1 unknown, the 48-hour silence;
 * - `/api/water/season` sorts the baked reaches by state, with no clock in it so an ETag holds;
 * - the base sets feature-state `season` on the reaches with Water off, and the solid layer's width and gap draw it:
 *   read back from the rendered pixels (a filled line, two thin edges at the same footprint, a hairline);
 * - the card says the state and its basis in words, and the legal window as the legal window.
 */

const NEAR = '#map=17/43.608/-116.19/0/0';
/** The canal's vertex east of the lateral (water.spec.ts). */
const CANAL_POINT: [number, number] = [-116.19, 43.608];
/** Half way along the lateral's first segment. */
const LATERAL_POINT: [number, number] = [-116.20775, 43.61025];
const SOURCE = 'canal_season';
const LEGAL_CREDIT = 'Idaho Department of Water Resources (IDWR), season of use';
const OSM = '© OpenStreetMap contributors';
const GAUGE_NAME = 'Fixture Canal Diversion';
const REACH = { source: 'landscape', sourceLayer: 'water.reaches' } as const;

type Info = { enabled: string[]; selection: { id: string; title: string } | null };
const info = (page: Page): Promise<Info> => page.evaluate(() => (globalThis as any).__tvt.layers);
const hasLayer = (page: Page, id: string) => page.evaluate((id) => Boolean((globalThis as any).__tvt.map.getLayer(id)), id);
const featureState = (page: Page, id: number) => page.evaluate(([src, layer, id]) => (globalThis as any).__tvt.map.getFeatureState({ source: src, sourceLayer: layer, id }), [REACH.source, REACH.sourceLayer, id] as const);
const water = (page: Page) => page.evaluate(() => (globalThis as any).__tvtWater?.info() ?? null);
const rendered = (page: Page, layers: string[]) =>
	page.evaluate((layers) => (globalThis as any).__tvt.map.queryRenderedFeatures({ layers: layers.filter((l) => (globalThis as any).__tvt.map.getLayer(l)) }).map((f: any) => ({ layer: f.layer.id, id: f.properties.id })), layers);

const db = () => postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });

let seeded: Seeded | null = null;
let madeSource = false;

/** Canal 1's current lifecycle, off by its gauge (or whichever state is asked), and the span that ended before it. */
async function setCanalOne(state: 'on' | 'off' | 'unknown') {
	const sql = db();
	try {
		await sql`delete from evt.event where source = ${SOURCE} and source_id like '1@%'`;
		const now = Date.now();
		const day = 86_400_000;
		const row = (id: string, severity: string, from: number, to: number | null) => ({
			id,
			severity,
			range: `[${new Date(from).toISOString()},${to === null ? '' : new Date(to).toISOString()})`
		});
		const attrs = (severity: string) => ({
			canal_id: 1,
			canal: 'Fixture Main Canal',
			canal_kind: 'main_canal',
			state: severity,
			basis: 'gauge',
			gauge: GAUGE,
			gauge_name: GAUGE_NAME,
			why: 'made up for the spec',
			credit: [`NOAA National Weather Service (NWPS), gauge ${GAUGE}`, OSM, 'U.S. Geological Survey, National Hydrography Dataset'],
			republish: 'yes'
		});
		// An ended span (on) and the current one: only the current one counts.
		for (const r of [row('1@fixture-ended', 'on', now - 60 * day, now - 2 * day), row('1@fixture-now', state, now - 2 * day, null)]) {
			await sql`insert into evt.event (source, source_id, kind, geom, declared, observed, active, severity, description, attributes, content_hash, updated_at)
			          values (${SOURCE}, ${r.id}, ${SOURCE}, ST_GeomFromEWKT('SRID=4326;POINT(-116.36 43.592)'), ${r.range}::tstzrange, tstzrange(${new Date(now - 60 * day)}, null), true,
			                  ${r.severity}, ${`Fixture Main Canal: ${r.severity}`}, ${sql.json(attrs(r.severity))}, ${Buffer.from(r.id + r.severity)}, ${new Date(now)})`;
		}
	} finally {
		await sql.end();
	}
}

async function seedSeason() {
	const sql = db();
	try {
		const [has] = await sql`select 1 as ok from ops.source where name = ${SOURCE}`;
		if (!has) {
			await sql`insert into ops.source (name, title, url, access) values (${SOURCE}, ${SOURCE}, 'https://example.test/', 'open')`;
			madeSource = true;
		}
		await sql`delete from evt.event where source = ${SOURCE} and source_id like '%@fixture%'`;
		const now = Date.now();
		const day = 86_400_000;
		await sql`insert into evt.event (source, source_id, kind, geom, declared, observed, active, severity, description, attributes, content_hash, updated_at)
		          values (${SOURCE}, '2@fixture-now', ${SOURCE}, ST_GeomFromEWKT('SRID=4326;POINT(-116.21 43.6075)'), tstzrange(${new Date(now - 30 * day)}, ${new Date(now + 30 * day)}), tstzrange(${new Date(now - 30 * day)}, null), true,
		                  'on', 'Fixture Lateral: in IDWR''s legal irrigation season (3/1 - 11/15), not delivery dates',
		                  ${sql.json({ canal_id: 2, canal: 'Fixture Lateral', canal_kind: 'lateral', state: 'on', basis: 'legal', season: '3/1 - 11/15', objectid: 7, why: 'made up for the spec', credit: [LEGAL_CREDIT, OSM], republish: 'internal' })},
		                  ${Buffer.from('fx-legal')}, ${new Date(now)})`;
	} finally {
		await sql.end();
	}
	await setCanalOne('off');
}

async function cleanSeason() {
	const sql = db();
	try {
		await sql`delete from evt.event where source = ${SOURCE} and source_id like '%@fixture%'`;
		if (madeSource) await sql`delete from ops.source where name = ${SOURCE}`;
	} finally {
		await sql.end();
	}
}

test.beforeAll(async () => {
	seeded = await seedWater();
	await seedSeason();
});

test.afterAll(async () => {
	await cleanSeason().catch(() => {});
	await cleanWater(seeded);
});

/** The map is up with the baked water drawn. */
async function ready(page: Page, hash: string) {
	await page.goto(`/${hash}`);
	await mapReady(page);
	await expect.poll(() => hasLayer(page, 'water.network.reaches'), { message: 'the baked water is in the style (landscape fixture)', timeout: 30_000 }).toBe(true);
}

/** The map's own idle: what it was asked to draw is drawn. */
const settle = (page: Page) =>
	page.evaluate(
		() =>
			new Promise<void>((resolve) => {
				const m = (globalThis as any).__tvt.map;
				m.once('idle', () => resolve());
				m.triggerRepaint();
			})
	);

interface Profile {
	/** Pixels in the column that differ from the ground beside the line. */
	count: number;
	/** The first and last such pixel (px from the top of the column), and so the line's footprint. */
	first: number;
	last: number;
	/** How many of the middle 5 px of the footprint differ (a hollow's are the ground). */
	middle: number;
}

/** A column of the rendered map through a point, read back from a screenshot: what is line and what is ground. */
async function profile(page: Page, point: [number, number]): Promise<Profile> {
	const at = await page.evaluate((p) => {
		const pt = (globalThis as any).__tvt.map.project(p);
		return { x: Math.round(pt.x), y: Math.round(pt.y) };
	}, point);
	const half = 70;
	const png = await page.screenshot({ clip: { x: at.x - 1, y: at.y - half, width: 3, height: half * 2 } });
	return page.evaluate(
		async ([b64, half]) => {
			const img = new Image();
			img.src = `data:image/png;base64,${b64}`;
			await img.decode();
			const c = document.createElement('canvas');
			c.width = img.width;
			c.height = img.height;
			const g = c.getContext('2d')!;
			g.drawImage(img, 0, 0);
			const scale = img.height / (half * 2);
			const col = (y: number) => [...g.getImageData(Math.floor(img.width / 2), Math.min(img.height - 1, Math.floor(y * scale)), 1, 1).data];
			// The ground beside the line: 60 px above its centre, which is clear of everything else at this zoom.
			const ground = col(half - 60);
			const differs = (px: number[]) => Math.max(Math.abs(px[0] - ground[0]), Math.abs(px[1] - ground[1]), Math.abs(px[2] - ground[2])) > 25;
			const marks: number[] = [];
			for (let y = half - 55; y < half + 55; y++) if (differs(col(y))) marks.push(y);
			const first = marks[0] ?? -1;
			const last = marks[marks.length - 1] ?? -1;
			const mid = Math.round((first + last) / 2);
			let middle = 0;
			for (let y = mid - 2; y <= mid + 2; y++) if (marks.includes(y)) middle++;
			return { count: marks.length, first, last, middle };
		},
		[png.toString('base64'), half] as const
	);
}

/** Put a state on the canal's main reach (the hook's own is put back on a reload). */
const force = async (page: Page, state: 'on' | 'off' | 'unknown') => {
	await page.evaluate(([src, layer, s]) => (globalThis as any).__tvt.map.setFeatureState({ source: src, sourceLayer: layer, id: 7001 }, { season: s }), [REACH.source, REACH.sourceLayer, state] as const);
	await settle(page);
};

test.describe('canal season: the API', () => {
	test('sorts the baked reaches by their canal’s current state, with the basis and credits, and revalidates by ETag', { tag: '@canal' }, async ({ request }) => {
		const res = await request.get('/api/water/season');
		expect(res.status()).toBe(200);
		expect(res.headers()['cache-control']).toBe('no-cache');
		const s = await res.json();
		// The main canal (7001) is off by its gauge, the ended "on" span left out; the lateral (7002, and its piped reach 7004) is on by IDWR's window.
		expect(s.reaches).toEqual({ on: [7002, 7004], off: [7001], unknown: [] });
		const byId = Object.fromEntries(s.canals.map((c: { id: number }) => [c.id, c]));
		expect(byId[1]).toMatchObject({ name: 'Fixture Main Canal', state: 'off', basis: 'gauge', gauge: GAUGE, gauge_name: GAUGE_NAME, until: null, republish: 'yes' });
		expect(byId[2]).toMatchObject({ state: 'on', basis: 'legal', season: '3/1 - 11/15', republish: 'internal' });
		// IDWR's legal window makes the answer internal, and its credit is in the list.
		expect(s.republish).toBe('internal');
		expect(s.credits).toContain(LEGAL_CREDIT);
		expect(byId[2].credit.map((i: number) => s.credits[i])).toEqual([LEGAL_CREDIT, OSM]);
		// Nothing of the City's or any private data, and no clock in the answer.
		expect(Object.keys(s).sort()).toEqual(['canals', 'credits', 'license', 'republish', 'reaches', 'updated'].sort());
		const etag = res.headers().etag;
		expect(etag).toBeTruthy();
		expect((await request.get('/api/water/season', { headers: { 'if-none-match': etag } })).status()).toBe(304);
	});
});

test.describe('canal season: the drawing', () => {
	test('sets feature-state on the baked reaches with Water off, and draws off hollow, on filled and unknown thin', { tag: '@canal' }, async ({ page, consoleErrors, offsite }) => {
		test.setTimeout(300_000);
		await ready(page, `${NEAR}&layers=none`);
		await expect.poll(async () => (await rendered(page, ['water.network.reaches'])).some((f: { id: number }) => f.id === 7001), { timeout: 60_000 }).toBe(true);
		expect((await info(page)).enabled).toEqual([]);
		// The hook put each canal's state on its reaches; a ditch and an NHD-only stream (no canal) have none.
		await expect.poll(() => featureState(page, 7001), { timeout: 60_000 }).toEqual({ season: 'off' });
		expect(await featureState(page, 7002)).toEqual({ season: 'on' });
		expect(await featureState(page, 7004)).toEqual({ season: 'on' });
		expect(await featureState(page, 7003)).toEqual({});
		expect(await featureState(page, 2251799813686239)).toEqual({});

		// K5: a gap only on the solid layer, no offset, no casing, and none under another line's features.
		const layers = await page.evaluate(() => (globalThis as any).__tvt.map.getStyle().layers.filter((l: any) => l.id.startsWith('water.network.')).map((l: any) => ({ id: l.id, type: l.type, paint: l.paint ?? {} })));
		for (const l of layers) {
			expect(l.id, l.id).not.toMatch(/casing|outline|halo/i);
			expect(Object.keys(l.paint), l.id).not.toContain('line-offset');
			if (l.id === 'water.network.reaches') {
				expect(JSON.stringify(l.paint['line-gap-width'])).toContain('feature-state');
				expect(l.paint['line-color']).toBe('#4a9fcc');
			} else expect(Object.keys(l.paint), l.id).not.toContain('line-gap-width');
		}

		// z17: the 14 m canal is about 32 px wide. Read the column through its vertex off the rendered map.
		const state = async (s: 'on' | 'off' | 'unknown') => {
			await force(page, s);
			return profile(page, CANAL_POINT);
		};
		const on = await state('on');
		const off = await state('off');
		const unknown = await state('unknown');
		await page.screenshot({ path: screenPath('canal-season-unknown.png') });
		await force(page, 'off');
		await page.screenshot({ path: screenPath('canal-season-off.png') });
		// Filled: a solid ribbon, all line across the middle.
		expect(on.count).toBeGreaterThan(20);
		expect(on.middle).toBe(5);
		// Hollow: only the two thin edges are line, the middle is the ground, and the footprint is the filled line's.
		expect(off.count).toBeGreaterThanOrEqual(2);
		expect(off.count).toBeLessThanOrEqual(8);
		expect(off.middle).toBe(0);
		expect(Math.abs(off.last - off.first - (on.last - on.first))).toBeLessThanOrEqual(3);
		// Unknown: a thin centre line, in the middle of where the ribbon was.
		expect(unknown.count).toBeGreaterThanOrEqual(1);
		expect(unknown.count).toBeLessThanOrEqual(3);
		expect(Math.abs((unknown.first + unknown.last) / 2 - (on.first + on.last) / 2)).toBeLessThanOrEqual(3);
		expect(consoleErrors).toEqual([]);
		expect(offsite).toEqual([]);
	});

	test('draws a canal that has become unknown (48 hours without a reading) as a thin line after a reload', { tag: '@canal' }, async ({ page }) => {
		test.setTimeout(300_000);
		await setCanalOne('unknown');
		try {
			await ready(page, `${NEAR}&layers=none`);
			await expect.poll(() => featureState(page, 7001), { timeout: 60_000 }).toEqual({ season: 'unknown' });
			await settle(page);
			const p = await profile(page, CANAL_POINT);
			expect(p.count).toBeGreaterThanOrEqual(1);
			expect(p.count).toBeLessThanOrEqual(3);
		} finally {
			await setCanalOne('off');
		}
	});

	test('leaves the reaches as today when the season has nothing for them', { tag: '@canal' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		const sql = db();
		try {
			const [{ n }] = await sql`select count(*)::int as n from evt.event where source = ${SOURCE} and source_id like '%@fixture%'`;
			expect(n).toBeGreaterThan(0);
			await sql`delete from evt.event where source = ${SOURCE} and source_id like '%@fixture%'`;
		} finally {
			await sql.end();
		}
		try {
			await ready(page, `${NEAR}&layers=none`);
			// With no lifecycle a canal reads unknown (the plugin's rule), and a reach with no canal has no state.
			await expect.poll(() => featureState(page, 7001), { timeout: 60_000 }).toEqual({ season: 'unknown' });
			expect(await featureState(page, 7003)).toEqual({});
			expect(consoleErrors).toEqual([]);
		} finally {
			await seedSeason();
		}
	});
});

test.describe('canal season: the card', () => {
	test('says the state and its basis in words, and the legal window as the legal window', { tag: '@canal' }, async ({ page }) => {
		test.setTimeout(300_000);
		await ready(page, `#map=14/${CANAL_POINT[1]}/${CANAL_POINT[0]}/0/0&layers=water`);
		await expect.poll(async () => (await water(page))?.visible, { timeout: 60_000 }).toBe(true);
		await expect.poll(async () => (await rendered(page, ['water.network.reaches'])).some((f: { id: number }) => f.id === 7001), { timeout: 60_000 }).toBe(true);
		const click = async (point: [number, number], id: string) => {
			const at = await page.evaluate((p) => {
				const pt = (globalThis as any).__tvt.map.project(p);
				return { x: pt.x, y: pt.y };
			}, point);
			await page.mouse.click(at.x, at.y);
			await expect.poll(async () => (await info(page)).selection?.id, { timeout: 30_000 }).toBe(id);
		};
		await click(CANAL_POINT, 'reach:7001');
		const card = page.locator('section.inspect');
		await expect(card).toContainText('Fixture Main Canal');
		await expect(card.locator('[data-canal-season]')).toHaveAttribute('data-canal-season', 'off');
		await expect(card).toContainText(`off (gauge ${GAUGE}, ${GAUGE_NAME})`);
		// The season's credits join the card's.
		await expect(card.locator('.credit')).toContainText('National Weather Service');
		await page.screenshot({ path: screenPath('canal-season-card-off.png') });
		await page.keyboard.press('Escape');
		await expect.poll(async () => (await info(page)).selection).toBeNull();

		// The lateral rests on IDWR's legal window: it says so, and that it is not delivery dates.
		await page.goto(`/#map=16/${LATERAL_POINT[1]}/${LATERAL_POINT[0]}/0/0&layers=water`);
		await mapReady(page);
		await expect.poll(async () => (await rendered(page, ['water.network.reaches'])).some((f: { id: number }) => f.id === 7002), { timeout: 60_000 }).toBe(true);
		await click(LATERAL_POINT, 'reach:7002');
		await expect(card).toContainText('Fixture Lateral');
		await expect(card.locator('[data-canal-season]')).toHaveAttribute('data-canal-season', 'on');
		await expect(card).toContainText("in IDWR's legal irrigation season (3/1 – 11/15), not delivery dates");
		await expect(card).toContainText('internal');
		await expect(card.locator('.credit')).toContainText(LEGAL_CREDIT);
		await page.screenshot({ path: screenPath('canal-season-card-legal.png') });
	});

	test('says unknown, with the 48 hours, when the gauge has gone silent', { tag: '@canal' }, async ({ page }) => {
		test.setTimeout(300_000);
		await setCanalOne('unknown');
		try {
			await ready(page, `#map=14/${CANAL_POINT[1]}/${CANAL_POINT[0]}/0/0&layers=water`);
			await expect.poll(async () => (await water(page))?.visible, { timeout: 60_000 }).toBe(true);
			await expect.poll(async () => (await rendered(page, ['water.network.reaches'])).some((f: { id: number }) => f.id === 7001), { timeout: 60_000 }).toBe(true);
			const at = await page.evaluate((p) => {
				const pt = (globalThis as any).__tvt.map.project(p);
				return { x: pt.x, y: pt.y };
			}, CANAL_POINT);
			await page.mouse.click(at.x, at.y);
			await expect.poll(async () => (await info(page)).selection?.id, { timeout: 30_000 }).toBe('reach:7001');
			const card = page.locator('section.inspect');
			await expect(card.locator('[data-canal-season]')).toHaveAttribute('data-canal-season', 'unknown');
			await expect(card).toContainText(`unknown: no reading for 48 hours (gauge ${GAUGE})`);
		} finally {
			await setCanalOne('off');
		}
	});
});
