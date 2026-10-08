import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	aimAt,
	AIM_ZOOM,
	clearDraft,
	compass,
	complete,
	draftKey,
	fitAim,
	frameChoice,
	isDraft,
	moveGround,
	movePixel,
	nextStep,
	pairNear,
	pendingIndex,
	placeGround,
	placePixel,
	quality,
	readDraft,
	removePair,
	rescalePairs,
	residualMark,
	sameWork,
	trueHeight,
	Undo,
	writeDraft,
	type Draft,
	type DraftPair
} from './draft.js';
import { calibrateKey } from './keys.js';

const frame = { frame: 'view-26/a.jpg', url: '/frames/view-26/a.jpg', width: 768, height: 466 };

describe('pairs', () => {
	it('fill the pending pair from either side, then start a new one', () => {
		let pairs: DraftPair[] = [];
		expect(nextStep(pairs)).toBe('either');
		({ pairs } = placePixel(pairs, [10, 20]));
		expect(pendingIndex(pairs)).toBe(0);
		expect(nextStep(pairs)).toBe('map');
		// A second image click moves the pending image point instead of starting a pair.
		({ pairs } = placePixel(pairs, [11, 21]));
		expect(pairs).toEqual([{ pixel: [11, 21] }]);
		const r = placeGround(pairs, [-116, 43, 800]);
		expect(r.index).toBe(0);
		pairs = r.pairs;
		expect(pendingIndex(pairs)).toBe(-1);
		expect(complete(pairs)).toEqual([{ pixel: [11, 21], ground: [-116, 43, 800] }]);
		// The map first this time.
		({ pairs } = placeGround(pairs, [-116.1, 43.1, 801]));
		expect(nextStep(pairs)).toBe('image');
		({ pairs } = placePixel(pairs, [30, 40]));
		expect(complete(pairs)).toHaveLength(2);
	});

	it('are never changed in place', () => {
		const a: DraftPair[] = [{ pixel: [1, 2], ground: [0, 0, 1] }];
		const frozen = structuredClone(a);
		placePixel(a, [5, 5]);
		placeGround(a, [1, 1, 1]);
		movePixel(a, 0, [9, 9]);
		moveGround(a, 0, [2, 2, 2]);
		removePair(a, 0);
		expect(a).toEqual(frozen);
	});

	it('move, remove and find by image point', () => {
		const a: DraftPair[] = [{ pixel: [100, 100], ground: [0, 0, 1] }, { pixel: [200, 100], ground: [1, 0, 1] }];
		expect(movePixel(a, 1, [205, 101])[1].pixel).toEqual([205, 101]);
		expect(moveGround(a, 0, [3, 3, 3])[0].ground).toEqual([3, 3, 3]);
		expect(removePair(a, 0)).toEqual([a[1]]);
		expect(removePair(a, 5)).toEqual(a);
		expect(pairNear(a, [198, 103], 10)).toBe(1);
		expect(pairNear(a, [150, 100], 10)).toBe(-1);
	});

	it('tell real changes from none', () => {
		const a = { pairs: [{ pixel: [1, 2], ground: [0, 0, 1] }] as DraftPair[], frame };
		expect(sameWork(a, structuredClone(a))).toBe(true);
		expect(sameWork(a, { ...a, frame: { ...frame, frame: 'view-26/b.jpg' } })).toBe(false);
		expect(sameWork(a, { ...a, pairs: movePixel(a.pairs, 0, [1, 3]) })).toBe(false);
		expect(sameWork(a, { ...a, pairs: [] })).toBe(false);
	});

	it('carry to a frame of another size only when the picture has the same shape', () => {
		const a: DraftPair[] = [{ pixel: [384, 216], ground: [0, 0, 1] }, { ground: [1, 1, 1] }];
		// 768×466 (34 px bar) and 1920×1166 (86 px bar) are both 16:9 above the bar.
		expect(rescalePairs(a, { width: 768, height: 466 }, { width: 1920, height: 1166 })).toEqual([
			{ pixel: [960, 540], ground: [0, 0, 1] },
			{ ground: [1, 1, 1] }
		]);
		expect(rescalePairs(a, { width: 768, height: 466 }, { width: 768, height: 466 })).toEqual(a);
		expect(rescalePairs(a, { width: 768, height: 466 }, { width: 640, height: 480 })).toBeNull();
	});
});

describe('aiming', () => {
	it('centres the pole and the finished pairs, facing the heading; the pole facing north without one', () => {
		const pole: [number, number] = [-116.3, 43.6];
		expect(aimAt(pole, [], null)).toEqual({ center: pole, bearing: 0, points: [pole] });
		const a = aimAt(pole, [{ pixel: [1, 1], ground: [-116.298, 43.602, 800] }, { ground: [-116.2, 43.7, 800] }], 35);
		expect(a.bearing).toBe(35);
		expect(a.center[0]).toBeCloseTo(-116.299, 9);
		expect(a.center[1]).toBeCloseTo(43.601, 9);
		// Everything with a ground point is to be on screen, the pending pair's too.
		expect(a.points).toEqual([pole, [-116.298, 43.602], [-116.2, 43.7]]);
	});

	/** Where a point lands on a W×H canvas at pitch 0 (MapLibre's projection, 512 px tiles), relative to the top left. */
	const D2R = Math.PI / 180;
	const mx = (lng: number) => (lng + 180) / 360;
	const my = (lat: number) => (1 - Math.log(Math.tan(Math.PI / 4 + (lat * D2R) / 2)) / Math.PI) / 2;
	function screen(p: readonly [number, number], fit: { center: [number, number]; zoom: number }, bearing: number, W: number, H: number, padLeft: number) {
		const k = 512 * 2 ** fit.zoom;
		const e = (mx(p[0]) - mx(fit.center[0])) * k;
		const n = (my(fit.center[1]) - my(p[1])) * k;
		const b = bearing * D2R;
		const sx = e * Math.cos(b) - n * Math.sin(b);
		const sy = e * Math.sin(b) + n * Math.cos(b);
		// The centre sits in the middle of the padded area.
		return { x: padLeft + (W - padLeft) / 2 + sx, y: H / 2 - sy };
	}
	/** A point `m` metres from `from` toward compass `deg`. */
	const toward = (from: [number, number], deg: number, m: number): [number, number] => [
		from[0] + (m * Math.sin(deg * D2R)) / (111_320 * Math.cos(from[1] * D2R)),
		from[1] + (m * Math.cos(deg * D2R)) / 111_320
	];

	it('fits the pole and the pairs beside the panel: z19 at most, z16 at least', () => {
		const pole: [number, number] = [-116.37459, 43.59325];
		const W = 1280;
		const H = 800;
		const padding = { top: 0, right: 0, bottom: 0, left: 580 };
		// A freeway camera looking east, its pairs up to 300 m out and 60 m to either side.
		for (const heading of [92, 0, 215]) {
			const points = [pole, toward(pole, heading, 300), toward(pole, heading + 12, 280), toward(pole, heading - 12, 260), toward(pole, heading, 40)];
			const fit = fitAim({ center: pole, bearing: heading, points }, { width: W, height: H, padding });
			expect(fit.zoom, `heading ${heading}`).toBeLessThan(AIM_ZOOM.max);
			expect(fit.zoom, `heading ${heading}`).toBeGreaterThanOrEqual(AIM_ZOOM.min);
			for (const p of points) {
				const s = screen(p, fit, heading, W, H, padding.left);
				expect(s.x, `heading ${heading}: x`).toBeGreaterThanOrEqual(padding.left + 47.9);
				expect(s.x, `heading ${heading}: x`).toBeLessThanOrEqual(W - 47.9);
				expect(s.y, `heading ${heading}: y`).toBeGreaterThanOrEqual(47.9);
				expect(s.y, `heading ${heading}: y`).toBeLessThanOrEqual(H - 47.9);
			}
		}
		// A close camera's pairs fit at z19 (never closer).
		const near = [pole, toward(pole, 10, 20), toward(pole, 350, 18)];
		expect(fitAim({ center: pole, bearing: 0, points: near }, { width: W, height: H, padding }).zoom).toBe(AIM_ZOOM.max);
		// The pole alone: on it, at z19.
		expect(fitAim({ center: pole, bearing: 0, points: [pole] }, { width: W, height: H, padding })).toEqual({ center: pole, zoom: AIM_ZOOM.max });
		// Pairs 3 km apart don't zoom out past z16.
		expect(fitAim({ center: pole, bearing: 0, points: [pole, toward(pole, 0, 3000)] }, { width: W, height: H, padding }).zoom).toBe(AIM_ZOOM.min);
	});
});

describe('drafts in storage', () => {
	const store = new Map<string, string>();
	beforeEach(() => {
		store.clear();
		vi.stubGlobal('localStorage', {
			getItem: (k: string) => store.get(k) ?? null,
			setItem: (k: string, v: string) => void store.set(k, v),
			removeItem: (k: string) => void store.delete(k)
		});
	});
	afterEach(() => vi.unstubAllGlobals());

	const draft: Draft = { v: 1, cameraId: 59, viewId: 26, frame, pairs: [{ pixel: [1, 2] }, { pixel: [3, 4], ground: [-116, 43, 800] }], base: 12, savedAt: 1 };

	it('round-trip under tvt:v2:calib-draft:<viewId>', () => {
		expect(writeDraft(draft)).toBe(true);
		expect([...store.keys()]).toEqual(['tvt:v2:calib-draft:26']);
		expect(draftKey(26)).toBe('calib-draft:26');
		expect(readDraft(26)).toEqual(draft);
		expect(readDraft(26, 59)).toEqual(draft);
		expect(readDraft(26, 60), "another camera's view id").toBeNull();
		clearDraft(26);
		expect(readDraft(26)).toBeNull();
	});

	it('read garbage as nothing', () => {
		store.set('tvt:v2:calib-draft:26', '{nope');
		expect(readDraft(26)).toBeNull();
		store.set('tvt:v2:calib-draft:26', JSON.stringify({ ...draft, pairs: [{}] }));
		expect(readDraft(26)).toBeNull();
		expect(isDraft({ ...draft, frame: { frame: 'x' } })).toBe(false);
		expect(isDraft({ ...draft, frame: null })).toBe(true);
	});

	it('cope with storage that throws', () => {
		vi.stubGlobal('localStorage', {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			},
			removeItem: () => {
				throw new Error('blocked');
			}
		});
		expect(writeDraft(draft)).toBe(false);
		expect(readDraft(26)).toBeNull();
		expect(() => clearDraft(26)).not.toThrow();
	});
});

describe('"Use this frame"', () => {
	it('posts an archive frame by its image, day and stamp, and an on-demand one by its sha', () => {
		const sha = 'a'.repeat(64);
		expect(frameChoice({ sha, archive: { image: 656, day: '2026-10-07', stamp: '20261007T151240Z' } })).toEqual({
			image: 656,
			day: '2026-10-07',
			stamp: '20261007T151240Z'
		});
		expect(frameChoice({ sha })).toEqual({ sha });
	});
});

describe('ground heights', () => {
	it('divide the drawn height by the exaggeration in force now', () => {
		const ground = 801.2;
		expect(trueHeight(ground * 1.3, 1.3)).toBeCloseTo(ground, 9);
		expect(trueHeight(ground, 1)).toBe(ground);
		expect(Math.abs(trueHeight(ground * 1.3, 1.3) - trueHeight(ground, 1))).toBeLessThan(0.25);
		expect(trueHeight(0, 0)).toBe(0);
	});
});

describe('undo', () => {
	it('pops what was pushed, newest first, within its limit', () => {
		const u = new Undo<number>(3);
		for (const n of [1, 2, 3, 4]) u.push(n);
		expect(u.size).toBe(3);
		expect([u.pop(), u.pop(), u.pop(), u.pop()]).toEqual([4, 3, 2, undefined]);
	});
});

describe('words', () => {
	it('say the fit and each error with a shape, never color alone', () => {
		expect(quality(0.4).text).toBe('great');
		expect(quality(2).word).toBe('good');
		expect(quality(4).text).toMatch(/^rough/);
		expect(quality(9).word).toBe('poor');
		expect(residualMark(1).shape).toBe('●');
		expect(residualMark(3).shape).toBe('▲');
		expect(residualMark(7).shape).toBe('■');
		expect(compass(0)).toBe('N');
		expect(compass(350)).toBe('N');
		expect(compass(-90)).toBe('W');
		expect(compass(135)).toBe('SE');
	});
});

describe('keys', () => {
	const key = (code: string, o: Partial<KeyboardEvent> = {}, target: unknown = null) =>
		calibrateKey({ code, key: '', ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...o, target: target as EventTarget | null });
	const input = { closest: (s: string) => (s.includes('input') ? {} : null) };

	it('Ctrl or Cmd+Z undoes, Delete or Backspace removes, Ctrl or Cmd+S saves', () => {
		expect(key('KeyZ', { ctrlKey: true })).toBe('undo');
		expect(key('KeyZ', { metaKey: true })).toBe('undo');
		expect(key('KeyZ', { metaKey: true, shiftKey: true }), 'redo is not undo').toBeNull();
		expect(key('KeyZ')).toBeNull();
		expect(key('Delete')).toBe('remove');
		expect(key('Backspace')).toBe('remove');
		expect(key('Backspace', { ctrlKey: true })).toBeNull();
		expect(key('KeyS', { ctrlKey: true })).toBe('save');
		expect(key('KeyS', { metaKey: true })).toBe('save');
		expect(key('KeyS')).toBeNull();
	});

	it('leave text fields alone, except Save', () => {
		expect(key('Backspace', {}, input)).toBeNull();
		expect(key('KeyZ', { ctrlKey: true }, input)).toBeNull();
		expect(key('KeyS', { ctrlKey: true }, input)).toBe('save');
	});
});
