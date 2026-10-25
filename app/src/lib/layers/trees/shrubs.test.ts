import { afterEach, describe, expect, it } from 'vitest';
import { deltaE } from '#lib/map/color.js';
import { allMeshes, lodMeshes, MESHES } from '#lib/scene/meshes.js';
import { PRIORITY } from '../types.js';
import {
	bushMesh,
	CENTRE_SNAP_DEG,
	LOOK_NAME,
	LOOKS,
	MESH_OF_LOOK,
	registerShrubMeshes,
	sageMesh,
	shrubInstance,
	shrubLowMesh,
	shrubsBuiltText,
	SHRUB_BELOW_PX,
	SHRUB_BUDGET,
	SHRUB_CAP_PHONE,
	SHRUB_COLORS,
	SHRUB_LIMIT,
	SHRUB_RADIUS_M,
	shrubHowWeKnow,
	shrubSelection,
	shrubsUrl,
	shrubsWanted,
	SHRUBS_SCENE,
	SHRUBS_ZOOM,
	type ShrubRow
} from './shrubs.js';
import { areaName, TREE_GREENS } from './trees.js';

/** A made-up shrub. */
const shrub = (o: Partial<ShrubRow> = {}): ShrubRow => ({ id: 'c-1-2', look: 'bush', lng: -116.2089, lat: 43.6275, h: 1.2, w: 1.9, ...o });
const tris = (m: { indices: Uint16Array }) => m.indices.length / 3;

describe('the shrubs’ models (S7 registry)', () => {
	let off: (() => void) | null = null;
	afterEach(() => off?.());

	it('are within their triangle budgets, the low-detail ones within 24', () => {
		for (const m of [bushMesh(), sageMesh()]) expect(tris(m)).toBeLessThanOrEqual(SHRUB_BUDGET);
		for (const look of LOOKS) expect(tris(shrubLowMesh(MESH_OF_LOOK[look])())).toBeLessThanOrEqual(24);
	});

	it('are a unit dome: widest vertex at radius 1, from the ground (0) to the top (1)', () => {
		for (const m of [bushMesh(), sageMesh()]) {
			expect(m.min[2]).toBeCloseTo(0, 5);
			expect(m.max[2]).toBeCloseTo(1, 5);
			expect(Math.max(m.max[0], m.max[1], -m.min[0], -m.min[1])).toBeLessThanOrEqual(1 + 1e-6);
			expect(Math.max(m.max[0], m.max[1], -m.min[0], -m.min[1])).toBeGreaterThan(0.95);
		}
	});

	it('are told apart by shape, not only by color', () => {
		const a = bushMesh().vertices;
		const b = sageMesh().vertices;
		expect(Array.from(a.slice(0, 60))).not.toEqual(Array.from(b.slice(0, 60)));
	});

	it('register both kinds, with a low-detail mesh under 6 px, and unregister', () => {
		off = registerShrubMeshes();
		for (const look of LOOKS) {
			const kind = MESH_OF_LOOK[look];
			expect(kind in MESHES).toBe(true);
			expect(allMeshes()[kind]).toBeDefined();
			expect(lodMeshes()[kind].belowPx).toBe(SHRUB_BELOW_PX);
			expect(tris(lodMeshes()[kind].mesh)).toBeLessThanOrEqual(24);
		}
		expect(SHRUB_BELOW_PX).toBe(6);
		off();
		off = null;
		for (const look of LOOKS) expect(MESH_OF_LOOK[look] in MESHES).toBe(false);
	});
});

describe('the shrubs in the scene', () => {
	it('keep the nearest 1,500 within about 300 m, none on a phone, from z17', () => {
		expect(SHRUBS_SCENE).toMatchObject({ cap: 1500, capPhone: 0, radiusM: 300, scenery: true, priority: PRIORITY.shrub });
		expect(SHRUB_LIMIT).toBe(1500);
		expect(SHRUB_RADIUS_M).toBe(300);
		expect(SHRUB_CAP_PHONE).toBe(0);
		expect(SHRUBS_ZOOM).toBe(17);
		expect(PRIORITY.shrub).toBe(34);
	});

	it('become instances scaled [w/2, w/2, h], on the ground, in their look’s model and color', () => {
		const i = shrubInstance(shrub({ look: 'sage', h: 0.8, w: 1.6, id: 'x' }));
		expect(i).toMatchObject({ id: 'shrub:x', mesh: 'shrub-sage', scale: [0.8, 0.8, 0.8], color: SHRUB_COLORS.sage, grounded: true, pickRadius: 0.8 });
		expect(shrubInstance(shrub()).mesh).toBe('shrub-bush');
	});

	it('are picked with a small card: height, type, “found in the lidar”', () => {
		const sel = shrubSelection(shrub({ h: 1.24 }));
		expect(sel).toMatchObject({ kind: 'shrub', layer: 'trees', title: 'Bush', at: [-116.2089, 43.6275] });
		expect(sel.fact).toBe('1.2 m tall · found in the lidar');
		expect(shrubSelection(shrub({ look: 'sage' })).title).toBe('Sage');
		expect(sel.source).toContain('USGS 3DEP lidar');
	});

	it('say the width is the model’s, not a measurement', () => {
		expect(shrubHowWeKnow({ look: 'bush' }).join(' ')).toMatch(/width is not measured/);
		expect(shrubHowWeKnow({ look: 'sage' }).join(' ')).toContain('Sage:');
	});

	it('keep their greens apart from the trees’ (ΔE 6 at the least) and from each other', () => {
		for (const look of LOOKS) for (const type of Object.values(TREE_GREENS)) for (const g of type) expect(deltaE(SHRUB_COLORS[look], g)).toBeGreaterThan(6);
		expect(deltaE(SHRUB_COLORS.bush, SHRUB_COLORS.sage)).toBeGreaterThan(8);
		expect(LOOK_NAME.bush).not.toBe(LOOK_NAME.sage);
	});
});

describe('fetching the shrubs', () => {
	it('asks for a box 300 m round the snapped centre, so a small pan asks for the same URL', () => {
		const a = shrubsWanted([-116.20892, 43.62755]);
		const b = shrubsWanted([-116.20871, 43.62772]);
		expect(a.centre).toEqual(b.centre);
		expect(shrubsUrl(a.box, a.centre)).toBe(shrubsUrl(b.box, b.centre));
		const [w, s, e, n] = a.box;
		// 300 m each way is about 0.0035° of longitude and 0.0027° of latitude, snapped out.
		expect(e - w).toBeGreaterThanOrEqual(2 * 0.0035 - 1e-9);
		expect(n - s).toBeGreaterThanOrEqual(2 * 0.0027 - 1e-9);
		expect(w).toBeLessThan(a.centre[0]);
		expect(e).toBeGreaterThan(a.centre[0]);
		expect(shrubsUrl(a.box, a.centre)).toMatch(/^\/api\/trees\/shrubs\?bbox=[-\d.,]+&center=[-\d.,]+&limit=1500$/);
		expect(CENTRE_SNAP_DEG).toBe(0.001);
	});

	it('moves to another URL once the centre crosses to another grid point', () => {
		const a = shrubsWanted([-116.2089, 43.6275]);
		const b = shrubsWanted([-116.2089, 43.6305]);
		expect(shrubsUrl(a.box, a.centre)).not.toBe(shrubsUrl(b.box, b.centre));
	});

	it('says where shrubs are built, never filling in from elsewhere', () => {
		expect(shrubsBuiltText([], areaName)).toBe('No shrubs are built yet.');
		const area = (a: string) => ({ area: a, bounds: [0, 0, 1, 1] as [number, number, number, number], shrubs: 1, built_at: null });
		expect(shrubsBuiltText([area('c')], areaName)).toBe('Shrubs are built for the North End so far.');
		expect(shrubsBuiltText([area('c'), area('d'), area('e')], areaName)).toBe('Shrubs are built for the North End, area d and area e so far.');
	});
});
