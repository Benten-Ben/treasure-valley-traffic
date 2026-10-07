import type { CadenceClass, LiveView } from '#lib/contracts/live.js';

/**
 * How fresh a camera picture is, in shapes and words (docs/14 §14.6
 * "Freshness"; §14.3 "never color alone"). Pure, so the windows (WP12), the
 * road-weather tabs (WP16), look-through and calibration all say it the same
 * way.
 *
 * Age is "seen" time: when our server first got that picture (repeats are
 * dropped). The UI says "seen", never "taken": the time printed under the
 * picture is ACHD's own clock.
 *
 * | Cadence | ● live | ▲ late | ■ stale | ◌ |
 * |---|---|---|---|---|
 * | key cameras and 511 on demand | ≤ 3 min | ≤ 10 min | > 10 min | no picture yet |
 * | road-weather views | < 20 min | ≤ 45 min | > 45 min | no picture yet |
 *
 * (The road-weather numbers follow §14.6 "Road weather", which 511's
 * 15-minute refresh set after the "Live images" table's 30/60.) A picture
 * that can't be had now (robots.txt says no, the on-demand limit, an error,
 * live images off) is ■ with its own word and the reason.
 */
export type FreshnessKind = 'fresh' | 'late' | 'stale' | 'waiting' | 'blocked' | 'capped' | 'offline' | 'off' | 'no_image';

export interface Shown {
	kind: FreshnessKind;
	/** ● ▲ ■ ◌: the shape carries the status, never the color alone. */
	shape: '●' | '▲' | '■' | '◌';
	/** One word (or two): "live", "late", "stale", "offline"… */
	word: string;
	/** The shape's color (a CSS value); the word stays ink. */
	color: string;
	/** The longer explanation, for the tooltip. */
	detail: string;
}

/** Seconds: a picture seen within `fresh` is live, within `late` is late, else stale. */
export const THRESHOLDS: Readonly<Record<CadenceClass, { fresh: number; late: number }>> = {
	key: { fresh: 180, late: 600 },
	on_demand: { fresh: 180, late: 600 },
	road_weather: { fresh: 20 * 60, late: 45 * 60 }
};

const TEAL = 'var(--accent-2)';
const AMBER = 'var(--accent)';
const MAGENTA = 'var(--alert)';
const SOFT = 'var(--ink-soft)';

export const BLOCKED_TEXT = "robots.txt doesn't allow it right now";
export const SEEN_NOTE = "Seen: when our server first got this picture. The time printed under the picture is ACHD's own clock.";

/** Fresh, late or stale, by age and cadence class. */
export function freshness(ageS: number, cadence: CadenceClass): 'fresh' | 'late' | 'stale' {
	const t = THRESHOLDS[cadence] ?? THRESHOLDS.key;
	if (cadence === 'road_weather' ? ageS < t.fresh : ageS <= t.fresh) return 'fresh';
	return ageS <= t.late ? 'late' : 'stale';
}

/** "0:48", "12:05", "1 h 05 min", "2 days": how long ago, for "seen … ago". */
export function formatAge(s: number): string {
	const t = Math.max(0, Math.floor(s));
	if (t < 3600) return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
	if (t < 86_400) return `${Math.floor(t / 3600)} h ${String(Math.floor((t % 3600) / 60)).padStart(2, '0')} min`;
	const d = Math.floor(t / 86_400);
	return `${d} day${d === 1 ? '' : 's'}`;
}

/** "updates about every minute", "updates about every 10 minutes". */
export function cadenceText(cadenceS: number, onDemand = false): string {
	const min = Math.round(cadenceS / 60);
	const every = min <= 1 ? 'about every minute' : `about every ${min} minutes`;
	return `updates ${every}${onDemand ? ' while open' : ''}`;
}

/** How far through its cadence a picture is (0 just seen, 1 a next one is due): the ring around the dot. */
export function ringProgress(ageS: number, cadenceS: number): number {
	if (!(cadenceS > 0) || !Number.isFinite(ageS)) return 1;
	return Math.min(1, Math.max(0, ageS / cadenceS));
}

/**
 * What a view's picture is now: from the live answer (`null` before the
 * first) and the picture's age in seconds (when it has one).
 */
export function shown(view: LiveView | null, ageS: number | null): Shown {
	if (!view) return { kind: 'waiting', shape: '◌', word: 'waiting', color: SOFT, detail: 'Asking for the newest picture…' };
	switch (view.state) {
		case 'disabled':
			return { kind: 'off', shape: '■', word: 'off', color: MAGENTA, detail: view.reason ?? 'Live camera images are off' };
		case 'no_image':
			return { kind: 'no_image', shape: '■', word: 'not on 511', color: SOFT, detail: view.reason ?? 'Not on 511 Idaho' };
		case 'blocked':
			return { kind: 'blocked', shape: '■', word: 'blocked', color: MAGENTA, detail: view.reason ?? BLOCKED_TEXT };
		case 'capped':
			return { kind: 'capped', shape: '■', word: 'limit reached', color: MAGENTA, detail: view.reason ?? 'On-demand limit reached' };
		case 'error':
			return { kind: 'offline', shape: '■', word: 'offline', color: MAGENTA, detail: view.reason ?? "Couldn't get a picture" };
	}
	if (!view.frame || ageS === null) {
		return { kind: 'waiting', shape: '◌', word: 'no picture yet', color: SOFT, detail: view.reason ?? 'Waiting for the first picture' };
	}
	const f = freshness(ageS, view.cadence);
	const t = THRESHOLDS[view.cadence] ?? THRESHOLDS.key;
	const mins = (s: number) => `${Math.round(s / 60)} min`;
	if (f === 'fresh') return { kind: 'fresh', shape: '●', word: 'live', color: TEAL, detail: `Seen ${formatAge(ageS)} ago (live: within ${mins(t.fresh)})` };
	if (f === 'late') return { kind: 'late', shape: '▲', word: 'late', color: AMBER, detail: `Seen ${formatAge(ageS)} ago: no new picture for over ${mins(t.fresh)}` };
	return { kind: 'stale', shape: '■', word: 'stale', color: MAGENTA, detail: `Seen ${formatAge(ageS)} ago: no new picture for over ${mins(t.late)}` };
}

/** "seen 0:48 ago · updates about every minute" (or "no picture yet · …"). */
export function footText(view: LiveView | null, ageS: number | null): string {
	const cadence = view ? cadenceText(view.cadenceS, view.source === '511') : '';
	const seen = view?.frame && ageS !== null ? `seen ${formatAge(ageS)} ago` : 'no picture yet';
	return cadence ? `${seen} · ${cadence}` : seen;
}

/**
 * The image-size check (§14.6, "Camera windows"): a live picture whose size
 * differs from the calibration's can't be looked through until the camera is
 * recalibrated. Null when the sizes agree (or either is unknown).
 */
export function sizeChanged(
	frame: { width: number; height: number } | null | undefined,
	cal: { imageWidth: number; imageHeight: number } | null | undefined
): string | null {
	if (!frame || !cal || !frame.width || !cal.imageWidth) return null;
	if (frame.width === cal.imageWidth && frame.height === cal.imageHeight) return null;
	return `Image size changed (${cal.imageWidth}×${cal.imageHeight} → ${frame.width}×${frame.height}); recalibrate`;
}
