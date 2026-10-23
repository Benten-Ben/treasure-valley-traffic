import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPropertyExpression, latest } from '@maplibre/maplibre-gl-style-spec';
import type { BaseLive } from '#lib/base/types.js';
import { lineWidth } from './palette.js';
import {
	applySeason,
	canalSeason,
	forgetSeason,
	HAIRLINE_PX,
	isLegalWindow,
	loadSeason,
	POLL_MS,
	readSeason,
	reachStates,
	RETRY_MS,
	SEASON_SOURCE,
	SEASON_SOURCE_LAYER,
	SEASON_URL,
	seasonLive,
	seasonPaint,
	seasonWords,
	windowText,
	type Season,
	type SeasonCanal,
	type SeasonMap,
	type SeasonState
} from './season.js';

/** A lifecycle as the API answers it: made-up canals, ids and gauge. */
const canal = (o: Partial<SeasonCanal> = {}): SeasonCanal => ({
	id: 1,
	name: 'Example Canal',
	state: 'on',
	basis: 'gauge',
	since: '2030-03-01T00:00:00.000Z',
	until: null,
	why: null,
	gauge: 'XTEST1',
	gauge_name: 'Example Canal Diversion at Nowhere',
	district: null,
	off_announced: null,
	end_from: null,
	season: null,
	credit: [0],
	republish: 'yes',
	...o
});

const answer = (o: Partial<Season> = {}): Season => ({
	canals: [canal()],
	reaches: { on: [], off: [], unknown: [] },
	credits: ['NOAA National Weather Service (NWPS), gauge XTEST1'],
	updated: '2030-03-01T00:00:00.000Z',
	republish: 'yes',
	license: 'x',
	...o
});

// -- the paint ------------------------------------------------------------------------------------------------------

type Evaluator = { evaluate(g: unknown, f: unknown, s: unknown): number };
const parsed = new Map<string, Evaluator>();

function paintAt(prop: 'line-width' | 'line-gap-width', width_m: number | undefined, zoom: number, season?: string): number {
	let e = parsed.get(prop);
	if (!e) {
		const spec = (latest as { paint_line: Record<string, unknown> }).paint_line[prop];
		const p = createPropertyExpression(seasonPaint()[prop] as never, prop, spec as never);
		if (p.result !== 'success') throw new Error(`${prop} does not parse: ${JSON.stringify(p.value)}`);
		parsed.set(prop, (e = p.value as Evaluator));
	}
	return e.evaluate({ zoom }, { type: 2, properties: width_m === undefined ? {} : { width_m } }, season ? { season } : {});
}

function todaysWidth(width_m: number | undefined, zoom: number): number {
	const parsed = createPropertyExpression(lineWidth() as never, 'line-width', (latest as { paint_line: Record<string, unknown> }).paint_line['line-width'] as never);
	if (parsed.result !== 'success') throw new Error('line-width does not parse');
	return (parsed.value as { evaluate(g: unknown, f: unknown): number }).evaluate({ zoom }, { type: 2, properties: width_m === undefined ? {} : { width_m } });
}

describe('the season’s paint', () => {
	it('is the reach layer’s own width for a canal that is on, has no state, or is under 3 px', () => {
		for (const z of [8, 12, 14, 15, 16, 17, 19, 22]) {
			for (const width_m of [0.5, 1.5, 4, 14]) {
				const today = todaysWidth(width_m, z);
				for (const state of [undefined, 'on']) {
					expect(paintAt('line-width', width_m, z, state), `${state} z${z} ${width_m} m`).toBeCloseTo(today, 6);
					expect(paintAt('line-gap-width', width_m, z, state)).toBe(0);
				}
				if (today < 3) {
					// Under 3 px nothing changes at all, whatever the state.
					for (const state of ['off', 'unknown']) expect(paintAt('line-width', width_m, z, state), `${state} z${z} ${width_m} m`).toBeCloseTo(today, 6);
				}
			}
		}
		// A tile with no width_m reads 1 m, as today.
		expect(paintAt('line-width', undefined, 17, 'on')).toBeCloseTo(todaysWidth(undefined, 17), 6);
	});

	it('draws an off canal as two thin edges at its true footprint, in the same colour (no casing)', () => {
		// A 14 m main canal is 8 px at z15, 16 px at z16: edges of a quarter of the width, between 0.6 and 1.2 px.
		for (const z of [15, 16, 17, 18]) {
			const on = paintAt('line-width', 14, z);
			const edge = paintAt('line-width', 14, z, 'off');
			const gap = paintAt('line-gap-width', 14, z, 'off');
			expect(edge, `z${z}`).toBeCloseTo(Math.max(0.6, Math.min(1.2, on / 4)), 6);
			expect(gap + 2 * edge, `the footprint at z${z}`).toBeCloseTo(on, 6);
			expect(gap).toBeGreaterThan(0);
		}
		// A 4 m lateral is hollow from the whole zoom where it reaches 3 px (z16 here), and plain before it.
		expect(paintAt('line-gap-width', 4, 15, 'off')).toBe(0);
		expect(paintAt('line-gap-width', 4, 16, 'off')).toBeGreaterThan(0);
		expect(paintAt('line-width', 4, 15, 'off')).toBeCloseTo(todaysWidth(4, 15), 6);
		// Half a zoom on, a line keeps the look of the whole zoom it is past, and its footprint never jumps to a doubled line.
		const half = paintAt('line-width', 4, 15.5, 'off') + paintAt('line-gap-width', 4, 15.5, 'off');
		expect(half).toBeLessThanOrEqual(todaysWidth(4, 15.5) + 1e-2);
	});

	it('draws an unknown canal as a thin centre line in the same colour, where it is wide enough', () => {
		expect(paintAt('line-width', 14, 16, 'unknown')).toBe(HAIRLINE_PX);
		expect(paintAt('line-gap-width', 14, 16, 'unknown')).toBe(0);
		expect(paintAt('line-width', 14, 22, 'unknown')).toBe(HAIRLINE_PX);
		// Too thin to carry a cue: as today.
		expect(paintAt('line-width', 1.5, 16, 'unknown')).toBeCloseTo(todaysWidth(1.5, 16), 6);
		// There is no dash to draw it with: the paint is only the width and the gap.
		expect(Object.keys(seasonPaint()).sort()).toEqual(['line-gap-width', 'line-width']);
	});

	it('reads a state it does not know as no state', () => {
		expect(paintAt('line-width', 14, 16, 'sideways')).toBeCloseTo(todaysWidth(14, 16), 6);
		expect(paintAt('line-gap-width', 14, 16, 'sideways')).toBe(0);
	});
});

// -- the words ----------------------------------------------------------------------------------------------------

describe('the card’s words', () => {
	it('names the gauge for a canal that is on or off by its reading', () => {
		expect(seasonWords(canal({ state: 'off' }))).toBe('off (gauge XTEST1, Example Canal Diversion at Nowhere)');
		expect(seasonWords(canal({ state: 'on' }))).toBe('on (gauge XTEST1, Example Canal Diversion at Nowhere)');
	});

	it('says unknown after 48 hours without a reading, and that it is the gauge’s silence', () => {
		const words = seasonWords(canal({ state: 'unknown' }));
		expect(words).toBe('unknown: no reading for 48 hours (gauge XTEST1)');
		expect(words).not.toMatch(/\bon\b|\boff\b/);
	});

	it('labels a legal-window state as the legal window, not delivery dates', () => {
		const inside = canal({ basis: 'legal', gauge: null, gauge_name: null, state: 'on', season: '3/1 - 11/15', republish: 'internal' });
		const outside = canal({ basis: 'legal', gauge: null, gauge_name: null, state: 'off', season: '3/1 - 11/15', republish: 'internal' });
		expect(seasonWords(inside)).toBe("in IDWR's legal irrigation season (3/1 – 11/15), not delivery dates");
		expect(seasonWords(outside)).toBe("outside IDWR's legal irrigation season (3/1 – 11/15), not delivery dates");
		expect(isLegalWindow(inside)).toBe(true);
		expect(isLegalWindow(canal())).toBe(false);
		expect(windowText('3/1 - 11/15')).toBe('3/1 – 11/15');
	});

	it('says so when a district’s span ends on IDWR’s date, and when its shut-off is not announced', () => {
		const ends = canal({ basis: 'district', district: 'Example Irrigation District', end_from: 'legal', season: '3/1 - 11/15', gauge: null, gauge_name: null });
		expect(seasonWords(ends)).toContain("Example Irrigation District's dates");
		expect(seasonWords(ends)).toContain("until IDWR's legal season ends");
		expect(isLegalWindow(ends)).toBe(true);
		const plain = canal({ basis: 'district', district: 'Example Irrigation District', state: 'off', gauge: null, gauge_name: null });
		expect(seasonWords(plain)).toBe("off (Example Irrigation District's dates)");
		expect(isLegalWindow(plain)).toBe(false);
	});

	it('words a canal that never switches off and a canal with no lifecycle', () => {
		expect(seasonWords(canal({ basis: 'always', why: 'a drain; drains and creeks never switch off', gauge: null }))).toBe('on all year (a drain; drains and creeks never switch off)');
		expect(seasonWords(null)).toMatch(/^unknown/);
		expect(seasonWords(canal({ basis: 'none', state: 'unknown' }))).toMatch(/^unknown/);
	});
});

// -- the answer ---------------------------------------------------------------------------------------------------

describe('reading the answer', () => {
	it('maps each reach to its canal’s state and finds a canal by id', () => {
		const s = answer({ canals: [canal({ id: 1 }), canal({ id: 2, state: 'off' })], reaches: { on: [10, 11], off: [20], unknown: [30] } });
		expect([...reachStates(s)]).toEqual([
			[10, 'on'],
			[11, 'on'],
			[20, 'off'],
			[30, 'unknown']
		]);
		expect(canalSeason(s, 2)?.state).toBe('off');
		expect(canalSeason(s, 99)).toBeNull();
		expect(canalSeason(null, 1)).toBeNull();
	});

	it('reads a reach named by two states as unknown, never on', () => {
		expect(reachStates(answer({ reaches: { on: [5], off: [5], unknown: [] } })).get(5)).toBe('unknown');
	});

	it('refuses a malformed answer, reads an unknown state as unknown, and drops ids that are not whole numbers', () => {
		expect(() => readSeason(null)).toThrow();
		expect(() => readSeason({ nope: true })).toThrow();
		const s = readSeason({ canals: [{ id: 1, state: 'maybe', basis: 'gauge', credit: [0, 'x'] }], reaches: { on: [1, 'a', 2.5, 3], off: 'no' } });
		expect(s.canals[0].state).toBe('unknown');
		expect(s.canals[0].credit).toEqual([0]);
		expect(s.reaches).toEqual({ on: [1, 3], off: [], unknown: [] });
	});
});

// -- the hook ---------------------------------------------------------------------------------------------------

/** A map that keeps feature-state per id, as the hook sees it. */
function fakeMap(opts: { source?: boolean } = {}) {
	const state = new Map<number, SeasonState>();
	const calls = { set: 0, remove: 0 };
	const handlers = new Map<string, Set<() => void>>();
	const hasSource = { value: opts.source ?? true };
	const map = {
		getSource: (id: string) => (id === SEASON_SOURCE && hasSource.value ? {} : undefined),
		setFeatureState(t: { source: string; sourceLayer: string; id: number }, s: { season: SeasonState }) {
			expect(t.source).toBe(SEASON_SOURCE);
			expect(t.sourceLayer).toBe(SEASON_SOURCE_LAYER);
			calls.set++;
			state.set(t.id, s.season);
		},
		removeFeatureState(t: { id: number }, key?: string) {
			expect(key).toBe('season');
			calls.remove++;
			state.delete(t.id);
		},
		getFeatureState: (t: { id: number }) => (state.has(t.id) ? { season: state.get(t.id) } : {}),
		on(type: string, f: () => void) {
			(handlers.get(type) ?? handlers.set(type, new Set()).get(type)!).add(f);
		},
		off(type: string, f: () => void) {
			handlers.get(type)?.delete(f);
		}
	};
	return { map: map as SeasonMap, state, calls, emit: (t: string) => handlers.get(t)?.forEach((f) => f()), handlers, hasSource };
}

const ok = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: async () => body });

describe('putting the state on the reaches', () => {
	it('sets feature-state by reach id, changing only what differs, and clears a reach that left the answer', () => {
		const f = fakeMap();
		let drawn = applySeason(f.map, new Map<number, SeasonState>([[1, 'on'], [2, 'off']]), new Map());
		expect(f.calls.set).toBe(2);
		drawn = applySeason(f.map, new Map<number, SeasonState>([[1, 'on'], [2, 'unknown'], [3, 'off']]), drawn);
		expect(f.calls.set).toBe(4);
		expect([...f.state]).toEqual([[1, 'on'], [2, 'unknown'], [3, 'off']]);
		drawn = applySeason(f.map, new Map([[3, 'off' as SeasonState]]), drawn);
		expect(f.calls.remove).toBe(2);
		expect([...f.state]).toEqual([[3, 'off']]);
		expect([...drawn]).toEqual([[3, 'off']]);
	});

	it('draws nothing while the landscape source is not on the map, and keeps what it had', () => {
		const f = fakeMap({ source: false });
		const had = new Map<number, SeasonState>([[9, 'on']]);
		const out = applySeason(f.map, new Map([[1, 'off' as SeasonState]]), had);
		expect(f.calls.set + f.calls.remove).toBe(0);
		expect([...out]).toEqual([[9, 'on']]);
	});
});

describe('the live hook', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		forgetSeason();
	});
	afterEach(() => {
		vi.useRealTimers();
		forgetSeason();
	});

	const live = (f: ReturnType<typeof fakeMap>) => ({ map: f.map, app: {}, layerIds: [] }) as unknown as BaseLive;

	it('loads the season, sets the states, polls every 15 minutes and stops on cleanup, removing its states', async () => {
		const f = fakeMap();
		const asked: string[] = [];
		let body = answer({ reaches: { on: [1], off: [2], unknown: [3] } });
		const stop = seasonLive(live(f), {
			fetch: (url) => {
				asked.push(url);
				return ok(body);
			}
		});
		await vi.advanceTimersByTimeAsync(0);
		expect(asked).toEqual([SEASON_URL]);
		expect([...f.state]).toEqual([[1, 'on'], [2, 'off'], [3, 'unknown']]);
		// Nothing changes until the poll is due.
		await vi.advanceTimersByTimeAsync(POLL_MS - 1000);
		expect(asked).toHaveLength(1);
		body = answer({ reaches: { on: [1], off: [], unknown: [2] } });
		await vi.advanceTimersByTimeAsync(1000);
		expect(asked).toHaveLength(2);
		expect([...f.state].sort()).toEqual([[1, 'on'], [2, 'unknown']]);
		stop();
		expect(f.state.size).toBe(0);
		expect(f.handlers.get('styledata')?.size).toBe(0);
		await vi.advanceTimersByTimeAsync(POLL_MS * 3);
		expect(asked).toHaveLength(2);
	});

	it('keeps what is drawn when a poll fails and tries again sooner', async () => {
		const f = fakeMap();
		let fail = false;
		let calls = 0;
		const stop = seasonLive(live(f), {
			fetch: () => {
				calls++;
				return fail ? Promise.reject(new Error('down')) : ok(answer({ reaches: { on: [], off: [7], unknown: [] } }));
			}
		});
		await vi.advanceTimersByTimeAsync(0);
		expect([...f.state]).toEqual([[7, 'off']]);
		fail = true;
		await vi.advanceTimersByTimeAsync(POLL_MS);
		expect(calls).toBe(2);
		expect([...f.state]).toEqual([[7, 'off']]);
		fail = false;
		await vi.advanceTimersByTimeAsync(RETRY_MS);
		expect(calls).toBe(3);
		await vi.advanceTimersByTimeAsync(RETRY_MS);
		expect(calls).toBe(3);
		stop();
	});

	it('draws no state it did not read: an HTTP error or a bad answer leaves the reaches as today', async () => {
		const f = fakeMap();
		const stop = seasonLive(live(f), { fetch: () => Promise.resolve({ ok: false, status: 500, json: async () => ({}) }) });
		await vi.advanceTimersByTimeAsync(0);
		expect(f.state.size).toBe(0);
		stop();
		const g = fakeMap();
		const stop2 = seasonLive(live(g), { fetch: () => ok({ nothing: 1 }) });
		await vi.advanceTimersByTimeAsync(0);
		expect(g.state.size).toBe(0);
		stop2();
	});

	it('puts the states back when a style change drops them', async () => {
		const f = fakeMap();
		const stop = seasonLive(live(f), { fetch: () => ok(answer({ reaches: { on: [1], off: [2], unknown: [] } })) });
		await vi.advanceTimersByTimeAsync(0);
		f.emit('styledata');
		expect(f.calls.set).toBe(2);
		f.state.clear();
		f.emit('styledata');
		expect([...f.state]).toEqual([[1, 'on'], [2, 'off']]);
		stop();
	});
});

describe('loading the season', () => {
	beforeEach(forgetSeason);
	afterEach(forgetSeason);

	it('asks once for a minute, again when asked fresh, and forgets a failure', async () => {
		let calls = 0;
		const get = () => {
			calls++;
			return ok(answer());
		};
		await loadSeason({ fetch: get, now: 0 });
		await loadSeason({ fetch: get, now: 30_000 });
		expect(calls).toBe(1);
		await loadSeason({ fetch: get, now: 61_000 });
		expect(calls).toBe(2);
		await loadSeason({ fetch: get, now: 61_500, fresh: true });
		expect(calls).toBe(3);
		forgetSeason();
		await expect(loadSeason({ fetch: () => Promise.resolve({ ok: false, status: 503, json: async () => ({}) }), now: 0 })).rejects.toThrow('503');
		await loadSeason({ fetch: get, now: 1 });
		expect(calls).toBe(4);
	});
});
