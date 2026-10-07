import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	clearDraft,
	compass,
	complete,
	draftKey,
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
