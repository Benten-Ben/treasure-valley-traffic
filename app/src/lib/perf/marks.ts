/**
 * Performance marks (docs/14 §14.9, "How we measure"). The harness
 * (`scripts/perf.mjs --real`) reads every `tvt:` mark with
 * `performance.getEntriesByType('mark')`.
 *
 * The boot sets `boot` and `manifest`; the app context sets `style-load`,
 * `first-frame`, `load` and `idle` when the map fires them; the `?perf` HUD
 * adds `tvt:layer:<id>:on` and `:idle` for each layer it sees turned on.
 */
export const MARK = {
	boot: 'tvt:boot',
	manifest: 'tvt:manifest',
	styleLoad: 'tvt:style-load',
	firstFrame: 'tvt:first-frame',
	load: 'tvt:load',
	idle: 'tvt:idle'
} as const;

export const layerMark = (id: string, phase: 'on' | 'idle') => `tvt:layer:${id}:${phase}`;

/** Set a mark; never throws (a mark is a measurement, not a feature). */
export function mark(name: string): void {
	try {
		performance.mark(name);
	} catch {
		/* no performance API */
	}
}

/** Every `tvt:` mark so far, as ms since navigation start (the first of each name). */
export function readMarks(): Record<string, number> {
	const out: Record<string, number> = {};
	for (const m of performance.getEntriesByType('mark')) if (m.name.startsWith('tvt:') && !(m.name in out)) out[m.name] = Math.round(m.startTime);
	return out;
}
