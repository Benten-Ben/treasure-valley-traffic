import type { Map } from 'maplibre-gl';
import type { DataMeta } from '#lib/contracts/meta.js';
import { setAerial, type BasemapManifest } from '#lib/map/style.js';
import { Modes } from '#lib/state/modes.svelte.js';
import { ViewManager } from '#lib/state/view.svelte.js';
import * as boot from './boot.js';
import type { AppCtx, AppStatus, DataTopic } from './context.js';

/**
 * The app context's implementation (see context.ts for the contract). The
 * `(map)` layout creates one per visit; MapHost hands it the map once.
 */
export interface AppOptions {
	/** Replace the hash of the current history entry (SvelteKit's shallow goto). */
	writeHash: (hash: string) => void;
	/** Whether the hash may be written now: the explore page, no navigation running. */
	canWriteHash: () => boolean;
	/** The router's current URL, to tell whether the browser has moved on (a navigation pending). */
	routerUrl: () => string;
}

/** What `__tvt.layers` reports; the layout supplies it (WP2's layer manager replaces it). */
export type LayersInfo = () => unknown;

const stripHash = (href: string) => href.replace(/#.*$/, '');

/** The map's next `idle`: a repaint is asked for, so an idle map answers at once. */
export function nextIdle(map: Map): Promise<void> {
	return new Promise((resolve) => {
		map.once('idle', () => resolve());
		map.triggerRepaint();
	});
}

export class App implements AppCtx {
	map = $state.raw<Map | null>(null);
	manifest = $state.raw<BasemapManifest | null>(null);
	status = $state<AppStatus>('loading');
	problem = $state<string | null>(null);
	meta = $state.raw<DataMeta | null>(null);
	aerial = $state(false);
	paused = $state(false);
	mapsCreated = 0;
	layersInfo: LayersInfo | null = null;

	readonly view: ViewManager;
	readonly modes: Modes;
	readonly styleReady: Promise<Map>;

	#resolveStyle!: (m: Map) => void;
	#rejectStyle!: (e: Error) => void;
	#pending = new Set<Promise<unknown>>();
	#navigation: Promise<unknown> | null = null;
	#navigated: (() => void)[] = [];
	#o: AppOptions;
	#cleanup: (() => void)[] = [];

	constructor(o: AppOptions) {
		this.#o = o;
		this.view = new ViewManager({ write: o.writeHash, canWrite: o.canWriteHash });
		this.modes = new Modes(this.view);
		this.styleReady = new Promise<Map>((resolve, reject) => {
			this.#resolveStyle = resolve;
			this.#rejectStyle = reject;
		});
		this.styleReady.catch(() => {});
		this.view.register('aerial', {
			save: () => this.aerial,
			restore: (on) => void this.setAerial(Boolean(on))
		});
		void boot.meta.then((m) => (this.meta = m));
	}

	dataUrl(path: string, version?: keyof DataMeta['versions']): Promise<string> {
		return boot.dataUrl(path, version);
	}

	#topics = new globalThis.Map<DataTopic, Set<() => void>>();

	notify(topic: DataTopic): void {
		for (const fn of this.#topics.get(topic) ?? []) fn();
	}

	subscribe(topic: DataTopic, fn: () => void): () => void {
		let set = this.#topics.get(topic);
		if (!set) this.#topics.set(topic, (set = new Set()));
		set.add(fn);
		return () => set.delete(fn);
	}

	/** MapHost hands over the map it created (once per visit). */
	attach(map: Map, manifest: BasemapManifest): void {
		this.map = map;
		this.manifest = manifest;
		this.mapsCreated += 1;
		this.view.attach(map);
		const onStyle = () => {
			performance.mark('tvt:style-load');
			this.status = 'ready';
			this.#resolveStyle(map);
		};
		if (map.isStyleLoaded()) onStyle();
		else map.once('style.load', onStyle);
		map.once('render', () => performance.mark('tvt:first-frame'));
		map.once('load', () => performance.mark('tvt:load'));
		map.once('idle', () => performance.mark('tvt:idle'));
		const lost = () => (this.paused = true);
		const restored = () => (this.paused = false);
		map.on('webglcontextlost', lost);
		map.on('webglcontextrestored', restored);
		this.#cleanup.push(() => {
			map.off('webglcontextlost', lost);
			map.off('webglcontextrestored', restored);
		});
	}

	/** The basemap isn't there (or the map couldn't start): say why, and stop waiting for it. */
	unavailable(reason: string, status: 'unavailable' | 'error' = 'unavailable'): void {
		this.status = status;
		this.problem = reason;
		this.#rejectStyle(new Error(reason));
	}

	/** MapHost is going away (leaving the map routes). */
	detach(): void {
		for (const f of this.#cleanup.splice(0)) f();
		this.view.detach();
		this.map = null;
	}

	setAerial(on: boolean): boolean {
		const map = this.map;
		const m = this.manifest;
		if (!map || !m) return false;
		this.aerial = setAerial(map, m, location.origin, on);
		return this.aerial;
	}

	exaggeration(): number {
		return this.map?.getTerrain()?.exaggeration ?? 1;
	}

	setExaggeration(value: number): void {
		const map = this.map;
		const t = map?.getTerrain();
		if (map && t && (t.exaggeration ?? 1) !== value) map.setTerrain({ ...t, exaggeration: value });
	}

	track<T>(p: Promise<T>): Promise<T> {
		this.#pending.add(p);
		const done = () => this.#pending.delete(p);
		p.then(done, done);
		return p;
	}

	/** A (non-shallow) navigation started; `complete` settles when it's done. */
	navigationStarted(complete: Promise<unknown>): void {
		const p = complete.catch(() => {});
		this.#navigation = p;
		void p.then(() => {
			if (this.#navigation === p) this.#navigation = null;
		});
	}

	/** A navigation finished (afterNavigate). */
	navigationFinished(): void {
		for (const f of this.#navigated.splice(0)) f();
	}

	#nextNavigation(timeoutMs: number): Promise<void> {
		return new Promise((resolve) => {
			const t = setTimeout(resolve, timeoutMs);
			this.#navigated.push(() => {
				clearTimeout(t);
				resolve();
			});
		});
	}

	/** The browser is at a URL the router hasn't reached yet (a Back or Forward just happened). */
	#urlPending(): boolean {
		return stripHash(location.href) !== stripHash(this.#o.routerUrl());
	}

	async whenReady(): Promise<void> {
		const map = await this.styleReady;
		const deadline = Date.now() + 30_000;
		while (Date.now() < deadline) {
			if (this.#navigation) await this.#navigation;
			else if (this.#urlPending()) await this.#nextNavigation(Math.max(0, deadline - Date.now()));
			else if (this.#pending.size) await Promise.allSettled([...this.#pending]);
			else break;
		}
		await nextIdle(map);
	}

	/** The read-only debug handle for tests and the console (docs/14 §14.8). */
	install(): void {
		const app = this;
		const handle = Object.freeze({
			get map() {
				return app.map;
			},
			get mapsCreated() {
				return app.mapsCreated;
			},
			/** Resolves (to true) once the map has settled; rejects when it's unavailable. */
			get ready() {
				const p = app.whenReady().then(() => true);
				p.catch(() => {});
				return p;
			},
			get layers() {
				return app.layersInfo?.() ?? null;
			},
			get mode() {
				return app.modes.current;
			},
			get status() {
				return app.status;
			},
			get view() {
				return app.view.current();
			}
		});
		Object.defineProperty(globalThis, '__tvt', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#handle = handle;
	}

	#handle: object | null = null;

	/** Remove the handle (leaving the map routes), if it's still this app's. */
	uninstall(): void {
		if (this.#handle && (globalThis as { __tvt?: unknown }).__tvt === this.#handle) Reflect.deleteProperty(globalThis, '__tvt');
		this.#handle = null;
	}
}
