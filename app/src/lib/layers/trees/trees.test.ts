import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { deltaE } from '#lib/map/color.js';
import { allMeshes } from '#lib/scene/meshes.js';
import { PRIORITY } from '../types.js';
import { TREE } from './icons.js';
import {
	builtText,
	contains,
	credits,
	dateText,
	discCollection,
	discOpacity,
	discRadius,
	DISCS,
	eventDetail,
	eventName,
	howWeKnow,
	KIND_OPACITY,
	kindText,
	lidarYear,
	metresToPx,
	MESH_OF_TYPE,
	modelFade,
	stillServes,
	TREE_GREENS,
	TREE_PREFIX,
	treeGreen,
	treeInstance,
	treeLayers,
	treeSelection,
	treesUrl,
	treeTitle,
	trunkIn,
	wantedBox,
	type Box,
	type TreeDetail,
	type TreeRow
} from './trees.js';

/** Made-up trees (no real records): one of each kind and type. */
const T = (o: Partial<TreeRow> = {}): TreeRow => ({ id: 'x-1', kind: 'placed', type: 'broadleaf', lng: -116.2, lat: 43.62, h: 18, r: 6, a: 0.45, n: 1.64, ...o });

describe('a tree as a 3D model (docs/19 §19.6)', () => {
	it('takes its type’s mesh: broadleaf a round crown, conifer stacked cones, narrow a column', () => {
		expect(MESH_OF_TYPE).toEqual({ broadleaf: 'tree-broad', conifer: 'tree-cone', narrow: 'tree-column' });
		const meshes = allMeshes();
		for (const m of Object.values(MESH_OF_TYPE)) expect(meshes[m], m).toBeTruthy();
		expect(treeInstance(T({ type: 'conifer' })).mesh).toBe('tree-cone');
		expect(treeInstance(T({ type: 'narrow' })).mesh).toBe('tree-column');
	});

	it('is scaled [r, r, h]: the meshes are a unit crown radius and height', () => {
		const i = treeInstance(T({ h: 21.5, r: 7.25 }));
		expect(i.scale).toEqual([7.25, 7.25, 21.5]);
		expect(i.lng).toBe(-116.2);
		expect(i.lat).toBe(43.62);
		expect(i.alt).toBeUndefined();
	});

	it('is solid when catalogued, lighter when placed, lightest when estimated (the engine dithers below 1)', () => {
		expect(KIND_OPACITY).toEqual({ catalogued: 1, placed: 0.8, estimated: 0.5 });
		expect(treeInstance(T({ kind: 'catalogued' })).opacity).toBe(1);
		expect(treeInstance(T({ kind: 'placed' })).opacity).toBe(0.8);
		expect(treeInstance(T({ kind: 'estimated' })).opacity).toBe(0.5);
		// And dithers in with the zoom, as the 3D cameras do.
		expect(treeInstance(T({ kind: 'placed' }), 0.5).opacity).toBeCloseTo(0.4, 9);
		expect(modelFade(14.6)).toBe(0);
		expect(modelFade(14.85)).toBeCloseTo(0.5, 9);
		expect(modelFade(15)).toBe(1);
	});

	it('has a soft shadow, a hit radius of its crown, and selects a tree through the picker', () => {
		const t = T({ id: 'c-1-2', h: 12, r: 4 });
		const i = treeInstance(t);
		expect(i.shadow).toBe(true);
		expect(i.pickRadius).toBe(4);
		expect(i.id).toBe(`${TREE_PREFIX}c-1-2`);
		expect(i.pick).toMatchObject({ kind: 'tree', id: 'c-1-2', layer: 'trees', title: 'Broadleaf tree', at: [-116.2, 43.62] });
		expect(i.pick?.data).toBe(t);
		expect(treeSelection(T({ type: 'conifer', h: 9.24, kind: 'estimated' })).fact).toBe('9.2 m tall · estimated');
		// Trees rank under streets (crowns line them) and over the plain sprites.
		expect(PRIORITY.tree).toBeLessThan(PRIORITY.street);
		expect(PRIORITY.tree).toBeGreaterThan(PRIORITY.sprite);
	});

	it('is a calm green, the same for the same id, from its type’s small range', () => {
		const ids = Array.from({ length: 60 }, (_, k) => `c-${k}-${k * 7}`);
		for (const type of ['broadleaf', 'conifer', 'narrow'] as const) {
			const used = new Set(ids.map((id) => treeGreen(id, type)));
			expect(used.size).toBeGreaterThan(1);
			for (const g of used) expect(TREE_GREENS[type]).toContain(g);
		}
		expect(treeGreen('boise-abc', 'broadleaf')).toBe(treeGreen('boise-abc', 'broadleaf'));
		expect(treeInstance(T({ id: 'q' })).color).toBe(treeGreen('q', 'broadleaf'));
	});
});

describe('the trees’ colors keep to the color budget (docs/14 §14.3)', () => {
	const ROUTES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948', '#99095c', '#a791fa', '#7f4315', '#9059af', '#8cc63f'];
	const GHOSTS = ['#b1c6e2', '#f5b59a', '#a4d2b2', '#f1c17b', '#f1b3c2', '#b3cda4', '#bab8d4', '#f4b3a7', '#deafb8', '#cbc0f1', '#d1b8a4', '#d1bad3', '#b9d88e'];
	const GROUND = ['#eee7da', '#f3ede2', '#b9d88f', '#a9cf85', '#d3e3b4', '#cbddae', '#e4e8d6'];
	const all = Object.values(TREE_GREENS).flat();

	it('every green is at least ΔE 10 from every route color (route aqua the nearest), 12 from camera teal, 15 from ghosts, parks and ground', () => {
		for (const g of all) {
			for (const r of ROUTES) expect(deltaE(g, r), `${g} vs ${r}`).toBeGreaterThanOrEqual(10);
			for (const r of [...GHOSTS, ...GROUND]) expect(deltaE(g, r), `${g} vs ${r}`).toBeGreaterThanOrEqual(15);
			// Not teal (cameras; the conifers are the nearest), amber (the interface) or magenta (problems).
			for (const r of ['#2c8c99', '#f2a20c', '#d9467a']) expect(deltaE(g, r), `${g} vs ${r}`).toBeGreaterThanOrEqual(12);
		}
	});

	it('conifers are the darkest; each type’s greens vary only a little', () => {
		const L = (hex: string) => {
			const n = parseInt(hex.slice(1), 16);
			return 0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255);
		};
		expect(Math.max(...TREE_GREENS.conifer.map(L))).toBeLessThan(Math.min(...TREE_GREENS.broadleaf.map(L), ...TREE_GREENS.narrow.map(L)));
		for (const greens of Object.values(TREE_GREENS))
			for (const a of greens) for (const b of greens) expect(deltaE(a, b)).toBeLessThanOrEqual(7);
	});
});

describe('crown discs (farther out, or without the scene)', () => {
	it('carry each tree’s radius, green and kind opacity', () => {
		const fc = discCollection([T({ id: 'a', kind: 'estimated', r: 3.5 })]);
		expect(fc.features[0].properties).toMatchObject({ id: 'a', kind: 'estimated', r: 3.5, o: 0.5, c: treeGreen('a', 'broadleaf') });
		expect(fc.features[0].geometry.coordinates).toEqual([-116.2, 43.62]);
	});

	it('are sized in metres at every zoom (exact between whole zooms), at least 1 px', () => {
		// 3.46 m per px at z14 at 43.6° N (docs/14 §14.4).
		expect(1 / metresToPx(1, 14)).toBeCloseTo(3.46, 1);
		const expr = discRadius() as unknown[];
		expect(expr.slice(0, 3)).toEqual(['interpolate', ['exponential', 2], ['zoom']]);
		const z15 = expr.indexOf(15);
		expect(expr[z15 + 1]).toEqual(['max', 1, ['*', ['get', 'r'], metresToPx(1, 15)]]);
		expect(metresToPx(1, 16) / metresToPx(1, 15)).toBeCloseTo(2, 9);
	});

	it('fade out over 14.7–15 when the models take over, and keep their kind’s opacity otherwise', () => {
		expect(discOpacity(false)).toEqual(['get', 'o']);
		expect(discOpacity(true)).toEqual(['interpolate', ['linear'], ['zoom'], 14.7, ['get', 'o'], 15, 0]);
	});

	it('are one circle layer in the scene slot: not draped, so the terrain keeps one draped run', () => {
		const [l] = treeLayers();
		expect(l.slot).toBe('scene');
		expect(l.layer.id).toBe(DISCS);
		expect(l.layer.type).toBe('circle');
		expect((l.layer.layout as Record<string, unknown>).visibility).toBe('none');
		expect((l.layer.paint as Record<string, unknown>)['circle-pitch-alignment']).toBe('map');
	});
});

describe('asking for the view’s trees', () => {
	const view: Box = [-116.215, 43.622, -116.205, 43.629];

	it('grows the view by a quarter, keeps it near the centre, and snaps it out to the grid', () => {
		const b = wantedBox(view, [-116.21, 43.6255], 50_000);
		expect(contains(b, [-116.2175, 43.62025, -116.2025, 43.63075])).toBe(true);
		for (const x of b) expect(Math.abs(Math.round(x / 0.002) * 0.002 - x)).toBeLessThan(1e-9);
		// A tilted view's bounds reach the horizon: kept within the radius of the centre.
		const far = wantedBox([-117, 43, -115, 44.5], [-116.21, 43.6255], 1000);
		expect(far[2] - far[0]).toBeLessThan(0.03);
		expect(far[3] - far[1]).toBeLessThan(0.03);
	});

	it('doesn’t ask again while what it has covers the view (at the same limit), unless that was cut and is much bigger', () => {
		const want: Box = [-116.21, 43.62, -116.2, 43.63];
		const big: Box = [-116.22, 43.61, -116.19, 43.64];
		expect(stillServes(null, want, 4000)).toBe(false);
		expect(stillServes({ box: big, limit: 4000, truncated: false }, want, 4000)).toBe(true);
		expect(stillServes({ box: big, limit: 8000, truncated: false }, want, 4000)).toBe(false);
		expect(stillServes({ box: big, limit: 4000, truncated: true }, want, 4000)).toBe(false);
		expect(stillServes({ box: want, limit: 4000, truncated: true }, want, 4000)).toBe(true);
		expect(stillServes({ box: want, limit: 4000, truncated: false }, big, 4000)).toBe(false);
		expect(treesUrl(want, 4000)).toBe('/api/trees?bbox=-116.21,43.62,-116.2,43.63&limit=4000');
	});
});

describe('the words (the legend and the tree panel)', () => {
	const detail = (o: Partial<TreeDetail> = {}): TreeDetail => ({
		id: 'x',
		area: 'c',
		kind: 'catalogued',
		type: 'broadleaf',
		height_m: 20,
		crown_radius_m: 7,
		ground_m: 820,
		lidar: 'USGS 3DEP QL1 lidar, Example project (flown Sep-Oct 2023)',
		fit: {},
		build_id: 'b',
		catalogue: null,
		log: [],
		...o
	});
	const cat = { catalogue: 'boise', catalogue_id: 'fake-1', common_name: 'Test linden (synthetic)', genus: 'Exemplia', species: 'fictus', dbh_in: 14, installed: '2009-04-15', last_verified: '2024-06-01', condition: 'Good', site_type: 'Street' };

	it('says where trees are built, never filling in from elsewhere', () => {
		expect(builtText([])).toBe('No trees are built yet.');
		expect(builtText([{ area: 'c', bounds: [0, 0, 1, 1], trees: 191, built_at: null }])).toBe('Trees are built for the North End so far.');
		expect(builtText([{ area: 'c', bounds: [0, 0, 1, 1], trees: 1, built_at: null }, { area: 'd', bounds: [0, 0, 1, 1], trees: 1, built_at: null }])).toBe(
			'Trees are built for the North End and area d so far.'
		);
	});

	it('explains each kind in plain words', () => {
		expect(kindText('catalogued')).toBe("In the City of Boise's inventory, measured by the 2023 lidar");
		expect(kindText('placed')).toBe('Found in the 2023 lidar; position and crown estimated by placement');
		expect(kindText('estimated')).toBe("In the City's inventory but not seen in the 2023 lidar; sized from its species and trunk diameter");
		expect(lidarYear(detail())).toBe('2023');
		expect(lidarYear(detail({ lidar: null, log: [{ at: '2021-05-01T00:00:00Z', event: 'measured', detail: {} }] }))).toBe('2021');
	});

	it('titles a tree by its species when the catalogue is here, else by its type', () => {
		expect(treeTitle(detail({ catalogue: cat }))).toBe('Test linden (synthetic)');
		expect(treeTitle(detail({ kind: 'estimated', catalogue: cat }))).toBe('Test linden (synthetic)');
		expect(treeTitle(detail())).toBe('Broadleaf tree');
		expect(treeTitle(detail({ kind: 'placed', type: 'narrow' }))).toBe('Narrow tree');
		expect(treeTitle(detail({ type: 'conifer' }))).toBe('Conifer');
	});

	it('says how we know: the lidar, the trunk point’s distance, or the placement', () => {
		expect(howWeKnow(detail({ fit: { trunk_to_crown_m: 2.44 } })).join(' ')).toContain('2.4 m from the trunk point');
		const placed = howWeKnow(detail({ kind: 'placed', fit: { width_vs_typical_sd: 1.2, crowded: true } })).join(' ');
		expect(placed).toContain('estimated by placement');
		expect(placed).toContain('1.2 standard deviations wider');
		expect(placed).toContain('cluster');
		const est = howWeKnow(detail({ kind: 'estimated', lidar: null, fit: { under_taller_crown: true, lidar_height_there_m: 21.6 } })).join(' ');
		expect(est).toContain("doesn't show it");
		expect(est).toContain('under a taller tree');
		expect(est).toContain('22 m');
	});

	it('names the log’s events and sums up each', () => {
		expect(eventName('measured')).toBe('Measured by lidar');
		expect(eventName('placed')).toBe('Placed from the lidar');
		expect(eventName('estimated')).toBe('Sized from species and trunk');
		expect(eventName('something_new')).toBe('Something new');
		expect(eventDetail({ at: '', event: 'measured', detail: { height_m: 26.83, crown_width_m: 18.9 } })).toBe('27 m tall, crown 19 m wide');
		expect(eventDetail({ at: '', event: 'estimated', detail: { height_m: 5.06, crown_width_m: 5.39, dbh_in: 7 } })).toBe('5.1 m tall, crown 5.4 m wide, trunk 7 in');
	});

	it('reads dates without moving a day, and the trunk from the catalogue or the estimate', () => {
		expect(dateText('2009-04-15')).toBe('Apr 15, 2009');
		expect(dateText('2023-10-24T12:00:00Z')).toBe('Oct 24, 2023');
		expect(dateText(null)).toBeNull();
		expect(trunkIn(detail({ catalogue: cat }))).toBe(14);
		expect(trunkIn(detail({ kind: 'estimated', fit: { dbh_in: 7 } }))).toBe(7);
		expect(trunkIn(detail())).toBeNull();
	});

	it('credits the lidar always, the City for catalogued and estimated trees, the Urban Tree Database for estimated ones', () => {
		expect(credits('placed', null)).toEqual(['USGS 3DEP lidar (2023)']);
		expect(credits('catalogued', 'boise')).toEqual(['USGS 3DEP lidar (2023)', 'City of Boise tree inventory']);
		const est = credits('estimated', 'boise');
		expect(est).toHaveLength(3);
		expect(est[2]).toContain('Urban Tree Database');
	});
});

describe('the icon', () => {
	it('is Phosphor’s Tree, duotone, exactly as phosphor-svelte ships it', () => {
		const require = createRequire(import.meta.url);
		const dir = dirname(require.resolve('phosphor-svelte/package.json'));
		const src = readFileSync(join(dir, 'lib', `${TREE.name}Icon.svelte`), 'utf8');
		const branch = /weight === "duotone"\}\s*([\s\S]*?)\{:else/.exec(src)?.[1] ?? '';
		const paths = [...branch.matchAll(/<path d="([^"]+)"([^>]*)\/>/g)];
		expect(TREE.tone).toBe(paths.find((p) => p[2].includes('opacity="0.2"'))?.[1]);
		expect(TREE.line).toBe(paths.find((p) => !p[2].includes('opacity'))?.[1]);
	});
});
