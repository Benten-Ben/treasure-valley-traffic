import { describe, expect, it } from 'vitest';
import { PRIORITY, type Selection } from '#lib/layers/types.js';
import { Picker, resolve, TIE_PX, type Hit } from './picker.js';

const sel = (kind: Selection['kind'], id: string, extra: Partial<Selection> = {}): Selection => ({ kind, id, layer: 'test', title: `${kind} ${id}`, ...extra });
const hit = (s: Selection, distance = 0): Hit => ({ selection: s, priority: PRIORITY[s.kind as keyof typeof PRIORITY], distance });

describe('picker', () => {
	it('picks by priority: bus > camera > hub > stop > route > lane > street', () => {
		const street = hit(sel('street', '1'));
		const route = hit(sel('route', '9'));
		const stop = hit(sel('stop', 's'));
		const camera = hit(sel('camera', 'c'), 9);
		const bus = hit(sel('bus', 'b'), 12);
		expect(resolve([street, route, stop, camera, bus])?.kind).toBe('bus');
		expect(resolve([street, route, stop, camera])?.kind).toBe('camera');
		expect(resolve([street, route, stop])?.kind).toBe('stop');
		expect(resolve([street, route])?.kind).toBe('route');
		expect(resolve([street])?.kind).toBe('street');
		expect(resolve([])).toBeNull();
	});

	it('ranks the landscape layers under the streets and trees, in the plan’s order (§3.3)', () => {
		const order = ['bus', 'camera', 'weather', 'hub', 'stop', 'route', 'lane', 'street', 'trail', 'tree', 'shrub', 'fence', 'sprite', 'water', 'paving', 'crop', 'soil'] as const;
		for (let i = 1; i < order.length; i++) expect(PRIORITY[order[i - 1]], `${order[i - 1]} over ${order[i]}`).toBeGreaterThan(PRIORITY[order[i]]);
		expect([PRIORITY.trail, PRIORITY.shrub, PRIORITY.fence, PRIORITY.water, PRIORITY.paving, PRIORITY.crop, PRIORITY.soil]).toEqual([38, 34, 33, 25, 22, 15, 10]);
		// The bus > camera > weather > hub > stop > route > lane > street order still holds, each against its neighbours.
		const rows = order.map((k, i) => hit(sel(k, String(i))));
		for (let i = 0; i < rows.length - 1; i++) expect(resolve([rows[i + 1], rows[i]])?.kind, `${order[i]} against ${order[i + 1]}`).toBe(order[i]);
		// A click on a crop field's fence opens the fence; in the middle of the field, the crop.
		expect(resolve([hit(sel('crop', 'c')), hit(sel('fence', 'f'), 6)])?.kind).toBe('fence');
		expect(resolve([hit(sel('crop', 'c')), hit(sel('soil', 's'))])?.kind).toBe('crop');
	});

	it('takes the nearest of equal priority', () => {
		expect(resolve([hit(sel('bus', 'far'), 10), hit(sel('bus', 'near'), 3)])?.id).toBe('near');
	});

	it('gives a near tie to what is selected, never a higher priority or a clear winner', () => {
		const a = sel('bus', 'a');
		const b = sel('bus', 'b');
		// Two buses at one stop: b is selected (lifted), a is 2 px nearer the pointer.
		expect(resolve([hit(a, 1), hit(b, 3)], b)?.id).toBe('b');
		expect(resolve([hit(a, 1), hit(b, 3)])?.id).toBe('a');
		expect(resolve([hit(a, 1), hit(b, 1 + TIE_PX)], { ...b })?.id).toBe('b');
		expect(resolve([hit(a, 1), hit(b, 1.5 + TIE_PX)], b)?.id).toBe('a');
		// Priority still comes first: a selected stop doesn't win over a bus.
		expect(resolve([hit(a, 5), hit(sel('stop', 's'), 0)], sel('stop', 's'))?.id).toBe('a');
		// Nothing selected among the hits: the nearest.
		expect(resolve([hit(a, 1), hit(b, 3)], sel('bus', 'c'))?.id).toBe('a');
	});

	it('lists every route where several share the street, once each, in number order', () => {
		const badge = (t: string) => ({ text: t, color: '#000', textColor: '#fff' });
		const r = resolve([
			hit(sel('route', '9', { badge: badge('9') })),
			hit(sel('route', '7', { badge: badge('7') })),
			hit(sel('route', '9', { badge: badge('9') })),
			hit(sel('route', '10', { badge: badge('10') })),
			hit(sel('street', 'x'))
		]);
		expect(r?.kind).toBe('routes');
		expect(r?.title).toBe('3 routes here: 7 · 9 · 10');
		expect(r?.items?.map((i) => i.id)).toEqual(['7', '9', '10']);
		// One route alone is just that route.
		expect(resolve([hit(sel('route', '9')), hit(sel('route', '9'))])?.kind).toBe('route');
	});

	it('hit-tests sprite sources with the mouse and touch radii, and selects on click only in Explore', () => {
		let exploring = true;
		const picked: (Selection | null)[] = [];
		const p = new Picker({ canPick: () => exploring, select: (s) => picked.push(s) });
		const target = sel('bus', 'b');
		p.addSource({ hits: (x, y, r) => (Math.hypot(x - 100, y - 100) <= Math.max(6, r) ? [hit(target, Math.hypot(x - 100, y - 100))] : []) });
		expect(p.pickAt({ x: 110, y: 100 }).top?.id).toBe('b');
		expect(p.pickAt({ x: 120, y: 100 }).top).toBeNull(); // beyond 14 px for a mouse
		expect(p.pickAt({ x: 120, y: 100 }, true).top?.id).toBe('b'); // within 22 px for touch
		// The click handler (as MapLibre calls it) asks canPick first.
		const listeners: Record<string, (e: unknown) => void> = {};
		const fakeMap = { on: (t: string, f: (e: unknown) => void) => (listeners[t] = f), off: () => {}, getLayer: () => undefined, getCanvas: () => ({ style: {} }) };
		p.attach(fakeMap as never);
		// Pick listeners hear each click once it has selected (the chrome pans a covered one clear).
		const heard: { id: string | null; x: number; y: number; selected: number }[] = [];
		const unpick = p.onPick((k) => heard.push({ id: k.selection?.id ?? null, x: k.x, y: k.y, selected: picked.length }));
		listeners.click({ point: { x: 101, y: 100 }, originalEvent: {} });
		expect(picked.map((s) => s?.id)).toEqual(['b']);
		expect(heard).toEqual([{ id: 'b', x: 101, y: 100, selected: 1 }]);
		listeners.click({ point: { x: 300, y: 300 }, originalEvent: {} });
		expect(picked.at(-1)).toBeNull(); // an empty click clears the selection
		expect(heard.at(-1)).toEqual({ id: null, x: 300, y: 300, selected: 2 });
		exploring = false;
		listeners.click({ point: { x: 101, y: 100 }, originalEvent: {} });
		expect(picked).toHaveLength(2);
		expect(heard).toHaveLength(2);
		exploring = true;
		unpick();
		listeners.click({ point: { x: 101, y: 100 }, originalEvent: {} });
		expect(heard).toHaveLength(2);
	});
});
