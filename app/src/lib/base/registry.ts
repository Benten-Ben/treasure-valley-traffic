import type { BaseContribution } from './types.js';

/**
 * The base-contribution registry. Every `#lib/base/<plugin>/<name>.base.ts` is found at build time
 * (like `#lib/layers/registry.ts`), and default-exports one `BaseContribution` or a list. They are
 * in the initial bundle, so they stay small: data and two functions, no scene code.
 */
const found = import.meta.glob<{ default: BaseContribution | readonly BaseContribution[] }>('./*/*.base.ts', { eager: true });

/** Every contribution, ordered by id so the style is the same whatever the glob's order. */
export const BASE_CONTRIBUTIONS: readonly BaseContribution[] = Object.values(found)
	.flatMap((m) => (Array.isArray(m.default) ? m.default : [m.default as BaseContribution]))
	.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

export function baseContribution(id: string): BaseContribution | undefined {
	return BASE_CONTRIBUTIONS.find((c) => c.id === id);
}
