import type { App } from '#lib/app/app.svelte.js';
import type { Scene } from './index.js';

/**
 * `app.scene()` (docs/14 §14.8, "App context"; "The 3D engine"): the 3D mesh
 * engine is a lazy chunk, and this small always-loaded part decides when it
 * loads:
 *
 * - never before the map's first `idle`;
 * - after that idle, it's prefetched (the code only) if Transit or Cameras
 *   is on;
 * - otherwise it loads when one of them is turned on;
 * - `app.scene()` resolves to the one Scene, creating it (and its custom
 *   layer) the first time an owner asks, after the first idle.
 *
 * `?scene-test` starts the test page of 1,000 instances (its code loads only
 * then) as `globalThis.__tvtSceneTest`.
 */
declare module '#lib/app/context.js' {
	interface AppCtx {
		/** The 3D mesh engine, loaded on demand (never before the map's first idle). */
		scene(): Promise<Scene>;
	}
}

declare module '#lib/app/app.svelte.js' {
	interface App {
		scene(): Promise<Scene>;
	}
}

/** The layers whose 3D objects live in the scene. */
export const SCENE_LAYERS = ['transit', 'cameras'] as const;

type SceneModule = typeof import('./index.js');

/** When and whether the chunk was requested (for tests and the ?perf HUD). */
export const sceneLoad = { requestedAt: null as number | null, reason: null as string | null };

export function installScene(app: App): () => void {
	let mod: Promise<SceneModule> | null = null;
	let scene: Promise<Scene> | null = null;
	let idled = false;
	let resolveIdle!: () => void;
	const firstIdle = new Promise<void>((r) => (resolveIdle = r));
	const cleanup: (() => void)[] = [];

	const load = (reason: string) => {
		if (!mod) {
			sceneLoad.requestedAt = performance.now();
			sceneLoad.reason = reason;
			mod = import('./index.js');
			mod.catch(() => (mod = null));
		}
		return mod;
	};

	app.scene = () => {
		scene ??= firstIdle.then(() => load('scene()')).then((m) => m.createScene(app));
		scene.catch(() => (scene = null));
		return scene;
	};

	const wanted = () => app.layers.set.enabled.some((id) => (SCENE_LAYERS as readonly string[]).includes(id));

	void app.styleReady
		.then((map) => {
			const onIdle = () => {
				idled = true;
				resolveIdle();
				if (wanted()) void load('prefetch').catch(() => {});
			};
			map.once('idle', onIdle);
			cleanup.push(() => map.off('idle', onIdle));
		})
		.catch(() => {});

	// Turning Transit or Cameras on (after the first idle) loads the code.
	cleanup.push(
		$effect.root(() => {
			$effect(() => {
				if (wanted() && idled) void load('layer on').catch(() => {});
			});
		})
	);

	if (typeof location !== 'undefined' && new URLSearchParams(location.search).has('scene-test')) {
		void app.whenReady().then(async () => {
			const [{ startSceneTest }, s] = await Promise.all([import('./test-scene.js'), app.scene()]);
			Object.defineProperty(globalThis, '__tvtSceneTest', { value: startSceneTest(app, s), configurable: true });
		});
	}

	return () => {
		for (const f of cleanup.splice(0)) f();
		void scene?.then((s) => s.destroy()).catch(() => {});
		scene = null;
	};
}
