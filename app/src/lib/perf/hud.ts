import { GeoJSONSource, type Map } from 'maplibre-gl';
import type { PerfFlags } from './flags.js';
import { layerMark, mark } from './marks.js';

/**
 * The `?perf` HUD and the `?lod=` hook (docs/14 §14.9, "How we measure";
 * fix 8). A lazy chunk: the boot loads it only when one of those flags is in
 * the URL, and the map waits for it, so the counters see the map's first
 * WebGL texture and first `setData`.
 *
 * The HUD shows, twice a second: rendered fps (median and p95 frame time over
 * the last 5 s), JS heap, tiles per source (in view + cached), network
 * requests and bytes so far, `setData` calls per second, and live WebGL
 * textures. `globalThis.__tvtPerf` exposes the same numbers to the harness
 * (`scripts/perf.mjs` S5 and S7).
 *
 * It reads a few MapLibre internals (tile managers) for its tile counts. This
 * is a debugging aid, not a feature; it guards every such read.
 */

interface PerfHandle {
	readonly setDataCalls: number;
	readonly setDataPerSecond: number;
	readonly textures: number;
	readonly frames: number;
	snapshot(): Snapshot;
}

interface Snapshot {
	fpsMedian: number | null;
	p95FrameMs: number | null;
	heapMB: number | null;
	tiles: Record<string, { inView: number; cached: number }>;
	requests: number;
	transferMB: number;
	setDataPerSecond: number;
	textures: number;
}

const counters = { setData: 0, setDataTimes: [] as number[], textures: 0, frames: 0 };
let installed = false;

/** Count live WebGL textures and GeoJSON `setData` calls (from now on). */
function installCounters(): void {
	if (installed) return;
	installed = true;
	const live = new WeakSet<WebGLTexture>();
	for (const C of [globalThis.WebGL2RenderingContext, globalThis.WebGLRenderingContext]) {
		if (!C) continue;
		const proto = C.prototype;
		const create = proto.createTexture;
		const del = proto.deleteTexture;
		proto.createTexture = function (this: WebGL2RenderingContext) {
			const t = create.call(this);
			if (t) {
				live.add(t);
				counters.textures++;
			}
			return t;
		};
		proto.deleteTexture = function (this: WebGL2RenderingContext, t: WebGLTexture | null) {
			if (t && live.has(t)) {
				live.delete(t);
				counters.textures--;
			}
			return del.call(this, t);
		};
	}
	const proto = GeoJSONSource.prototype as unknown as Record<string, (...a: unknown[]) => unknown>;
	for (const name of ['setData', 'updateData']) {
		const orig = proto[name];
		if (typeof orig !== 'function') continue;
		proto[name] = function (this: unknown, ...a: unknown[]) {
			counters.setData++;
			counters.setDataTimes.push(performance.now());
			return orig.apply(this, a);
		};
	}
}

/** The app's map, once MapHost has handed it to the app context (`__tvt.map`). */
function whenMap(): Promise<Map> {
	const until = Date.now() + 120_000;
	return new Promise((resolve, reject) => {
		const look = () => {
			const map = (globalThis as { __tvt?: { map?: Map | null } }).__tvt?.map;
			if (map) resolve(map);
			else if (Date.now() > until) reject(new Error('no map within 2 minutes'));
			else setTimeout(look, 50);
		};
		look();
	});
}

const DEM_SOURCES = ['terrain', 'hillshade'];

/** `?lod=M,R`: coarser DEM tiles toward the horizon at high pitch (fix 8, A/B only until measured). */
function applyLod(map: Map, [levels, ratio]: [number, number]): void {
	const apply = () => {
		for (const id of DEM_SOURCES) if (map.getSource(id)) map.setSourceTileLodParams(levels, ratio, id);
	};
	if (map.isStyleLoaded()) apply();
	else map.once('style.load', apply);
}

const pct = (sorted: number[], q: number) => (sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))] : null);

function tileCounts(map: Map): Snapshot['tiles'] {
	const out: Snapshot['tiles'] = {};
	try {
		const style = (map as unknown as { style?: { tileManagers?: Record<string, unknown>; sourceCaches?: Record<string, unknown> } }).style;
		const managers = style?.tileManagers ?? style?.sourceCaches ?? {};
		for (const [id, tm] of Object.entries(managers) as [string, { _tiles?: object; _cache?: { order?: unknown[] } }][]) {
			out[id] = { inView: Object.keys(tm._tiles ?? {}).length, cached: tm._cache?.order?.length ?? 0 };
		}
	} catch {
		/* internals moved: no tile counts */
	}
	return out;
}

function network(): { requests: number; transferMB: number } {
	const entries = performance.getEntriesByType('resource') as PerformanceResourceTiming[];
	return { requests: entries.length, transferMB: +(entries.reduce((s, e) => s + (e.transferSize || 0), 0) / 1e6).toFixed(2) };
}

function startHud(map: Map): PerfHandle {
	const frames: number[] = [];
	map.on('render', () => {
		counters.frames++;
		frames.push(performance.now());
		if (frames.length > 600) frames.splice(0, frames.length - 600);
	});
	// Make room for every resource (the default buffer holds 250).
	performance.setResourceTimingBufferSize?.(5000);

	const snapshot = (): Snapshot => {
		const now = performance.now();
		const recent = frames.filter((t) => now - t < 5000);
		const gaps = recent.slice(1).map((t, i) => t - recent[i]).sort((a, b) => a - b);
		const med = pct(gaps, 0.5);
		while (counters.setDataTimes.length && now - counters.setDataTimes[0] > 1000) counters.setDataTimes.shift();
		const heap = (performance as { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize;
		return {
			fpsMedian: med ? +(1000 / med).toFixed(1) : null,
			p95FrameMs: pct(gaps, 0.95) === null ? null : +pct(gaps, 0.95)!.toFixed(1),
			heapMB: heap === undefined ? null : +(heap / 1e6).toFixed(1),
			tiles: tileCounts(map),
			...network(),
			setDataPerSecond: counters.setDataTimes.length,
			textures: counters.textures
		};
	};

	const box = document.createElement('pre');
	box.className = 'tvt-perf-hud';
	box.setAttribute('aria-hidden', 'true');
	Object.assign(box.style, {
		position: 'fixed',
		left: '8px',
		top: '64px',
		zIndex: '1000',
		margin: '0',
		padding: '6px 8px',
		borderRadius: '8px',
		background: 'rgba(20, 24, 31, 0.82)',
		color: '#f4f1ea',
		font: '11px/1.35 "Overpass Mono", ui-monospace, monospace',
		pointerEvents: 'none',
		whiteSpace: 'pre'
	});
	document.body.append(box);

	// Layer marks: tvt:layer:<id>:on when a layer turns on, :idle at the map's next idle once it's ready.
	const on = new Set<string>();
	const waiting = new Set<string>();
	const info = () =>
		(globalThis as { __tvt?: { layers?: { enabled?: string[]; status?: Record<string, string> } | null } }).__tvt?.layers ?? null;
	map.on('idle', () => {
		const status = info()?.status ?? {};
		for (const id of [...waiting]) {
			if (status[id] === 'ready' || status[id] === 'stale') {
				mark(layerMark(id, 'idle'));
				waiting.delete(id);
			}
		}
	});

	const tick = () => {
		const enabled = new Set(info()?.enabled ?? []);
		for (const id of enabled) {
			if (on.has(id)) continue;
			on.add(id);
			waiting.add(id);
			mark(layerMark(id, 'on'));
		}
		for (const id of [...on]) if (!enabled.has(id)) on.delete(id);
		const s = snapshot();
		const tiles = Object.entries(s.tiles)
			.filter(([, t]) => t.inView || t.cached)
			.map(([id, t]) => `  ${id.padEnd(14)} ${String(t.inView).padStart(3)} + ${t.cached}`)
			.join('\n');
		box.textContent = [
			`fps     ${s.fpsMedian ?? 'idle'}${s.p95FrameMs !== null ? `  p95 ${s.p95FrameMs} ms` : ''}`,
			`heap    ${s.heapMB ?? '?'} MB`,
			`net     ${s.requests} req, ${s.transferMB} MB`,
			`setData ${s.setDataPerSecond}/s (${counters.setData})`,
			`gl tex  ${s.textures}`,
			`tiles (in view + cached)`,
			tiles
		].join('\n');
	};
	tick();
	setInterval(tick, 500);

	return {
		get setDataCalls() {
			return counters.setData;
		},
		get setDataPerSecond() {
			return snapshot().setDataPerSecond;
		},
		get textures() {
			return counters.textures;
		},
		get frames() {
			return counters.frames;
		},
		snapshot
	};
}

/** Start what the flags ask for. Resolves once the counters are in place (before the map exists). */
export function startPerfTools(flags: PerfFlags): void {
	if (flags.hud) installCounters();
	whenMap().then(
		(map) => {
			if (flags.lod) applyLod(map, flags.lod);
			if (flags.hud) {
				const handle = startHud(map);
				Object.defineProperty(globalThis, '__tvtPerf', { value: handle, configurable: true });
			}
		},
		(e) => console.warn('perf tools:', e.message)
	);
}
