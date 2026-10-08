import type { StepKind, TrackStep, TrackVehicle, Tracks } from '#lib/contracts/tracks.js';

/**
 * Bus playback, pure and unit-tested (docs/14 §14.4, "Playback"; WP8).
 *
 * Buses are drawn where they were at the playhead T (the clock's, a little
 * behind live), interpolated between their reported fixes along the steps
 * the tracks API sends:
 *
 * | Step | Position at T |
 * |---|---|
 * | along | constant speed along the step's path between t0 and t1 |
 * | straight | linear between the two fixes |
 * | still | at the fix |
 * | gap | held at the fix, then a 300 ms fade-jump to the next |
 * | newest fix reached | waits there, never extrapolated: "waiting for GPS" under 120 s, hollow (stale) up to 15 min, then hidden |
 *
 * **No jumps at step boundaries.** An along step runs on the route's shape
 * (the fix projected onto it), while a still or straight step starts at the
 * raw GPS fix, a few metres off it; and a bus waiting at a stop reports a
 * slightly different fix every time. So each step starts where the previous
 * one ended (`chain`): a still step holds where the bus already is (up to
 * HOLD_M from its own fix, beyond which it glides there over the step), a
 * straight step or a gap starts there too, and an along step starts there
 * and eases onto its path, the offset shrinking to nothing at its end.
 *
 * The feed merges every poll's steps by (vehicle, t0), so a bus's newest fix
 * (t1 = null) is replaced once the next fix arrives, and prunes steps that
 * ended more than 6 minutes before T. Per frame, `positionAt` does the math
 * for one bus without allocating (it fills an `out` object and keeps a hint
 * of the step it found last).
 */

/** "waiting for GPS" until a bus's newest fix is this old (s), then hollow. */
export const WAIT_S = 120;
/** Hidden once its newest fix is this old (s). */
export const HIDE_S = 900;
/** A gap ends with a fade-jump this long (s, playhead time). */
export const FADE_S = 0.3;
/** Steps that ended this long before T are pruned (s). */
export const KEEP_S = 360;
/** Heading: the path tangent over ± this many metres. */
export const TANGENT_M = 8;
/** Heading low-pass time constant (ms). */
export const HEADING_TAU_MS = 300;
/** Running: some fix of the route in [T − 15 min, T] (§14.4 "Running"). */
export const RUN_WINDOW_S = 900;
/** Trails reach back this far (s). */
export const TRAIL_S = 300;
/** A bus faster than this is a GPS jump, not a bus (m/s); the loop's rate never needs more. */
export const MAX_SPEED = 30;
/** A still step holds where the bus already is while that's within this of its own fix (m); beyond, it glides there. */
export const HOLD_M = 30;

const M_PER_DEG_LAT = 110_574;
const M_PER_DEG_LON_EQ = 111_320;
const DEG = Math.PI / 180;

// -- prepared tracks ------------------------------------------------------------------------------

/** One step, prepared for fast lookups: its path in local metres with cumulative lengths. */
export interface PStep {
	t0: number;
	t1: number | null;
	kind: StepKind | null;
	lon: number;
	lat: number;
	bearing: number | null;
	/** m/s from the API (null: unknown). */
	speed: number | null;
	/** along only: flat lon,lat,… (endpoints included). */
	path: number[] | null;
	/** Cumulative metres at each path vertex (along only). */
	cum: Float64Array | null;
	/** Path length, metres (0 without a path). */
	len: number;
	/** Where the step starts as drawn: where the previous one ended (`chain`), else the fix. */
	slon: number;
	slat: number;
	/** along only: the start's offset from the path's first point, eased out along the step. */
	dlon: number;
	dlat: number;
	/** still only: glide from the start to the fix over the step (the start is more than HOLD_M away). */
	glide: boolean;
}

/** One bus's steps in time order, plus a lookup hint (the step found last). */
export interface Track {
	vid: string;
	steps: PStep[];
	hint: number;
}

/** Metres per degree of longitude at a latitude. */
export const mPerDegLon = (lat: number) => M_PER_DEG_LON_EQ * Math.cos(lat * DEG);

/** Metres between two lon/lat points (equirectangular; fine at bus scale). */
export function metres(lon0: number, lat0: number, lon1: number, lat1: number): number {
	const kx = mPerDegLon((lat0 + lat1) / 2);
	return Math.hypot((lon1 - lon0) * kx, (lat1 - lat0) * M_PER_DEG_LAT);
}

/** Compass bearing (degrees clockwise from north) from one point to another. */
export function bearingTo(lon0: number, lat0: number, lon1: number, lat1: number): number {
	const kx = mPerDegLon((lat0 + lat1) / 2);
	const b = Math.atan2((lon1 - lon0) * kx, (lat1 - lat0) * M_PER_DEG_LAT) / DEG;
	return (b + 360) % 360;
}

export function prepareStep(s: TrackStep): PStep {
	const [, t0, t1, kind, lon, lat, bearing, speed, path] = s;
	let cum: Float64Array | null = null;
	let len = 0;
	if (kind === 'along' && path && path.length >= 4) {
		cum = new Float64Array(path.length / 2);
		for (let i = 2; i < path.length; i += 2) {
			len += metres(path[i - 2], path[i - 1], path[i], path[i + 1]);
			cum[i / 2] = len;
		}
	}
	return { t0, t1, kind, lon, lat, bearing, speed, path: cum ? path : null, cum, len, slon: lon, slat: lat, dlon: 0, dlat: 0, glide: false };
}

/** The key of a bus's step (its vehicle and t0), as the feed merges them. */
export const stepKey = (vid: string, t0: number) => `${vid}\u0000${t0}`;

/** Where a step ends as drawn, given the step after it (which starts at its own fix). */
function endOf(s: PStep, next: PStep): [number, number] {
	if (s.kind === 'along' && s.path) return [s.path[s.path.length - 2], s.path[s.path.length - 1]];
	// A straight step runs to the next fix, and a gap jumps there.
	if (s.kind === 'straight' || s.kind === 'gap') return [next.lon, next.lat];
	// Still (or an along step with no path, drawn still): where it held, or the fix it glided to.
	return s.glide ? [s.lon, s.lat] : [s.slon, s.slat];
}

/**
 * Start each of a bus's steps where the previous one ended (time order;
 * see "No jumps at step boundaries" above). A step with no step just
 * before it (its first, or after one was pruned) starts where `known` says
 * it did last time, else at its fix.
 */
export function chain(vid: string, steps: PStep[], known?: ReadonlyMap<string, readonly [number, number]>): void {
	for (let i = 0; i < steps.length; i++) {
		const s = steps[i];
		const prev = i > 0 ? steps[i - 1] : null;
		let start: readonly [number, number] = [s.lon, s.lat];
		if (prev && prev.t1 !== null && prev.t1 === s.t0) start = endOf(prev, s);
		else start = known?.get(stepKey(vid, s.t0)) ?? start;
		s.slon = start[0];
		s.slat = start[1];
		s.dlon = s.path ? s.slon - s.path[0] : 0;
		s.dlat = s.path ? s.slat - s.path[1] : 0;
		s.glide = s.kind !== 'along' && s.kind !== 'straight' && s.kind !== 'gap' && s.t1 !== null && metres(s.slon, s.slat, s.lon, s.lat) > HOLD_M;
	}
}

/** Steps grouped per bus, in time order, each starting where the one before it ended. */
export function buildTracks(steps: Iterable<TrackStep>, known?: ReadonlyMap<string, readonly [number, number]>): Map<string, Track> {
	const by = new Map<string, Track>();
	for (const s of steps) {
		let t = by.get(s[0]);
		if (!t) by.set(s[0], (t = { vid: s[0], steps: [], hint: 0 }));
		t.steps.push(prepareStep(s));
	}
	for (const t of by.values()) {
		t.steps.sort((a, b) => a.t0 - b.t0);
		chain(t.vid, t.steps, known);
	}
	return by;
}

// -- the feed --------------------------------------------------------------------------------------

const key = (s: TrackStep) => `${s[0]}\u0000${s[1]}`;

/**
 * What the client knows: steps merged from every poll (keyed by vehicle and
 * t0, so a later poll replaces a bus's newest fix), the vehicles, the
 * running spans and the newest fix of any bus.
 */
export class Feed {
	steps = new Map<string, TrackStep>();
	vehicles: Record<string, TrackVehicle> = {};
	routeRuns: Record<string, [number, number][]> = {};
	lastFix: number | null = null;
	/** The server's clock at the last poll (epoch s). */
	now: number | null = null;
	/** Prepared tracks, rebuilt by merge and prune. */
	tracks = new Map<string, Track>();

	/** Merge one poll's answer (`replace`: drop everything first, after a reload). */
	merge(t: Pick<Tracks, 'now' | 'vehicles' | 'steps' | 'routeRuns' | 'lastFix'>, replace = false): void {
		if (replace) {
			this.steps.clear();
			this.vehicles = {};
		}
		for (const s of t.steps) this.steps.set(key(s), s);
		this.vehicles = { ...this.vehicles, ...t.vehicles };
		this.routeRuns = t.routeRuns;
		this.lastFix = t.lastFix;
		this.now = t.now;
		this.#rebuild();
	}

	/**
	 * Drop steps that ended more than KEEP_S before T, and newest fixes past
	 * HIDE_S; vehicles with no step left go too.
	 */
	prune(T: number): void {
		let changed = false;
		for (const [k, s] of this.steps) {
			const end = s[2] ?? s[1] + HIDE_S;
			if (end < T - KEEP_S) {
				this.steps.delete(k);
				changed = true;
			}
		}
		if (changed) this.#rebuild();
	}

	/** Where each step started as drawn, so pruning the steps before one doesn't move it. */
	#starts = new Map<string, readonly [number, number]>();

	#rebuild() {
		const hints = new Map([...this.tracks].map(([vid, t]) => [vid, t.hint]));
		this.tracks = buildTracks(this.steps.values(), this.#starts);
		const starts = new Map<string, readonly [number, number]>();
		for (const [vid, t] of this.tracks) {
			t.hint = Math.min(hints.get(vid) ?? 0, t.steps.length - 1);
			for (const s of t.steps) starts.set(stepKey(vid, s.t0), [s.slon, s.slat]);
		}
		this.#starts = starts;
		const vehicles: Record<string, TrackVehicle> = {};
		for (const vid of this.tracks.keys()) if (this.vehicles[vid]) vehicles[vid] = this.vehicles[vid];
		this.vehicles = vehicles;
	}
}

// -- positions -------------------------------------------------------------------------------------

export type BusState = 'moving' | 'still' | 'gap' | 'waiting' | 'stale' | 'hidden';

/** Where a bus is at T (filled in place by `positionAt`). */
export interface BusAt {
	lon: number;
	lat: number;
	/** The heading to turn toward (degrees), or null to keep the current one. */
	heading: number | null;
	/** m/s right now (0 when not moving). */
	speed: number;
	state: BusState;
	opacity: number;
	/** The newest fix at or before T (epoch s). */
	fix: number;
	/** The step being played (null at a newest fix). */
	kind: StepKind | null;
	/** m/s of the step being played, as the card says it (null: unknown). */
	stepSpeed: number | null;
}

export const busAt = (): BusAt => ({ lon: 0, lat: 0, heading: null, speed: 0, state: 'hidden', opacity: 0, fix: 0, kind: null, stepSpeed: null });

/** The index of the last step with t0 ≤ T (−1: none), searching from the hint. */
export function stepIndex(track: Track, T: number): number {
	const s = track.steps;
	if (!s.length || T < s[0].t0) return -1;
	let i = Math.min(Math.max(track.hint, 0), s.length - 1);
	if (s[i].t0 > T) {
		while (i > 0 && s[i].t0 > T) i--;
	} else {
		while (i + 1 < s.length && s[i + 1].t0 <= T) i++;
	}
	track.hint = i;
	return i;
}

/**
 * A point `d` metres along a prepared path, into out.lon/out.lat, plus the
 * step's start offset eased out along it (all of it at 0 m, none at the end).
 */
function along(step: PStep, d: number, out: { lon: number; lat: number }): void {
	const path = step.path!;
	const cum = step.cum!;
	const n = cum.length;
	if (d <= 0) {
		out.lon = step.slon;
		out.lat = step.slat;
		return;
	}
	if (d >= step.len) {
		out.lon = path[2 * n - 2];
		out.lat = path[2 * n - 1];
		return;
	}
	let lo = 0;
	let hi = n - 1;
	while (hi - lo > 1) {
		const mid = (lo + hi) >> 1;
		if (cum[mid] <= d) lo = mid;
		else hi = mid;
	}
	const span = cum[hi] - cum[lo];
	const f = span > 0 ? (d - cum[lo]) / span : 0;
	const ease = 1 - d / step.len;
	out.lon = path[2 * lo] + (path[2 * hi] - path[2 * lo]) * f + step.dlon * ease;
	out.lat = path[2 * lo + 1] + (path[2 * hi + 1] - path[2 * lo + 1]) * f + step.dlat * ease;
}

const p0 = { lon: 0, lat: 0 };
const p1 = { lon: 0, lat: 0 };

/** The path tangent at `d` metres (over ±TANGENT_M), as a bearing; null on a zero-length path. */
function tangent(step: PStep, d: number): number | null {
	along(step, Math.max(0, d - TANGENT_M), p0);
	along(step, Math.min(step.len, d + TANGENT_M), p1);
	if (p0.lon === p1.lon && p0.lat === p1.lat) return null;
	return bearingTo(p0.lon, p0.lat, p1.lon, p1.lat);
}

/** Wait at a reached newest fix: waiting, then stale, then hidden. */
function waitAt(out: BusAt, lon: number, lat: number, age: number, fix: number, heading: number | null): BusAt {
	out.lon = lon;
	out.lat = lat;
	out.speed = 0;
	out.kind = null;
	out.stepSpeed = 0;
	out.fix = fix;
	out.heading = heading;
	if (age > HIDE_S) {
		out.state = 'hidden';
		out.opacity = 0;
	} else {
		out.state = age < WAIT_S ? 'waiting' : 'stale';
		out.opacity = 1;
	}
	return out;
}

/** Where a bus is at T. Fills and returns `out`. */
export function positionAt(track: Track, T: number, out: BusAt = busAt()): BusAt {
	const i = stepIndex(track, T);
	if (i < 0) {
		out.state = 'hidden';
		out.opacity = 0;
		out.speed = 0;
		out.heading = null;
		out.kind = null;
		out.stepSpeed = null;
		return out;
	}
	const s = track.steps[i];
	const next = i + 1 < track.steps.length && track.steps[i + 1].t0 === s.t1 ? track.steps[i + 1] : null;
	const first = i === 0;
	// The newest fix: wait there (where the step before it ended).
	if (s.t1 === null) return waitAt(out, s.slon, s.slat, T - s.t0, s.t0, first ? s.bearing : null);
	// The step is over but the next fix hasn't arrived: wait at its end when known, else where it started.
	if (T >= s.t1) {
		if (s.kind === 'along' && s.path) {
			const n = s.path.length;
			return waitAt(out, s.path[n - 2], s.path[n - 1], T - s.t1, s.t1, null);
		}
		return s.glide
			? waitAt(out, s.lon, s.lat, T - s.t0, s.t0, s.bearing)
			: waitAt(out, s.slon, s.slat, T - s.t0, s.t0, s.kind === 'still' ? s.bearing : null);
	}
	const dt = s.t1 - s.t0;
	const f = dt > 0 ? (T - s.t0) / dt : 1;
	out.fix = s.t0;
	out.kind = s.kind;
	out.opacity = 1;
	switch (s.kind) {
		case 'along': {
			if (!s.path) break;
			const d = f * s.len;
			along(s, d, out);
			out.heading = tangent(s, d);
			const v = s.speed ?? (dt > 0 ? s.len / dt : 0);
			out.speed = Math.min(v, MAX_SPEED);
			out.stepSpeed = v;
			out.state = v > 0.3 ? 'moving' : 'still';
			return out;
		}
		case 'straight': {
			if (!next) break;
			out.lon = s.slon + (next.slon - s.slon) * f;
			out.lat = s.slat + (next.slat - s.slat) * f;
			const chord = metres(s.slon, s.slat, next.slon, next.slat);
			out.heading = chord >= 1 ? bearingTo(s.slon, s.slat, next.slon, next.slat) : null;
			const v = s.speed ?? (dt > 0 ? chord / dt : 0);
			out.speed = Math.min(v, MAX_SPEED);
			out.stepSpeed = v;
			out.state = v > 0.3 ? 'moving' : 'still';
			return out;
		}
		case 'gap': {
			const fadeFrom = s.t1 - FADE_S;
			out.speed = 0;
			out.stepSpeed = null;
			out.heading = null;
			out.state = 'gap';
			if (next && T >= fadeFrom) {
				const g = (T - fadeFrom) / FADE_S;
				const there = g >= 0.5;
				out.lon = there ? next.slon : s.slon;
				out.lat = there ? next.slat : s.slat;
				out.opacity = Math.abs(1 - 2 * g);
			} else {
				out.lon = s.slon;
				out.lat = s.slat;
			}
			return out;
		}
		default:
			break;
	}
	// still (or a step that can't be drawn): where the bus already is, or gliding to its fix.
	out.speed = 0;
	if (s.glide) {
		out.lon = s.slon + (s.lon - s.slon) * f;
		out.lat = s.slat + (s.lat - s.slat) * f;
		// Slow, but the loop needs to know it moves.
		out.speed = dt > 0 ? Math.min(metres(s.slon, s.slat, s.lon, s.lat) / dt, MAX_SPEED) : 0;
	} else {
		out.lon = s.slon;
		out.lat = s.slat;
	}
	out.stepSpeed = 0;
	out.heading = s.kind === 'still' || first ? s.bearing : null;
	out.state = 'still';
	return out;
}

/** Turn `from` toward `to` (degrees) with a low-pass of time constant `tauMs` over `dtMs`. */
export function smoothAngle(from: number | null, to: number | null, dtMs: number, tauMs = HEADING_TAU_MS): number | null {
	if (to === null) return from;
	if (from === null) return to;
	if (!(dtMs > 0)) return from;
	const diff = ((((to - from) % 360) + 540) % 360) - 180;
	const k = 1 - Math.exp(-dtMs / tauMs);
	return (from + diff * k + 360) % 360;
}

// -- running routes --------------------------------------------------------------------------------

/** §14.4 "Running": a route runs at T iff some span starts at or before T and ends at or after T − 900 s. */
export function runningAt(runs: Record<string, [number, number][]>, T: number): Set<string> {
	const out = new Set<string>();
	for (const route in runs) {
		const spans = runs[route];
		for (let i = 0; i < spans.length; i++) {
			if (spans[i][0] <= T && spans[i][1] >= T - RUN_WINDOW_S) {
				out.add(route);
				break;
			}
		}
	}
	return out;
}

export function sameSet<T>(a: ReadonlySet<T>, b: ReadonlySet<T>): boolean {
	if (a.size !== b.size) return false;
	for (const x of a) if (!b.has(x)) return false;
	return true;
}

// -- trails ----------------------------------------------------------------------------------------

/**
 * One bus's breadcrumb over [T − TRAIL_S, T] as lines of flat lon,lat: along
 * the step paths, straight between fixes, broken at gaps, ending where the
 * bus is now.
 */
export function trail(track: Track, T: number, now: BusAt, windowS = TRAIL_S): number[][] {
	const lines: number[][] = [];
	let line: number[] = [];
	const push = (lon: number, lat: number) => {
		const n = line.length;
		if (n && line[n - 2] === lon && line[n - 1] === lat) return;
		line.push(lon, lat);
	};
	const from = T - windowS;
	const tmp = { lon: 0, lat: 0 };
	for (let i = 0; i < track.steps.length; i++) {
		const s = track.steps[i];
		if (s.t0 > T) break;
		const end = s.t1 ?? T;
		if (end < from) continue;
		if (s.kind === 'gap') {
			if (line.length >= 4) lines.push(line);
			line = [];
			continue;
		}
		const a = s.t1 && s.t1 > s.t0 ? Math.max(0, (from - s.t0) / (s.t1 - s.t0)) : 0;
		const b = s.t1 && s.t1 > s.t0 ? Math.min(1, (T - s.t0) / (s.t1 - s.t0)) : 0;
		if (s.kind === 'along' && s.path && s.cum) {
			along(s, a * s.len, tmp);
			push(tmp.lon, tmp.lat);
			for (let k = 0; k < s.cum.length; k++) {
				const d = s.cum[k];
				if (d > a * s.len && d < b * s.len) push(s.path[2 * k], s.path[2 * k + 1]);
			}
			along(s, b * s.len, tmp);
			push(tmp.lon, tmp.lat);
		} else push(s.slon, s.slat);
	}
	if (now.state !== 'hidden' && now.state !== 'gap') push(now.lon, now.lat);
	if (line.length >= 4) lines.push(line);
	return lines;
}

// -- words -----------------------------------------------------------------------------------------

/** "18 mph", or "stopped". */
export function speedText(ms: number | null): string | null {
	if (ms === null) return null;
	const mph = ms * 2.236936;
	return mph < 1 ? 'stopped' : `${Math.round(mph)} mph`;
}
