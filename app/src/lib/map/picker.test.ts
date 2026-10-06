import { describe, expect, it } from 'vitest';
import { PRIORITY, type Selection } from '#lib/layers/types.js';
import { Picker, resolve, type Hit } from './picker.js';

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

	it('takes the nearest of equal priority', () => {
		expect(resolve([hit(sel('bus', 'far'), 10), hit(sel('bus', 'near'), 3)])?.id).toBe('near');
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
		listeners.click({ point: { x: 101, y: 100 }, originalEvent: {} });
		expect(picked.map((s) => s?.id)).toEqual(['b']);
		listeners.click({ point: { x: 300, y: 300 }, originalEvent: {} });
		expect(picked.at(-1)).toBeNull(); // an empty click clears the selection
		exploring = false;
		listeners.click({ point: { x: 101, y: 100 }, originalEvent: {} });
		expect(picked).toHaveLength(2);
	});
});
