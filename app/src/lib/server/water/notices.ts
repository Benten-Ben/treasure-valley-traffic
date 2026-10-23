import { CREDITS, type EcoliSample, type Hazard, type Notices } from '#lib/layers/water/water.js';
import { iso, num, round, str, type Sql } from './common.js';

/**
 * River notices for the Water layer (landscape sprint plan v3 §4.2 P4-app): `GET /api/water/notices`, from what
 * the water plugin already polls:
 *
 * - **Hazards** (`boise_river_hazards`, hourly): the active and potential hazards on the Boise River, as the
 *   open `river_hazard` lifecycles in `evt.event`, in the City's own words (name and description). The staff
 *   user names and internal comments were never stored.
 * - **E. coli results** (`boise_ecoli`, twice a day): the City's layer keeps only its latest round, so each
 *   site's newest sample is here with its earlier ones (kept in `raw.record`) as history. We show the
 *   numbers and units as published and make no swim or no-swim call.
 *
 * **Internal:** neither source states a licence (a courtesy note to the City is due), so this is for the
 * tailnet map, credited, not republished. Without the plugin's rows: empty lists, never a 500.
 */

/** Earlier results kept per site on the card. */
export const HISTORY = 6;
/** The most E. coli records read (the sites are few; a year of twice-weekly rounds is several hundred). */
export const ECOLI_ROWS = 800;

const SEVERITY_ORDER: Record<string, number> = { extreme: 0, permanent: 1, temporary: 2 };

/** The description minus its leading "<name>: " (the poller joins the two). */
export function hazardText(name: string | null, description: string | null): string | null {
	if (!description) return null;
	const text = name && description.startsWith(`${name}: `) ? description.slice(name.length + 2) : name && description === name ? null : description;
	return str(text)?.slice(0, 600) ?? null;
}

export async function notices(sql: Sql): Promise<Notices> {
	const [hazardRows, sampleRows, polled] = await Promise.all([
		sql`
			select source_id, severity, attributes, description, lower(declared) as since,
			       ST_X(ST_PointOnSurface(geom)) as lng, ST_Y(ST_PointOnSurface(geom)) as lat
			from evt.event
			where source = 'boise_river_hazards' and kind = 'river_hazard' and active
			order by source_id`,
		sql`
			select source_id, payload, ST_X(ST_PointOnSurface(geom)) as lng, ST_Y(ST_PointOnSurface(geom)) as lat
			from raw.record
			where source = 'boise_ecoli' and removed_at is null
			order by payload->>'SampleDatetime' desc, source_id
			limit ${ECOLI_ROWS}`,
		sql`
			select source, max(started_at) as at from ops.fetch
			where source in ('boise_river_hazards', 'boise_ecoli') and ok group by source`
	]);

	const hazards: Hazard[] = hazardRows
		.map((h) => {
			const a = (h.attributes ?? {}) as Record<string, unknown>;
			const name = str(a.name);
			return {
				id: String(h.source_id),
				kind: (['extreme', 'permanent', 'temporary'].includes(String(a.type ?? h.severity)) ? String(a.type ?? h.severity) : 'temporary') as Hazard['kind'],
				status: (a.status === 'potential' ? 'potential' : 'active') as Hazard['status'],
				name,
				description: hazardText(name, str(h.description)),
				mile_marker: str(a.mile_marker),
				since: iso(h.since),
				edited: str(a.edited),
				lng: h.lng === null ? null : round(Number(h.lng), 6),
				lat: h.lat === null ? null : round(Number(h.lat), 6)
			};
		})
		.sort((a, b) => SEVERITY_ORDER[a.kind] - SEVERITY_ORDER[b.kind] || a.id.localeCompare(b.id, 'en', { numeric: true }));

	// Rows arrive newest first: the first of a site is its latest sample.
	const bySite = new Map<string, EcoliSample>();
	for (const row of sampleRows) {
		const p = (row.payload ?? {}) as Record<string, unknown>;
		const site = str(p.SampleName);
		const sampled = str(p.SampleDatetime);
		if (!site || !sampled) continue;
		const result = num(p.FinalResultNumeric);
		const units = str(p.Units);
		const seen = bySite.get(site);
		if (!seen) {
			bySite.set(site, {
				id: site,
				site: str(p.SampleDescription),
				sampled: sampled.slice(0, 10),
				result: result !== null && Number.isFinite(result) ? result : null,
				units,
				lng: row.lng === null ? null : round(Number(row.lng), 6),
				lat: row.lat === null ? null : round(Number(row.lat), 6),
				history: []
			});
		} else if (seen.history.length < HISTORY && !(sampled.slice(0, 10) === seen.sampled && result === seen.result)) {
			seen.history.push({ sampled: sampled.slice(0, 10), result: result !== null && Number.isFinite(result) ? result : null, units });
		}
	}

	const at = (source: string) => iso(polled.find((p) => p.source === source)?.at);
	return {
		hazards,
		ecoli: [...bySite.values()].sort((a, b) => a.id.localeCompare(b.id, 'en', { numeric: true })),
		polled: { boise_river_hazards: at('boise_river_hazards'), boise_ecoli: at('boise_ecoli') },
		credit: [CREDITS.boiseHazards, CREDITS.boiseEcoli],
		license: 'none stated (City of Boise disclaimer only); internal use with credit',
		republish: 'internal'
	};
}
