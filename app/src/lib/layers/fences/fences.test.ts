import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import { describe, expect, it } from 'vitest';
import { PRIORITY } from '../types.js';
import def from './def.js';
import { WALL } from './icons.js';
import {
	buildSegments,
	colorOf,
	creditOf,
	fenceLayers,
	fenceSelection,
	linesUrl,
	lengthText,
	materialText,
	metresFeet,
	ORDER,
	segmentsOf,
	shiftedLeft,
	THICKNESS,
	LINE_FROM_ZOOM,
	SOURCE,
	type FenceFeature,
	type FenceProps
} from './fences.js';
import { ESTIMATED, POST } from './palette.js';

/** A made-up fence from (lng, lat) running east in `n` hops of about 10 m. */
function fence(id: string, over: Partial<FenceProps> = {}, at: [number, number] = [-116.2, 43.6], n = 3): FenceFeature {
	const step = 10 / (111_320 * Math.cos((at[1] * Math.PI) / 180));
	return {
		type: 'Feature',
		id,
		geometry: { type: 'LineString', coordinates: Array.from({ length: n + 1 }, (_, i) => [at[0] + i * step, at[1]]) },
		properties: { id, type: 'fence', look: 'open', h: 1.8, hs: 'tagged', m: null, ft: null, len: 30, name: null, ...over }
	};
}

describe('the data URL', () => {
	it('carries the layer version when /api/meta has one', () => {
		const meta = { versions: { layers: { 'fences.lines': '20261022T1200Z-abc123' } } } as never;
		expect(linesUrl(meta)).toBe('/api/fences/lines?v=20261022T1200Z-abc123');
		expect(linesUrl(null)).toBe('/api/fences/lines');
		expect(linesUrl({ versions: { layers: {} } } as never)).toBe('/api/fences/lines');
	});

	it("credits OpenStreetMap, the build's own credit when it has one", () => {
		expect(creditOf(null)).toBe('© OpenStreetMap contributors');
		expect(creditOf({ layers: { 'fences.lines': { credit: '© OpenStreetMap contributors' } } } as never)).toBe('© OpenStreetMap contributors');
	});
});

describe('the always-loaded def', () => {
	it('imports only what the initial bundle already holds: not fences.ts, the palette or the scene (a layer loads lazily)', () => {
		const src = readFileSync(join(__dirname, 'def.ts'), 'utf8');
		const imports = [...src.matchAll(/^import (?!type\b)[^;]*from '([^']+)'/gm)].map((m) => m[1]);
		expect(imports.sort()).toEqual(['#lib/contracts/layer-tiles.js', '../prefetch.js']);
	});

	it("is not imported by the layer's module or its helpers, and imports neither (so it is part of the registry's chunk, not one of its own)", () => {
		for (const f of ['fences.ts', 'index.svelte.ts', 'palette.ts', 'icons.ts']) {
			const src = readFileSync(join(__dirname, f), 'utf8');
			expect(src, f).not.toMatch(/from '\.\/def(\.js)?'/);
		}
		expect(readFileSync(join(__dirname, 'def.ts'), 'utf8')).not.toMatch(/from '\.\/(fences|index\.svelte)(\.js)?'/);
	});

	it('says the same place in the stack as the module', () => {
		expect(def.order).toBe(ORDER);
	});

	it('prefetches exactly the URL the module takes', async () => {
		const meta = { versions: { layers: { 'fences.lines': 'v7' } } } as never;
		const seen: string[] = [];
		const real = globalThis.fetch;
		globalThis.fetch = ((u: string) => (seen.push(u), Promise.resolve(new Response('{}')))) as never;
		try {
			def.prefetch!({ meta } as never);
		} finally {
			globalThis.fetch = real;
		}
		expect(seen).toEqual([linesUrl(meta)]);
	});
});

describe('the segments', () => {
	it('makes one segment per hop, carrying the fence, with the type, height and look', () => {
		const pick = fenceSelection(fence('osm:w1').properties);
		const segs = segmentsOf(fence('osm:w1'), pick);
		expect(segs).toHaveLength(3);
		expect(segs.map((s) => s.id)).toEqual(['osm:w1:0', 'osm:w1:1', 'osm:w1:2']);
		for (const s of segs) {
			expect(s).toMatchObject({ height: 1.8, thickness: THICKNESS.fence, look: 'open', color: POST });
			expect(s.pick).toBe(pick);
		}
		// Consecutive segments join end to end.
		expect(segs[0].to).toEqual(segs[1].from);
	});

	it('draws walls thick and solid, and mixes an estimated height 25% toward cream', () => {
		const wall = segmentsOf(fence('osm:w2', { type: 'wall', look: 'solid', h: 2.4, hs: 'default' }), null);
		expect(wall[0]).toMatchObject({ thickness: 0.3, look: 'solid', height: 2.4, color: ESTIMATED, pick: null });
		expect(colorOf('tagged')).toBe(POST);
		expect(colorOf('default')).toBe(ESTIMATED);
	});

	it('stands a retaining wall to the left of the line, so its right (low) face is on the line', () => {
		// Heading east: left is north.
		const s = segmentsOf(fence('osm:w3', { type: 'retaining_wall', look: 'solid' }), null)[0];
		expect(s.from[1]).toBeGreaterThan(43.6);
		expect(s.to[1]).toBeGreaterThan(43.6);
		const north = (s.from[1] - 43.6) * 111_195;
		expect(north).toBeCloseTo(THICKNESS.retaining_wall / 2, 2);
		// A plain fence stays on its line.
		expect(segmentsOf(fence('osm:w4'), null)[0].from[1]).toBe(43.6);
		// Heading north: left is west.
		const w = shiftedLeft([-116.2, 43.6], [-116.2, 43.601], 0.5);
		expect(w.from[0]).toBeLessThan(-116.2);
		expect(w.from[1]).toBe(43.6);
	});

	it('keeps the segments within the radius of the view, the nearest ones first when over the cap', () => {
		const near = fence('osm:w5', {}, [-116.2, 43.6], 3);
		const far = fence('osm:w6', {}, [-116.2, 43.7], 3);
		const all = buildSegments([near, far], [-116.2, 43.6], () => null, 1500, 100);
		expect(all.map((s) => s.id)).toEqual(['osm:w5:0', 'osm:w5:1', 'osm:w5:2']);
		const many = fence('osm:w7', {}, [-116.2, 43.6], 40);
		const capped = buildSegments([many], [-116.2, 43.6], () => null, 1500, 5);
		expect(capped).toHaveLength(5);
		// The nearest to the centre, which is the line's start.
		expect(capped.map((s) => s.id).sort()).toEqual(['osm:w7:0', 'osm:w7:1', 'osm:w7:2', 'osm:w7:3', 'osm:w7:4']);
	});

	it('builds none for a cap of 0 (a phone)', () => {
		expect(buildSegments([fence('osm:w8')], [-116.2, 43.6], () => null, 1500, 0)).toEqual([]);
	});

	it('asks for each fence’s selection once per segment list, so a hover tints it whole', () => {
		const f = fence('osm:w9');
		const picks = new Map<string, ReturnType<typeof fenceSelection>>();
		const all = buildSegments([f], [-116.2, 43.6], (x) => picks.get(x.properties.id) ?? picks.set(x.properties.id, fenceSelection(x.properties)).get(x.properties.id)!);
		expect(new Set(all.map((s) => s.pick)).size).toBe(1);
	});
});

describe('the selection and its words', () => {
	it('selects a fence at the fence priority, with its source', () => {
		const s = fenceSelection(fence('osm:w10', { type: 'retaining_wall', look: 'solid', h: 1.5, hs: 'default' }).properties, [-116.2, 43.6]);
		expect(s).toMatchObject({ kind: 'fence', layer: 'fences', title: 'Retaining wall', source: 'OpenStreetMap', at: [-116.2, 43.6] });
		expect(s.fact).toBe('solid · about 1.5 m (5 ft)');
		expect(PRIORITY.fence).toBe(33);
	});

	it('names the fence when a contributor did, and says a tagged height plainly', () => {
		const s = fenceSelection(fence('osm:w11', { name: 'Garden wall', type: 'wall' }).properties);
		expect(s.title).toBe('Wall: Garden wall');
		expect(s.fact).toBe('see-through · 1.8 m (6 ft)');
	});

	it('writes sizes and materials', () => {
		expect(metresFeet(1.8)).toBe('1.8 m (6 ft)');
		expect(metresFeet(12.4)).toBe('12 m (41 ft)');
		expect(lengthText(250)).toBe('250 m (820 ft)');
		expect(lengthText(2400)).toBe('2.4 km (1.5 mi)');
		expect(materialText({ m: null, ft: null })).toBeNull();
		expect(materialText({ m: 'wood', ft: null })).toBe('wood');
		expect(materialText({ m: null, ft: 'chain_link' })).toBe('chain link');
		expect(materialText({ m: 'metal', ft: 'chain_link' })).toBe('metal (chain link)');
	});
});

describe('the 2D line', () => {
	const layers = fenceLayers();

	it('sits in land, shows from z14.5 at every zoom after, and has a halo under the line and ticks over it', () => {
		expect(layers.map((l) => l.layer.id)).toEqual(['fences-halo', 'fences-line', 'fences-posts']);
		for (const l of layers) {
			expect(l.slot).toBe('land');
			expect(l.layer.type).toBe('line');
			expect(l.layer.minzoom).toBe(LINE_FROM_ZOOM);
			expect(l.layer.maxzoom).toBeUndefined();
		}
		const halo = layers[0].layer as { paint: Record<string, unknown> };
		expect(halo.paint['line-color']).toBe('#FFFBF4');
		// A pixel each side of the line.
		// Widths are a zoom expression at the top level (MapLibre refuses it anywhere else), 2 px wider than the line.
		const w = (l: unknown) => (l as { paint: Record<string, unknown[]> }).paint['line-width'];
		expect(w(halo)[0]).toBe('interpolate');
		expect(w(halo)[2]).toEqual(['zoom']);
		const style = { version: 8, sources: { [SOURCE]: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } }, layers: layers.map((l) => l.layer) };
		expect(validateStyleMin(style as never)).toEqual([]);
		expect((layers[1].layer as { paint: Record<string, unknown> }).paint['line-color']).toEqual(['case', ['boolean', ['feature-state', 'hover'], false], '#2b2a33', POST]);
		expect((layers[2].layer as { paint: Record<string, unknown> }).paint['line-dasharray']).toBeTruthy();
	});
});

describe('the icon', () => {
	it('is Phosphor’s Wall, duotone, exactly as phosphor-svelte ships it', () => {
		const require = createRequire(import.meta.url);
		const dir = dirname(require.resolve('phosphor-svelte/package.json'));
		const src = readFileSync(join(dir, 'lib', `${WALL.name}Icon.svelte`), 'utf8');
		const branch = /weight === "duotone"\}\s*([\s\S]*?)\{:else/.exec(src)?.[1] ?? '';
		const paths = [...branch.matchAll(/<path d="([^"]+)"([^>]*)\/>/g)];
		expect(WALL.tone).toBe(paths.find((p) => p[2].includes('opacity="0.2"'))?.[1]);
		expect(WALL.line).toBe(paths.find((p) => !p[2].includes('opacity'))?.[1]);
	});
});
