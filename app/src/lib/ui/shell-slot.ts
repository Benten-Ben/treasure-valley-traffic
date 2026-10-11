import type { Component } from 'svelte';
import type { AppCtx } from '#lib/app/context.js';

/**
 * Where the chrome's chunk waits for Chrome.svelte (docs/14 §14.9, "Shell
 * paint"). Types only: src/hooks.client.ts starts loading ChromeShell as the
 * app's entry runs and keeps it in `globalThis.__tvtShell`; Chrome.svelte
 * takes it from there. A module with code shared by the entry and the map's
 * route would be a chunk of its own, one more request on every first load.
 *
 * When the chunk has arrived by the time the map's layout mounts (it usually
 * has: it is small, and the layout waits for MapLibre's chunk), Chrome.svelte
 * mounts the shell in the same pass as the layout, before MapHost creates
 * the map, so the shell paints first. Asking `import()` again there answers
 * a task later, and by then the map can have asked for its first frame: on
 * SwiftShader that frame takes over a second, and the shell came after it.
 */
export type Shell = Component<{ app: AppCtx }>;

export interface ShellSlot {
	/** The import in flight (a failure stays failed, for Chrome.svelte to report). */
	loading: Promise<Shell>;
	/** The shell, once its chunk has arrived. */
	loaded: Shell | null;
}

export type WithShellSlot = typeof globalThis & { __tvtShell?: ShellSlot };
