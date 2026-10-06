import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Map as MapLibre } from 'maplibre-gl';
import {
	chooseInitialView,
	defaultView,
	formatHash,
	formatView,
	getParam,
	latLngDigits,
	normalizeBearing,
	parseHash,
	parseView,
	setParam,
	ViewManager,
	type CameraView
} from './view.svelte.js';
import { PREFIX } from './persisted.svelte.js';

/** Just enough of a MapLibre map for the view module. */
export function fakeMap(init: Partial<CameraView> = {}) {
	const s = {
		center: init.center ?? [-116.4, 43.6],
		zoom: init.zoom ?? 10,
		bearing: init.bearing ?? 0,
		pitch: init.pitch ?? 45,
		roll: 0,
		fov: 36.87,
		padding: { top: 0, right: 0, bottom: 0, left: 0 },
		maxZoom: 22,
		maxPitch: 75,
		clamped: true,
		terrain: { source: 'terrain', exaggeration: 1.3 } as { source: string; exaggeration?: number } | null
	};
	const handlers: Record<string, (() => void)[]> = {};
	const fire = (type: string) => (handlers[type] ?? []).forEach((f) => f());
	const map = {
		state: s,
		fire,
		getCenter: () => ({ lng: s.center[0], lat: s.center[1] }),
		getZoom: () => s.zoom,
		getBearing: () => s.bearing,
		getPitch: () => s.pitch,
		getRoll: () => s.roll,
		getVerticalFieldOfView: () => s.fov,
		setVerticalFieldOfView: (v: number) => void (s.fov = v),
		getPadding: () => ({ ...s.padding }),
		getMaxZoom: () => s.maxZoom,
		setMaxZoom: (v: number) => void (s.maxZoom = v),
		getMaxPitch: () => s.maxPitch,
		setMaxPitch: (v: number) => void (s.maxPitch = v),
		getCenterClampedToGround: () => s.clamped,
		setCenterClampedToGround: (v: boolean) => void (s.clamped = v),
		getTerrain: () => s.terrain,
		setTerrain: vi.fn((t: { source: string; exaggeration?: number } | null) => void (s.terrain = t)),
		stop: vi.fn(),
		jumpTo: vi.fn((o: { center?: [number, number]; zoom?: number; bearing?: number; pitch?: number; roll?: number; padding?: typeof s.padding }) => {
			if (o.center) s.center = [o.center[0], o.center[1]];
			if (o.zoom !== undefined) s.zoom = o.zoom;
			if (o.bearing !== undefined) s.bearing = o.bearing;
			if (o.pitch !== undefined) s.pitch = o.pitch;
			if (o.roll !== undefined) s.roll = o.roll;
			if (o.padding) s.padding = { ...o.padding };
			fire('moveend');
		}),
		on: (type: string, f: () => void) => void (handlers[type] ??= []).push(f),
		off: (type: string, f: () => void) => void (handlers[type] = (handlers[type] ?? []).filter((g) => g !== f))
	};
	return map;
}

function memoryStorage() {
	const data = new Map<string, string>();
	return {
		data,
		getItem: (k: string) => data.get(k) ?? null,
		setItem: (k: string, v: string) => void data.set(k, v),
		removeItem: (k: string) => void data.delete(k)
	};
}

describe('the hash', () => {
	it('formats a view rounded for a URL, about a pixel at its zoom', () => {
		expect(formatView({ center: [-116.2023, 43.615], zoom: 14, bearing: 20, pitch: 50 })).toBe('14/43.615/-116.2023/20/50');
		expect(latLngDigits(14)).toBe(6);
		expect(latLngDigits(10)).toBe(5);
		expect(formatView({ center: [-116.24682135, 43.60123456], zoom: 13.3712, bearing: -0.04, pitch: 41.25 })).toBe(
			'13.37/43.601235/-116.246821/0/41.3'
		);
	});

	it('normalizes bearings into (−180, 180]', () => {
		expect(normalizeBearing(190)).toBe(-170);
		expect(normalizeBearing(-180)).toBe(180);
		expect(normalizeBearing(360)).toBe(0);
		expect(normalizeBearing(-12)).toBe(-12);
	});

	it('parses views and rejects nonsense', () => {
		expect(parseView('14/43.615/-116.2023')).toEqual({ center: [-116.2023, 43.615], zoom: 14, bearing: 0, pitch: 0 });
		expect(parseView('14/43.615/-116.2023/20/50')).toEqual({ center: [-116.2023, 43.615], zoom: 14, bearing: 20, pitch: 50 });
		for (const bad of ['', '14', '14/43.6', '14/a/b', '30/43.6/-116', '14/95/-116', '14/43.6/-200', '14/43.6/-116/0/95', '14//-116'])
			expect(parseView(bad), bad).toBeNull();
	});

	it('reads the #map= form, keeping the other pieces verbatim', () => {
		const h = parseHash('#map=14/43.615/-116.2023/20/50&layers=transit,streets&x');
		expect(h).toEqual({
			view: { center: [-116.2023, 43.615], zoom: 14, bearing: 20, pitch: 50 },
			raw: '14/43.615/-116.2023/20/50',
			legacy: false,
			params: ['layers=transit,streets', 'x']
		});
		expect(formatHash(h.view, h.params)).toBe('#map=14/43.615/-116.2023/20/50&layers=transit,streets&x');
	});

	it('recognises an old MapLibre-style hash', () => {
		const h = parseHash('#14/43.6150/-116.2023/20/50');
		expect(h.legacy).toBe(true);
		expect(h.view).toEqual({ center: [-116.2023, 43.615], zoom: 14, bearing: 20, pitch: 50 });
		expect(formatHash(h.view)).toBe('#map=14/43.615/-116.2023/20/50');
	});

	it('treats an empty or foreign hash as no view', () => {
		expect(parseHash('')).toEqual({ view: null, raw: null, legacy: false, params: [] });
		expect(parseHash('#about').view).toBeNull();
		expect(parseHash('#map=nonsense').view).toBeNull();
		expect(formatHash(null, [])).toBe('');
	});

	it('sets, replaces and removes one piece', () => {
		let p = setParam([], 'layers', 'transit,streets');
		expect(p).toEqual(['layers=transit,streets']);
		p = setParam(['a=1', ...p], 'layers', 'cameras');
		expect(p).toEqual(['a=1', 'layers=cameras']);
		expect(getParam(p, 'layers')).toBe('cameras');
		expect(getParam(p, 'nope')).toBeNull();
		expect(setParam(p, 'layers', null)).toEqual(['a=1']);
	});
});

describe('the first view', () => {
	const fallback = defaultView({ center: [-116.4, 43.6], zoom: 10, terrain: { exaggeration: 1.3 } as never });
	const saved: CameraView = { center: [-116.2468213579, 43.6012345678], zoom: 13.37, bearing: 17.3, pitch: 41.2 };

	it('defaults to the manifest view, tilted only with terrain', () => {
		expect(fallback).toEqual({ center: [-116.4, 43.6], zoom: 10, bearing: 0, pitch: 45 });
		expect(defaultView({ center: [-116.4, 43.6], zoom: 10 }).pitch).toBe(0);
	});

	it('prefers the URL, then the saved view, then the default', () => {
		const url = parseHash('#map=12/43.5/-116.5/0/0');
		expect(chooseInitialView({ hash: url, saved, fallback })).toEqual({ view: url.view, source: 'url' });
		expect(chooseInitialView({ hash: parseHash(''), saved, fallback })).toEqual({ view: saved, source: 'saved' });
		expect(chooseInitialView({ hash: parseHash(''), fallback })).toEqual({ view: fallback, source: 'default' });
	});

	it('uses the exact saved view when the URL is that view rounded', () => {
		const hash = parseHash(`#map=${formatView(saved)}`);
		expect(chooseInitialView({ hash, saved, fallback }).view).toBe(saved);
	});

	it('lets a deep link choose its own view', () => {
		const override: CameraView = { center: [-116.35, 43.62], zoom: 16, bearing: 0, pitch: 50 };
		expect(chooseInitialView({ hash: parseHash('#map=12/43.5/-116.5/0/0'), saved, override, fallback })).toEqual({
			view: override,
			source: 'override'
		});
	});
});

describe('ViewManager', () => {
	let storage: ReturnType<typeof memoryStorage>;
	beforeEach(() => {
		storage = memoryStorage();
		vi.stubGlobal('localStorage', storage);
		vi.useFakeTimers();
	});
	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	function setup(hash = '', canWrite = () => true) {
		let current = hash;
		const written: string[] = [];
		const vm = new ViewManager({
			write: (h) => {
				written.push(h);
				current = h;
			},
			canWrite,
			readHash: () => current
		});
		return { vm, written, setHash: (h: string) => (current = h) };
	}

	it('opens at the URL, saved or default view', () => {
		const manifest = { center: [-116.4, 43.6] as [number, number], zoom: 10, terrain: { exaggeration: 1.3 } as never };
		expect(setup('#14/43.615/-116.2023/20/50').vm.initial(manifest)).toMatchObject({ source: 'url', legacy: true });
		expect(setup('').vm.initial(manifest)).toMatchObject({ source: 'default', view: { zoom: 10, pitch: 45 } });
		storage.setItem(`${PREFIX}view`, JSON.stringify({ center: [-116.3, 43.61], zoom: 12, bearing: 5, pitch: 30 }));
		expect(setup('').vm.initial(manifest)).toMatchObject({ source: 'saved', view: { zoom: 12 } });
		const { vm } = setup('');
		vm.preferInitial({ center: [-116.35, 43.62], zoom: 16, bearing: 0, pitch: 50 });
		expect(vm.initial(manifest)).toMatchObject({ source: 'override', view: { zoom: 16, pitch: 50 } });
	});

	it('writes the hash and the exact view 500 ms after the map stops, keeping other pieces', () => {
		const { vm, written } = setup('#map=10/43.6/-116.4/0/45&layers=transit');
		vm.initial({ center: [-116.4, 43.6], zoom: 10 });
		const map = fakeMap();
		vm.attach(map as unknown as MapLibre);
		map.jumpTo({ center: [-116.2468213579, 43.6012345678], zoom: 13.37, bearing: 17.3, pitch: 41.2 });
		vi.advanceTimersByTime(499);
		expect(written).toEqual([]);
		vi.advanceTimersByTime(1);
		expect(written).toEqual(['#map=13.37/43.601235/-116.246821/17.3/41.2&layers=transit']);
		expect(JSON.parse(storage.getItem(`${PREFIX}view`)!)).toEqual({
			center: [-116.2468213579, 43.6012345678],
			zoom: 13.37,
			bearing: 17.3,
			pitch: 41.2
		});
		// Moving again within the debounce writes once, for the last view.
		map.jumpTo({ zoom: 14 });
		vi.advanceTimersByTime(200);
		map.jumpTo({ zoom: 15 });
		vi.advanceTimersByTime(500);
		expect(written).toHaveLength(2);
		expect(written[1]).toMatch(/^#map=15\//);
	});

	it("doesn't write while suspended, nor when the app says not now", () => {
		let allowed = false;
		const { vm, written } = setup('', () => allowed);
		const map = fakeMap();
		vm.attach(map as unknown as MapLibre);
		map.jumpTo({ zoom: 12 });
		vi.advanceTimersByTime(1000);
		expect(written).toEqual([]);
		allowed = true;
		vm.suspend();
		map.jumpTo({ zoom: 13 });
		vi.advanceTimersByTime(1000);
		expect(written).toEqual([]);
		vm.resume();
		vm.touch();
		vi.advanceTimersByTime(500);
		expect(written).toEqual(['#map=13/43.6/-116.4/0/45']);
	});

	it('restores a snapshot exactly, parts included', () => {
		const { vm } = setup();
		const map = fakeMap({ center: [-116.2023, 43.615], zoom: 14, bearing: 20, pitch: 50 });
		vm.attach(map as unknown as MapLibre);
		let aerial = false;
		vm.register('aerial', { save: () => aerial, restore: (v) => (aerial = v as boolean) });
		const snap = vm.snapshot();
		expect(snap).toMatchObject({ center: [-116.2023, 43.615], zoom: 14, bearing: 20, pitch: 50, roll: 0, exaggeration: 1.3, parts: { aerial: false } });

		// A mode changes everything…
		aerial = true;
		map.state.maxPitch = 85;
		map.state.fov = 50;
		map.state.clamped = false;
		map.state.terrain = { source: 'terrain', exaggeration: 1 };
		map.jumpTo({ center: [-116.35, 43.62], zoom: 19, bearing: -5, pitch: 0, roll: 3, padding: { top: 0, right: 0, bottom: 0, left: 576 } });

		// …and restore puts it all back.
		vm.restore(snap);
		expect(map.getCenter()).toEqual({ lng: -116.2023, lat: 43.615 });
		expect([map.getZoom(), map.getBearing(), map.getPitch(), map.getRoll()]).toEqual([14, 20, 50, 0]);
		expect(map.getPadding()).toEqual({ top: 0, right: 0, bottom: 0, left: 0 });
		expect([map.getMaxPitch(), map.getVerticalFieldOfView(), map.getCenterClampedToGround()]).toEqual([75, 36.87, true]);
		expect(map.getTerrain()).toEqual({ source: 'terrain', exaggeration: 1.3 });
		expect(aerial).toBe(false);
		expect(map.stop).toHaveBeenCalled();
	});

	it('applies a typed hash, but not its own writes', () => {
		const { vm, written, setHash } = setup();
		const map = fakeMap();
		vm.attach(map as unknown as MapLibre);
		map.jumpTo({ zoom: 12 });
		vi.advanceTimersByTime(500);
		expect(vm.applyHash(written[0])).toBe(false);
		setHash('#map=15/43.62/-116.35/10/30');
		expect(vm.applyHash()).toBe(true);
		expect(map.getZoom()).toBe(15);
		expect(map.getCenter()).toEqual({ lng: -116.35, lat: 43.62 });
	});
});
