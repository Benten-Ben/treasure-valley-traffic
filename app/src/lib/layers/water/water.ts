/**
 * The Water layer's shared, browser-safe parts (landscape sprint plan v3 §4.2 P4-app): what the water APIs
 * answer (`/api/water/…`, built by `#lib/server/water`), and the words a card, a legend row and a tooltip use.
 * Pure, so they're unit-tested; the server and the card both import the types from here, as Trees does.
 *
 * The rules the words keep:
 * - A canal's card names the **irrigation service areas it runs through** (IDWR's layer says where an
 *   organization may deliver water, not who runs a canal), so no sentence here says who "operates" a canal.
 * - Estimates say so: widths are estimates until measured; a line only the federal map shows says it isn't in
 *   OpenStreetMap; an area is not a legal (regulatory) boundary.
 * - E. coli results and river hazards are the City's own words and numbers, shown as published. We make no
 *   swim or no-swim call and never call a river safe.
 */

export type ReachKind = 'river' | 'stream' | 'canal' | 'lateral' | 'ditch' | 'drain';
export type CanalKind = 'main_canal' | 'canal' | 'lateral' | 'ditch' | 'drain';
export type Flow = 'perennial' | 'intermittent' | 'ephemeral' | 'unknown';
export type WidthFrom = 'osm_tag' | 'order' | 'kind' | 'measured';
export type BodyKind = 'lake' | 'reservoir' | 'pond' | 'river' | 'canal' | 'basin' | 'wastewater' | 'wetland' | 'pool' | 'water' | 'dock';
export type StructureKind = 'dam' | 'weir' | 'lock_gate' | 'sluice_gate' | 'waterfall' | 'spring' | 'gauge';
export type EvidenceSource = 'osm_waterways' | 'nhd_hr' | 'hydroshare_canals';
export type SourceId = EvidenceSource | 'nwps_gauges';

/** The picked kinds a water selection can be (`Selection.data.type`). */
export type WaterThing = 'reach' | 'body' | 'gauge' | 'structure' | 'hazard' | 'ecoli';

export const REACH_KINDS: readonly ReachKind[] = ['river', 'stream', 'canal', 'lateral', 'ditch', 'drain'];

// -- the API's answers ---------------------------------------------------------------------------------------------

/** One reading of a gauge: the latest we hold, with each value in words and units. */
export interface GaugeReading {
	/** When it was observed, ISO. */
	at: string;
	facts: { label: string; value: number; unit: string }[];
}

/** NWPS's flood category for an open flood episode at a gauge (action stage and above). */
export interface GaugeFlood {
	category: 'action' | 'minor' | 'moderate' | 'major';
	peak: string | null;
	since: string | null;
}

export interface GaugeSummary {
	lid: string;
	name: string;
	/** What it measures, when we matched it (a reach, a body or a canal). */
	measures: { type: 'reach' | 'body' | 'canal'; id: number; name: string | null; kind: string } | null;
	reading: GaugeReading | null;
	flood: GaugeFlood | null;
	/** Whether NWPS names a USGS site for it (the record's `usgsId`): the credit of every card showing its reading follows. */
	usgs: boolean;
}

export interface Evidence {
	source: EvidenceSource;
	source_id: string;
	role: 'geometry' | 'attributes' | 'agrees' | 'name';
	/** The share of the reach's length within 20 m of it, 0 to 1. */
	share: number | null;
	distance_m: number | null;
}

export interface ServiceArea {
	name: string;
	/** The share of the canal's length inside it, 0 to 1. */
	share: number;
	/** The canal's head lies in it. */
	at_head: boolean;
}

export interface CanalDetail {
	id: number;
	name: string;
	kind: CanalKind;
	length_m: number;
	piped_m: number;
	reaches: number;
	/** What the head leaves: a river, a reservoir or another canal, by name when we know it. */
	source: { kind: 'river' | 'canal' | 'reservoir' | 'unknown'; name: string | null };
	head_structure: { id: number; kind: StructureKind; name: string | null } | null;
	sources: string[];
	gauge: GaugeSummary | null;
	/** IDWR's service areas it runs through: internal (no licence stated), shown only on this tailnet map. */
	service_areas: ServiceArea[];
}

export interface ReachDetail {
	id: number;
	kind: ReachKind;
	name: string | null;
	name_from: 'osm' | 'nhd' | 'hydroshare' | null;
	flow: Flow;
	piped: boolean;
	width_m: number;
	width_from: WidthFrom;
	stream_order: number | null;
	geometry_from: 'osm' | 'nhd';
	confirmed: boolean;
	length_m: number;
	evidence: Evidence[];
	canal: CanalDetail | null;
	/** A gauge on the reach itself (a river), when it isn't the canal's. */
	gauge: GaugeSummary | null;
	credit: string[];
}

export interface BodyDetail {
	id: number;
	kind: BodyKind;
	name: string | null;
	intermittent: boolean;
	area_m2: number;
	geometry_from: 'osm' | 'nhd';
	confirmed: boolean;
	/** The OpenStreetMap object it comes from, as text ("way 123"), when it has one. */
	osm: string | null;
	gauge: GaugeSummary | null;
	credit: string[];
}

export interface StructureDetail {
	id: number;
	kind: StructureKind;
	name: string | null;
	source: SourceId;
	reach: { id: number; kind: ReachKind; name: string | null } | null;
	/** The canals whose head is this structure. */
	head_of: { id: number; name: string }[];
	gauge: GaugeSummary | null;
	credit: string[];
}

export interface GaugeDetail extends GaugeSummary {
	method: 'name' | 'nearest' | 'none';
	distance_m: number | null;
	credit: string[];
}

/** The map's water points: structures and gauges, all of them (about a thousand). */
export interface WaterPoints {
	structures: { id: number; kind: StructureKind; name: string | null; minzoom: number; lng: number; lat: number }[];
	gauges: { lid: string; name: string; lng: number; lat: number; flood: GaugeFlood['category'] | null }[];
	credit: string[];
}

export interface Hazard {
	id: string;
	kind: 'extreme' | 'permanent' | 'temporary';
	status: 'active' | 'potential';
	name: string | null;
	/** The City's own words. */
	description: string | null;
	mile_marker: string | null;
	since: string | null;
	edited: string | null;
	lng: number | null;
	lat: number | null;
}

export interface EcoliSample {
	/** The site's sample name: the key. */
	id: string;
	site: string | null;
	/** 'YYYY-MM-DD'. */
	sampled: string;
	result: number | null;
	units: string | null;
	lng: number | null;
	lat: number | null;
	/** Earlier results at the site, newest first (the layer itself keeps only the latest round). */
	history: { sampled: string; result: number | null; units: string | null }[];
}

export interface Notices {
	hazards: Hazard[];
	ecoli: EcoliSample[];
	/** Each source's last good poll, ISO. */
	polled: { boise_river_hazards: string | null; boise_ecoli: string | null };
	credit: string[];
	license: string;
	republish: 'internal';
}

// -- words -----------------------------------------------------------------------------------------------------------

export const KIND_WORD: Record<ReachKind, string> = {
	river: 'River',
	stream: 'Creek or stream',
	canal: 'Canal',
	lateral: 'Lateral',
	ditch: 'Ditch',
	drain: 'Drain'
};

export const CANAL_KIND_WORD: Record<CanalKind, string> = {
	main_canal: 'Main canal',
	canal: 'Canal',
	lateral: 'Lateral',
	ditch: 'Ditch',
	drain: 'Drain'
};

export const BODY_WORD: Record<BodyKind, string> = {
	lake: 'Lake',
	reservoir: 'Reservoir',
	pond: 'Pond',
	river: 'River (drawn as an area)',
	canal: 'Canal (drawn as an area)',
	basin: 'Basin',
	wastewater: 'Wastewater pond',
	wetland: 'Wetland',
	pool: 'Pool',
	water: 'Water',
	dock: 'Dock basin'
};

export const STRUCTURE_WORD: Record<StructureKind, string> = {
	dam: 'Dam',
	weir: 'Weir',
	lock_gate: 'Lock gate',
	sluice_gate: 'Sluice gate',
	waterfall: 'Waterfall',
	spring: 'Spring',
	gauge: 'Gauge'
};

export const FLOW_WORD: Record<Flow, string> = {
	perennial: 'Flows all year',
	intermittent: 'Dries up part of the year (intermittent)',
	ephemeral: 'Flows only after rain or snowmelt (ephemeral)',
	unknown: 'Flow not known'
};

export const SOURCE_NAME: Record<SourceId, string> = {
	osm_waterways: 'OpenStreetMap',
	nhd_hr: 'USGS National Hydrography Dataset',
	hydroshare_canals: "HydroShare's Treasure Valley Irrigation System",
	nwps_gauges: 'NOAA National Water Prediction Service'
};

export const CREDITS = {
	osm: '© OpenStreetMap contributors',
	nhd: 'USGS National Hydrography Dataset',
	hydroshare: 'Treasure Valley Irrigation System, HydroShare (CC BY 4.0; Tatum, Bittmann, Stone and Kaiser, 2022)',
	nwps: 'NOAA National Weather Service (National Water Prediction Service)',
	usgs: 'observations courtesy of the U.S. Geological Survey',
	idwr: 'Irrigation service areas: Idaho Department of Water Resources (internal use)',
	boiseHazards: 'Boise Fire Department and City of Boise (Float the Boise)',
	boiseEcoli: 'City of Boise Parks and Recreation'
} as const;

/** "8 m (26 ft)". */
export function metresFeet(m: number): string {
	const d = m >= 10 ? 0 : 1;
	return `${m.toFixed(d).replace(/\.0$/, '')} m (${Math.round(m * 3.28084)} ft)`;
}

/** "12.3 km (7.6 mi)" or "640 m". */
export function lengthText(m: number): string {
	if (m < 1000) return `${Math.round(m)} m (${Math.round(m * 3.28084)} ft)`;
	const km = m / 1000;
	return `${km.toFixed(km >= 10 ? 0 : 1)} km (${(km * 0.621371).toFixed(km * 0.621371 >= 10 ? 0 : 1)} mi)`;
}

/** "12 acres (4.9 ha)" or "0.3 acres (1,200 m²)". */
export function areaText(m2: number): string {
	const acres = m2 / 4046.8564224;
	const ha = m2 / 10_000;
	if (acres < 1) return `${acres.toFixed(2)} acres (${Math.round(m2).toLocaleString('en-US')} m²)`;
	return `${acres >= 100 ? Math.round(acres).toLocaleString('en-US') : acres.toFixed(1)} acres (${ha >= 100 ? Math.round(ha).toLocaleString('en-US') : ha.toFixed(1)} ha)`;
}

/** How we know a width, in words. Widths are estimates until measured. */
export function widthHow(from: WidthFrom): string {
	switch (from) {
		case 'osm_tag':
			return "from OpenStreetMap's width tag";
		case 'order':
			return "estimated from the stream's order (size class)";
		case 'kind':
			return 'estimated from what kind of waterway it is';
		case 'measured':
			return 'measured from aerial imagery';
	}
}

export const percent = (share: number) => `${Math.round(share * 100)}%`;

/** A reach or body's title: its name, or "Unnamed ditch". */
export function reachTitle(kind: ReachKind, name: string | null | undefined, piped = false): string {
	const base = name?.trim() || `Unnamed ${KIND_WORD[kind].toLowerCase()}`;
	return piped && !name?.trim() ? `${base} (piped)` : base;
}

export function bodyTitle(kind: BodyKind, name: string | null | undefined): string {
	return name?.trim() || `Unnamed ${BODY_WORD[kind].toLowerCase().replace(/ \(.*\)$/, '')}`;
}

/** One fact for the tooltip: "Canal · about 5 m wide". */
export function reachFact(kind: ReachKind, widthM: number, o: { intermittent?: boolean; piped?: boolean; nhdOnly?: boolean } = {}): string {
	const bits = [KIND_WORD[kind]];
	if (o.piped) bits.push('piped');
	else if (o.intermittent) bits.push('dries up part of the year');
	const w = Number.isFinite(widthM) && widthM > 0 ? `about ${metresFeet(widthM).split(' (')[0]} wide` : null;
	return [bits.join(', '), w, o.nhdOnly ? 'federal map only' : null].filter(Boolean).join(' · ');
}

/** The source line of a tooltip for a baked reach or area. */
export function sourceLine(nhdOnly: boolean): string {
	return nhdOnly ? 'USGS NHD (not in OpenStreetMap)' : 'OpenStreetMap · USGS NHD';
}

/** Where a reach's line comes from, in words. */
export function geometryWords(from: 'osm' | 'nhd', confirmed: boolean): string {
	if (from === 'nhd') return "Drawn from the federal hydrography map (USGS NHD) alone: OpenStreetMap doesn't have this line.";
	return confirmed ? "Drawn from OpenStreetMap's line, which the federal map (USGS NHD) agrees with." : "Drawn from OpenStreetMap's line; the federal map (USGS NHD) doesn't clearly agree with it.";
}

/** Where an area's outline comes from, in words. */
export function outlineWords(from: 'osm' | 'nhd', confirmed: boolean): string {
	if (from === 'nhd') return "Outline from the federal hydrography map (USGS NHD) alone: OpenStreetMap doesn't have this area.";
	return confirmed ? "Outline from OpenStreetMap, which the federal map (USGS NHD) agrees with." : "Outline from OpenStreetMap; the federal map (USGS NHD) doesn't clearly agree with it.";
}

export function nameWords(from: ReachDetail['name_from']): string | null {
	switch (from) {
		case 'osm':
			return 'name from OpenStreetMap';
		case 'nhd':
			return 'name from USGS NHD (GNIS)';
		case 'hydroshare':
			return "name from HydroShare's canal network";
		default:
			return null;
	}
}

/** What a canal's head leaves, in words: "Leaves the Boise River". */
export function canalSourceWords(s: CanalDetail['source']): string | null {
	const name = s.name?.trim();
	switch (s.kind) {
		case 'river':
			return name ? `Leaves ${name}` : 'Leaves a river';
		case 'canal':
			return name ? `Leaves ${name}` : 'Leaves another canal';
		case 'reservoir':
			return name ? `Leaves ${name}` : 'Leaves a reservoir';
		default:
			return null;
	}
}

/** IDWR's service areas, as a card sentence. Never says who runs the canal. */
export function serviceAreasWords(areas: readonly ServiceArea[]): string {
	if (!areas.length) return '';
	const list = areas.map((a) => `${a.name} (${percent(a.share)} of its length${a.at_head ? ', and its head' : ''})`).join('; ');
	return `Irrigation service areas it runs through: ${list}.`;
}

export const SERVICE_AREA_NOTE =
	"A service area is where an irrigation organization may deliver its water rights. It doesn't say who runs this canal or when water flows.";

/** The credits a reach's card shows. The gauge's own credit applies (USGS only where its record names a site). */
export function reachCredits(
	d: Pick<ReachDetail, 'geometry_from' | 'name_from' | 'evidence'> & {
		canal: { service_areas: readonly unknown[]; gauge: { usgs: boolean } | null } | null;
		gauge?: { usgs: boolean } | null;
	}
): string[] {
	const out: string[] = [];
	if (d.geometry_from === 'osm' || d.evidence.some((e) => e.source === 'osm_waterways')) out.push(CREDITS.osm);
	out.push(CREDITS.nhd);
	if (d.name_from === 'hydroshare' || d.evidence.some((e) => e.source === 'hydroshare_canals')) out.push(CREDITS.hydroshare);
	const gauge = d.canal?.gauge ?? d.gauge ?? null;
	if (gauge) out.push(...gaugeCredits(gauge.usgs));
	if (d.canal?.service_areas.length) out.push(CREDITS.idwr);
	return out;
}

// -- gauges --------------------------------------------------------------------------------------------------------

/**
 * A reading's values in words. NWPS's second value, `unit` kcfs, is flow in thousands of cubic feet a second;
 * we say cfs. A value in feet is the stage, or the pool's elevation at a reservoir (`pe` starting HP).
 */
export function readingFacts(
	pe: string | null,
	units: readonly (string | null)[],
	values: readonly (number | null)[]
): GaugeReading['facts'] {
	const out: GaugeReading['facts'] = [];
	values.forEach((v, i) => {
		const unit = (units[i] ?? '').trim().toLowerCase();
		if (v === null || v === undefined || !Number.isFinite(v)) return;
		if (unit === 'kcfs') out.push({ label: 'Flow', value: Math.round(v * 1000), unit: 'cfs' });
		else if (unit === 'cfs') out.push({ label: 'Flow', value: Math.round(v), unit: 'cfs' });
		else if (unit === 'ft') out.push({ label: (pe ?? '').toUpperCase().startsWith('HP') ? 'Pool elevation' : 'Stage', value: Math.round(v * 100) / 100, unit: 'ft' });
		else out.push({ label: 'Reading', value: v, unit: unit || '' });
	});
	return out;
}

export const FLOOD_WORD: Record<GaugeFlood['category'], string> = {
	action: 'action stage',
	minor: 'minor flooding',
	moderate: 'moderate flooding',
	major: 'major flooding'
};

/** The gauge sentence about floods. Absence of an open episode is not a forecast of safety. */
export function floodWords(flood: GaugeFlood | null): string {
	return flood
		? `NWPS's category for the latest observation: ${FLOOD_WORD[flood.category]}.`
		: 'No open flood episode: NWPS has not put the latest observation at action stage or above.';
}

/** "3 h ago" style age, from two times. */
export function ageText(iso: string, now = Date.now()): string {
	const ms = now - Date.parse(iso);
	if (!Number.isFinite(ms)) return '';
	const min = Math.max(0, Math.round(ms / 60_000));
	if (min < 2) return 'just now';
	if (min < 120) return `${min} min ago`;
	const h = Math.round(min / 60);
	if (h < 48) return `${h} h ago`;
	return `${Math.round(h / 24)} days ago`;
}

/** The credit lines for a gauge: NOAA/NWS always, USGS only where NWPS names a USGS site. */
export function gaugeCredits(usgs: boolean): string[] {
	return usgs ? [`${CREDITS.nwps}; ${CREDITS.usgs}`] : [CREDITS.nwps];
}

// -- notices -------------------------------------------------------------------------------------------------------

export const HAZARD_WORD: Record<Hazard['kind'], string> = {
	extreme: 'Extreme hazard',
	permanent: 'Permanent hazard',
	temporary: 'Temporary hazard'
};

export const HAZARD_STATUS_WORD: Record<Hazard['status'], string> = {
	active: 'Active',
	potential: 'Potential'
};

export const HAZARD_NOTE = "Shown as the City publishes it. It isn't a complete list and conditions change: check the City's own notices before floating.";
export const ECOLI_NOTE = "Results are the City of Boise's, shown as published. We make no swim or no-swim call: check the City's own notice before getting in.";

export function ecoliResultText(s: Pick<EcoliSample, 'result' | 'units'>): string {
	if (s.result === null || !Number.isFinite(s.result)) return 'No result';
	return `${s.result.toLocaleString('en-US', { maximumFractionDigits: 1 })} ${s.units ?? ''}`.trim();
}

/** 'YYYY-MM-DD' as "Sep 28, 2026". */
export function dayText(day: string | null): string {
	if (!day) return '';
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(day);
	if (!m) return day;
	const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	return `${months[Number(m[2]) - 1] ?? m[2]} ${Number(m[3])}, ${m[1]}`;
}

// -- card lines --------------------------------------------------------------------------------------------------

const ROLE_WORD: Record<Evidence['role'], string> = {
	geometry: 'Its line',
	attributes: 'Its facts (flow, size class, name)',
	name: 'Its name',
	agrees: 'Also agrees'
};

/** One "how we know" line: what a source gave and how closely it follows the line. */
export function evidenceWords(e: Evidence): string {
	const near = e.share !== null && e.share > 0 ? ` (${percent(e.share)} of its length within 20 m${e.distance_m !== null ? `, median ${Math.round(e.distance_m)} m apart` : ''})` : '';
	return `${ROLE_WORD[e.role]}: ${SOURCE_NAME[e.source]}, ${e.source_id}${near}`;
}

/** A reading's values in one line: "Stage 7.33 ft · Flow 1,660 cfs". */
export function readingText(r: GaugeReading): string {
	return r.facts.map((f) => `${f.label} ${f.value.toLocaleString('en-US')} ${f.unit}`.trim()).join(' · ');
}

/** What a gauge measures, in words. */
export function measuresWords(m: GaugeSummary['measures']): string | null {
	if (!m) return null;
	const what = m.type === 'canal' ? (CANAL_KIND_WORD[m.kind as CanalKind] ?? 'Canal') : m.type === 'body' ? (BODY_WORD[m.kind as BodyKind] ?? 'Water') : (KIND_WORD[m.kind as ReachKind] ?? 'Waterway');
	return `${m.name ?? `Unnamed ${what.toLowerCase()}`} (${what.toLowerCase()})`;
}
