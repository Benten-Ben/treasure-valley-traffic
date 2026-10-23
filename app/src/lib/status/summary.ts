import type { BuildStatus, DataMeta, SourceStatus } from '#lib/contracts/meta.js';

/**
 * What a status chip says about scheduled work (landscape sprint, M1), from
 * /api/meta's `status`: one shape, one short headline, and the lines for its
 * tooltip. Pure, so the chip (wave 2: it goes in the app shell, which S3a and
 * S3b own) only draws it.
 *
 * In docs/14's words (§14.3, "never color alone"): the shape carries the
 * level, the headline says what, the color only repeats it.
 *
 * | Level | Shape | When |
 * |---|---|---|
 * | fresh | ● | every scheduled source fresh, nothing failed, no build waiting or running long |
 * | late | ▲ | a source late or failing; a build failed (marked or not; a killed run reads failed too), waiting over 2 days, or running over 18 h |
 * | stale | ■ | a source stale, or never fetched |
 * | unknown | ◌ | no status (no database, before migration 0021, or an older server) |
 *
 * A build marked out of date is normal between a source's update and the
 * lead's run by hand, so a waiting build shows in the headline and lines but
 * raises the level only once it has waited PENDING_LATE_S.
 */

export type StatusLevel = 'fresh' | 'late' | 'stale' | 'unknown';

export interface StatusChip {
	level: StatusLevel;
	shape: '●' | '▲' | '■' | '◌';
	/** The shape's color (a CSS value); the words stay ink. */
	color: string;
	/** Short: "Data fresh", "2 sources late", "1 source stale · 1 build waiting". */
	headline: string;
	/**
	 * How many sources and builds the headline counts, for the compact chip (shape and number);
	 * null when there is nothing to count (fresh, unknown).
	 */
	count: number | null;
	/** One per source or build worth a word, worst first, for the tooltip. */
	lines: string[];
}

/** A marked build waiting longer than this raises the chip to ▲ (s). */
export const PENDING_LATE_S = 2 * 86_400;
/**
 * A run going longer than this raises the chip to ▲ (s): longer than heavy's
 * day window (06:00-23:15), so no run under heavy can still be going. The
 * likeliest case is a worker step logged with `start` whose process was
 * killed: a killed `builds.Run` reads failed at once (it no longer holds its
 * lock), but a `start` run can't be told from a live one.
 */
export const RUNNING_LATE_S = 18 * 3600;
/** At most this many lines in the tooltip; the rest are counted. */
export const LINES_MAX = 8;

const COLOR: Record<StatusLevel, string> = {
	fresh: 'var(--accent-2)',
	late: 'var(--accent)',
	stale: 'var(--alert)',
	unknown: 'var(--ink-soft)'
};
const SHAPE: Record<StatusLevel, StatusChip['shape']> = { fresh: '●', late: '▲', stale: '■', unknown: '◌' };

/** "40 s", "12 min", "5 h", "3 days". */
export function span(seconds: number): string {
	const s = Math.max(0, Math.round(seconds));
	if (s < 90) return `${s} s`;
	if (s < 90 * 60) return `${Math.round(s / 60)} min`;
	if (s < 36 * 3600) return `${Math.round(s / 3600)} h`;
	const d = Math.round(s / 86_400);
	return `${d} day${d === 1 ? '' : 's'}`;
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function sourceLine(s: SourceStatus, now: number): string {
	const every = `every ${span(s.everyS)}`;
	const tries = s.failures > 0 ? `, ${plural(s.failures, 'failed try', 'failed tries')} since` : '';
	if (s.state === 'never' || s.lastOkAt === null) return `${s.source}: no good fetch yet (${every})${tries}`;
	const word = s.state === 'fresh' ? 'failing' : s.state;
	return `${s.source}: ${word}, last good fetch ${span(now - s.lastOkAt)} ago (${every})${tries}`;
}

function buildLine(b: BuildStatus, now: number): string {
	const built = b.lastOkAt === null ? 'never built' : `last built ${span(now - b.lastOkAt)} ago`;
	switch (b.state) {
		case 'running': {
			const long = runningLong(b, now) ? ', longer than a run should take' : '';
			return `${b.build}: running for ${b.lastRunAt === null ? '?' : span(now - b.lastRunAt)}${long}; ${built}`;
		}
		case 'pending':
			return `${b.build}: waiting ${b.pendingSince === null ? '' : `${span(now - b.pendingSince)} `}for a run; ${built}`;
		case 'failed': {
			const marked = b.pendingSince === null ? '' : `; marked ${span(now - b.pendingSince)} ago`;
			return `${b.build}: its last run failed${marked}; ${built}`;
		}
		default:
			return `${b.build}: ${built}`;
	}
}

const runningLong = (b: BuildStatus, now: number) =>
	b.state === 'running' && b.lastRunAt !== null && now - b.lastRunAt > RUNNING_LATE_S;

/** The chip for /api/meta's answer (null: it didn't answer). `now` in epoch s. */
export function statusChip(meta: Pick<DataMeta, 'status'> | null | undefined, now = Date.now() / 1000): StatusChip {
	const st = meta?.status;
	if (!st) {
		return {
			level: 'unknown',
			shape: SHAPE.unknown,
			color: COLOR.unknown,
			headline: 'Status unknown',
			count: null,
			lines: [meta ? "The server didn't say how its scheduled sources are doing" : "The server didn't answer"]
		};
	}
	const { sources: n, attention } = st;
	const waiting = st.builds.filter((b) => b.state === 'pending');
	const failedBuilds = st.builds.filter((b) => b.state === 'failed');
	const longWait = waiting.some((b) => b.pendingSince !== null && now - b.pendingSince > PENDING_LATE_S);
	const longRuns = st.builds.filter((b) => runningLong(b, now));
	// Failing sources that are still fresh (the late, stale and never ones are counted as such).
	const failingFresh = attention.filter((s) => s.state === 'fresh' && s.failures > 0).length;

	const level: StatusLevel =
		n.stale + n.never > 0
			? 'stale'
			: n.late + n.failing + failedBuilds.length + longRuns.length > 0 || longWait
				? 'late'
				: 'fresh';

	const counted =
		n.stale + n.never + n.late + failingFresh + failedBuilds.length + longRuns.length + waiting.length;
	const parts: string[] = [];
	if (n.stale) parts.push(`${plural(n.stale, 'source')} stale`);
	if (n.never) parts.push(`${plural(n.never, 'source')} never fetched`);
	if (n.late) parts.push(`${plural(n.late, 'source')} late`);
	if (failingFresh) parts.push(`${plural(failingFresh, 'source')} failing`);
	if (failedBuilds.length) parts.push(`${plural(failedBuilds.length, 'build')} failed`);
	if (longRuns.length) parts.push(`${plural(longRuns.length, 'build')} running long`);
	if (waiting.length) parts.push(`${plural(waiting.length, 'build')} waiting`);
	const headline = parts.length ? parts.slice(0, 2).join(' · ') + (parts.length > 2 ? ' · …' : '') : 'Data fresh';

	const all = [
		...attention.map((s) => sourceLine(s, now)),
		...st.builds.filter((b) => b.state !== 'built').map((b) => buildLine(b, now))
	];
	const lines = all.length > LINES_MAX ? [...all.slice(0, LINES_MAX - 1), `and ${all.length - LINES_MAX + 1} more`] : all;
	if (!lines.length) {
		const total = n.fresh + n.late + n.stale + n.never;
		lines.push(`${plural(total, 'scheduled source')}, all fresh`);
	}
	return { level, shape: SHAPE[level], color: COLOR[level], headline, count: counted > 0 ? counted : null, lines };
}
