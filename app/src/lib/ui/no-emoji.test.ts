import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * The visual review checklist (docs/14 §14.11, WP15): "no emoji icons left;
 * Phosphor duotone everywhere". Icons come from Phosphor (ch. 13 §13.7);
 * status uses the shapes ● ▲ ■ ◌, which are plain text. This scans every
 * source file for a character that browsers draw as a color emoji by default,
 * or one forced to emoji with U+FE0F. (A symbol that may be drawn either way,
 * like ▶, carries U+FE0E so it stays text.)
 */
const SRC = join(import.meta.dirname, '..', '..');
const EMOJI = /\p{Emoji_Presentation}|\u{FE0F}/u;

function files(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
		e.isDirectory() ? files(join(dir, e.name)) : /\.(svelte|ts|css|html)$/.test(e.name) ? [join(dir, e.name)] : []
	);
}

describe('no emoji icons', () => {
	it('no source file draws a color emoji', () => {
		const found: string[] = [];
		for (const f of files(SRC))
			readFileSync(f, 'utf8')
				.split('\n')
				.forEach((line, i) => {
					if (EMOJI.test(line)) found.push(`${relative(SRC, f)}:${i + 1}: ${line.trim().slice(0, 80)}`);
				});
		expect(found).toEqual([]);
	});

	it('the scan sees the app (and would catch one)', () => {
		expect(files(SRC).length).toBeGreaterThan(100);
		expect(EMOJI.test(`${String.fromCodePoint(0x1f68c)} 38 buses`)).toBe(true);
		expect(EMOJI.test(`\u{25B6}\u{FE0F}`)).toBe(true);
		expect(EMOJI.test('● live ▲ late ■ offline ◌ not calibrated')).toBe(false);
	});
});
