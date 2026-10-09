import { describe, expect, it } from 'vitest';
import { LEFT_COLUMN, RIGHT_COLUMN } from '#lib/state/windows.svelte.js';
import { landing } from '../cameras/place.js';
import { CLEAR_PX, MAX_LAND_ZOOM, stationLanding, TABLET_RIGHT_COLUMN, zoomToLand } from './place.js';

const desk = { left: 0, top: 0, width: 1280, height: 800 };

describe('road weather: where a clicked station goes', () => {
	it('stays put in the free middle of a desktop', () => {
		expect(stationLanding({ x: 640, y: 400 }, desk, 400, 'desktop')).toBeNull();
		expect(stationLanding({ x: LEFT_COLUMN + CLEAR_PX, y: 400 }, desk, 400, 'desktop')).toBeNull();
		expect(stationLanding({ x: 1280 - RIGHT_COLUMN - CLEAR_PX, y: 400 }, desk, 400, 'desktop')).toBeNull();
	});

	it('pans into the free middle, where its window fits beside it, from under the inspect card or the legends', () => {
		const land = landing(desk, 400, 'desktop');
		expect(land).toEqual({ x: 388, y: 400 });
		// Example Grade at z11 in the verifier's screenshot: right of the free middle, under the inspect card.
		expect(stationLanding({ x: 1100, y: 420 }, desk, 400, 'desktop')).toEqual(land);
		expect(stationLanding({ x: 1280 - RIGHT_COLUMN - CLEAR_PX + 1, y: 400 }, desk, 400, 'desktop')).toEqual(land);
		expect(stationLanding({ x: 200, y: 400 }, desk, 400, 'desktop')).toEqual(land);
		// Under the top bar or the toolbar.
		expect(stationLanding({ x: 640, y: 60 }, desk, 400, 'desktop')).toEqual(land);
		expect(stationLanding({ x: 640, y: 760 }, desk, 400, 'desktop')).toEqual(land);
	});

	it('lands in the middle of a desktop too narrow for a window between the columns', () => {
		const narrow = { left: 0, top: 0, width: 1024, height: 768 };
		expect(landing(narrow, 400, 'desktop')).toBeNull();
		expect(stationLanding({ x: 1000, y: 384 }, narrow, 400, 'desktop')).toEqual({ x: 512, y: 384 });
	});

	it('on a tablet, comes out from under its narrower inspect column', () => {
		const tab = { left: 0, top: 0, width: 800, height: 1024 };
		expect(stationLanding({ x: 300, y: 500 }, tab, 400, 'tablet')).toBeNull();
		expect(stationLanding({ x: 700, y: 500 }, tab, 400, 'tablet')).toEqual({ x: Math.round((800 - TABLET_RIGHT_COLUMN) / 2), y: 512 });
	});

	it('on a phone, rises above the sheet a window lifts', () => {
		const phone = { left: 0, top: 0, width: 390, height: 844 };
		expect(stationLanding({ x: 195, y: 300 }, phone, 400, 'phone')).toBeNull();
		expect(stationLanding({ x: 195, y: 422 }, phone, 400, 'phone')).toEqual(landing(phone, 400, 'phone'));
		expect(stationLanding({ x: 195, y: 40 }, phone, 400, 'phone')).toEqual({ x: 195, y: 228 });
	});

	it('counts from the map’s box, not the page’s', () => {
		const offset = { left: 100, top: 50, width: 1280, height: 800 };
		expect(stationLanding({ x: 740, y: 450 }, offset, 400, 'desktop')).toBeNull();
		expect(stationLanding({ x: 1200, y: 450 }, offset, 400, 'desktop')).toEqual(landing(offset, 400, 'desktop'));
	});

	describe('how far it zooms in, when the map’s bounds would stop the pan short', () => {
		// The map's maxBounds: the base map's bounds plus 0.15° (map/create.ts).
		const BOUNDS: [[number, number], [number, number]] = [
			[-117.2, 42.85],
			[-115.8, 44.0]
		];
		const land = { x: 388, y: 400 };
		const mx = (lon: number) => (lon + 180) / 360;
		const my = (lat: number) => (1 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / Math.PI) / 2;
		/** Whether, at `zoom`, the view with the station at `land` stays inside the bounds (as MapLibre keeps it). */
		const fits = (at: [number, number], zoom: number, size = desk) => {
			const world = 512 * 2 ** zoom;
			const x = mx(at[0]) * world;
			const y = my(at[1]) * world;
			return (
				x - land.x >= mx(BOUNDS[0][0]) * world - 1 &&
				x + size.width - land.x <= mx(BOUNDS[1][0]) * world + 1 &&
				y - land.y >= my(BOUNDS[1][1]) * world - 1 &&
				y + size.height - land.y <= my(BOUNDS[0][1]) * world + 1
			);
		};
		const grade: [number, number] = [-116.24, 43.56];

		it('keeps the zoom when a pan can get there', () => {
			expect(zoomToLand(grade, land, desk, BOUNDS, 11)).toBe(11);
			expect(fits(grade, 11)).toBe(true);
		});

		it('zooms in just enough where the view spans the bounds (z 9.3 on a desktop: no room to pan at all)', () => {
			// Example Grade at the wide view of the @wp16 spec: a pan alone left it under the inspect card.
			expect(fits(grade, 9.33)).toBe(false);
			const z = zoomToLand(grade, land, desk, BOUNDS, 9.33)!;
			expect(z).toBeGreaterThan(10.4);
			expect(z).toBeLessThan(10.6);
			expect(fits(grade, z)).toBe(true);
			expect(fits(grade, z - 0.05)).toBe(false);
		});

		it('on a phone too, with its landing point above the sheet', () => {
			const phone = { left: 0, top: 0, width: 390, height: 844 };
			const up = { x: 195, y: 228 };
			const z = zoomToLand(grade, up, phone, BOUNDS, 8)!;
			expect(z).toBeGreaterThan(8);
			const world = 512 * 2 ** z;
			expect(my(grade[1]) * world - up.y).toBeGreaterThanOrEqual(my(BOUNDS[1][1]) * world - 1);
			expect(mx(grade[0]) * world + phone.width - up.x).toBeLessThanOrEqual(mx(BOUNDS[1][0]) * world + 1);
		});

		it('stays put when no zoom up to its limit can get there, or the station is outside the bounds', () => {
			expect(zoomToLand([-115.8001, 43.5], land, desk, BOUNDS, 10)).toBeNull();
			expect(zoomToLand([-115.5, 43.5], land, desk, BOUNDS, 10)).toBeNull();
			expect(zoomToLand([-116.5, 44.2], land, desk, BOUNDS, 10)).toBeNull();
			expect(zoomToLand(grade, land, desk, BOUNDS, 9.33, 10)).toBeNull();
			expect(MAX_LAND_ZOOM).toBe(14);
		});
	});
});
