import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { CHROME_ICONS } from './chrome-icons.js';
import { LAYER_ICONS } from './icons.js';

/** phosphor-svelte's own duotone branch of an icon component: [tone path, line path]. */
function phosphorDuotone(name: string): [string, string] {
	const require = createRequire(import.meta.url);
	const dir = dirname(require.resolve('phosphor-svelte/package.json'));
	const src = readFileSync(join(dir, 'lib', `${name}Icon.svelte`), 'utf8');
	const branch = /weight === "duotone"\}\s*([\s\S]*?)\{:else/.exec(src)?.[1] ?? '';
	const paths = [...branch.matchAll(/<path d="([^"]+)"([^>]*)\/>/g)];
	const tone = paths.find((p) => p[2].includes('opacity="0.2"'))?.[1] ?? '';
	const line = paths.find((p) => !p[2].includes('opacity'))?.[1] ?? '';
	return [tone, line];
}

describe('icons', () => {
	it('are Phosphor’s duotone paths, exactly as phosphor-svelte ships them', () => {
		const all = [...LAYER_ICONS, ...CHROME_ICONS];
		expect(all.length).toBeGreaterThanOrEqual(6);
		for (const icon of all) {
			const [tone, line] = phosphorDuotone(icon.name);
			expect(tone, `${icon.name} tone`).not.toBe('');
			expect(icon.tone, `${icon.name} tone`).toBe(tone);
			expect(icon.line, `${icon.name} line`).toBe(line);
		}
	});
});
