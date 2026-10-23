import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { createPropertyExpression, latest, validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import { ANCHORS, DRAPED_TYPES, insertSlotted } from '#lib/map/order.js';
import { INK } from '#lib/map/materials.js';
import type { AgencyState, TrailStatus } from '#lib/server/trails/status.js';
import { PRIORITY } from '../types.js';
import def from './def.js';
import { TRAILS } from './icons.js';
import {
	agencyLayer,
	CREAM,
	DASHED,
	DETAIL_ZOOM,
	HIT_AGENCY,
	HIT_WAYS,
	ICON_IDS,
	INFORMAL_WORDS,
	kindWord,
	L,
	LOOKS,
	CREDIT_BOTH,
	lineSelection,
	lineSev,
	lineWidth,
	markLayer,
	metresFeet,
	pavedSelection,
	planStatus,
	SEVERITY_ORDER,
	selectedFilter,
	selectedIds,
	SL,
	SRC,
	stateEntries,
	stateKey,
	stateWord,
	surfaceText,
	TRAIL_LAYER_IDS,
	trailLayers,
	UMBER,
	waySelection,
	wayLayer,
	widthText,
	worstSev,
	countsText,
	type Sev,
	type Statuses
} from './trails.js';

/**
 * The Trails layer as data (trails.ts): its style layers (valid, in their slots, no ink casing), the status
 * as feature-state (and the plan from one status to the next), the words, and the selections. Made-up ways,
 * lines and ids throughout; nothing here is real data.
 */

const status = (o: Partial<Statuses> = {}): Statuses => ({ way: () => null, line: () => null, ...o });

const agency = (o: Partial<AgencyState>): AgencyState => ({
	source: 'r2r_trails',
	id: 'x',
	kind: 'trail',
	name: 'Example Ridge',
	system: 'Ridge to Rivers',
	state: 'dry',
	severity: 'open',
	label: 'Dry / Tacky',
	set_at: null,
	since: null,
	ways: [],
	partial: [],
	line_id: 1,
	drawn: false,
	gap_m: 0,
	along_m: 0,
	covered: null,
	...o
});

describe('the icon', () => {
	it('is Phosphor’s PersonSimpleHike duotone, exactly as phosphor-svelte ships it', () => {
		const require = createRequire(import.meta.url);
		const dir = dirname(require.resolve('phosphor-svelte/package.json'));
		const src = readFileSync(join(dir, 'lib', 'PersonSimpleHikeIcon.svelte'), 'utf8');
		const branch = /weight === "duotone"\}\s*([\s\S]*?)\{:else/.exec(src)?.[1] ?? '';
		const paths = [...branch.matchAll(/<path d="([^"]+)"([^>]*)\/>/g)];
		expect(TRAILS.tone).toBe(paths.find((p) => p[2].includes('opacity="0.2"'))![1]);
		expect(TRAILS.line).toBe(paths.find((p) => !p[2].includes('opacity'))![1]);
	});
});

describe('the layer def', () => {
	it('is Trails in the Landscape tray, hiding Protomaps’ footpaths while it is on', () => {
		expect(def).toMatchObject({ id: 'trails', title: 'Trails', group: 'landscape', suppresses: ['paths'] });
		// Fields, Soils and Trails switch Auto to Clay (plan §3.6): Trails does not keep Valley.
		expect(def.keepsValley).toBeFalsy();
	});

	it('is offered while the database is up and the trails tiles have a build', () => {
		const meta = (layers: Record<string, string>, database = 'ok') => ({ database, versions: { layers } }) as never;
		expect(def.available(null)).toBe(true);
		expect(def.available(meta({ 'trails.paths': 'v1' }))).toBe(true);
		expect(def.available(meta({}))).toBe('No trails built yet');
		expect(def.available(meta({}, 'down'))).toBe(true);
	});

	it('picks at the trail priority, over the trees and under the streets (plan §3.3)', () => {
		expect(PRIORITY.trail).toBe(38);
		expect(PRIORITY.trail).toBeLessThan(PRIORITY.street);
		expect(PRIORITY.trail).toBeGreaterThan(PRIORITY.tree);
	});
});

describe('the style layers', () => {
	const all = trailLayers();

	it('are valid MapLibre layers: expressions, sources, source-layers, zoom-only interpolations', () => {
		const sources = Object.fromEntries(Object.values(SRC).map((id) => [id, { type: 'vector', tiles: ['https://example.com/{z}/{x}/{y}'] }]));
		const errors = validateStyleMin({ version: 8, glyphs: 'https://example.com/{fontstack}/{range}.pbf', sources, layers: all.map((l) => l.layer) } as never);
		expect(errors.map((e: { message: string }) => e.message)).toEqual([]);
	});

	it('have unique ids, all beginning "trails-", all hidden to start with', () => {
		const ids = all.map((l) => l.layer.id);
		expect(new Set(ids).size).toBe(ids.length);
		expect(ids).toEqual([...TRAIL_LAYER_IDS]);
		for (const l of all) {
			expect(l.layer.id).toMatch(/^trails-/);
			expect((l.layer.layout as { visibility?: string }).visibility).toBe('none');
		}
	});

	it('put the lines in land, the icons in points and the names in labels: no symbol below the routes anchor', () => {
		for (const { slot, layer } of all) {
			if (layer.type === 'symbol') expect(['points', 'labels'], layer.id).toContain(slot);
			else expect(slot, layer.id).toBe('land');
			if (DRAPED_TYPES.has(layer.type)) expect(slot).toBe('land');
		}
		expect(all.filter((l) => l.slot === 'points').map((l) => l.layer.id)).toEqual(DASHED.map(markLayer));
		expect(all.filter((l) => l.slot === 'labels').map((l) => l.layer.id)).toEqual([L.routeNames, L.names, L.informalWords]);
	});

	it('keep the draped run single: every line sits between the ground and the routes anchor', () => {
		const style = ['ground', 'areas', 'water', 'surfaces', 'base', 'land', 'streets', 'lanes', 'footprints', 'routes', 'scene', 'points', 'labels', 'overlay'].map((s) => ({
			id: ANCHORS[s as keyof typeof ANCHORS],
			type: 'background',
			layout: { visibility: 'none' }
		}));
		const out = insertSlotted(style as never, all, 30);
		const order = out.map((l) => l.id);
		for (const { slot, layer } of all) {
			if (slot === 'land') {
				expect(order.indexOf(layer.id)).toBeGreaterThan(order.indexOf(ANCHORS.base));
				expect(order.indexOf(layer.id)).toBeLessThan(order.indexOf(ANCHORS.land));
			}
		}
	});

	it('read the three tile sets: ways and the hit line from paths, the routes’ wash from routes, the agencies from agency and marks', () => {
		const by = (id: string) => all.find((l) => l.layer.id === id)!.layer as { source: string; 'source-layer': string };
		expect(by(L.ways)).toMatchObject({ source: SRC.paths, 'source-layer': SL.paths });
		expect(by(L.routes)).toMatchObject({ source: SRC.routes, 'source-layer': SL.routes });
		expect(by(agencyLayer('closed'))).toMatchObject({ source: SRC.agency, 'source-layer': SL.agency });
		for (const sev of DASHED) expect(by(markLayer(sev))).toMatchObject({ source: SRC.agency, 'source-layer': SL.marks });
		expect(HIT_WAYS.map(by).every((l) => l.source === SRC.paths)).toBe(true);
		expect(HIT_AGENCY.map(by).every((l) => l.source === SRC.agency)).toBe(true);
	});

	it('draw ways from z10 and give each state its own layer from z13, the informal ways from z16', () => {
		const get = (id: string) => all.find((l) => l.layer.id === id)!.layer;
		expect(get(L.ways).minzoom).toBe(10);
		for (const sev of DASHED) expect(get(wayLayer(sev)).minzoom, sev).toBe(DETAIL_ZOOM);
		for (const sev of DASHED) expect(get(agencyLayer(sev)).minzoom, sev).toBe(10);
		expect(get(L.informal).minzoom).toBe(16);
		expect(get(L.informalWords).minzoom).toBe(16);
	});

	it('draw the plain ways whatever their state below z13, where only the agencies’ lines carry one', () => {
		const paint = (all.find((l) => l.layer.id === L.ways)!.layer as { paint: Record<string, unknown> }).paint;
		const opacity = paint['line-opacity'] as unknown[];
		expect(opacity.slice(0, 5)).toEqual(['step', ['zoom'], 1, DETAIL_ZOOM, expect.anything()]);
	});

	it('draw one plain umber agency line where no state is known (a failed or late status), not a bare halo', () => {
		const ref = latest as unknown as Record<string, Record<string, unknown>> & { default?: Record<string, Record<string, unknown>> };
		const spec = (ref.paint_line ?? ref.default!.paint_line)['line-opacity'];
		const opacityOf = (id: string, zoom: number, state: Record<string, unknown>, properties: Record<string, unknown> = { kind: 'trail' }): number => {
			const layer = all.find((l) => l.layer.id === id)!.layer as { paint: Record<string, unknown> };
			const parsed = createPropertyExpression(layer.paint['line-opacity'] as never, 'line-opacity', spec as never);
			if (parsed.result !== 'success') throw new Error(JSON.stringify(parsed.value));
			return parsed.value.evaluate({ zoom }, { type: 'LineString', properties } as never, state) as number;
		};
		const agencyIds = [agencyLayer('open'), agencyLayer('not_evaluated'), ...DASHED.map(agencyLayer)];
		for (const zoom of [10, 12, 14]) {
			// No feature-state: the halo is there, so exactly one umber layer must be too (open).
			expect(opacityOf(L.haloAgency, zoom, {})).toBeGreaterThan(0);
			expect(agencyIds.filter((id) => opacityOf(id, zoom, {}) > 0), `z${zoom}`).toEqual([agencyLayer('open')]);
			// Each known state still draws its own one layer; an ended row draws nothing, halo included.
			for (const sev of ['open', 'not_evaluated', ...DASHED]) expect(agencyIds.filter((id) => opacityOf(id, zoom, { sev }) > 0), `${sev} z${zoom}`).toEqual([agencyLayer(sev as Sev)]);
			expect(agencyIds.filter((id) => opacityOf(id, zoom, { sev: 'ended' }) > 0)).toEqual([]);
			expect(opacityOf(L.haloAgency, zoom, { sev: 'ended' })).toBe(0);
			// A closure or a detour with no state known draws nothing (no walkable-looking line, no halo): only a trail falls back to plain.
			for (const kind of ['closure', 'detour']) {
				expect(agencyIds.filter((id) => opacityOf(id, zoom, {}, { kind }) > 0), `${kind} z${zoom}`).toEqual([]);
				expect(opacityOf(L.haloAgency, zoom, {}, { kind })).toBe(0);
				expect(agencyIds.filter((id) => opacityOf(id, zoom, { sev: 'closed' }, { kind }) > 0)).toEqual([agencyLayer('closed')]);
			}
		}
	});

	it('give each state its own dash, and no two the same (K8: each dash has its word)', () => {
		const dashes = DASHED.map((sev) => JSON.stringify(LOOKS[sev].dash));
		expect(new Set(dashes).size).toBe(dashes.length);
		for (const sev of DASHED) {
			const l = all.find((x) => x.layer.id === wayLayer(sev))!.layer as { paint: Record<string, unknown> };
			expect(l.paint['line-dasharray']).toEqual(LOOKS[sev].dash);
			// A state's layer draws only where its feature-state is that state.
			expect(JSON.stringify(l.paint['line-opacity'])).toContain(`"${sev}"`);
		}
		// ...and none has the informal ways' dots.
		expect(dashes).not.toContain(JSON.stringify([0.1, 3.4]));
		for (const sev of DASHED) expect(LOOKS[sev].word.length).toBeGreaterThan(2);
	});

	it('never use red or green: one umber for every line', () => {
		const colors = new Set<string>();
		for (const { layer } of all) {
			const c = (layer.paint as Record<string, unknown> | undefined)?.['line-color'];
			if (typeof c === 'string') colors.add(c);
		}
		expect([...colors].sort()).toEqual([CREAM, UMBER].sort());
	});

	it('never draw an ink casing under a trail line (K7)', () => {
		const lines = all.filter((l) => l.layer.type === 'line');
		expect(lines.length).toBeGreaterThan(10);
		for (const { layer } of lines) {
			const paint = layer.paint as Record<string, unknown>;
			const color = paint['line-color'];
			expect(color, `${layer.id}'s color`).not.toBe(INK);
			expect(JSON.stringify(paint).toLowerCase(), layer.id).not.toContain(INK.toLowerCase());
			expect(layer.id, 'no layer is a casing').not.toMatch(/casing/);
			// The only layer under the umber lines is a cream halo, and the wash of the routes (umber itself).
			if (/halo/.test(layer.id)) expect(color, layer.id).toBe(CREAM);
		}
		// The text layers' halos are cream too.
		for (const { layer } of all.filter((l) => l.layer.type === 'symbol')) {
			const p = layer.paint as Record<string, unknown>;
			if (p['text-halo-color']) expect(p['text-halo-color']).toBe(CREAM);
		}
	});

	it('keep the umber legible: 7:1 or better against the cream of its halo', () => {
		const lum = (hex: string) => {
			const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
			return 0.2126 * r + 0.7152 * g + 0.0722 * b;
		};
		const ratio = (a: string, b: string) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);
		expect(ratio(UMBER, CREAM)).toBeGreaterThanOrEqual(7);
	});

	it('make the hit lines invisible and wide, so a thin trail can be clicked', () => {
		for (const id of [L.hitWays, L.hitAgency]) {
			const p = (all.find((l) => l.layer.id === id)!.layer as { paint: Record<string, unknown> }).paint;
			expect(p['line-opacity']).toBe(0);
			expect(p['line-width']).toBeGreaterThanOrEqual(12);
		}
	});

	it('name an image for every icon layer, and draw every image', () => {
		for (const sev of DASHED) {
			const l = all.find((x) => x.layer.id === markLayer(sev))!.layer as { layout: Record<string, unknown> };
			expect(ICON_IDS).toContain(l.layout['icon-image']);
			expect(l.layout['icon-image']).toBe(LOOKS[sev].icon);
		}
		expect(new Set(DASHED.map((s) => LOOKS[s].icon)).size).toBe(DASHED.length);
	});

	it('draw a state’s icon and arrowheads along the line, the arrowheads turning with it', () => {
		const get = (sev: (typeof DASHED)[number]) => (all.find((x) => x.layer.id === markLayer(sev))!.layer as { layout: Record<string, unknown> }).layout;
		expect(get('detour')['icon-rotation-alignment']).toBe('map');
		expect(get('closed')['icon-rotation-alignment']).toBe('viewport');
		expect(get('closed')['symbol-placement']).toBe('line');
		// The ✕ marks are the sign of a closure at valley zoom: from z10.
		expect((all.find((x) => x.layer.id === markLayer('closed'))!.layer as { minzoom: number }).minzoom).toBe(10);
	});

	it('draw the tread at its width in metres from z16 (a 3 m path is 3 m on the ground at z18)', () => {
		const e = lineWidth(1) as unknown as unknown[];
		expect(e.slice(0, 3)).toEqual(['interpolate', ['exponential', 2], ['zoom']]);
		expect(JSON.stringify(e)).toContain('width_m');
	});
});

describe('the status as feature-state', () => {
	const s = (o: Partial<Pick<TrailStatus, 'ways' | 'agencies' | 'hidden'>> = {}) => ({ ways: {}, agencies: [], hidden: [], ...o });

	it('puts each painted way’s state on the ways’ tiles', () => {
		expect(stateEntries(s({ ways: { '9500000001': 'closed', '9500000002': 'open' } }))).toEqual([
			{ source: SRC.paths, sourceLayer: 'paths', id: 9500000001, state: { sev: 'closed' } },
			{ source: SRC.paths, sourceLayer: 'paths', id: 9500000002, state: { sev: 'open' } }
		]);
	});

	it('puts each agency line’s state on its drawn parts and on its whole line, by line_id', () => {
		const got = stateEntries(s({ agencies: [agency({ line_id: 7, severity: 'closed', state: 'closed' })] }));
		expect(got).toEqual([
			{ source: SRC.agency, sourceLayer: 'agency', id: 7, state: { sev: 'closed' } },
			{ source: SRC.agency, sourceLayer: 'marks', id: 7, state: { sev: 'closed' } }
		]);
	});

	it('paints R2R’s unevaluated trails not_evaluated, and a row the City has ended draws nothing', () => {
		expect(lineSev({ source: 'r2r_trails', severity: null })).toBe('not_evaluated');
		expect(lineSev({ source: 'boise_greenbelt_closures', severity: null })).toBeNull();
		const got = stateEntries(s({ agencies: [agency({ line_id: 3, severity: null, state: 'unset' }), agency({ line_id: 4, source: 'boise_greenbelt_closures', kind: 'closure', severity: null, state: 'ended' })] }));
		expect(got.map((e) => [e.id, e.sourceLayer, e.state.sev])).toEqual([
			[3, 'agency', 'not_evaluated'],
			[3, 'marks', 'not_evaluated'],
			[4, 'agency', 'ended'],
			[4, 'marks', 'ended']
		]);
	});

	it('skips a line that has no id yet (before trails-match) and hides informal ways near a closure', () => {
		const got = stateEntries(s({ agencies: [agency({ line_id: null })], hidden: [9500000009] }));
		expect(got).toEqual([{ source: SRC.paths, sourceLayer: 'paths', id: 9500000009, state: { hide: true } }]);
	});

	it('keeps a way’s state and its hiding together (one feature, one entry)', () => {
		const got = stateEntries(s({ ways: { '5': 'caution' }, hidden: [5] }));
		expect(got).toEqual([{ source: SRC.paths, sourceLayer: 'paths', id: 5, state: { sev: 'caution', hide: true } }]);
	});

	it('plans only the change from one status to the next: set the new and changed, remove the dropped', () => {
		const first = stateEntries(s({ ways: { '1': 'open', '2': 'closed', '3': 'caution' } }));
		const applied = new Map(first.map((e) => [stateKey(e), e]));
		expect(planStatus(applied, first)).toEqual({ set: [], remove: [] });
		const next = stateEntries(s({ ways: { '1': 'open', '2': 'open', '4': 'detour' } }));
		const plan = planStatus(applied, next);
		expect(plan.set.map((e) => [e.id, e.state.sev])).toEqual([
			[2, 'open'],
			[4, 'detour']
		]);
		expect(plan.remove.map((e) => e.id)).toEqual([3]);
	});

	it('uses the severity order status.ts uses', async () => {
		vi.doUnmock('#lib/server/trails/status.js');
		const server = await import('#lib/server/trails/status.js');
		expect([...SEVERITY_ORDER]).toEqual(server.SEVERITY_ORDER);
		for (const a of [
			{ source: 'r2r_trails', state: 'dry', severity: 'open' },
			{ source: 'r2r_trails', state: 'unset', severity: null },
			{ source: 'boise_greenbelt_closures', state: 'ended', severity: null },
			{ source: 'boise_greenbelt_closures', state: 'detour', severity: 'detour' }
		] as const)
			expect(lineSev(a)).toBe(server.wayState(a));
	});

	it('shows a way carrying several lines in the worst state', () => {
		const lines = [
			{ severity: 'open', source: 'r2r_trails', paints: true },
			{ severity: 'closed', source: 'boise_greenbelt_closures', paints: true },
			{ severity: null, source: 'r2r_trails', paints: true }
		] as const;
		expect(worstSev(lines)).toBe('closed');
		expect(worstSev([])).toBeNull();
		expect(worstSev([{ severity: null, source: 'boise_greenbelt_closures', paints: true }])).toBeNull();
	});

	it('leaves a line along only part of a way out of the headline, as the map does', () => {
		const part = { severity: 'closed', source: 'boise_greenbelt_closures', paints: false } as const;
		expect(worstSev([part])).toBeNull();
		expect(worstSev([part, { severity: 'caution', source: 'r2r_trails', paints: true }])).toBe('caution');
	});
});

describe('selections', () => {
	it('opens a way as a trail selection with its name and its state, credited to the City for the state and OpenStreetMap for the way', () => {
		const sel = waySelection({ id: 9500000001, properties: { kind: 'path', name: 'Example Ridge Trail', informal: false } }, status({ way: () => 'closed' }));
		expect(sel).toMatchObject({ kind: 'trail', id: 'way:9500000001', layer: 'trails', title: 'Example Ridge Trail', fact: 'Closed', source: CREDIT_BOTH });
		expect(sel!.source).toContain('City of Boise');
		expect(sel!.source).toContain('© OpenStreetMap contributors');
		// A way with no state is OpenStreetMap's alone.
		expect(waySelection({ id: 8, properties: { kind: 'path' } }, status())!.source).toBe('© OpenStreetMap contributors');
		expect(sel!.data).toMatchObject({ type: 'way', id: 9500000001, sev: 'closed' });
	});

	it('words an unnamed path by its kind and an informal one as informal, not an official trail', () => {
		expect(waySelection({ id: 5, properties: { kind: 'cycleway' } }, status())).toMatchObject({ title: 'Unnamed bike path', fact: 'Bike path' });
		expect(waySelection({ id: 6, properties: { kind: 'path', informal: true } }, status())).toMatchObject({ title: 'Informal path', fact: INFORMAL_WORDS });
		expect(waySelection({ id: 0, properties: {} }, status())).toBeNull();
		expect(waySelection({ properties: {} }, status())).toBeNull();
	});

	it('opens an agency line by its line id, in the agency’s words', () => {
		const sel = lineSelection({ id: 7, properties: { kind: 'trail', name: 'Example Gulch' } }, status({ line: () => ({ sev: 'closed', label: 'CLOSED', state: 'closed', name: 'Example Gulch' }) }));
		expect(sel).toMatchObject({ kind: 'trail', id: 'line:7', title: 'Example Gulch', fact: 'CLOSED', source: CREDIT_BOTH });
		expect(sel!.data).toMatchObject({ type: 'line', id: 7, sev: 'closed' });
		expect(lineSelection({ id: 7, properties: { kind: 'detour' } }, status())!.title).toBe('Detour');
	});

	it('opens nothing the map hides: an informal way near a closure, or an agency row that has ended', () => {
		const hid = status({ hidden: (id) => id === 6 });
		expect(waySelection({ id: 6, properties: { kind: 'path', informal: true } }, hid)).toBeNull();
		expect(waySelection({ id: 7, properties: { kind: 'path', informal: true } }, hid)).not.toBeNull();
		// A paved tread is a base layer: still clickable.
		expect(pavedSelection({ properties: { id: 6, kind: 'cycleway', material: 'asphalt' } }, false, hid)).toMatchObject({ id: 'way:6' });
		const ended = status({ line: () => ({ sev: null, label: null, state: 'ended', name: 'Example Closure' }) });
		expect(lineSelection({ id: 7, properties: { kind: 'closure' } }, ended)).toBeNull();
		// A line the status doesn't know still opens (it draws plain).
		expect(lineSelection({ id: 7, properties: { kind: 'trail' } }, status())).not.toBeNull();
	});

	it('opens a paved tread as the way it is, and a paved area as paving', () => {
		expect(pavedSelection({ properties: { id: 9101, kind: 'cycleway', material: 'asphalt', w: 3 } }, false, status())).toMatchObject({ kind: 'trail', id: 'way:9101' });
		expect(pavedSelection({ properties: { id: 9201, kind: 'pedestrian', material: 'concrete' } }, true, status())).toMatchObject({ kind: 'paving', id: 'area:9201', title: 'Pedestrian plaza' });
	});

	it('knows which feature a selection stands for, so only that one is outlined', () => {
		expect(selectedIds({ kind: 'trail', id: 'way:42', layer: 'trails', title: 'x' })).toEqual({ way: 42, line: null });
		expect(selectedIds({ kind: 'trail', id: 'line:7', layer: 'trails', title: 'x' })).toEqual({ way: null, line: 7 });
		expect(selectedIds({ kind: 'paving', id: 'area:9', layer: 'trails', title: 'x' })).toEqual({ way: null, line: null });
		expect(selectedIds({ kind: 'street', id: '4', layer: 'streets', title: 'x' })).toEqual({ way: null, line: null });
		expect(selectedIds(null)).toEqual({ way: null, line: null });
		expect(selectedFilter(42)).toEqual(['==', ['id'], 42]);
		expect(selectedFilter(null)).toEqual(['==', ['id'], -1]);
	});
});

describe('words', () => {
	it('says a way’s kind, a state in the agency’s words first, and a width in metres and feet', () => {
		expect(kindWord('footway')).toBe('Footpath');
		expect(kindWord('whatever')).toBe('Trail');
		expect(stateWord('closed', 'CLOSED')).toBe('CLOSED');
		expect(stateWord('muddy_further_out')).toBe('Dry at the start, could be muddy further out');
		expect(stateWord('mystery')).toBe('mystery');
		expect(metresFeet(0.8)).toBe('0.8 m · 2.6 ft');
		expect(metresFeet(12)).toBe('12 m · 39 ft');
	});

	it('says where a surface came from: tagged, the kind’s default, or R2R’s dirt default (on the card only)', () => {
		expect(surfaceText({ surface: 'paved', surface_from: 'osm', surface_default: null, surface_tag: 'asphalt' })).toEqual({ text: 'Paved', how: 'tagged "asphalt" in OpenStreetMap' });
		expect(surfaceText({ surface: 'dirt', surface_from: 'default', surface_default: 'track', surface_tag: null }).how).toContain("OpenStreetMap's default for a track");
		const r2r = surfaceText({ surface: 'dirt', surface_from: 'default', surface_default: 'Ridge to Rivers trail', surface_tag: null });
		expect(r2r.text).toBe('Dirt');
		expect(r2r.how).toContain('Ridge to Rivers trail runs along it');
		expect(surfaceText({ surface: 'unknown', surface_from: 'none', surface_default: null, surface_tag: null }).text).toBe('Not mapped');
	});

	it('says a width was estimated when the tag is missing', () => {
		expect(widthText({ width_m: 3, width_from: 'osm' })).toEqual({ text: '3.0 m · 9.8 ft', how: 'tagged in OpenStreetMap' });
		expect(widthText({ width_m: 0.8, width_from: 'estimated' })!.how).toBe('estimated from the kind of way');
		expect(widthText({ width_m: null, width_from: 'estimated' })).toBeNull();
	});

	it('counts R2R’s trails by what they are', () => {
		expect(countsText({ dry: 200, frozen: 5, closed: 7, muddy: 3, muddy_further_out: 1, frozen_then_muddy: 2, not_evaluated: 26 })).toEqual([
			'7 closed',
			'3 muddy',
			'3 with caution',
			'205 open',
			'26 not evaluated'
		]);
		expect(countsText({})).toEqual([]);
	});
});
