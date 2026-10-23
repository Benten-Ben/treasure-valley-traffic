import type { MapGeoJSONFeature } from 'maplibre-gl';
import type { DataMeta } from '#lib/contracts/meta.js';
import { layerCredit, layerVersion } from '#lib/contracts/layer-tiles.js';
import { INK } from '#lib/map/color.js';
import type { SlottedLayer } from '#lib/map/order.js';
import type { StaticSegment } from '#lib/scene/batches/static.js';
import { PRIORITY, type Selection } from '../types.js';
import { ESTIMATED, HALO, POST } from './palette.js';

/**
 * The Fences layer's pure parts (plan §4.2 P10): the style of the 2D line, the 3D segments built from the same
 * features, and the words the card and legend use. Only what contributors have mapped in OpenStreetMap is here: most
 * backyard fences aren't mapped yet, and a mapped fence never says where anyone's land ends.
 */

export const URL_PATH = '/api/fences/lines';
export const SOURCE = 'fences-lines';
/** The scene group of the 3D batch. */
export const GROUP = 'fences';
export const HALO_LAYER = 'fences-halo';
export const LINE_LAYER = 'fences-line';
export const POSTS_LAYER = 'fences-posts';
export const LAYER_IDS = [HALO_LAYER, LINE_LAYER, POSTS_LAYER] as const;
/** The 2D line shows from here in (plan §3.5). */
export const LINE_FROM_ZOOM = 14.5;
/** The low 3D walls from here in. */
export const WALLS_FROM_ZOOM = 15.5;
/** The scene is asked for a little before the walls show. */
export const SCENE_FROM_ZOOM = 15.2;
export const FALLBACK_CREDIT = '© OpenStreetMap contributors';

/** The data's URL, with the version /api/meta reports when it has one (immutable then). */
export function linesUrl(meta: Pick<DataMeta, 'versions'> | null | undefined): string {
	const v = layerVersion(meta, 'fences', 'lines');
	return v ? `${URL_PATH}?v=${encodeURIComponent(v)}` : URL_PATH;
}

/** The credit the map shows while the layer is on. */
export function creditOf(meta: Pick<DataMeta, 'layers'> | null | undefined): string {
	return layerCredit(meta, 'fences', 'lines') ?? FALLBACK_CREDIT;
}

// -- the data ---------------------------------------------------------------------------------------

export type FenceType = 'fence' | 'wall' | 'retaining_wall' | 'guard_rail' | 'jersey_barrier' | 'other';

/** What each feature of the API carries (`#lib/server/fences/lines`). */
export interface FenceProps {
	id: string;
	type: FenceType;
	look: 'solid' | 'open';
	/** Metres. */
	h: number;
	/** `tagged`: in OpenStreetMap; `default`: estimated by type. */
	hs: 'tagged' | 'default';
	m: string | null;
	ft: string | null;
	len: number;
	name: string | null;
}

export type FenceFeature = GeoJSON.Feature<GeoJSON.LineString, FenceProps>;
export type FenceCollection = GeoJSON.FeatureCollection<GeoJSON.LineString, FenceProps>;

// -- words ------------------------------------------------------------------------------------------

export const TYPE_NAME: Record<FenceType, string> = {
	fence: 'Fence',
	wall: 'Wall',
	retaining_wall: 'Retaining wall',
	guard_rail: 'Guard rail',
	jersey_barrier: 'Jersey barrier',
	other: 'Barrier'
};

export const lookWord = (look: 'solid' | 'open') => (look === 'open' ? 'See-through' : 'Solid');

const FT = 3.28084;
/** "1.8 m (6 ft)". */
export function metresFeet(m: number): string {
	const metres = m < 10 ? Math.round(m * 10) / 10 : Math.round(m);
	return `${metres} m (${Math.round(m * FT)} ft)`;
}

/** A length: metres under a kilometre, kilometres above. */
export function lengthText(m: number): string {
	return m >= 1000 ? `${(m / 1000).toFixed(1)} km (${(m / 1609.344).toFixed(1)} mi)` : `${Math.round(m)} m (${Math.round(m * FT)} ft)`;
}

/** Tags as the words a person says: `chain_link` → "chain link". */
export function tagWords(v: string | null | undefined): string | null {
	if (!v) return null;
	return v.replace(/[_;]+/g, ' ').trim() || null;
}

/** The material, from the material tag or else the fence type tag, as tagged. */
export function materialText(p: Pick<FenceProps, 'm' | 'ft'>): string | null {
	const m = tagWords(p.m);
	const ft = tagWords(p.ft);
	if (m && ft && m !== ft) return `${m} (${ft})`;
	return m ?? ft;
}

/** How we know the height, in words. */
export function heightNote(hs: FenceProps['hs']): string {
	return hs === 'tagged' ? 'tagged in OpenStreetMap' : 'estimated from its type';
}

export const MAPPED_NOTE = 'mapped (OpenStreetMap)';
export const NOT_MAPPED_NOTE = "Mapped in OpenStreetMap; most backyard fences aren't mapped yet";

export function fenceSelection(p: FenceProps, at?: [number, number]): Selection {
	return {
		kind: 'fence',
		id: p.id,
		layer: 'fences',
		title: p.name ? `${TYPE_NAME[p.type]}: ${p.name}` : TYPE_NAME[p.type],
		fact: `${lookWord(p.look).toLowerCase()} · ${heightFact(p)}`,
		source: 'OpenStreetMap',
		...(at ? { at } : {}),
		data: p
	};
}

function heightFact(p: FenceProps): string {
	return `${p.hs === 'tagged' ? '' : 'about '}${metresFeet(p.h)}`;
}

// -- the 2D line ------------------------------------------------------------------------------------

/**
 * The 2D line, in `land` (draped): a 1 px cream halo under the line in the post tone, and post ticks on fences and
 * guard rails (a short dash across the line every few pixels; walls and barriers get none). A solid fence's line is a
 * little heavier than a see-through one's, so the two read apart without color.
 */
export function fenceLayers(): SlottedLayer[] {
	const hover = ['boolean', ['feature-state', 'hover'], false];
	const width = (a: number, b: number) => ['interpolate', ['linear'], ['zoom'], LINE_FROM_ZOOM, a, 19, b];
	const solid = ['==', ['get', 'look'], 'solid'];
	// A zoom expression must be the top level, so the data-driven look sits inside the stops.
	const stops = (z0: [number, number], z1: [number, number], extra = 0) => [
		'interpolate',
		['linear'],
		['zoom'],
		LINE_FROM_ZOOM,
		['case', solid, z0[0] + extra, z0[1] + extra],
		19,
		['case', solid, z1[0] + extra, z1[1] + extra]
	];
	const lineWidth = stops([1.5, 1], [3, 2]);
	return [
		{
			slot: 'land',
			layer: {
				id: HALO_LAYER,
				type: 'line',
				source: SOURCE,
				minzoom: LINE_FROM_ZOOM,
				layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' },
				paint: {
					'line-color': HALO,
					'line-opacity': 0.9,
					// 1 px each side of the line.
					'line-width': stops([1.5, 1], [3, 2], 2) as never
				}
			}
		},
		{
			slot: 'land',
			layer: {
				id: LINE_LAYER,
				type: 'line',
				source: SOURCE,
				minzoom: LINE_FROM_ZOOM,
				layout: { visibility: 'none', 'line-cap': 'butt', 'line-join': 'round' },
				paint: {
					'line-color': ['case', hover, INK, POST] as never,
					'line-width': lineWidth as never
				}
			}
		},
		{
			slot: 'land',
			layer: {
				id: POSTS_LAYER,
				type: 'line',
				source: SOURCE,
				minzoom: LINE_FROM_ZOOM,
				filter: ['in', ['get', 'type'], ['literal', ['fence', 'guard_rail']]],
				layout: { visibility: 'none', 'line-cap': 'butt' },
				paint: {
					'line-color': ['case', hover, INK, POST] as never,
					'line-width': width(4, 7) as never,
					// A tick 1/4 of the width long, every 4 widths: about every 16 px at z14.5.
					'line-dasharray': [0.25, 3.75]
				}
			}
		}
	];
}

/** The picked fence of a MapLibre feature (its properties are flat). */
export function propsOf(f: MapGeoJSONFeature): FenceProps | null {
	const p = f.properties as Partial<FenceProps> | null;
	if (!p?.id || !p.type || !(p.h! > 0)) return null;
	return {
		id: String(p.id),
		type: p.type,
		look: p.look === 'open' ? 'open' : 'solid',
		h: Number(p.h),
		hs: p.hs === 'tagged' ? 'tagged' : 'default',
		m: p.m ?? null,
		ft: p.ft ?? null,
		len: Number(p.len ?? 0),
		name: p.name ?? null
	};
}

// -- the 3D segments --------------------------------------------------------------------------------

/** Metres across: fences and guard rails 0.15 and 0.2, walls and retaining walls 0.3, a jersey barrier 0.4. */
export const THICKNESS: Record<FenceType, number> = { fence: 0.15, wall: 0.3, retaining_wall: 0.3, guard_rail: 0.2, jersey_barrier: 0.4, other: 0.15 };
/** The 3D batch's reach: segments within this many metres of the view's centre. */
export const RADIUS_M = 1500;
/** The most segments in the batch (about ten boxes each when see-through, so a few thousand at most; plan §4.2 S7). */
export const SEGMENT_CAP = 3000;
export const M_PER_DEG = (6371008.8 * Math.PI) / 180;
const DEG = Math.PI / 180;

/** The color of a 3D fence: the post tone, or the estimated tone for a height we estimated. */
export const colorOf = (hs: FenceProps['hs']) => (hs === 'tagged' ? POST : ESTIMATED);

/**
 * A wall that holds earth back, drawn so its face looks to its low side. OpenStreetMap draws a retaining wall with the
 * lower ground on the right of the line's direction (as a cliff), so the box stands half its thickness to the left of
 * the line, which puts its right face on the mapped line. (⚠️ a reading of the tag convention, not a survey.)
 */
export function shiftedLeft(from: [number, number], to: [number, number], metres: number): { from: [number, number]; to: [number, number] } {
	const cos = Math.cos(((from[1] + to[1]) / 2) * DEG);
	const dx = (to[0] - from[0]) * cos * M_PER_DEG;
	const dy = (to[1] - from[1]) * M_PER_DEG;
	const len = Math.hypot(dx, dy);
	if (len < 1e-9) return { from, to };
	// The left-hand normal, in metres, as degrees.
	const lx = (-dy / len) * metres;
	const ly = (dx / len) * metres;
	const dLng = lx / (M_PER_DEG * cos);
	const dLat = ly / M_PER_DEG;
	return { from: [from[0] + dLng, from[1] + dLat], to: [to[0] + dLng, to[1] + dLat] };
}

/** The 3D segments of one fence, between its vertices, with the fence's selection. */
export function segmentsOf(f: FenceFeature, pick: Selection | null): StaticSegment[] {
	const p = f.properties;
	const th = THICKNESS[p.type];
	const color = colorOf(p.hs);
	const out: StaticSegment[] = [];
	const c = f.geometry.coordinates;
	for (let i = 0; i + 1 < c.length; i++) {
		let from = c[i] as [number, number];
		let to = c[i + 1] as [number, number];
		if (p.type === 'retaining_wall') ({ from, to } = shiftedLeft(from, to, th / 2));
		out.push({ id: `${p.id}:${i}`, from, to, height: p.h, thickness: th, look: p.look, color, pick });
	}
	return out;
}

const dist2 = (lng: number, lat: number, cLng: number, cLat: number, kx: number) => {
	const dx = (lng - cLng) * kx;
	const dy = (lat - cLat) * M_PER_DEG;
	return dx * dx + dy * dy;
};

/**
 * The 3D batch for a view: every segment whose middle is within `radiusM` of `centre`, the nearest `cap` of them
 * (`cap` 0, as on a phone, builds none). `pickOf` gives each fence's selection (one per fence, so a hover tints it whole).
 */
export function buildSegments(
	features: readonly FenceFeature[],
	centre: [number, number],
	pickOf: (f: FenceFeature) => Selection | null,
	radiusM = RADIUS_M,
	cap = SEGMENT_CAP
): StaticSegment[] {
	if (cap <= 0) return [];
	const kx = M_PER_DEG * Math.cos(centre[1] * DEG);
	const r2 = radiusM * radiusM;
	const kept: { d: number; seg: StaticSegment }[] = [];
	// A fence with no vertex within the radius (and a margin for a long segment between two) has nothing near it.
	const reach2 = (radiusM + 300) ** 2;
	for (const f of features) {
		if (!f.geometry.coordinates.some((v) => dist2(v[0], v[1], centre[0], centre[1], kx) <= reach2)) continue;
		for (const s of segmentsOf(f, pickOf(f))) {
			const d = dist2((s.from[0] + s.to[0]) / 2, (s.from[1] + s.to[1]) / 2, centre[0], centre[1], kx);
			if (d <= r2) kept.push({ d, seg: s });
		}
	}
	if (kept.length > cap) kept.sort((a, b) => a.d - b.d).length = cap;
	return kept.map((k) => k.seg);
}
