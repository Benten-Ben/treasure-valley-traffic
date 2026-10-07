import type { AppCtx } from '#lib/app/context.js';
import { followOf } from '#lib/state/follow.svelte.js';
import { historyOf } from '#lib/state/history.svelte.js';
import { Z_BASE, type Point, type WindowManager, type WindowSpec } from '#lib/state/windows.svelte.js';
import TestWindow from './TestWindow.svelte';
import { toasts } from './toasts.svelte.js';

/**
 * The test window (`?window-test`; the `windows` spec, WP3 acceptance): a
 * 'test' window kind, so pinned test windows reopen after a reload, and a
 * handle for the spec at `globalThis.__tvtWindows`:
 *
 * - `open(n, anchor?)`: open test window n (key `test:n`); false when it
 *   couldn't (every window pinned);
 * - `info()`: the layout, limit, safe area and each window's key, number,
 *   rect, pinned and z-index;
 * - `remembered(key)`, `toasts()`, `history()`;
 * - `followTest()`: follow a made-up target drifting east at about 30 m/s
 *   from the centre; `following()` names what's followed (or null).
 *
 * Its code loads only with `?window-test`.
 */
export function testSpec(n: number, anchor?: Point): WindowSpec {
	return {
		key: `test:${n}`,
		title: `Test window ${n}`,
		component: TestWindow,
		props: { n },
		aspect: 16 / 9,
		anchor,
		status: { shape: '●', word: 'test pattern', color: 'var(--accent-2)', detail: 'A drawn test pattern; no camera image' },
		restore: { kind: 'test', data: n }
	};
}

export function startWindowTest(app: AppCtx, windows: WindowManager): () => void {
	const unkind = windows.registerKind('test', (data) => (typeof data === 'number' ? testSpec(data) : null));
	const handle = Object.freeze({
		open: (n: number, anchor?: Point) => windows.open(testSpec(n, anchor)) !== null,
		close: (n: number) => windows.close(`test:${n}`),
		info: () => ({
			layout: windows.layout,
			limit: windows.limit,
			safe: windows.safe,
			pending: windows.pending,
			list: windows.list.map((w) => ({
				key: w.key,
				number: w.number,
				rect: w.rect,
				pinned: w.pinned,
				z: Z_BASE + windows.rank(w.key)
			}))
		}),
		remembered: (key: string) => windows.remembered(key),
		toasts: () => toasts.list.map((t) => t.text),
		history: () => historyOf(app).stack.length,
		followTest: () => {
			const map = app.map;
			if (!map) return false;
			const c = map.getCenter();
			const t0 = performance.now();
			const position = (): [number, number] => [c.lng + 0.0004 * ((performance.now() - t0) / 1000), c.lat];
			return followOf(app).start({ kind: 'test', id: 'drift', label: 'the test target', position });
		},
		following: () => followOf(app).current?.label ?? null
	});
	Object.defineProperty(globalThis, '__tvtWindows', { value: handle, configurable: true });
	return () => {
		unkind();
		if ((globalThis as { __tvtWindows?: unknown }).__tvtWindows === handle) Reflect.deleteProperty(globalThis, '__tvtWindows');
	};
}
