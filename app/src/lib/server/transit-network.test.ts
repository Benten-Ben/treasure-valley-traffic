import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
	CLAY,
	CREAM,
	INK,
	ROUTE_PALETTE,
	UNKNOWN_ROUTE,
	WHITE,
	badge,
	cacheControl,
	computeGhost,
	contrast,
	deltaE,
	flatCoords,
	ghostOf,
	hubsOf,
	routesOf
} from './transit-network.js';

// docs/14 §14.4's palette table: name, hex, ghost on clay, badge text, halo.
const TABLE: [string, string, string, 'white' | 'ink', boolean][] = [
	['blue', '#2a78d6', '#b1c6e2', 'white', true],
	['orange', '#eb6834', '#f5b59a', 'ink', true],
	['aqua', '#1baf7a', '#a4d2b2', 'ink', false],
	['yellow', '#eda100', '#f1c17b', 'ink', false],
	['pink', '#e87ba4', '#f1b3c2', 'ink', false],
	['green', '#008300', '#b3cda4', 'white', false],
	['violet', '#4a3aa7', '#bab8d4', 'white', false],
	['red', '#e34948', '#f4b3a7', 'white', true],
	['wine', '#99095c', '#deafb8', 'white', false],
	['lavender', '#a791fa', '#cbc0f1', 'ink', false],
	['brown', '#7f4315', '#d1b8a4', 'white', false],
	['plum', '#9059af', '#d1bad3', 'white', false],
	['lime', '#8cc63f', '#b9d88e', 'ink', false]
];

describe('route palette', () => {
	it('pins the 13 slots in order, with their ghosts', () => {
		expect(ROUTE_PALETTE.map((p) => [p.name, p.color, p.ghost])).toEqual(TABLE.map(([n, c, g]) => [n, c, g]));
	});

	it('matches ingest/route_colors.py slot for slot', () => {
		const py = readFileSync(resolve(import.meta.dirname, '../../../../ingest/route_colors.py'), 'utf8');
		const block = py.slice(py.indexOf('PALETTE_SLOTS = ['), py.indexOf(']\n', py.indexOf('PALETTE_SLOTS = [')));
		const slots = [...block.matchAll(/\("(\w+)", "(#[0-9a-f]{6})"\)/g)].map((m) => [m[1], m[2]]);
		expect(slots).toEqual(ROUTE_PALETTE.map((p) => [p.name, p.color]));
		for (const [name, value] of [['CLAY', CLAY], ['INK', INK], ['CREAM', CREAM], ['UNKNOWN', UNKNOWN_ROUTE]]) {
			expect(py).toContain(`${name} = "${value}"`);
		}
	});

	it('computes ghosts the way the Python build does', () => {
		for (const [, color, ghost] of TABLE) {
			expect(deltaE(ghost, CLAY)).toBeGreaterThanOrEqual(14);
			expect(computeGhost(color)).toBe(ghost);          // the formula reproduces the pinned table
			expect(ghostOf(color.toUpperCase())).toBe(ghost);
		}
		expect(ghostOf(UNKNOWN_ROUTE)).toBe('#c5bfb5');   // route_colors.ghost('#8a857c')
		expect(ghostOf('#123456')).toBe('#abb2b7');
	});

	it('follows the badge rule: blue, orange, red and the unknown gray get a halo', () => {
		for (const [name, color, , text, halo] of TABLE) {
			const b = badge(color);
			expect(b.textColor, name).toBe(text === 'white' ? WHITE : INK);
			expect(b.halo, name).toBe(halo);
			if (halo) expect(contrast(b.textColor, b.textColor === WHITE ? INK : CREAM)).toBeGreaterThanOrEqual(4.5);
			else expect(contrast(color, b.textColor)).toBeGreaterThanOrEqual(4.5);
		}
		expect(badge(UNKNOWN_ROUTE)).toEqual({ textColor: INK, halo: true });
	});
});

describe('assembling the network', () => {
	it('numbers routes from 1 and fills in what a route lacks', () => {
		const routes = routesOf([
			{ route_id: '2', short_name: '2', long_name: 'Broadway', color: '#1BAF7A', text_color: '#2b2a33', sort_order: 1 },
			{ route_id: 'T', short_name: 'R1', long_name: null, color: null, text_color: null, sort_order: 2 },
			{ route_id: '17', short_name: '17', long_name: null, color: '#2a78d6', text_color: 'garbage', sort_order: 3 }
		]);
		expect(routes.map((r) => r.rid)).toEqual([1, 2, 3]);
		expect(routes[0]).toEqual({
			id: '2', rid: 1, shortName: '2', longName: 'Broadway', color: '#1baf7a', ghost: '#a4d2b2',
			textColor: INK, halo: false, sortOrder: 1
		});
		expect(routes[1]).toMatchObject({ color: UNKNOWN_ROUTE, ghost: '#c5bfb5', textColor: INK, halo: true });
		expect(routes[2]).toMatchObject({ textColor: WHITE, halo: true });
	});

	it('flattens coordinates to 6 decimals', () => {
		expect(flatCoords([[-116.20361234, 43.61521], [-116.2, 43.6000004]])).toEqual([-116.203612, 43.61521, -116.2, 43.6]);
	});

	it('joins hub stops within 300 m and names the station', () => {
		const hubs = hubsOf([
			{ stop_id: 'AB000', name: 'Main Street Station - Lower Deck', lon: -116.2036, lat: 43.6152, route_ids: ['2', '3', '4', '5', '7', '9'] },
			{ stop_id: 'AB002', name: 'Main Street Station - Upper Deck', lon: -116.2030, lat: 43.6155, route_ids: ['16', '17', '29', '3', '4', '5', '9'] },
			{ stop_id: 'AB001', name: 'Towne Square Mall P&R', lon: -116.2755, lat: 43.6105, route_ids: ['21', '24', '28', '29', '4', '42'] }
		]);
		expect(hubs.map((h) => [h.id, h.name])).toEqual([['AB002', 'Main Street Station'], ['AB001', 'Towne Square Mall P&R']]);
		expect(hubs[0].routes).toEqual(['16', '17', '2', '29', '3', '4', '5', '7', '9']);
		expect(hubs[0].lon).toBeCloseTo(-116.2033, 4);
	});

	it('is immutable only for the current build', () => {
		const built = { build: 'abc-123', bundled: true };
		expect(cacheControl(built, 'abc-123')).toBe('public, max-age=31536000, immutable');
		expect(cacheControl(built, 'older')).toBe('no-cache');
		expect(cacheControl(built, null)).toBe('no-cache');
		expect(cacheControl({ build: 'none', bundled: false }, 'none')).toBe('no-cache');
	});
});
