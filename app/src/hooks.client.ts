import type { ShellSlot, WithShellSlot } from '#lib/ui/shell-slot.js';

/**
 * Client hooks. Only one job so far: start loading the map's chrome early
 * (docs/14 §14.9, "Shell paint": the top bar and toolbar paint before the
 * map).
 *
 * The chrome (ChromeShell) is its own chunk, to keep the initial JavaScript
 * within its budget, and Chrome.svelte imports it when the map layout mounts.
 * By then MapLibre's chunk has loaded and the map's first frame is close, so
 * in real Chrome the shell used to appear 35–96 ms after the map's first
 * frame (§14.11). This module runs with the app's entry, before the route's
 * own JavaScript, so importing the chunk here fetches it alongside MapLibre
 * instead, and Chrome.svelte takes the loaded shell from `__tvtShell`
 * (#lib/ui/shell-slot.ts) as the layout mounts, before the map exists. It's
 * the same chunk and the same requests, only sooner. A failure here is
 * Chrome.svelte's to report.
 *
 * Only the map's routes ('/' and /calibrate/…) show the chrome. The app has
 * no base path; `$app/paths` would say so, but it pulled modules into the
 * initial JavaScript (about 0.6 KB gzip), against 0.3 KB for this hook.
 */
const path = location.pathname;
if (path === '/' || path.startsWith('/calibrate/')) {
	const slot: ShellSlot = { loading: import('#lib/ui/ChromeShell.svelte').then((m) => (slot.loaded = m.default)), loaded: null };
	slot.loading.catch(() => {});
	(globalThis as WithShellSlot).__tvtShell = slot;
}
