import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { rttStacks } from '#lib/map/order.js';
import { ROAD_WEATHER_ICON, THERMOMETER } from './icons.js';
import { BADGE_LAYER, HOLLOW_IMAGE, roadWeatherLayers, SOLID_IMAGE, SOURCE, stationFeatures } from './layers.js';
import type { RoadWeatherStation } from './model.js';

const VALLEY = [-117.05, 43.0, -115.95, 43.85] as const;

const station = (id: number, lon: number, lat: number, hollow = false): RoadWeatherStation => ({
	id,
	name: `Station ${id} (synthetic)`,
	provider: id === 3 ? 'ODOT' : 'ITD RWIS',
	lon,
	lat,
	hollow,
	views: [
		{ id: id * 10, imageId: id * 100, label: 'View 1', sortOrder: 0, disabled: false, seenAt: null, ageS: null, capturing: true, feed: hollow ? 'no_feed' : 'live' },
		{ id: id * 10 + 1, imageId: id * 100 + 1, label: 'View 2', sortOrder: 1, disabled: false, seenAt: null, ageS: null, capturing: true, feed: hollow ? 'no_feed' : 'unknown' }
	]
});

describe('road-weather map layers', () => {
	it('draws the stations inside the base map, with what the badge and the picker need', () => {
		const fc = stationFeatures([station(1, -116.24, 43.56), station(2, -116.43, 43.69, true), station(4, -114.5, 42.6)], VALLEY);
		expect(fc.features.map((f) => f.id)).toEqual([1, 2]);
		expect(fc.features[1].properties).toEqual({ id: 2, name: 'Station 2 (synthetic)', provider: 'ITD RWIS', hollow: true, views: 2, fact: 'No live feed on any of 2 views' });
		expect(fc.features[0].geometry).toEqual({ type: 'Point', coordinates: [-116.24, 43.56] });
	});

	it('is one hidden symbol layer in the labels slot, hollow badges for hollow stations', () => {
		const layers = roadWeatherLayers();
		expect(layers.map((l) => [l.slot, l.layer.id, l.layer.type])).toEqual([['labels', BADGE_LAYER, 'symbol']]);
		const l = layers[0].layer as { source: string; layout: Record<string, unknown> };
		expect(l.source).toBe(SOURCE);
		expect(l.layout.visibility).toBe('none');
		expect(l.layout['icon-image']).toEqual(['case', ['boolean', ['get', 'hollow'], false], HOLLOW_IMAGE, SOLID_IMAGE]);
		expect(l.layout['icon-allow-overlap']).toBe(true);
		expect(l.layout['text-optional']).toBe(true);
	});

	it('never adds a draped run: symbols sit outside the draped block', () => {
		const layers = roadWeatherLayers().map((l) => ({ id: l.layer.id, type: l.layer.type, visible: true }));
		const order = [
			{ id: 'streets', type: 'line', visible: true },
			{ id: 'anchor:routes', type: 'background', visible: false },
			{ id: 'buildings-3d', type: 'fill-extrusion', visible: true },
			...layers,
			{ id: 'anchor:labels', type: 'background', visible: false }
		];
		expect(rttStacks(order)).toBe(1);
	});
});

/** phosphor-svelte's own duotone branch of an icon component: [tone path, line path]. */
function phosphorDuotone(name: string): [string, string] {
	const require = createRequire(import.meta.url);
	const dir = dirname(require.resolve('phosphor-svelte/package.json'));
	const src = readFileSync(join(dir, 'lib', `${name}Icon.svelte`), 'utf8');
	const branch = /weight === "duotone"\}\s*([\s\S]*?)\{:else/.exec(src)?.[1] ?? '';
	const paths = [...branch.matchAll(/<path d="([^"]+)"([^>]*)\/>/g)];
	return [paths.find((p) => p[2].includes('opacity="0.2"'))?.[1] ?? '', paths.find((p) => !p[2].includes('opacity'))?.[1] ?? ''];
}

describe('the thermometer-and-road icon', () => {
	it('is Phosphor’s duotone ThermometerSimple and RoadHorizon, exactly as phosphor-svelte ships them', () => {
		expect(ROAD_WEATHER_ICON.map((p) => p.icon.name)).toEqual(['ThermometerSimple', 'RoadHorizon']);
		for (const { icon } of ROAD_WEATHER_ICON) {
			const [tone, line] = phosphorDuotone(icon.name);
			expect(tone, icon.name).not.toBe('');
			expect(icon.tone, `${icon.name} tone`).toBe(tone);
			expect(icon.line, `${icon.name} line`).toBe(line);
		}
		expect(THERMOMETER.name).toBe('ThermometerSimple');
	});

	it('keeps both parts inside the 256 box', () => {
		// The parts' own extents in Phosphor's 256 box: thermometer x 64–192, y 8–248; road x 17–239, y 56–199.
		const extent = { ThermometerSimple: [64, 8, 192, 248], RoadHorizon: [17, 56, 239, 199] } as const;
		for (const p of ROAD_WEATHER_ICON) {
			const [x0, y0, x1, y1] = extent[p.icon.name as keyof typeof extent];
			for (const [x, y] of [[x0, y0], [x1, y1]]) {
				expect(p.x + x * p.scale).toBeGreaterThanOrEqual(0);
				expect(p.x + x * p.scale).toBeLessThanOrEqual(256);
				expect(p.y + y * p.scale).toBeGreaterThanOrEqual(0);
				expect(p.y + y * p.scale).toBeLessThanOrEqual(256);
			}
		}
	});
});
