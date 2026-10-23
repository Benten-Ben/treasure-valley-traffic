import type { Selection } from '../types.js';
import type { PatternKey } from './patterns.js';
import type { Step } from './palette.js';
import type { SoilCard, SoilRestriction } from '#lib/server/soils/units.js';

/**
 * What the Soils layer shows and says (landscape sprint P1-app; plugins/soils/README.md, "The Show by codes").
 * Pure: the module, the legend and the card share it.
 */

/** The words on the card and the legend about what this is (NRCS asks for them). */
export const REGULATORY = 'Mapped soil, not a site test; not for regulatory decisions';
export const CREDIT = 'Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)';
/** Over the Malheur County part of the box NRCS has no digital data. */
export const NOT_SURVEYED = 'Not surveyed: NRCS has no digital soil data for this part of Malheur County, Oregon.';
/** The water-held classes are ours: NRCS's classes are for 150 cm, scaled to the top metre. */
export const WATER_NOTE = "Our scaling to the top metre of NRCS's classes for 150 cm; NRCS doesn't rate 100 cm.";
export const WATER_CLASS_TEXT = ['under 5 cm', '5 to 10 cm', '10 to 15 cm', '15 to 20 cm', '20 cm or more'] as const;

/** The wash shows one property at a time. The key is also the tiles' property name. */
export type ShowBy = 'restr' | 'drain' | 'aws' | 'farm' | 'hsg';
export const SHOW_BY: readonly ShowBy[] = ['restr', 'drain', 'aws', 'farm', 'hsg'];
export const DEFAULT_SHOW_BY: ShowBy = 'restr';

export interface ShowByDef {
	key: ShowBy;
	/** The chip: "Hardpan or bedrock". */
	short: string;
	/** The legend's heading for the ramp. */
	title: string;
	/** What each code (0, 1, ...) means, palest first. */
	levels: readonly string[];
	/** The gray step each code draws in (the ramp is five steps; a shorter scale spreads over it). */
	steps: readonly Step[];
	/** The hatch or stipple the wash carries for this property, and what it says. */
	patterns: readonly { key: PatternKey; text: string }[];
	/** An extra line under the ramp. */
	note?: string;
}

export const SHOW_BY_DEFS: Record<ShowBy, ShowByDef> = {
	restr: {
		key: 'restr',
		short: 'Hardpan or bedrock',
		title: 'Depth to a hardpan or bedrock',
		levels: ['None within 150 cm', '100 to 150 cm', '50 to 100 cm', '25 to 50 cm', 'Under 25 cm'],
		steps: [0, 1, 2, 3, 4],
		patterns: [
			{ key: 'hatch', text: 'Hardpan within 50 cm' },
			{ key: 'stipple', text: 'Bedrock within 50 cm' }
		]
	},
	drain: {
		key: 'drain',
		short: 'Drainage',
		title: 'How well the soil drains',
		levels: ['Excessively drained', 'Well drained', 'Moderately well drained', 'Somewhat poorly drained', 'Poorly or very poorly drained'],
		steps: [0, 1, 2, 3, 4],
		patterns: []
	},
	aws: {
		key: 'aws',
		short: 'Water held',
		title: 'Water the soil holds in the top metre',
		levels: [...WATER_CLASS_TEXT],
		steps: [0, 1, 2, 3, 4],
		patterns: [],
		note: WATER_NOTE
	},
	farm: {
		key: 'farm',
		short: 'Farmland',
		title: 'Farmland class',
		levels: ['Not prime farmland', 'Farmland of statewide, local or unique importance', 'Prime farmland'],
		steps: [0, 2, 4],
		patterns: [
			{ key: 'hatch', text: 'Only once drained' },
			{ key: 'cross', text: 'Only once reclaimed of salts and sodium' }
		]
	},
	hsg: {
		key: 'hsg',
		short: 'Runoff',
		title: 'Runoff (hydrologic group)',
		levels: ['A: little runoff', 'B', 'C', 'D: much runoff'],
		steps: [0, 1, 3, 4],
		patterns: [{ key: 'hatch', text: 'Dual group (A/D, B/D, C/D): D where undrained' }]
	}
};

/** The properties a feature of the tiles carries. */
export interface SoilProps {
	mukey?: string | number;
	symbol?: string;
	restr?: number;
	pat?: string;
	drain?: number;
	aws?: number;
	farm?: number;
	cond?: string;
	hsg?: number;
	dual?: boolean | number;
}

export const SOURCE = 'USDA NRCS Soil Survey (SSURGO)';

/** The selection for a click on a map unit; the card reads the rest from the API. */
export function soilSelection(p: SoilProps, at?: [number, number]): Selection | null {
	const id = p.mukey === undefined || p.mukey === null || p.mukey === '' ? null : String(p.mukey);
	if (!id || !/^\d{1,9}$/.test(id)) return null;
	return {
		kind: 'soil',
		id,
		layer: 'soils',
		title: p.symbol ? `Soil ${p.symbol}` : 'Soil map unit',
		fact: p.symbol ? `Map unit ${p.symbol}` : undefined,
		source: SOURCE,
		...(at ? { at } : {}),
		data: { ...p }
	};
}

/** "Hardpan (duripan) from 40 cm", or why there is none. */
export function restrictionText(r: SoilRestriction | null): string {
	if (!r) return 'None found within the depth NRCS describes';
	const kind = r.kind.charAt(0).toUpperCase() + r.kind.slice(1);
	const from = r.top_cm === null ? '' : ` from ${r.top_cm} cm`;
	return `${kind}${from}${r.hard ? ` (${r.hard.toLowerCase()})` : ''}`;
}

/** "17.4 cm in the top metre (15 to 20 cm)". */
export function waterText(card: Pick<SoilCard, 'water_cm' | 'water_class'>): string | null {
	if (card.water_cm === null) return null;
	const cls = card.water_class === null ? '' : ` (${WATER_CLASS_TEXT[card.water_class] ?? ''})`;
	return `${Math.round(card.water_cm * 10) / 10} cm in the top metre${cls}`;
}

/** "B/D, D where undrained" for a dual group; "B" otherwise. */
export function groupText(card: Pick<SoilCard, 'hydrologic_group' | 'hydrologic_dual'>): string | null {
	const g = card.hydrologic_group;
	if (!g) return null;
	return card.hydrologic_dual ? `${g}, ${g.split('/')[1] ?? 'D'} where undrained` : g;
}

/** The hydric rating as one row's value: "No (dominant component); 12% of the map unit's components". */
export function hydricText(card: Pick<SoilCard, 'hydric' | 'hydric_percent'>): string | null {
	if (!card.hydric && card.hydric_percent === null) return null;
	const own = card.hydric ? `${card.hydric} (dominant component)` : '';
	const share = card.hydric_percent === null ? '' : `${own ? '; ' : ''}${card.hydric_percent}% hydric components`;
	return `${own}${share}`;
}

/** The survey area's line: "Ada County Area, Idaho (ID001), version 24 (2025-09-23), 1:24,000". */
export function surveyText(s: SoilCard['survey']): string | null {
	if (!s) return null;
	const bits = [`${s.name} (${s.symbol})`];
	if (s.version !== null) bits.push(`version ${s.version}${s.saverest ? ` (${s.saverest.slice(0, 10)})` : ''}`);
	else if (s.saverest) bits.push(s.saverest.slice(0, 10));
	if (s.scale) bits.push(`1:${s.scale.toLocaleString('en-US')}`);
	return bits.join(', ');
}
