import type postgres from 'postgres';
import type { BuildState, BuildStatus, DataStatus, SourceState, SourceStatus } from '#lib/contracts/meta.js';

/**
 * Scheduled work at a glance for /api/meta's `status` (landscape sprint, M1):
 * the views of migration 0021, `ops.source_status` (each scheduled source's
 * last good fetch against its schedule) and `ops.build_status` (each build's
 * age and state). The views make every judgement, so the app, the VM's
 * `bin/status` and `python3 -m ingest.builds` agree; this only counts, orders
 * and trims. Names and times only: error text and reasons stay on the server.
 */

export const ATTENTION_MAX = 20;
export const BUILDS_MAX = 40;

const SOURCE_STATES: readonly SourceState[] = ['fresh', 'late', 'stale', 'never'];
const BUILD_STATES: readonly BuildState[] = ['built', 'pending', 'running', 'failed'];
/** Attention order: worst first. */
const SOURCE_RANK: Record<SourceState, number> = { stale: 0, never: 1, late: 2, fresh: 3 };
const BUILD_RANK: Record<BuildState, number> = { running: 0, pending: 1, failed: 2, built: 3 };

const num = (v: unknown) => (v === null || v === undefined ? null : Number(v));

/** A row of ops.source_status as readStatus selects it. */
export interface SourceRow {
	source: string;
	state: string;
	last_ok_at: number | null;
	every_s: number;
	failures: number;
}

/** A row of ops.build_status as readStatus selects it. */
export interface BuildRow {
	build: string;
	state: string;
	last_ok_at: number | null;
	pending_since: number | null;
	last_run_at: number | null;
}

/** Count, order and trim the views' rows (pure; tested). Rows in a state the contract doesn't know are left out. */
export function summarize(sources: readonly SourceRow[], builds: readonly BuildRow[]): DataStatus {
	const counts = { fresh: 0, late: 0, stale: 0, never: 0, failing: 0 };
	const attention: SourceStatus[] = [];
	for (const r of sources) {
		if (!SOURCE_STATES.includes(r.state as SourceState)) continue;
		const s: SourceStatus = {
			source: String(r.source),
			state: r.state as SourceState,
			lastOkAt: num(r.last_ok_at),
			everyS: Number(r.every_s),
			failures: Number(r.failures) || 0
		};
		counts[s.state] += 1;
		if (s.failures > 0) counts.failing += 1;
		if (s.state !== 'fresh' || s.failures > 0) attention.push(s);
	}
	attention.sort(
		(a, b) =>
			SOURCE_RANK[a.state] - SOURCE_RANK[b.state] ||
			(a.lastOkAt ?? -Infinity) - (b.lastOkAt ?? -Infinity) ||
			a.source.localeCompare(b.source)
	);
	const list: BuildStatus[] = builds
		.filter((r) => BUILD_STATES.includes(r.state as BuildState))
		.map((r) => ({
			build: String(r.build),
			state: r.state as BuildState,
			lastOkAt: num(r.last_ok_at),
			pendingSince: num(r.pending_since),
			lastRunAt: num(r.last_run_at)
		}));
	list.sort(
		(a, b) =>
			BUILD_RANK[a.state] - BUILD_RANK[b.state] ||
			(a.pendingSince ?? Infinity) - (b.pendingSince ?? Infinity) ||
			a.build.localeCompare(b.build)
	);
	return { sources: counts, attention: attention.slice(0, ATTENTION_MAX), builds: list.slice(0, BUILDS_MAX) };
}

/**
 * Read both views with any postgres.js client. Call it only once they exist
 * (versions.ts checks with to_regclass); it throws if a query fails.
 */
export async function readStatus(sql: postgres.Sql): Promise<DataStatus> {
	const { sources, builds } = await readStatusRows(sql);
	return summarize(sources, builds);
}

/** The views' rows, as summarize takes them (every scheduled source, every build). */
export async function readStatusRows(sql: postgres.Sql): Promise<{ sources: SourceRow[]; builds: BuildRow[] }> {
	const [sources, builds] = await Promise.all([
		sql`select source, state, extract(epoch from last_ok_at)::float8 as last_ok_at,
		           extract(epoch from schedule)::float8 as every_s, failures
		    from ops.source_status`,
		sql`select build, state, extract(epoch from last_ok_at)::float8 as last_ok_at,
		           extract(epoch from pending_since)::float8 as pending_since,
		           extract(epoch from last_run_at)::float8 as last_run_at
		    from ops.build_status`
	]);
	return { sources: sources as unknown as SourceRow[], builds: builds as unknown as BuildRow[] };
}
