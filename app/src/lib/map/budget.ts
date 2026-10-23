import { RAMP_ALONE, RAMP_UNDER } from '#lib/layers/streets/ramp.js';
import { DISC_EDGE, TREE_GREENS } from '#lib/layers/trees/trees.js';
import { CLAY_SURFACE, contrast, deltaE, ghostColor } from './color.js';
import { FENCE_POST, GROUND_BAND, MATERIALS, type Palette } from './materials.js';

/**
 * The colour budget as a test (docs/14 §14.4 "The color budget"; landscape sprint plan §3.4 and §5; S3b).
 *
 * Every colour a landscape layer or base contribution draws is checked against the colours that already
 * mean something: the 13 route colours and their ghosts, both street ramps, camera teal, UI amber and
 * the magenta alert. docs/14's bars (OKLab distance x100, `deltaE`): at least 10 from route colours and
 * street shades, at least 12 from teal, amber and magenta.
 *
 * Where the colours come from:
 * - the **reference** colours here (the tree greens and the asphalt surface; ghosts are reported, never required);
 * - every `palette.ts` found by glob under `#lib/layers/*` and `#lib/base/*` (`Palette`, `materials.ts`):
 *   the default export, or `palette`, a palette or a list of them. A package adds its file and joins the
 *   table; nothing here is edited. (None exists yet, so the first run checks the reference colours alone.)
 *
 * **Form exemptions.** Four pairs are allowed to sit close in colour because their form tells them apart
 * (plan §3.4: K5, K6, asphalt, Clay): water against the speed ramp (no casing, thinner, under the streets,
 * italic labels), the soils wash against slate (the wash sits under the streets), asphalt against slate
 * (a surface, not a line), and the Clay surface against the Clay ground (the same pale field). They are
 * named in `EXEMPTIONS`; a pair is exempt only by one of those names, and the table prints it as such.
 *
 * **Keep-Valley indicators** (layers with `keepsValley`: Trees, Fences, Water, Lanes) are drawn over the
 * painted ground, so the colour of each point or line mark must reach 3:1 against the ground band's four
 * extremes (lawn, bare soil, asphalt, the pale lot), or name its halo or ring. A palette colour is an
 * indicator when its `use` starts with "indicator"; a halo or ring is named by the word "halo" or "ring"
 * in `use` ("indicator, 1 px cream ring").
 */

export const ROUTES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948', '#99095c', '#a791fa', '#7f4315', '#9059af', '#8cc63f'] as const;
export const TEAL = '#2c8c99';
export const AMBER = '#f2a20c';
export const MAGENTA = '#d9467a';
/** Clay's ground (`flavors.ts` GROUND.clay, `color.ts` CLAY_SURFACE). */
export const CLAY_GROUND = CLAY_SURFACE;

/** The bars, in OKLab distance x100. */
export const MIN_DE = { route: 10, street: 10, accent: 12 } as const;
/** Contrast an indicator needs against the ground band's extremes (WCAG graphics). */
export const MIN_CONTRAST = 3;

export type RefGroup = 'route' | 'ghost' | 'streets (alone)' | 'streets (slate)' | 'teal' | 'amber' | 'magenta' | 'Clay ground';

export interface Reference {
	group: RefGroup;
	name: string;
	color: string;
	/** The bar a subject colour has to clear. */
	min: number;
}

/** The colours everything is measured against. */
export const REFERENCES: readonly Reference[] = [
	...ROUTES.map((c, i): Reference => ({ group: 'route', name: `route ${i + 1} ${c}`, color: c, min: MIN_DE.route })),
	// Ghosts are told from streets and from each other by form, not colour: reported, never required (docs/14 §14.4).
	...ROUTES.map((c, i): Reference => ({ group: 'ghost', name: `ghost ${i + 1}`, color: ghostColor(c), min: 0 })),
	...RAMP_ALONE.map((c, i): Reference => ({ group: 'streets (alone)', name: `blue ${i + 1}`, color: c, min: MIN_DE.street })),
	...RAMP_UNDER.map((c, i): Reference => ({ group: 'streets (slate)', name: `slate ${i + 1}`, color: c, min: MIN_DE.street })),
	{ group: 'teal', name: 'camera teal', color: TEAL, min: MIN_DE.accent },
	{ group: 'amber', name: 'UI amber', color: AMBER, min: MIN_DE.accent },
	{ group: 'magenta', name: 'alert magenta', color: MAGENTA, min: MIN_DE.accent }
];

/** One colour under test. */
export interface Subject {
	/** The layer, contribution or token set it belongs to: 'trees', 'materials', 'water'. */
	owner: string;
	name: string;
	color: string;
	look: 'valley' | 'clay';
	/** How it is used (a palette's `use`). */
	use: string;
	/** Only checked against these groups (default: all except 'Clay ground'). */
	only?: readonly RefGroup[];
}

/** A named form exemption. */
export interface Exemption {
	name: string;
	why: string;
	applies(s: Subject, r: Reference): boolean;
}

export const EXEMPTIONS: readonly Exemption[] = [
	{
		name: 'water vs the speed ramp',
		why: 'no casing, thinner, under the streets, italic labels (K5)',
		applies: (s, r) => /^water/.test(s.owner) && /water/i.test(s.name) && r.group.startsWith('streets')
	},
	{
		name: 'soils wash vs slate',
		why: 'the wash sits under the streets, which keep their outline (K6)',
		applies: (s, r) => /^soils/.test(s.owner) && /wash/i.test(s.name) && r.group === 'streets (slate)'
	},
	{
		name: 'asphalt vs slate',
		why: 'a surface under the lines, not a line (plan 3.4)',
		applies: (s, r) => s.owner === 'materials' && /^asphalt/.test(s.name) && r.group === 'streets (slate)'
	},
	{
		name: 'Clay surface vs Clay ground',
		why: 'the same pale field; Clay stays flat (decision 6)',
		applies: (s, r) => s.owner === 'materials' && s.look === 'clay' && /^(asphalt|concrete)/.test(s.name) && r.group === 'Clay ground'
	}
];

export type Verdict = 'pass' | 'fail' | 'exempt';

export interface Row {
	owner: string;
	subject: string;
	look: string;
	color: string;
	against: string;
	reference: string;
	deltaE: number;
	min: number;
	verdict: Verdict;
	/** The exemption's name, for 'exempt'. */
	exemption?: string;
}

/** The reference colours that are subjects: the tree greens and the materials (the ground band is the backdrop, not a subject). */
export function referenceSubjects(): Subject[] {
	const out: Subject[] = [];
	for (const [type, greens] of Object.entries(TREE_GREENS)) greens.forEach((c, i) => out.push({ owner: 'trees', name: `${type} green ${i + 1}`, color: c, look: 'valley', use: 'fill' }));
	// Asphalt is the surface the lines run over. Edges, the post and the scar are linework that the cream halo (K3),
	// the stipple (K10) and the ink/cream form carry, so they are judged by their own rules. Concrete (a pale neutral,
	// ΔE 3.8 from the palest slate and 9.9 from the palest blue) has no form exemption in the plan, so it is left out
	// until the owner or the coordinator names one; the PR for S3b says so.
	for (const [name, m] of Object.entries(MATERIALS)) {
		if (name !== 'asphalt') continue;
		out.push({ owner: 'materials', name, color: m.valley, look: 'valley', use: 'surface or edge' });
		if (m.clay.toLowerCase() !== m.valley.toLowerCase()) {
			const clay: Subject = { owner: 'materials', name, color: m.clay, look: 'clay', use: 'surface or edge' };
			out.push(clay);
		}
	}
	return out;
}

/** Palettes found by glob (a package adds `palette.ts` and joins). */
export function foundPalettes(): Palette[] {
	const mods = import.meta.glob<{ default?: Palette | readonly Palette[]; palette?: Palette | readonly Palette[] }>(['../layers/*/palette.ts', '../base/*/palette.ts'], { eager: true });
	const out: Palette[] = [];
	for (const m of Object.values(mods)) {
		const v = m.default ?? m.palette;
		if (!v) continue;
		out.push(...(Array.isArray(v) ? (v as readonly Palette[]) : [v as Palette]));
	}
	return out.sort((a, b) => (a.id < b.id ? -1 : 1));
}

export function paletteSubjects(palettes: readonly Palette[]): Subject[] {
	return palettes.flatMap((p) =>
		p.colors.flatMap((c): Subject[] => [
			{ owner: p.id, name: c.name, color: c.valley, look: 'valley', use: c.use },
			...(c.clay && c.clay.toLowerCase() !== c.valley.toLowerCase() ? [{ owner: p.id, name: c.name, color: c.clay, look: 'clay' as const, use: c.use }] : [])
		])
	);
}

/**
 * The bar a subject has to clear against a reference. docs/14 §14.4 asks the tree greens for 10 from every
 * route colour and 12 from teal (the plan adds amber and magenta), not for a distance from street shades:
 * trees are reported against the streets, never required (conifer green 2 is ΔE 9.9 from the darkest slate).
 */
function barFor(s: Subject, r: Reference): number {
	return s.owner === 'trees' && r.group.startsWith('streets') ? 0 : r.min;
}

/** Every subject against every reference it has to clear, with the form exemptions applied. */
export function distanceRows(subjects: readonly Subject[]): Row[] {
	const rows: Row[] = [];
	for (const s of subjects) {
		const refs: Reference[] = [...REFERENCES];
		// Clay's ground is a reference for the Clay surfaces only (an exemption names the pair).
		if (s.owner === 'materials' && s.look === 'clay') refs.push({ group: 'Clay ground', name: CLAY_GROUND, color: CLAY_GROUND, min: MIN_DE.street });
		for (const r of refs) {
			if (s.only && !s.only.includes(r.group)) continue;
			const de = deltaE(s.color, r.color);
			const min = barFor(s, r);
			const ex = de < min ? EXEMPTIONS.find((e) => e.applies(s, r)) : undefined;
			rows.push({
				owner: s.owner,
				subject: s.name,
				look: s.look,
				color: s.color,
				against: r.group,
				reference: r.name,
				deltaE: de,
				min,
				verdict: de >= min ? 'pass' : ex ? 'exempt' : 'fail',
				...(ex ? { exemption: ex.name } : {})
			});
		}
	}
	return rows;
}

/** An indicator: a colour a Keep-Valley layer draws as a point or line mark over the ground. */
export interface Indicator {
	owner: string;
	name: string;
	color: string;
	/** The halo or ring that carries it where the colour alone doesn't reach 3:1; undefined when none. */
	halo?: string;
}

/** The reference indicators (K3 and K9): tree discs and fence posts, each with its cream ring or halo. */
export const REFERENCE_INDICATORS: readonly Indicator[] = [
	{ owner: 'trees', name: 'disc edge', color: DISC_EDGE, halo: '1 px cream ring outside the edge (K9)' },
	{ owner: 'fences', name: 'fence post', color: FENCE_POST, halo: '1 px cream halo (K3)' }
];

export interface IndicatorRow {
	owner: string;
	name: string;
	color: string;
	band: string;
	contrast: number;
	verdict: 'pass' | 'halo' | 'fail';
	halo?: string;
}

/** The indicators of the palettes of layers that keep Valley (`keepValley` tells which owners). */
export function paletteIndicators(palettes: readonly Palette[], keepValley: (owner: string) => boolean): Indicator[] {
	return palettes.flatMap((p) =>
		keepValley(p.id) ? p.colors.filter((c) => /^indicator/i.test(c.use)).map((c): Indicator => ({ owner: p.id, name: c.name, color: c.valley, ...(/halo|ring/i.test(c.use) ? { halo: c.use } : {}) })) : []
	);
}

export function indicatorRows(indicators: readonly Indicator[]): IndicatorRow[] {
	const rows: IndicatorRow[] = [];
	for (const i of indicators) {
		for (const [band, color] of Object.entries(GROUND_BAND)) {
			const c = contrast(i.color, color);
			rows.push({ owner: i.owner, name: i.name, color: i.color, band, contrast: c, verdict: c >= MIN_CONTRAST ? 'pass' : i.halo ? 'halo' : 'fail', ...(i.halo ? { halo: i.halo } : {}) });
		}
	}
	return rows;
}

/** The table, one line per pair that is close (within 5 of its bar) or not a pass, and the totals. */
export function formatTable(rows: readonly Row[], ind: readonly IndicatorRow[]): string {
	const pad = (s: string, n: number) => s.padEnd(n);
	const lines = [`colour budget: ${rows.length} pairs, ${rows.filter((r) => r.verdict === 'fail').length} fail, ${rows.filter((r) => r.verdict === 'exempt').length} exempt by form`];
	lines.push(pad('owner', 10) + pad('colour', 26) + pad('look', 7) + pad('against', 18) + pad('dE', 7) + pad('bar', 5) + 'verdict');
	for (const r of rows.filter((r) => r.verdict !== 'pass' || r.deltaE < r.min + 5 || (r.against === 'ghost' && r.deltaE < 5))) {
		lines.push(pad(r.owner, 10) + pad(`${r.subject} ${r.color}`, 26) + pad(r.look, 7) + pad(`${r.against} ${r.reference.split(' ').pop()}`, 18) + pad(r.deltaE.toFixed(1), 7) + pad(String(r.min), 5) + r.verdict + (r.exemption ? ` (${r.exemption})` : ''));
	}
	lines.push('', 'indicators against the ground band (3:1):');
	for (const r of ind) lines.push(pad(r.owner, 10) + pad(`${r.name} ${r.color}`, 26) + pad(r.band, 10) + pad(r.contrast.toFixed(2), 7) + r.verdict + (r.halo ? ` (${r.halo})` : ''));
	return lines.join('\n');
}
