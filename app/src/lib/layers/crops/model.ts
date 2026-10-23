import type { Selection } from '../types.js';
import { GROUP_SHORT, groupOfLetter, isCrop, type TileGroup } from './palette.js';

/**
 * The Crop fields layer's pure parts: the card's words (from `GET /api/farm/fields/<id>`, which
 * `#lib/server/farm/fields.ts` shapes), the selection a click makes, and the year switcher's arithmetic.
 * Fields are estimated outlines, so every line says "estimated" or "USDA's map" where it matters.
 */

/** The card API's field (src/lib/server/farm/fields.ts), as the client reads it. */
export interface FieldYear {
	year: number;
	code: number;
	name: string | null;
	group: string;
}
export interface FieldCard {
	id: number;
	acres: number | null;
	county: string | null;
	years: FieldYear[];
	agree: Record<string, number>;
	july: { year: number; state: 'green' | 'growing' | 'bare'; ndvi: number | null } | null;
	growth: 'farmed' | 'built_over' | 'being_built' | null;
	growth_detail: { developed_by?: number; permits?: number | null; permit_years?: (number | null)[]; unconfirmed?: string } | null;
	plat: { approved: number; pending: number; built: number; plats: { id: number; name: string | null; status: string; applied_on: string | null; share: number }[] } | null;
	valid_to: string | null;
	centre: [number, number];
	bbox: [number, number, number, number];
	credit: string | null;
	license: string | null;
}
export interface YearInfo {
	built: boolean;
	year: number | null;
	label: string | null;
	first_year: number | null;
	edition: string | null;
}

/** A field's properties in the z11-and-up tiles (`farm.crop_fields`). */
export interface FieldProps {
	id?: number;
	a?: number;
	g?: string;
	n?: string;
	y?: string;
	s?: string;
	st?: string;
	p?: boolean;
}

/** The crop group a field has in `year` (from the tiles' letters); undefined when none is painted. */
export function groupInYear(props: Pick<FieldProps, 'y' | 'g'>, year: number, firstYear: number, currentYear: number): TileGroup | undefined {
	if (year === currentYear && props.g) return props.g as TileGroup;
	return groupOfLetter(props.y?.[year - firstYear]);
}

export const fmtAcres = (a: number | null | undefined): string => {
	if (a === null || a === undefined || !Number.isFinite(a)) return 'size unknown';
	const n = a < 10 ? Math.round(a * 10) / 10 : Math.round(a);
	return `${n.toLocaleString('en-US')} ${n === 1 ? 'acre' : 'acres'}`;
};

/** "Estimated field · 24 acres · Canyon County". */
export function subtitle(acres: number | null | undefined, county: string | null | undefined): string {
	return ['Estimated field', fmtAcres(acres), county ? `${county} County` : null].filter(Boolean).join(' · ');
}

const groupWord = (g: string): string => GROUP_SHORT[g as TileGroup] ?? 'Other';

/** The newest year's crop, in words: the CDL's name, else the group. */
export function cropNow(card: Pick<FieldCard, 'years'>): { year: number; name: string; group: string } | null {
	const y = card.years.at(-1);
	if (!y) return null;
	return { year: y.year, name: y.name ?? groupWord(y.group), group: y.group };
}

/**
 * The rotation, each run of years in one group: "Hay 2018–2023 → Pasture 2024 → Built 2025". A field that was
 * one group throughout says so ("Hay in all eight years").
 */
export function rotationText(years: readonly FieldYear[]): string {
	if (!years.length) return '';
	const runs: { group: string; from: number; to: number }[] = [];
	for (const y of years) {
		const last = runs.at(-1);
		if (last && last.group === y.group) last.to = y.year;
		else runs.push({ group: y.group, from: y.year, to: y.year });
	}
	if (runs.length === 1) return `${groupWord(runs[0].group)} in all ${years.length === 8 ? 'eight' : years.length} years`;
	return runs.map((r) => `${groupWord(r.group)} ${r.from === r.to ? r.from : `${r.from}–${r.to}`}`).join(' → ');
}

/** How sure USDA's map is: the CDL pixels that agree with the field's code, for the newest year held. */
export function howSure(agree: Record<string, number>): { year: number; share: number; word: string; text: string } | null {
	const years = Object.keys(agree).map(Number).filter(Number.isFinite).sort((a, b) => b - a);
	if (!years.length) return null;
	const year = years[0];
	const share = agree[String(year)];
	const word = share >= 0.8 ? 'Fairly sure' : share >= 0.5 ? 'Somewhat sure' : 'Not very sure';
	return { year, share, word, text: `${word}: USDA's ${year} map agrees with this field's crop on ${Math.round(share * 100)}% of its pixels.` };
}

const JULY_WORD = { green: 'green', growing: 'growing', bare: 'bare or harvested' } as const;

/** The July state, from Sentinel-2's median in its own year. */
export function julyText(july: FieldCard['july']): string | null {
	if (!july) return null;
	const ndvi = july.ndvi === null ? '' : ` (greenness ${july.ndvi.toFixed(2)})`;
	return `July ${july.year}: ${JULY_WORD[july.state] ?? july.state}${ndvi}`;
}

/** The growth flag as stored by `farm-derive`; null for a field still farmed. */
export function growthText(card: Pick<FieldCard, 'growth' | 'growth_detail'>): string | null {
	const d = card.growth_detail;
	if (card.growth === 'built_over') return d?.developed_by ? `Built over: developed by ${d.developed_by}` : 'Built over';
	if (card.growth === 'being_built') {
		const years = d?.permit_years?.filter((y): y is number => typeof y === 'number');
		const since = years?.length ? ` since ${Math.min(...years)}` : '';
		return d?.permits ? `Being built: ${d.permits} new-construction permit${d.permits === 1 ? '' : 's'}${since}` : 'Being built';
	}
	return d?.unconfirmed ? `Developed in the newest map, but no permits found` : null;
}

/** The plat line: the share of the field under an approved or recorded plat, the largest by name. */
export function platText(plat: FieldCard['plat']): string | null {
	if (!plat) return null;
	const pct = (x: number) => `${Math.round(x * 100)}%`;
	const parts: string[] = [];
	if (plat.approved >= 0.01) parts.push(`${pct(plat.approved)} under an approved plat`);
	if (plat.pending >= 0.01) parts.push(`${pct(plat.pending)} under a pending plat`);
	if (plat.built >= 0.01) parts.push(`${pct(plat.built)} under a built plat`);
	if (!parts.length) return null;
	const names = plat.plats.map((p) => p.name).filter(Boolean).slice(0, 2);
	return `${parts.join(', ')}${names.length ? ` (${names.join(', ')})` : ''}`;
}

/** The new USDA method (2024 on) moves hay into grass and pasture and developed land up: not a real change. */
export const METHOD_NOTE = '2024–25 maps use a new USDA method';
export const METHOD_FROM = 2024;
export const methodNote = (year: number): string | null => (year >= METHOD_FROM ? METHOD_NOTE : null);

/** What a click on a field in the tiles selects (the card fetches the rest). */
export function fieldSelection(p: FieldProps, id: string | number, year: number, at?: [number, number]): Selection {
	const group = p.g && isCrop(p.g) ? GROUP_SHORT[p.g] : null;
	return {
		kind: 'crop',
		id: String(id),
		layer: 'crops',
		title: 'Estimated field',
		fact: [fmtAcres(p.a), p.n ?? group].filter(Boolean).join(' · '),
		source: "USDA NASS Crop Sequence Boundaries and Cropland Data Layer",
		...(at ? { at } : {}),
		data: { props: p, year }
	};
}

/** The years the switcher offers: the edition's window, oldest first. */
export function yearsOf(info: Pick<YearInfo, 'year' | 'first_year'>): number[] {
	if (info.year === null || info.first_year === null) return [];
	return Array.from({ length: info.year - info.first_year + 1 }, (_, i) => info.first_year! + i);
}
