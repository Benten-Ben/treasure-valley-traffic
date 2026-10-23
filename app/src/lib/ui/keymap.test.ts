import type { Map } from 'maplibre-gl';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AppCtx } from '#lib/app/context.js';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { allBindings } from './keys.js';
import { HOME, LANDSCAPE_TRAY_EVENT, homeFlight, overviewBounds, overviewCamera, registerDefaultKeys, VALLEY } from './keymap.js';
import { cardLanding, chromePadding } from './padding.js';

describe('Overview frames the populated valley, not the tiles', () => {
	it('the valley box, Caldwell to east Boise and Kuna to Eagle', () => {
		expect(overviewBounds()).toEqual([
			[VALLEY[0], VALLEY[1]],
			[VALLEY[2], VALLEY[3]]
		]);
		// The manifest's study box holds it whole: the valley, not the desert south of it.
		expect(overviewBounds([-117.05, 43.0, -115.95, 43.85])).toEqual(overviewBounds());
	});

	it('stays within smaller tiles, and ignores tiles elsewhere', () => {
		expect(overviewBounds([-116.3, 43.5, -116.0, 43.7])).toEqual([
			[-116.3, 43.5],
			[VALLEY[2], 43.7]
		]);
		expect(overviewBounds([-100, 40, -99, 41])).toEqual(overviewBounds());
	});
});

describe('H and O land left of the open inspect card (§14.3 "Regions")', () => {
	const stored = chromePadding({ layout: 'desktop', width: 1280, height: 800 });
	const card = cardLanding({ layout: 'desktop', width: 1280, height: 800, stored });

	it('Home: over Meridian, offset into the area the card leaves', () => {
		expect(homeFlight(null)).toEqual({ ...HOME, duration: 1200 });
		expect(homeFlight(card)).toEqual({ ...HOME, duration: 1200, offset: [-160, 0] });
	});

	it('Overview: fitted with the card\'s column as more padding', () => {
		const cameraForBounds = vi.fn(() => ({ center: { lng: -116.4, lat: 43.6 }, zoom: 10.2, bearing: 0 }));
		const map = { cameraForBounds } as unknown as Map;
		expect(overviewCamera(map, null, null)).toMatchObject({ zoom: 10.2, bearing: 0, pitch: 0 });
		expect(cameraForBounds).toHaveBeenLastCalledWith(overviewBounds(), { padding: { top: 40, right: 40, bottom: 40, left: 40 }, bearing: 0, pitch: 0 });
		overviewCamera(map, null, card);
		expect(cameraForBounds).toHaveBeenLastCalledWith(overviewBounds(), { padding: { top: 40, right: 360, bottom: 40, left: 40 }, bearing: 0, pitch: 0 });
	});
});

describe('with no view history, H under reduced motion still lands left of the card', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('jumps, then pans by the landing offset at once', () => {
		vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('reduce'), addEventListener() {}, removeEventListener() {} }));
		const stored = chromePadding({ layout: 'desktop', width: 1280, height: 800 });
		const card = cardLanding({ layout: 'desktop', width: 1280, height: 800, stored });
		const map = { jumpTo: vi.fn(), panBy: vi.fn(), flyTo: vi.fn() };
		const app = { map, layers: { defs: [] }, modes: { current: 'explore' }, manifest: null, landing: () => card } as unknown as AppCtx;
		const off = registerDefaultKeys(app, { help: () => {} });
		try {
			allBindings()
				.find((b) => b.id === 'home')!
				.run({} as KeyboardEvent);
			expect(map.flyTo).not.toHaveBeenCalled();
			expect(map.jumpTo).toHaveBeenCalledWith(expect.objectContaining({ center: HOME.center, zoom: HOME.zoom, pitch: HOME.pitch, bearing: HOME.bearing }));
			expect(map.panBy).toHaveBeenCalledTimes(1);
			const [by, how] = map.panBy.mock.calls[0] as [[number, number], unknown];
			expect(by.map((v) => v + 0)).toEqual([160, 0]); // -0 from the history's negation
			expect(how).toEqual({ animate: false });
		} finally {
			off();
		}
	});
});

describe('the Landscape tray keys (owner, Oct 22)', () => {
	const defs = [
		{ id: 'streets', title: 'Streets', key: '2' },
		{ id: 'trees', title: 'Trees', group: 'landscape' },
		{ id: 'water', title: 'Water', group: 'landscape' }
	];
	const withApp = (list: unknown[], body: () => void) => {
		const toggle = vi.fn();
		const solo = vi.fn();
		const app = { map: null, layers: { defs: list, toggle, solo, allOff: vi.fn() }, modes: { current: 'explore' }, manifest: null } as unknown as AppCtx;
		const off = registerDefaultKeys(app, { help: () => {} });
		try {
			body();
		} finally {
			off();
		}
		return { toggle, solo };
	};

	it('0 opens and closes the tray, 1 stays all-off, and tray layers get no digit of their own', () => {
		withApp(defs, () => {
			const ids = allBindings().map((b) => b.id);
			expect(ids).toContain('landscape-tray');
			expect(ids).toContain('all-layers');
			expect(ids).toContain('layer-streets');
			expect(ids.filter((i) => /trees|water/.test(i))).toEqual([]);
			const zero = allBindings().find((b) => b.id === 'landscape-tray')!;
			expect(zero.codes).toContain('Digit0');
			const dispatchEvent = vi.fn();
			vi.stubGlobal('dispatchEvent', dispatchEvent);
			try {
				zero.run({} as KeyboardEvent);
			} finally {
				vi.unstubAllGlobals();
			}
			expect(dispatchEvent).toHaveBeenCalledTimes(1);
			expect((dispatchEvent.mock.calls[0][0] as Event).type).toBe(LANDSCAPE_TRAY_EVENT);
		});
	});

	it('without tray layers there is no 0', () => {
		withApp([defs[0]], () => expect(allBindings().map((b) => b.id)).not.toContain('landscape-tray'));
	});

	it('the Landscape icon is Phosphor Mountains, exactly as phosphor-svelte ships it', async () => {
		// The component's module script holds the path data; read it the way icons.test.ts reads the package.
		const require = createRequire(import.meta.url);
		const dir = dirname(require.resolve('phosphor-svelte/package.json'));
		const pkg = readFileSync(join(dir, 'lib', 'MountainsIcon.svelte'), 'utf8');
		const branch = /weight === "duotone"\}\s*([\s\S]*?)\{:else/.exec(pkg)?.[1] ?? '';
		const paths = [...branch.matchAll(/<path d="([^"]+)"([^>]*)\/>/g)];
		const tone = paths.find((p) => p[2].includes('opacity="0.2"'))?.[1];
		const line = paths.find((p) => !p[2].includes('opacity'))?.[1];
		const src = readFileSync(join(__dirname, 'LandscapeTray.svelte'), 'utf8');
		expect(tone && src.includes(`tone: '${tone}'`)).toBe(true);
		expect(line && src.includes(`line: '${line}'`)).toBe(true);
	});
});
