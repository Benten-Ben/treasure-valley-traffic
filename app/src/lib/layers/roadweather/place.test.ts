import { describe, expect, it } from 'vitest';
import { LEFT_COLUMN, RIGHT_COLUMN } from '#lib/state/windows.svelte.js';
import { landing } from '../cameras/place.js';
import { CLEAR_PX, stationLanding, TABLET_RIGHT_COLUMN } from './place.js';

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
});
