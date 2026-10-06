import type { Map as MapLibre } from 'maplibre-gl';
import type { BasemapManifest } from '#lib/map/style.js';
import { readStored, writeStored } from './persisted.svelte.js';

/**
 * The view module (docs/14 §14.3 "Modes and the view stack", §14.8 "View
 * module").
 *
 * - **Hash:** it owns `#map=z/lat/lng/bearing/pitch`, written on `moveend`
 *   (debounced 500 ms) as a shallow, replacing navigation, never through
 *   MapLibre's own `hash` option. Other `&key=value` pieces of the hash (WP2's
 *   `layers=`) are kept as they are; `setParam` changes them. Writing is
 *   suspended while a mode is active.
 * - **Memory:** the exact view is also saved in `tvt:v2:view`. On boot the
 *   URL wins, then the saved view, then the manifest's default; when the
 *   URL's rounded view is the saved view rounded, the exact saved one is used.
 * - **Legacy links:** an old `#z/lat/lng/bearing/pitch` hash is rewritten
 *   once to the `#map=` form.
 * - **Snapshots:** `snapshot()` captures everything a mode may change (camera
 *   and its limits, padding, field of view, terrain exaggeration, plus the
 *   registered parts: `aerial` and `layers` from WP1; `look` and `windows`
 *   register from their own packages), and `restore()` puts it all back
 *   exactly, with `jumpTo`.
 */

export interface CameraView {
	center: [number, number];
	zoom: number;
	bearing: number;
	pitch: number;
}

export interface Padding {
	top: number;
	right: number;
	bottom: number;
	left: number;
}

export interface ViewSnapshot {
	center: [number, number];
	zoom: number;
	bearing: number;
	pitch: number;
	roll: number;
	/** Vertical field of view, degrees. */
	fov: number;
	padding: Padding;
	maxZoom: number;
	maxPitch: number;
	centerClampedToGround: boolean;
	/** Terrain exaggeration, or null without terrain. */
	exaggeration: number | null;
	/** What each registered part saved: aerial, layers, look, windows… */
	parts: Record<string, unknown>;
}

/** A piece of app state that a snapshot carries (aerial, layer visibility, look, open windows). */
export interface SnapshotPart {
	save(): unknown;
	restore(value: unknown): void;
}

// --- the hash ------------------------------------------------------------------

/** Decimal places for lat/lng at a zoom: about a pixel, plus one digit. */
export function latLngDigits(zoom: number): number {
	return Math.max(0, Math.ceil((zoom * Math.LN2 + Math.log(512 / 360 / 0.5)) / Math.LN10)) + 1;
}

const fixed = (x: number, digits: number) => String(+x.toFixed(digits));

/** Bearing in (−180, 180]. */
export function normalizeBearing(b: number): number {
	const r = ((((b + 180) % 360) + 360) % 360) - 180;
	return r === -180 ? 180 : r;
}

/** `z/lat/lng/bearing/pitch`, rounded for a URL. */
export function formatView(v: CameraView): string {
	const d = latLngDigits(v.zoom);
	return [
		fixed(v.zoom, 2),
		fixed(v.center[1], d),
		fixed(v.center[0], d),
		fixed(normalizeBearing(v.bearing), 1),
		fixed(v.pitch, 1)
	].join('/');
}

const NUMBER = /^-?\d+(?:\.\d+)?$/;

/** Parse `z/lat/lng[/bearing[/pitch]]`; null when it isn't a sensible view. */
export function parseView(s: string): CameraView | null {
	const parts = s.split('/');
	if (parts.length < 3 || parts.length > 5 || !parts.every((p) => NUMBER.test(p))) return null;
	const [zoom, lat, lng, bearing = 0, pitch = 0] = parts.map(Number);
	if (zoom < 0 || zoom > 24 || Math.abs(lat) > 90 || Math.abs(lng) > 180 || pitch < 0 || pitch > 90) return null;
	return { center: [lng, lat], zoom, bearing, pitch };
}

export interface ParsedHash {
	view: CameraView | null;
	/** The `map=` value as written, for comparing with a saved view. */
	raw: string | null;
	/** An old MapLibre-style `#z/lat/lng/…` hash. */
	legacy: boolean;
	/** Every other `&`-separated piece, verbatim. */
	params: string[];
}

export function parseHash(hash: string): ParsedHash {
	const h = hash.replace(/^#/, '');
	if (!h) return { view: null, raw: null, legacy: false, params: [] };
	if (/^[-\d./]+$/.test(h)) {
		const view = parseView(h);
		if (view) return { view, raw: null, legacy: true, params: [] };
	}
	let view: CameraView | null = null;
	let raw: string | null = null;
	const params: string[] = [];
	for (const piece of h.split('&')) {
		if (!piece) continue;
		if (piece.startsWith('map=')) {
			raw = safeDecode(piece.slice(4));
			view = parseView(raw);
		} else params.push(piece);
	}
	return { view, raw: view ? raw : null, legacy: false, params };
}

function safeDecode(s: string): string {
	try {
		return decodeURIComponent(s);
	} catch {
		return s;
	}
}

/** `#map=…&other=pieces`, or '' when there's nothing to say. */
export function formatHash(view: CameraView | null, params: string[] = []): string {
	const pieces = [...(view ? [`map=${formatView(view)}`] : []), ...params];
	return pieces.length ? `#${pieces.join('&')}` : '';
}

/** The value of `key` among hash pieces, or null. */
export function getParam(params: string[], key: string): string | null {
	const p = params.find((x) => x === key || x.startsWith(`${key}=`));
	return p === undefined ? null : safeDecode(p.slice(key.length + 1));
}

/** Pieces with `key` set to `value` (or removed when null), order kept. */
export function setParam(params: string[], key: string, value: string | null): string[] {
	const enc = (s: string) => encodeURIComponent(s).replace(/%2F/gi, '/').replace(/%2C/gi, ',').replace(/%3A/gi, ':');
	const piece = value === null ? null : `${key}=${enc(value)}`;
	const i = params.findIndex((x) => x === key || x.startsWith(`${key}=`));
	if (i === -1) return piece ? [...params, piece] : params;
	return piece ? params.with(i, piece) : params.filter((_, j) => j !== i);
}

// --- the first view --------------------------------------------------------------

export type ViewSource = 'url' | 'saved' | 'default' | 'override';

export const SAVED_VIEW_KEY = 'view';

export function isCameraView(v: unknown): v is CameraView {
	const x = v as CameraView;
	return (
		!!x &&
		Array.isArray(x.center) &&
		x.center.length === 2 &&
		[x.center[0], x.center[1], x.zoom, x.bearing, x.pitch].every((n) => typeof n === 'number' && Number.isFinite(n))
	);
}

/** The manifest's view: the valley at its zoom, tilted when there's terrain. */
export function defaultView(m: Pick<BasemapManifest, 'center' | 'zoom' | 'terrain'>): CameraView {
	return { center: [m.center[0], m.center[1]], zoom: m.zoom, bearing: 0, pitch: m.terrain ? 45 : 0 };
}

/**
 * Which view the map opens at. An override (a deep link that knows where it
 * wants to be) wins; then the URL; then the saved view; then the default.
 * The URL's view is rounded, so when it matches the saved view rounded the
 * same way, the exact saved view is used: a reload comes back exactly.
 */
export function chooseInitialView(o: {
	hash: ParsedHash;
	saved?: CameraView;
	override?: CameraView;
	fallback: CameraView;
}): { view: CameraView; source: ViewSource } {
	if (o.override) return { view: o.override, source: 'override' };
	if (o.hash.view) {
		const exact = o.saved && !o.hash.legacy && o.hash.raw === formatView(o.saved);
		return { view: exact ? o.saved! : o.hash.view, source: 'url' };
	}
	if (o.saved) return { view: o.saved, source: 'saved' };
	return { view: o.fallback, source: 'default' };
}

// --- the manager -------------------------------------------------------------------

export interface ViewManagerOptions {
	/** Replace the current history entry's hash (SvelteKit's shallow goto in the app). */
	write: (hash: string) => void;
	/** Whether the hash may be written now (the explore page, no navigation running). */
	canWrite?: () => boolean;
	/** Read the current hash (location.hash in the app). */
	readHash?: () => string;
	debounceMs?: number;
}

export class ViewManager {
	/** The view as of the last `moveend` (not per frame). */
	camera = $state.raw<CameraView | null>(null);

	#map: MapLibre | null = null;
	#suspended = 0;
	#timer: ReturnType<typeof setTimeout> | undefined;
	#parts = new Map<string, SnapshotPart>();
	#params: string[] = [];
	#o: Required<ViewManagerOptions>;
	/** A view requested before the map existed (a deep link's own view). */
	#override: CameraView | undefined;
	#lastWritten = '';

	constructor(options: ViewManagerOptions) {
		this.#o = {
			canWrite: () => true,
			readHash: () => (typeof location === 'undefined' ? '' : location.hash),
			debounceMs: 500,
			...options
		};
	}

	get suspended(): boolean {
		return this.#suspended > 0;
	}

	get map(): MapLibre | null {
		return this.#map;
	}

	/** Ask for the map to open at this view (only before it exists; the first ask wins). */
	preferInitial(view: CameraView): void {
		if (!this.#map && !this.#override) this.#override = view;
	}

	/** The view the map should open at, and where it came from. Also takes the hash's other pieces. */
	initial(manifest: Pick<BasemapManifest, 'center' | 'zoom' | 'terrain'>): {
		view: CameraView;
		source: ViewSource;
		legacy: boolean;
	} {
		const hash = parseHash(this.#o.readHash());
		this.#params = hash.params;
		const saved = readStored(SAVED_VIEW_KEY, isCameraView);
		const chosen = chooseInitialView({ hash, saved, override: this.#override, fallback: defaultView(manifest) });
		return { ...chosen, legacy: hash.legacy };
	}

	attach(map: MapLibre): void {
		this.#map = map;
		this.camera = this.current();
		map.on('moveend', this.#onMoveEnd);
	}

	detach(): void {
		clearTimeout(this.#timer);
		this.#map?.off('moveend', this.#onMoveEnd);
		this.#map = null;
	}

	current(): CameraView | null {
		const m = this.#map;
		if (!m) return null;
		const c = m.getCenter();
		return { center: [c.lng, c.lat], zoom: m.getZoom(), bearing: m.getBearing(), pitch: m.getPitch() };
	}

	/** Stop writing the hash (a mode is active). Calls nest. */
	suspend(): void {
		this.#suspended++;
		clearTimeout(this.#timer);
	}

	resume(): void {
		this.#suspended = Math.max(0, this.#suspended - 1);
	}

	/** Add a part to every snapshot. Returns its removal. */
	register(name: string, part: SnapshotPart): () => void {
		this.#parts.set(name, part);
		return () => {
			if (this.#parts.get(name) === part) this.#parts.delete(name);
		};
	}

	snapshot(): ViewSnapshot {
		const m = this.#map;
		if (!m) throw new Error('no map to snapshot');
		const c = m.getCenter();
		const p = m.getPadding();
		const parts: Record<string, unknown> = {};
		for (const [name, part] of this.#parts) parts[name] = part.save();
		const terrain = m.getTerrain();
		return {
			center: [c.lng, c.lat],
			zoom: m.getZoom(),
			bearing: m.getBearing(),
			pitch: m.getPitch(),
			roll: m.getRoll(),
			fov: m.getVerticalFieldOfView(),
			padding: { top: p.top ?? 0, right: p.right ?? 0, bottom: p.bottom ?? 0, left: p.left ?? 0 },
			maxZoom: m.getMaxZoom(),
			maxPitch: m.getMaxPitch(),
			centerClampedToGround: m.getCenterClampedToGround(),
			exaggeration: terrain ? (terrain.exaggeration ?? 1) : null,
			parts
		};
	}

	/** Put a snapshot back exactly: limits, terrain, parts, then the camera with jumpTo. */
	restore(s: ViewSnapshot): void {
		const m = this.#map;
		if (!m) return;
		m.stop();
		if (m.getMaxZoom() !== s.maxZoom) m.setMaxZoom(s.maxZoom);
		if (m.getMaxPitch() !== s.maxPitch) m.setMaxPitch(s.maxPitch);
		if (m.getCenterClampedToGround() !== s.centerClampedToGround) m.setCenterClampedToGround(s.centerClampedToGround);
		if (Math.abs(m.getVerticalFieldOfView() - s.fov) > 1e-9) m.setVerticalFieldOfView(s.fov);
		const terrain = m.getTerrain();
		if (terrain && s.exaggeration !== null && (terrain.exaggeration ?? 1) !== s.exaggeration)
			m.setTerrain({ ...terrain, exaggeration: s.exaggeration });
		for (const [name, value] of Object.entries(s.parts)) this.#parts.get(name)?.restore(value);
		m.jumpTo({
			center: s.center,
			zoom: s.zoom,
			bearing: s.bearing,
			pitch: s.pitch,
			roll: s.roll,
			padding: s.padding
		});
		this.camera = this.current();
	}

	/** Move the map to a view (no animation). */
	jumpTo(v: CameraView): void {
		this.#map?.jumpTo({ center: v.center, zoom: v.zoom, bearing: v.bearing, pitch: v.pitch });
	}

	/** The hash pieces other than `map=`. */
	get params(): string[] {
		return this.#params;
	}

	/** Set (or with null, remove) one `&key=value` piece of the hash; written with the next view write. */
	setParam(key: string, value: string | null): void {
		this.#params = setParam(this.#params, key, value);
		this.#schedule();
	}

	getParam(key: string): string | null {
		return getParam(this.#params, key);
	}

	/** The hash for the map's current view. */
	hash(): string {
		return formatHash(this.current(), this.#params);
	}

	/** Write the hash and the saved view now, if allowed. Returns whether it wrote. */
	writeNow(): boolean {
		clearTimeout(this.#timer);
		const view = this.current();
		if (!view || this.suspended || !this.#o.canWrite()) return false;
		writeStored(SAVED_VIEW_KEY, view);
		const hash = formatHash(view, this.#params);
		if (hash === this.#o.readHash() || hash === this.#lastWritten) {
			this.#lastWritten = hash;
			return false;
		}
		this.#lastWritten = hash;
		this.#o.write(hash);
		return true;
	}

	/**
	 * The hash changed by itself (typed in the address bar, or a link to
	 * `#map=…`): go there. Our own writes are recognised and ignored.
	 */
	applyHash(hash = this.#o.readHash()): boolean {
		if (this.suspended || hash === this.#lastWritten) return false;
		const parsed = parseHash(hash);
		this.#params = parsed.params;
		if (!parsed.view) return false;
		const now = this.current();
		if (now && formatView(now) === formatView(parsed.view)) return false;
		this.jumpTo(parsed.view);
		return true;
	}

	/** Write the hash after the usual debounce (when a mode has just put a view back). */
	touch(): void {
		this.#schedule();
	}

	#schedule() {
		clearTimeout(this.#timer);
		if (this.suspended) return;
		this.#timer = setTimeout(() => this.writeNow(), this.#o.debounceMs);
	}

	#onMoveEnd = () => {
		this.camera = this.current();
		this.#schedule();
	};
}
