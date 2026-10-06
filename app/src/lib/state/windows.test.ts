import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'svelte';
import {
	besideAnchor,
	cascadeRect,
	clampRect,
	clampWidth,
	dockRect,
	fitWidth,
	layoutFor,
	lowestFree,
	maxWidth,
	openingArea,
	pickVictim,
	safeArea,
	snapRect,
	snapWidth,
	STORE_KEY,
	WindowManager,
	type WindowSpec
} from './windows.svelte.js';
import { PREFIX } from './persisted.svelte.js';

const Dummy = (() => {}) as unknown as Component;
const spec = (n: number | string, extra: Partial<WindowSpec> = {}): WindowSpec => ({ key: `test:${n}`, title: `Test ${n}`, component: Dummy, aspect: 16 / 9, ...extra });

function memoryStorage() {
	const data = new Map<string, string>();
	return {
		getItem: (k: string) => data.get(k) ?? null,
		setItem: (k: string, v: string) => void data.set(k, String(v)),
		removeItem: (k: string) => void data.delete(k),
		clear: () => data.clear(),
		key: (i: number) => [...data.keys()][i] ?? null,
		get length() {
			return data.size;
		},
		data
	};
}

describe('window geometry', () => {
	const safe = safeArea(1280, 800);

	it('the safe area sits below the top bar and above the toolbar', () => {
		expect(safe).toEqual({ left: 16, top: 76, right: 1264, bottom: 696 });
		expect(safeArea(1280, 800, { top: 90, bottom: 120 })).toEqual({ left: 16, top: 90, right: 1264, bottom: 680 });
	});

	it('layouts and limits follow the breakpoints', () => {
		expect([layoutFor(390), layoutFor(599), layoutFor(600), layoutFor(1023), layoutFor(1024), layoutFor(1920)]).toEqual([
			'phone',
			'phone',
			'tablet',
			'tablet',
			'desktop',
			'desktop'
		]);
	});

	it('widths run from 260 px to min(60vw, 960 px)', () => {
		expect(maxWidth(1280)).toBe(768);
		expect(maxWidth(1920)).toBe(960);
		expect(maxWidth(300)).toBe(260);
		expect(clampWidth(100, 1280)).toBe(260);
		expect(clampWidth(2000, 1280)).toBe(768);
		expect(clampWidth(400, 1280)).toBe(400);
	});

	it('a rect is kept inside the safe area', () => {
		expect(clampRect({ x: -50, y: 10, w: 400, h: 300 }, safe)).toEqual({ x: 16, y: 76, w: 400, h: 300 });
		expect(clampRect({ x: 1200, y: 600, w: 400, h: 300 }, safe)).toEqual({ x: 864, y: 396, w: 400, h: 300 });
		// Taller than the area: its top stays in.
		expect(clampRect({ x: 100, y: 300, w: 400, h: 900 }, safe).y).toBe(76);
	});

	it('moves snap to the area edges and to other windows within 8 px', () => {
		expect(snapRect({ x: 22, y: 83, w: 400, h: 300 }, safe, [])).toMatchObject({ x: 16, y: 76 });
		expect(snapRect({ x: 30, y: 100, w: 400, h: 300 }, safe, [])).toMatchObject({ x: 30, y: 100 });
		// Beside another window: my left edge to its right edge, tops aligned.
		const other = { x: 400, y: 200, w: 300, h: 200 };
		expect(snapRect({ x: 705, y: 195, w: 300, h: 200 }, safe, [other])).toMatchObject({ x: 700, y: 200 });
		// A window far below doesn't pull the x edge.
		expect(snapRect({ x: 705, y: 500, w: 300, h: 100 }, safe, [{ x: 400, y: 80, w: 300, h: 100 }])).toMatchObject({ x: 705 });
		expect(snapWidth({ x: 100, y: 100, w: 1160, h: 300 }, safe, [])).toBe(1164);
	});

	it('a new window opens 24 px beside its anchor, away from the centre, never covering it', () => {
		const left = besideAnchor({ x: 500, y: 400 }, { w: 300, h: 200 }, safe, 1280)!;
		expect(left).toEqual({ x: 176, y: 300, w: 300, h: 200 });
		const right = besideAnchor({ x: 900, y: 400 }, { w: 300, h: 200 }, safe, 1280)!;
		expect(right).toEqual({ x: 924, y: 300, w: 300, h: 200 });
		// No room on the far side: the near side.
		expect(besideAnchor({ x: 100, y: 400 }, { w: 300, h: 200 }, safe, 1280)).toMatchObject({ x: 124 });
		// No room on either side.
		expect(besideAnchor({ x: 640, y: 400 }, { w: 700, h: 200 }, safe, 1280)).toBeNull();
		// Near the top, clamped down, still clear of the anchor.
		const top = besideAnchor({ x: 900, y: 60 }, { w: 300, h: 200 }, safe, 1280)!;
		expect(top.y).toBe(76);
		expect(top.x).toBe(924);
	});

	it('cascades from the top left of the free middle, skipping occupied slots', () => {
		const area = openingArea(safe, 1280);
		expect(area.left).toBe(312);
		const a = cascadeRect({ w: 400, h: 300 }, area, safe, []);
		expect(a).toMatchObject({ x: 312, y: 76 });
		const b = cascadeRect({ w: 400, h: 300 }, area, safe, [a]);
		expect(b).toMatchObject({ x: 340, y: 104 });
		// Too narrow for a window between the columns: the whole safe area.
		expect(openingArea(safeArea(1024, 768), 1024).left).toBe(16);
	});

	it('docks to an edge, below windows already docked there', () => {
		const first = dockRect('left', { x: 500, y: 300, w: 300, h: 200 }, safe, []);
		expect(first).toEqual({ x: 16, y: 76, w: 300, h: 200 });
		const second = dockRect('left', { x: 500, y: 300, w: 300, h: 200 }, safe, [first]);
		expect(second).toEqual({ x: 16, y: 284, w: 300, h: 200 });
		expect(dockRect('right', { x: 0, y: 0, w: 300, h: 200 }, safe, [])).toEqual({ x: 964, y: 76, w: 300, h: 200 });
	});

	it('picks the least recently focused unpinned window, and the lowest free number', () => {
		const wins = [
			{ key: 'a', pinned: false, focusedAt: 5 },
			{ key: 'b', pinned: true, focusedAt: 1 },
			{ key: 'c', pinned: false, focusedAt: 3 }
		];
		expect(pickVictim(wins)).toBe('c');
		expect(pickVictim(wins.map((w) => ({ ...w, pinned: true })))).toBeNull();
		expect(lowestFree([])).toBe(1);
		expect(lowestFree([1, 2, 4])).toBe(3);
	});

	it('narrows a tall window to fit, keeping the picture aspect', () => {
		expect(fitWidth(600, 500, 16 / 9, 600)).toBe(600);
		expect(fitWidth(600, 700, 16 / 9, 600)).toBeCloseTo(600 - (100 * 16) / 9);
	});
});

describe('WindowManager', () => {
	const toast = vi.fn();
	const make = (vw = 1280, vh = 800) => new WindowManager({ persist: false, toast, viewport: { w: vw, h: vh }, activeElement: () => null });
	beforeEach(() => toast.mockClear());

	it('opens up to 4 on a desktop; a 5th replaces the least recently focused', () => {
		const m = make();
		const closed: string[] = [];
		for (let i = 1; i <= 4; i++) m.open(spec(i, { onclose: () => closed.push(`test:${i}`) }));
		expect(m.list.map((w) => w.number)).toEqual([1, 2, 3, 4]);
		m.focus('test:1');
		m.open(spec(5));
		expect(m.list.map((w) => w.key)).toEqual(['test:1', 'test:3', 'test:4', 'test:5']);
		expect(closed).toEqual(['test:2']);
		// The newcomer takes the freed number.
		expect(m.numberOf('test:5')).toBe(2);
	});

	it('never replaces a pinned window; all pinned → a toast and nothing opens', () => {
		const m = make();
		for (let i = 1; i <= 4; i++) m.open(spec(i));
		m.pin('test:1');
		m.pin('test:2');
		m.focus('test:3');
		m.focus('test:4');
		m.open(spec(5));
		expect(m.isOpen('test:1') && m.isOpen('test:2')).toBe(true);
		expect(m.isOpen('test:3')).toBe(false);
		for (const k of ['test:4', 'test:5']) m.pin(k);
		expect(m.open(spec(6))).toBeNull();
		expect(toast).toHaveBeenCalledWith('All 4 windows are pinned: unpin one to open another.');
		expect(m.list).toHaveLength(4);
	});

	it('reopening an open key focuses it and takes the new title', () => {
		const m = make();
		m.open(spec(1));
		m.open(spec(2));
		const again = m.open({ ...spec(1), title: 'Renamed' })!;
		expect(m.list).toHaveLength(2);
		expect(again.title).toBe('Renamed');
		expect(m.top?.key).toBe('test:1');
		expect(m.rank('test:1')).toBe(1);
		expect(m.rank('test:2')).toBe(0);
	});

	it('limits are 2 on a tablet and 3 on a phone; shrinking the screen closes the oldest', () => {
		const t = make(800, 1000);
		expect(t.layout).toBe('tablet');
		t.open(spec(1));
		t.open(spec(2));
		t.open(spec(3));
		expect(t.list.map((w) => w.key)).toEqual(['test:2', 'test:3']);
		const m = make();
		for (let i = 1; i <= 4; i++) m.open(spec(i));
		m.pin('test:1');
		m.setViewport(390, 844);
		expect(m.layout).toBe('phone');
		expect(m.list.map((w) => w.key)).toEqual(['test:1', 'test:3', 'test:4']);
		expect(toast).toHaveBeenCalledWith('Closed a window: this screen holds 3.');
	});

	it('moves stay inside the safe area and snap; resizes keep the picture aspect', () => {
		const m = make();
		m.open(spec(1));
		m.measured('test:1', 325);
		expect(m.move('test:1', { x: -100, y: 0 })).toMatchObject({ x: 16, y: 76 });
		expect(m.move('test:1', { x: 2000, y: 2000 })).toMatchObject({ x: 864, y: 371 });
		// At the right edge it can't grow (the grip is bottom right).
		expect(m.resize('test:1', 560)!.w).toBe(400);
		m.move('test:1', { x: 100, y: 100 });
		const r = m.resize('test:1', 560)!;
		expect(r.w).toBe(560);
		expect(r.h).toBe(Math.round(325 + 160 / (16 / 9)));
		expect(r.x).toBe(100);
		expect(r.x + r.w).toBeLessThanOrEqual(1264);
		expect(m.resize('test:1', 100)!.w).toBe(260);
		expect(m.resize('test:1', 5000)!.w).toBe(768);
	});

	it('a window taller than the safe area narrows until it fits', () => {
		const m = make(1280, 600);
		m.open(spec(1, { width: 700 }));
		// 700 px wide → 394 px of picture plus chrome: more than the 420 px of room.
		m.measured('test:1', 700 / (16 / 9) + 96);
		const r = m.get('test:1')!.rect;
		expect(r.h).toBeLessThanOrEqual(420);
		expect(r.w).toBeLessThan(700);
		expect(r.y).toBe(76);
	});

	it('docks without dragging, and opens beside an anchor', () => {
		const m = make();
		m.open(spec(1, { anchor: { x: 1000, y: 400 } }));
		// Right of centre, but no room on the right: to its left, clear of it.
		expect(m.get('test:1')!.rect).toMatchObject({ x: 576, w: 400 });
		m.measured('test:1', 200);
		const r = m.dock('test:1', 'left')!;
		expect(r).toMatchObject({ x: 16, y: 76 });
		m.open(spec(2));
		m.measured('test:2', 200);
		expect(m.dock('test:2', 'left')).toMatchObject({ x: 16, y: 284 });
		// No room below any more: back to the top.
		m.open(spec(3));
		m.measured('test:3', 300);
		expect(m.dock('test:3', 'left')).toMatchObject({ x: 16, y: 76 });
	});

	it('the snapshot part puts the open windows back', () => {
		const m = make();
		m.open(spec(1));
		m.open(spec(2));
		const part = m.part();
		const saved = part.save();
		m.close('test:1');
		m.open(spec(3));
		part.restore(saved);
		expect(m.list.map((w) => w.key)).toEqual(['test:1', 'test:2']);
		expect(m.list.map((w) => w.number)).toEqual([1, 2]);
		expect(m.get('test:1')!.takeFocus).toBe(false);
	});

	it('listeners hear every change', () => {
		const m = make();
		const heard = vi.fn();
		const off = m.listen(heard);
		m.open(spec(1));
		m.move('test:1', { x: 300, y: 300 });
		m.close('test:1');
		off();
		m.open(spec(2));
		expect(heard).toHaveBeenCalledTimes(3);
	});
});

describe('WindowManager memory', () => {
	let store: ReturnType<typeof memoryStorage>;
	beforeEach(() => {
		store = memoryStorage();
		vi.stubGlobal('localStorage', store);
	});
	afterEach(() => vi.unstubAllGlobals());

	const make = () => new WindowManager({ toast: () => {}, viewport: { w: 1280, h: 800 }, activeElement: () => null });

	it('remembers a moved window’s place per key, for the next visit', () => {
		const a = make();
		a.open(spec(1));
		a.move('test:1', { x: 500, y: 300 });
		a.resize('test:1', 480);
		a.close('test:1');
		const stored = JSON.parse(store.data.get(PREFIX + STORE_KEY)!);
		expect(stored.rects['test:1']).toMatchObject({ x: 500, y: 300, w: 480 });
		const b = make();
		const w = b.open(spec(1))!;
		expect(w.rect).toMatchObject({ x: 500, y: 300, w: 480 });
	});

	it('only pinned windows reopen, once their kind is registered', async () => {
		const a = make();
		a.open(spec(1, { restore: { kind: 'test', data: 1 } }));
		a.open(spec(2, { restore: { kind: 'test', data: 2 } }));
		a.pin('test:2');
		const b = make();
		expect(b.list).toEqual([]);
		expect(b.pending).toEqual([{ key: 'test:2', kind: 'test' }]);
		const opener = vi.fn((n: unknown) => spec(n as number));
		b.registerKind('test', opener);
		await vi.waitFor(() => expect(b.list.map((w) => w.key)).toEqual(['test:2']));
		expect(opener).toHaveBeenCalledWith(2);
		expect(b.get('test:2')).toMatchObject({ pinned: true, takeFocus: false });
		// Unpinning forgets it.
		b.pin('test:2', false);
		expect(make().pending).toEqual([]);
	});

	it('ignores stored data of the wrong shape', () => {
		store.setItem(PREFIX + STORE_KEY, JSON.stringify({ rects: { a: { x: 'no' } }, pinned: 3 }));
		const m = make();
		expect(m.remembered('a')).toBeNull();
		expect(m.pending).toEqual([]);
	});
});
