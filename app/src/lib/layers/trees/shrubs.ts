import { registerMeshKind, unregisterMeshKind, type SceneInstance } from '#lib/scene/index.js';
import { Builder, icosphere, rgb, seeded, TINT, type Mesh } from '#lib/scene/meshes.js';
import { PRIORITY, type Selection } from '../types.js';
import { fmtM, inBox, SNAP_DEG, type Box } from './trees.js';

/**
 * The shrubs' shared pieces (docs/19 §19.8, plan P11-app): the API's shapes, the two models, how a shrub becomes a
 * scene instance, and the words the legend and the card use. Pure, so it is tested without a map.
 *
 * - **From z17** (with the 3D scene running; off on phones) the nearest shrubs to the view's centre, at most
 *   SHRUB_LIMIT within about SHRUB_RADIUS_M, are drawn as low-poly domes by look: `bush` (green in the summer photo)
 *   and `sage` (not green; a plant by its lidar scatter). Shrubs have no disc: below z17 nothing is drawn.
 * - The two looks are told apart by shape and by name in the legend and the card, never by color alone.
 * - A shrub's width is the model fitted on the test areas (plugins/trees/README.md), not a measurement.
 */

export type ShrubLook = 'bush' | 'sage';
export const LOOKS: readonly ShrubLook[] = ['bush', 'sage'];

/** One shrub in a view (GET /api/trees/shrubs): h height, w crown width (diameter), both metres. */
export interface ShrubRow {
	id: string;
	look: ShrubLook;
	lng: number;
	lat: number;
	h: number;
	w: number;
}

export interface ShrubsInView {
	shrubs: ShrubRow[];
	/** More shrubs were within reach than `limit`: these are the nearest the centre. */
	truncated: boolean;
}

/** Where shrubs are built (GET /api/trees/shrubs/areas). */
export interface ShrubArea {
	area: string;
	/** [west, south, east, north] of its outline. */
	bounds: [number, number, number, number];
	shrubs: number;
	built_at: string | null;
}

// --- the numbers -------------------------------------------------------------------------------------

/** Where shrubs are built (small; the legend says where, and the map waits for no shrub). */
export const SHRUB_AREAS_URL = '/api/trees/shrubs/areas';
/** Shrubs draw from this zoom (plan §3.5). */
export const SHRUBS_ZOOM = 17;
/** The scene is asked for a little before. */
export const SHRUBS_SCENE_ZOOM = 16.5;
/** At most this many shrubs, the nearest the centre (S7's cap; the API's limit is the same). */
export const SHRUB_LIMIT = 1500;
/** Shrubs within about this many metres of the view's centre. */
export const SHRUB_RADIUS_M = 300;
/** Phones draw no shrubs (S7's capPhone). */
export const SHRUB_CAP_PHONE = 0;
/** The scene group of the shrubs. */
export const SHRUBS_3D = 'shrubs-3d';
/** Scene instance ids are the shrub's id after this. */
export const SHRUB_PREFIX = 'shrub:';

/**
 * The shrubs' scene options as production passes them to `scene.set`: the nearest SHRUB_LIMIT within
 * SHRUB_RADIUS_M, none on phones, and scenery (it never moves).
 */
export const SHRUBS_SCENE = { priority: PRIORITY.shrub, cap: SHRUB_LIMIT, capPhone: SHRUB_CAP_PHONE, radiusM: SHRUB_RADIUS_M, scenery: true } as const;

// --- models ------------------------------------------------------------------------------------------

export const MESH_OF_LOOK: Record<ShrubLook, string> = { bush: 'shrub-bush', sage: 'shrub-sage' };
/** Triangle budgets: the full mesh (an icosphere of 80) and the low-detail one under BELOW_PX (an icosphere of 20). */
export const SHRUB_BUDGET = 80;
export const SHRUB_BELOW_PX = 6;

/**
 * Two greens apart from the trees' (docs/14's color budget): the bush a yellower green, the sage a grey one. They
 * are told apart by shape too, and by name.
 */
export const SHRUB_COLORS: Record<ShrubLook, string> = { bush: '#a3ad55', sage: '#a7aa96' };
/** The legend swatch's edge (the same dark edge as the tree discs). */
export const SHRUB_EDGE = '#3f4f2e';

/**
 * A lumpy dome, unit width (widest vertex at radius 1) and height (0 to 1), its underside flattened by `flat`:
 * an icosphere of 20 · 4^levels faces, each vertex pushed in or out by up to `lump` (seeded).
 */
function dome(levels: number, lump: number, flat: number, seed: number): Mesh {
	const { v, f } = icosphere(levels);
	const rand = seeded(seed);
	const p = v.map(([x, y, z]): [number, number, number] => {
		const k = 1 + lump * (rand() * 2 - 1);
		return [x * k, y * k, (z < 0 ? z * flat : z) * k];
	});
	const across = Math.max(...p.map(([x, y]) => Math.hypot(x, y)));
	const bottom = Math.min(...p.map((q) => q[2]));
	const top = Math.max(...p.map((q) => q[2]));
	const fitted = p.map(([x, y, z]): [number, number, number] => [x / across, y / across, (z - bottom) / (top - bottom)]);
	const b = new Builder();
	const centre: [number, number, number] = [0, 0, (-bottom) / (top - bottom)];
	const white = rgb('#ffffff');
	for (const [i, j, k] of f) {
		const [a, c, d] = [fitted[i], fitted[j], fitted[k]];
		const cross: [number, number, number] = [
			(c[1] - a[1]) * (d[2] - a[2]) - (c[2] - a[2]) * (d[1] - a[1]),
			(c[2] - a[2]) * (d[0] - a[0]) - (c[0] - a[0]) * (d[2] - a[2]),
			(c[0] - a[0]) * (d[1] - a[1]) - (c[1] - a[1]) * (d[0] - a[0])
		];
		const mid = [(a[0] + c[0] + d[0]) / 3 - centre[0], (a[1] + c[1] + d[1]) / 3 - centre[1], (a[2] + c[2] + d[2]) / 3 - centre[2]];
		const out = cross[0] * mid[0] + cross[1] * mid[1] + cross[2] * mid[2] >= 0;
		const len = Math.hypot(...cross) || 1;
		const n: [number, number, number] = [cross[0] / len, cross[1] / len, cross[2] / len];
		b.poly([a, c, d], white, TINT.instance, out ? n : [-n[0], -n[1], -n[2]]);
	}
	return b.build('shrub');
}

/** A bush: a rounded dome (80 triangles). */
export const bushMesh = (): Mesh => ({ ...dome(1, 0.07, 0.3, 11), kind: MESH_OF_LOOK.bush });
/** Sage: a squatter, rougher dome (80 triangles). */
export const sageMesh = (): Mesh => ({ ...dome(1, 0.16, 0.5, 23), kind: MESH_OF_LOOK.sage });
/** The low-detail mesh of both: an icosphere's 20 faces, flattened below. */
export const shrubLowMesh = (kind: string) => (): Mesh => ({ ...dome(0, 0.04, 0.3, 5), kind });

/** Register both models with the scene's mesh registry (S7); returns the unregister. */
export function registerShrubMeshes(): () => void {
	for (const look of LOOKS) {
		const kind = MESH_OF_LOOK[look];
		registerMeshKind(kind, look === 'bush' ? bushMesh : sageMesh, SHRUB_BUDGET, { build: shrubLowMesh(kind), belowPx: SHRUB_BELOW_PX });
	}
	return () => {
		for (const look of LOOKS) unregisterMeshKind(MESH_OF_LOOK[look]);
	};
}

// --- words, picks and scene instances -----------------------------------------------------------------

export const LOOK_NAME: Record<ShrubLook, string> = { bush: 'Bush', sage: 'Sage' };
export const LOOK_ABOUT: Record<ShrubLook, string> = { bush: 'green in the summer photo', sage: 'not green in the summer photo; a plant by its lidar returns' };
/** Where a shrub comes from, as on its card and tooltip. */
export const SHRUB_SOURCE = 'USGS 3DEP lidar · USDA NAIP';
/** The shrubs' credit: their inputs, and the crop cover's Sentinel-2 (docs/19 §19.8). */
export const SHRUB_CREDIT = 'USGS 3DEP lidar, USDA NAIP, USDA NASS CSB and CDL (the crop cover reads Sentinel-2: contains modified Copernicus Sentinel data 2025)';
const FOUND = 'found in the lidar';

/** What a click on the shrub selects. */
export function shrubSelection(s: ShrubRow): Selection {
	return {
		kind: 'shrub',
		id: s.id,
		layer: 'trees',
		title: LOOK_NAME[s.look],
		fact: `${fmtM(s.h)} tall · ${FOUND}`,
		source: SHRUB_SOURCE,
		at: [s.lng, s.lat],
		data: s
	};
}

/** The shrub as a scene instance: its look's model, scaled [w/2, w/2, h], in its look's color. */
export function shrubInstance(s: ShrubRow, pick: Selection | null = shrubSelection(s)): SceneInstance {
	return {
		id: `${SHRUB_PREFIX}${s.id}`,
		mesh: MESH_OF_LOOK[s.look],
		lng: s.lng,
		lat: s.lat,
		scale: [s.w / 2, s.w / 2, s.h],
		color: SHRUB_COLORS[s.look],
		shadow: true,
		pick,
		pickRadius: s.w / 2,
		grounded: true
	};
}

/** The card's lines: what the shrub is, and how we know (the width is a model's, not a measurement). */
export function shrubHowWeKnow(s: Pick<ShrubRow, 'look'>): string[] {
	return [
		`Its height is measured by the lidar: a plant 0.3 to 2.4 m tall, ${FOUND}.`,
		`${LOOK_NAME[s.look]}: ${LOOK_ABOUT[s.look]}.`,
		`Its width is not measured: it follows the width that ${s.look === 'bush' ? 'bushes' : 'sages'} of its height had in the test areas.`
	];
}

// --- fetching ----------------------------------------------------------------------------------------

/** The centre snaps to a grid of this many degrees (about 100 m), so small pans ask for the same URL. */
export const CENTRE_SNAP_DEG = 0.001;
const r6 = (x: number) => Math.round(x * 1e6) / 1e6;
const snap = (x: number, g: number) => r6(Math.round(x / g) * g);

/**
 * The box and the centre to ask for: the view's centre snapped, and the box SHRUB_RADIUS_M around it (snapped out to
 * the trees' grid). The same URL for small pans.
 */
export function shrubsWanted(centre: [number, number]): { box: Box; centre: [number, number] } {
	const c: [number, number] = [snap(centre[0], CENTRE_SNAP_DEG), snap(centre[1], CENTRE_SNAP_DEG)];
	const kx = SHRUB_RADIUS_M / (111_320 * Math.cos((c[1] * Math.PI) / 180));
	const ky = SHRUB_RADIUS_M / 110_574;
	const down = (x: number) => r6(Math.floor(x / SNAP_DEG) * SNAP_DEG);
	const up = (x: number) => r6(Math.ceil(x / SNAP_DEG) * SNAP_DEG);
	return { box: [down(c[0] - kx), down(c[1] - ky), up(c[0] + kx), up(c[1] + ky)], centre: c };
}

export const shrubsUrl = (box: Box, centre: [number, number], limit = SHRUB_LIMIT) =>
	`/api/trees/shrubs?bbox=${box.join(',')}&center=${centre.join(',')}&limit=${limit}`;

/** Whether a shrub is in a box (the scene gets those in view). */
export const shrubInBox = (b: Box, s: Pick<ShrubRow, 'lng' | 'lat'>) => inBox(b, s.lng, s.lat);

/** Where shrubs are built, in words (the legend). */
export function shrubsBuiltText(areas: readonly ShrubArea[], name: (area: string) => string): string {
	if (!areas.length) return 'No shrubs are built yet.';
	const names = areas.map((a) => name(a.area));
	const list = names.length <= 1 ? (names[0] ?? '') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`;
	return `Shrubs are built for ${list} so far.`;
}
