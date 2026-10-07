import type { Component } from 'svelte';
import type { AppCtx } from '#lib/app/context.js';
import { toasts } from '#lib/ui/toasts.svelte.js';
import { readStored, writeStored } from './persisted.svelte.js';
import type { SnapshotPart } from './view.svelte.js';

/**
 * The window manager (docs/14 §14.3 "Regions" and "Stacking", §14.6 "Camera
 * windows"; WP3). Only camera windows float; this is the generic part, which
 * WP12 (camera windows) and WP16 (road-weather stations) fill.
 *
 * - **Limit:** at most 4 windows on a desktop (1024 px and wider), 2 on a
 *   tablet, and on a phone one bottom sheet with up to 3 window tabs.
 *   Opening another replaces the least recently focused unpinned window; if
 *   every window is pinned, a toast says so and nothing opens.
 * - **Numbers:** each open window has a number badge (1–4, the lowest free
 *   one), which WP12 also draws on its camera (`numberOf`).
 * - **Place:** inside the safe area, below the top bar and above the
 *   toolbar, never under either. A new window opens 24 px beside its anchor
 *   (the camera's screen position), on the side away from the screen centre
 *   and never covering it; otherwise it cascades from the top left of the
 *   free middle of the screen (between the legend and inspect columns when
 *   there's room for a window there).
 * - **Size:** 400 px wide by default, from 260 px to min(60vw, 960 px).
 *   Resizing is aspect-locked: it sets the width and the picture keeps its
 *   aspect, so the height follows; a window taller than the safe area
 *   narrows until it fits.
 * - **Snap:** moves and resizes snap to the safe area's edges and to other
 *   windows' edges within 8 px.
 * - **Memory** (`tvt:v2:windows`): position and size per key; pinned
 *   windows reopen on the next visit once their kind is registered
 *   (`registerKind`); only pinned ones do.
 * - **Modes:** the open windows are a part of every view snapshot
 *   (`part()`), so leaving a mode puts them back.
 *
 * Window contents are components; the frame (Window.svelte) draws the
 * header (number badge, title, status as shape and word, pin, dock and close
 * buttons) and handles dragging, resizing, focus and the dialog semantics.
 */

// --- geometry (pure) ---------------------------------------------------------------

export type Layout = 'desktop' | 'tablet' | 'phone';

/** Windows open at once: floating on desktops and tablets, sheet tabs on phones. */
export const LIMITS: Readonly<Record<Layout, number>> = { desktop: 4, tablet: 2, phone: 3 };

export function layoutFor(width: number): Layout {
	return width < 600 ? 'phone' : width < 1024 ? 'tablet' : 'desktop';
}

export const WIDTH = { default: 400, min: 260, max: 960 } as const;
export const SNAP_PX = 8;
/** Gap between a new window and its anchor (the camera on screen). */
export const BESIDE_PX = 24;
export const CASCADE_STEP = 28;
/** Side margin of the safe area. */
export const MARGIN = 16;
/** Top of the safe area without a measured top bar: 12 + 52 + 12 px. */
export const SAFE_TOP = 76;
/** Bottom margin of the safe area without a measured toolbar: 16 + 72 + 16 px. */
export const SAFE_BOTTOM = 104;
/** The legend column (16 + 280 + 16) and the right column (16 + 360 + 16), §14.3. */
export const LEFT_COLUMN = 312;
export const RIGHT_COLUMN = 392;
/** z-index band of floating windows (§14.3: 30–39; focus raises). */
export const Z_BASE = 30;
/** A window's header and footer before it has been measured. */
export const CHROME_ESTIMATE = 96;

export interface Rect {
	x: number;
	y: number;
	w: number;
	h: number;
}

export interface Box {
	left: number;
	top: number;
	right: number;
	bottom: number;
}

export interface Point {
	x: number;
	y: number;
}

/** Where the bars are: the safe area's top (px from the top) and bottom margin (px from the bottom). */
export interface Bars {
	top: number;
	bottom: number;
}

export function safeArea(vw: number, vh: number, bars: Bars = { top: SAFE_TOP, bottom: SAFE_BOTTOM }): Box {
	return {
		left: MARGIN,
		top: bars.top,
		right: Math.max(MARGIN + WIDTH.min, vw - MARGIN),
		bottom: Math.max(bars.top, vh - bars.bottom)
	};
}

/** Where new windows open: the middle between the legend and right columns, when a default window fits there. */
export function openingArea(safe: Box, vw: number): Box {
	const left = LEFT_COLUMN;
	const right = vw - RIGHT_COLUMN;
	return right - left >= WIDTH.default ? { ...safe, left, right } : safe;
}

/** The widest a window may be: min(60vw, 960 px), within the safe area, never under 260 px. */
export function maxWidth(vw: number, safe?: Box): number {
	const cap = Math.min(0.6 * vw, WIDTH.max, safe ? safe.right - safe.left : Infinity);
	return Math.max(WIDTH.min, Math.floor(cap));
}

export function clampWidth(w: number, vw: number, safe?: Box): number {
	return Math.round(Math.min(maxWidth(vw, safe), Math.max(WIDTH.min, w)));
}

/** A height estimate before the window is measured: the picture at its aspect plus the chrome. */
export function estimateHeight(w: number, aspect?: number): number {
	return Math.round(aspect ? w / aspect + CHROME_ESTIMATE : 240);
}

/** Keep a rect inside the safe area (a rect taller than the area keeps its top edge in). */
export function clampRect(r: Rect, safe: Box): Rect {
	const x = Math.min(Math.max(r.x, safe.left), Math.max(safe.left, safe.right - r.w));
	const y = Math.min(Math.max(r.y, safe.top), Math.max(safe.top, safe.bottom - r.h));
	return { ...r, x: Math.round(x), y: Math.round(y) };
}

const near = (a0: number, a1: number, b0: number, b1: number, px: number) => a0 < b1 + px && b0 < a1 + px;

function nearest(v: number, candidates: number[], px: number): number {
	let best = v;
	let d = px + 1e-9;
	for (const c of candidates) {
		const dd = Math.abs(c - v);
		if (dd < d) {
			d = dd;
			best = c;
		}
	}
	return best;
}

/**
 * Snap a moved rect to the safe area's edges and to the edges of other
 * windows beside it, within `px`; then keep it in the safe area.
 */
export function snapRect(r: Rect, safe: Box, others: Rect[], px = SNAP_PX): Rect {
	const xs = [safe.left, safe.right - r.w];
	const ys = [safe.top, safe.bottom - r.h];
	for (const o of others) {
		if (near(r.y, r.y + r.h, o.y, o.y + o.h, px)) xs.push(o.x, o.x + o.w, o.x - r.w, o.x + o.w - r.w);
		if (near(r.x, r.x + r.w, o.x, o.x + o.w, px)) ys.push(o.y, o.y + o.h, o.y - r.h, o.y + o.h - r.h);
	}
	return clampRect({ ...r, x: nearest(r.x, xs, px), y: nearest(r.y, ys, px) }, safe);
}

/** Snap a resized rect's right edge to the safe area's edge or another window's edge within `px`. */
export function snapWidth(r: Rect, safe: Box, others: Rect[], px = SNAP_PX): number {
	const edges = [safe.right];
	for (const o of others) if (near(r.y, r.y + r.h, o.y, o.y + o.h, px)) edges.push(o.x, o.x + o.w);
	return nearest(r.x + r.w, edges, px) - r.x;
}

const covers = (r: Rect, p: Point) => p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h;

/**
 * A rect 24 px beside `anchor`, on the side away from the screen centre
 * (else the other side), vertically centred on it and kept in the safe area,
 * never covering the anchor. Null when neither side has room.
 */
export function besideAnchor(anchor: Point, size: { w: number; h: number }, safe: Box, vw: number): Rect | null {
	const sides: ('left' | 'right')[] = anchor.x < vw / 2 ? ['left', 'right'] : ['right', 'left'];
	for (const side of sides) {
		const x = side === 'left' ? anchor.x - BESIDE_PX - size.w : anchor.x + BESIDE_PX;
		if (x < safe.left || x + size.w > safe.right) continue;
		const r = clampRect({ x, y: anchor.y - size.h / 2, ...size }, safe);
		if (!covers(r, anchor)) return r;
	}
	return null;
}

/** The first cascade slot (from the top left of `area`) that no open window starts at. */
export function cascadeRect(size: { w: number; h: number }, area: Box, safe: Box, open: Rect[]): Rect {
	for (let k = 0; k < 10; k++) {
		const r = clampRect({ x: area.left + k * CASCADE_STEP, y: area.top + k * CASCADE_STEP, ...size }, safe);
		if (!open.some((o) => Math.abs(o.x - r.x) < 4 && Math.abs(o.y - r.y) < 4)) return r;
	}
	return clampRect({ x: area.left, y: area.top, ...size }, safe);
}

/** Dock to the left or right edge of the safe area, below windows already docked there when there's room. */
export function dockRect(side: 'left' | 'right', r: Rect, safe: Box, others: Rect[]): Rect {
	const x = side === 'left' ? safe.left : safe.right - r.w;
	const docked = others.filter((o) => (side === 'left' ? o.x <= safe.left + 1 : o.x + o.w >= safe.right - 1)).sort((a, b) => a.y - b.y);
	let y = safe.top;
	for (const o of docked) if (y < o.y + o.h && o.y < y + r.h) y = o.y + o.h + SNAP_PX;
	if (y + r.h > safe.bottom) y = safe.top;
	return clampRect({ ...r, x, y }, safe);
}

/** The least recently focused unpinned window, or null when all are pinned. */
export function pickVictim(wins: readonly Pick<WinState, 'key' | 'pinned' | 'focusedAt'>[]): string | null {
	let best: Pick<WinState, 'key' | 'pinned' | 'focusedAt'> | null = null;
	for (const w of wins) if (!w.pinned && (!best || w.focusedAt < best.focusedAt)) best = w;
	return best?.key ?? null;
}

/** The lowest number from 1 not in use. */
export function lowestFree(used: readonly number[]): number {
	let n = 1;
	while (used.includes(n)) n++;
	return n;
}

/** The width at which a window measured `h` tall at width `w` fits `room` px, keeping the picture's aspect. */
export function fitWidth(w: number, h: number, aspect: number, room: number): number {
	return h <= room ? w : w - (h - room) * aspect;
}

// --- windows -----------------------------------------------------------------------

/** A status in the header: a shape and a word (● live, ▲ late, ■ offline, ◌ not calibrated); never color alone. */
export interface WindowStatus {
	shape: string;
	word: string;
	/** The shape's color (the word stays ink, §14.3). */
	color?: string;
	/** A longer explanation (tooltip). */
	detail?: string;
}

export interface WindowSpec {
	/** Stable identity ('camera:123'): reopening the same key focuses the open window; memory is per key. */
	key: string;
	title: string;
	/** The content. It gets `win` (this window's state) and `props`. */
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	component: Component<any>;
	props?: Record<string, unknown>;
	/** Width / height of the content's picture: resizing keeps it. */
	aspect?: number;
	/** Opening width (default 400). */
	width?: number;
	/** Screen point (viewport px) to open beside: the camera. */
	anchor?: Point;
	status?: WindowStatus | null;
	/** How to reopen it on the next visit when pinned: a registered kind and its data (JSON). */
	restore?: { kind: string; data: unknown };
	/** Called once when it closes (by the viewer, by replacement or by code). */
	onclose?: () => void;
}

export interface WinState {
	readonly key: string;
	readonly title: string;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	readonly component: Component<any>;
	readonly props: Record<string, unknown>;
	readonly aspect: number | null;
	readonly status: WindowStatus | null;
	readonly restore: { kind: string; data: unknown } | null;
	readonly onclose: (() => void) | null;
	/** The badge number, 1–4. */
	readonly number: number;
	/** Where it is, viewport px (h as last measured, or estimated). */
	readonly rect: Rect;
	readonly pinned: boolean;
	/** Focus order (higher is more recent). */
	readonly focusedAt: number;
	/** Its height has been measured at least once. */
	readonly measured: boolean;
	/** The element that had focus when it opened (focus goes back there on close). */
	readonly opener: HTMLElement | null;
	/** Move focus into it when it mounts (not for windows reopened by themselves). */
	readonly takeFocus: boolean;
}

export interface OpenOptions {
	/** Move keyboard focus into it (default true). */
	focus?: boolean;
	pinned?: boolean;
}

/** Recreates a window of a kind from its stored data (WP12 registers 'camera'). */
export type KindOpener = (data: unknown) => WindowSpec | null | Promise<WindowSpec | null>;

interface StoredRect {
	x: number;
	y: number;
	w: number;
	/** Last used, epoch ms (the oldest are forgotten first). */
	t: number;
}

interface StoredPin {
	key: string;
	kind: string;
	data: unknown;
}

interface StoredWindows {
	rects: Record<string, StoredRect>;
	pinned: StoredPin[];
}

export const STORE_KEY = 'windows';
/** Keys whose position is remembered. */
export const MEMORY_MAX = 40;

const isNum = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);

function isStored(v: unknown): v is StoredWindows {
	const s = v as StoredWindows;
	return (
		!!s &&
		typeof s.rects === 'object' &&
		s.rects !== null &&
		Object.values(s.rects).every((r) => r && isNum(r.x) && isNum(r.y) && isNum(r.w)) &&
		Array.isArray(s.pinned) &&
		s.pinned.every((p) => p && typeof p.key === 'string' && typeof p.kind === 'string')
	);
}

export interface ManagerOptions {
	/** Remember positions and pins in localStorage (default true). */
	persist?: boolean;
	/** How to say "all windows are pinned" (default: a toast). */
	toast?: (text: string) => void;
	viewport?: { w: number; h: number };
	/** The focused element (document.activeElement in the app). */
	activeElement?: () => Element | null;
	now?: () => number;
}

export class WindowManager {
	/** Open windows, in opening order ($state.raw: replaced, never mutated). */
	list = $state.raw<WinState[]>([]);
	layout = $state<Layout>('desktop');
	/** The safe area, as of the last viewport update. */
	safe = $state.raw<Box>(safeArea(1280, 800));

	#vw = 1280;
	#vh = 800;
	#bars: Bars = { top: SAFE_TOP, bottom: SAFE_BOTTOM };
	#seq = 0;
	#kinds = new Map<string, KindOpener>();
	#pending: StoredPin[];
	#memory: StoredWindows;
	#listeners = new Set<(list: readonly WinState[]) => void>();
	#o: Required<ManagerOptions>;

	constructor(o: ManagerOptions = {}) {
		this.#o = {
			persist: o.persist ?? true,
			toast: o.toast ?? ((text) => void toasts.show(text, { kind: 'info', key: 'windows' })),
			viewport: o.viewport ?? { w: 1280, h: 800 },
			activeElement: o.activeElement ?? (() => (typeof document === 'undefined' ? null : document.activeElement)),
			now: o.now ?? (() => Date.now())
		};
		this.#memory = (this.#o.persist ? readStored(STORE_KEY, isStored) : undefined) ?? { rects: {}, pinned: [] };
		this.#pending = [...this.#memory.pinned];
		this.setViewport(this.#o.viewport.w, this.#o.viewport.h);
	}

	/** Windows allowed at once on this screen. */
	get limit(): number {
		return LIMITS[this.layout];
	}

	get viewport(): { w: number; h: number } {
		return { w: this.#vw, h: this.#vh };
	}

	/** The screen changed size (or the bars moved): the limit, then every window's place. */
	setViewport(w: number, h: number, bars?: Bars): void {
		this.#vw = w;
		this.#vh = h;
		if (bars) this.#bars = bars;
		const safe = safeArea(w, h, this.#bars);
		if (!sameBox(safe, this.safe)) this.safe = safe;
		const layout = layoutFor(w);
		if (layout !== this.layout) this.layout = layout;
		this.#trim();
		this.#reclamp();
	}

	get(key: string): WinState | undefined {
		return this.list.find((w) => w.key === key);
	}

	isOpen(key: string): boolean {
		return this.list.some((w) => w.key === key);
	}

	/** A window's badge number, or null when it isn't open. */
	numberOf(key: string): number | null {
		return this.get(key)?.number ?? null;
	}

	/** Stacking order: 0 for the least recently focused. */
	rank(key: string): number {
		const w = this.get(key);
		return w ? this.list.filter((x) => x.focusedAt < w.focusedAt).length : 0;
	}

	/** The most recently focused window. */
	get top(): WinState | null {
		let best: WinState | null = null;
		for (const w of this.list) if (!best || w.focusedAt > best.focusedAt) best = w;
		return best;
	}

	/**
	 * Open a window (or focus it when its key is open, taking the new title,
	 * props and status). Returns null when the screen is full of pinned
	 * windows (a toast says so).
	 */
	open(spec: WindowSpec, o: OpenOptions = {}): WinState | null {
		const take = o.focus ?? true;
		if (this.isOpen(spec.key)) {
			this.update(spec.key, {
				title: spec.title,
				props: spec.props,
				status: spec.status,
				aspect: spec.aspect,
				restore: spec.restore,
				onclose: spec.onclose
			});
			this.focus(spec.key);
			if (take) this.#set(spec.key, { takeFocus: true });
			return this.get(spec.key)!;
		}
		if (this.list.length >= this.limit) {
			const victim = pickVictim(this.list);
			if (!victim) {
				const n = this.list.length;
				this.#o.toast(`All ${n === 1 ? 'windows are' : `${n} windows are`} pinned: unpin one to open another.`);
				return null;
			}
			this.close(victim, { returnFocus: false });
		}
		const safe = this.safe;
		const saved = this.#memory.rects[spec.key];
		const w = clampWidth(saved?.w ?? spec.width ?? WIDTH.default, this.#vw, safe);
		const size = { w, h: Math.min(estimateHeight(w, spec.aspect), safe.bottom - safe.top) };
		const others = this.list.map((x) => x.rect);
		const rect = saved
			? clampRect({ x: saved.x, y: saved.y, ...size }, safe)
			: ((spec.anchor && besideAnchor(spec.anchor, size, safe, this.#vw)) ?? cascadeRect(size, openingArea(safe, this.#vw), safe, others));
		const active = take ? this.#o.activeElement() : null;
		const win: WinState = {
			key: spec.key,
			title: spec.title,
			component: spec.component,
			props: spec.props ?? {},
			aspect: spec.aspect ?? null,
			status: spec.status ?? null,
			restore: spec.restore ?? null,
			onclose: spec.onclose ?? null,
			number: lowestFree(this.list.map((x) => x.number)),
			rect,
			pinned: o.pinned ?? false,
			focusedAt: ++this.#seq,
			measured: false,
			opener: isFocusable(active) ? active : null,
			takeFocus: take
		};
		this.list = [...this.list, win];
		if (win.pinned) this.#rememberPin(win);
		if (saved) this.#touchRect(spec.key);
		this.#emit();
		return win;
	}

	/**
	 * Close a window. Focus goes back to where it was when the window opened,
	 * if it was inside the window. `forget: false` keeps a pinned window's
	 * memory (it closed only because the screen got smaller).
	 */
	close(key: string, o: { returnFocus?: boolean; forget?: boolean } = {}): void {
		const w = this.get(key);
		if (!w) return;
		const hadFocus = this.#focusIn() === key;
		this.list = this.list.filter((x) => x.key !== key);
		if (w.pinned && (o.forget ?? true)) this.#forgetPin(key);
		this.#emit();
		try {
			w.onclose?.();
		} finally {
			if ((o.returnFocus ?? true) && hadFocus && w.opener?.isConnected) w.opener.focus({ preventScroll: true });
		}
	}

	/** Close every window (leaving the map). */
	closeAll(): void {
		for (const w of [...this.list]) this.close(w.key, { returnFocus: false, forget: false });
	}

	/** Raise a window to the top of the stack (focus raises, §14.3). */
	focus(key: string): void {
		const w = this.get(key);
		if (!w || (this.top === w && w.focusedAt === this.#seq)) return;
		this.#set(key, { focusedAt: ++this.#seq });
	}

	/** The window's frame took focus (or the viewer moved it there): clear the one-time focus request. */
	focused(key: string): void {
		if (this.get(key)?.takeFocus) this.#set(key, { takeFocus: false });
	}

	/** Change its title, content props, status or picture aspect. */
	update(key: string, patch: Partial<Pick<WindowSpec, 'title' | 'props' | 'status' | 'aspect' | 'restore' | 'onclose'>>): void {
		const w = this.get(key);
		if (!w) return;
		const next: Partial<WinState> = {};
		if (patch.title !== undefined) Object.assign(next, { title: patch.title });
		if (patch.props !== undefined) Object.assign(next, { props: patch.props });
		if (patch.status !== undefined) Object.assign(next, { status: patch.status });
		if (patch.aspect !== undefined) Object.assign(next, { aspect: patch.aspect ?? null });
		if (patch.restore !== undefined) Object.assign(next, { restore: patch.restore ?? null });
		if (patch.onclose !== undefined) Object.assign(next, { onclose: patch.onclose ?? null });
		this.#set(key, next);
		const after = this.get(key)!;
		if (after.pinned && patch.restore !== undefined) this.#rememberPin(after);
	}

	/** Where a window would land if moved to `pos`: snapped and kept in the safe area. */
	placeFor(key: string, pos: Point, snap = true): Rect {
		const w = this.get(key);
		const r = { ...(w?.rect ?? { w: WIDTH.default, h: 240 }), x: pos.x, y: pos.y };
		return snap ? snapRect(r, this.safe, this.#others(key)) : clampRect(r, this.safe);
	}

	/** Move a window (the viewer dragged it): snapped, kept in the safe area, and remembered. */
	move(key: string, pos: Point, o: { snap?: boolean; remember?: boolean } = {}): Rect | null {
		if (!this.isOpen(key)) return null;
		const rect = this.placeFor(key, pos, o.snap ?? true);
		this.#set(key, { rect });
		if (o.remember ?? true) this.#rememberRect(key, rect);
		return rect;
	}

	/** The width a resize to `w` would give: snapped to edges, within the limits. */
	widthFor(key: string, w: number, snap = true): number {
		const win = this.get(key);
		if (!win) return clampWidth(w, this.#vw, this.safe);
		const r = { ...win.rect, w };
		const snapped = snap ? snapWidth(r, this.safe, this.#others(key)) : w;
		return clampWidth(Math.min(snapped, this.safe.right - win.rect.x), this.#vw, this.safe);
	}

	/** Resize a window by its width (aspect-locked: the height follows the picture). */
	resize(key: string, width: number, o: { snap?: boolean; remember?: boolean } = {}): Rect | null {
		const win = this.get(key);
		if (!win) return null;
		const w = this.widthFor(key, width, o.snap ?? true);
		const h = win.aspect ? win.rect.h + (w - win.rect.w) / win.aspect : win.rect.h;
		const rect = clampRect({ ...win.rect, w, h: Math.round(h) }, this.safe);
		this.#set(key, { rect });
		if (o.remember ?? true) this.#rememberRect(key, rect);
		return rect;
	}

	/**
	 * The frame reports its rendered height. A window taller than the safe
	 * area narrows (keeping its picture's aspect) until it fits; every window
	 * stays inside the area.
	 */
	measured(key: string, height: number): void {
		const win = this.get(key);
		if (!win) return;
		if (win.measured && Math.abs(height - win.rect.h) < 0.5) return;
		const room = this.safe.bottom - this.safe.top;
		let rect: Rect = { ...win.rect, h: Math.round(height) };
		if (win.aspect && height > room + 1) {
			const w = clampWidth(fitWidth(rect.w, height, win.aspect, room), this.#vw, this.safe);
			if (w < rect.w) rect = { ...rect, w, h: Math.round(height - (rect.w - w) / win.aspect) };
		}
		this.#set(key, { rect: clampRect(rect, this.safe), measured: true });
	}

	/** Pin (or unpin): a pinned window is never replaced, and reopens on the next visit. */
	pin(key: string, on?: boolean): void {
		const w = this.get(key);
		if (!w) return;
		const pinned = on ?? !w.pinned;
		if (pinned === w.pinned) return;
		this.#set(key, { pinned });
		if (pinned) this.#rememberPin(this.get(key)!);
		else this.#forgetPin(key);
	}

	/** Dock to the left or right edge of the safe area (WCAG 2.5.7: placing without dragging). */
	dock(key: string, side: 'left' | 'right'): Rect | null {
		const w = this.get(key);
		if (!w) return null;
		const rect = dockRect(side, w.rect, this.safe, this.#others(key));
		this.#set(key, { rect });
		this.#rememberRect(key, rect);
		return rect;
	}

	/**
	 * Say how to reopen a kind of window: pinned windows of that kind from an
	 * earlier visit reopen now (without taking focus). Returns its removal.
	 */
	registerKind(kind: string, opener: KindOpener): () => void {
		this.#kinds.set(kind, opener);
		const due = this.#pending.filter((p) => p.kind === kind);
		this.#pending = this.#pending.filter((p) => p.kind !== kind);
		for (const p of due) {
			Promise.resolve()
				.then(() => opener(p.data))
				.then((spec) => {
					if (!spec || this.isOpen(spec.key) || this.#kinds.get(kind) !== opener) return;
					this.open({ ...spec, restore: spec.restore ?? { kind, data: p.data } }, { focus: false, pinned: true });
				})
				.catch((e) => console.error(`couldn't reopen the pinned window ${p.key}`, e));
		}
		return () => {
			if (this.#kinds.get(kind) === opener) this.#kinds.delete(kind);
		};
	}

	/** Pinned windows from an earlier visit still waiting for their kind. */
	get pending(): readonly { key: string; kind: string }[] {
		return this.#pending.map(({ key, kind }) => ({ key, kind }));
	}

	/** The remembered place of a key, if any. */
	remembered(key: string): { x: number; y: number; w: number } | null {
		const r = this.#memory.rects[key];
		return r ? { x: r.x, y: r.y, w: r.w } : null;
	}

	/** The view snapshot's part for the open windows (§14.3, "Modes and the view stack"). */
	part(): SnapshotPart {
		return {
			save: () => this.list,
			restore: (v) => this.#restoreList(v as readonly WinState[])
		};
	}

	/** Hear about every change to the open windows (for drawing badges on cameras). */
	listen(fn: (list: readonly WinState[]) => void): () => void {
		this.#listeners.add(fn);
		return () => this.#listeners.delete(fn);
	}

	// --- inside ------------------------------------------------------------------------

	#others(key: string): Rect[] {
		return this.list.filter((w) => w.key !== key).map((w) => w.rect);
	}

	#set(key: string, patch: Partial<WinState>): void {
		let changed = false;
		const next = this.list.map((w) => {
			if (w.key !== key) return w;
			changed = true;
			return { ...w, ...patch };
		});
		if (!changed) return;
		this.list = next;
		this.#emit();
	}

	#emit() {
		for (const fn of this.#listeners) fn(this.list);
	}

	/** The key of the window holding keyboard focus, if any. */
	#focusIn(): string | null {
		const el = this.#o.activeElement() as (Element & { closest?: (s: string) => Element | null }) | null;
		return el?.closest?.('[data-window-key]')?.getAttribute('data-window-key') ?? null;
	}

	/** Too many windows for this screen: the least recently focused close (unpinned first). */
	#trim() {
		const over = this.list.length - this.limit;
		if (over <= 0) return;
		const order = [...this.list].sort((a, b) => Number(a.pinned) - Number(b.pinned) || a.focusedAt - b.focusedAt);
		for (const w of order.slice(0, over)) this.close(w.key, { returnFocus: false, forget: false });
		this.#o.toast(`Closed ${over === 1 ? 'a window' : `${over} windows`}: this screen holds ${this.limit}.`);
	}

	#reclamp() {
		const safe = this.safe;
		let changed = false;
		const next = this.list.map((w) => {
			const rect = clampRect({ ...w.rect, w: clampWidth(w.rect.w, this.#vw, safe) }, safe);
			if (sameRect(rect, w.rect)) return w;
			changed = true;
			return { ...w, rect };
		});
		if (changed) {
			this.list = next;
			this.#emit();
		}
	}

	#restoreList(saved: readonly WinState[]) {
		if (!Array.isArray(saved)) return;
		const keep = new Set(saved.map((w) => w.key));
		for (const w of [...this.list]) if (!keep.has(w.key)) this.close(w.key, { returnFocus: false, forget: false });
		const open = new Map(this.list.map((w) => [w.key, w]));
		this.list = saved.map((w) => open.get(w.key) ?? { ...w, takeFocus: false, rect: clampRect(w.rect, this.safe) });
		this.#seq = Math.max(this.#seq, ...this.list.map((w) => w.focusedAt));
		this.#emit();
	}

	#save() {
		if (this.#o.persist) writeStored(STORE_KEY, this.#memory);
	}

	#rememberRect(key: string, r: Rect) {
		const rects = { ...this.#memory.rects, [key]: { x: r.x, y: r.y, w: r.w, t: this.#o.now() } };
		const keys = Object.keys(rects);
		if (keys.length > MEMORY_MAX) {
			for (const k of keys.sort((a, b) => rects[a].t - rects[b].t).slice(0, keys.length - MEMORY_MAX)) delete rects[k];
		}
		this.#memory = { ...this.#memory, rects };
		this.#save();
	}

	#touchRect(key: string) {
		const r = this.#memory.rects[key];
		if (r) this.#rememberRect(key, { x: r.x, y: r.y, w: r.w, h: 0 });
	}

	#rememberPin(w: WinState) {
		if (!w.restore) return;
		const pin: StoredPin = { key: w.key, kind: w.restore.kind, data: w.restore.data };
		this.#memory = { ...this.#memory, pinned: [...this.#memory.pinned.filter((p) => p.key !== w.key), pin] };
		this.#save();
	}

	#forgetPin(key: string) {
		if (!this.#memory.pinned.some((p) => p.key === key)) return;
		this.#memory = { ...this.#memory, pinned: this.#memory.pinned.filter((p) => p.key !== key) };
		this.#save();
	}
}

const sameBox = (a: Box, b: Box) => a.left === b.left && a.top === b.top && a.right === b.right && a.bottom === b.bottom;
const sameRect = (a: Rect, b: Rect) => a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;

function isFocusable(el: Element | null): el is HTMLElement {
	return !!el && typeof (el as HTMLElement).focus === 'function' && el !== (typeof document === 'undefined' ? null : document.body);
}

// --- the app's window manager ---------------------------------------------------------

declare module '#lib/app/context.js' {
	interface AppCtx {
		/** The window manager (WP3). The chrome installs it; code that can run earlier uses `windowsOf(app)`. */
		readonly windows: WindowManager;
	}
}

declare module '#lib/app/app.svelte.js' {
	interface App {
		readonly windows: WindowManager;
	}
}

const managers = new WeakMap<object, WindowManager>();

/** The app's window manager, created the first time it's asked for (and then `app.windows`). */
export function windowsOf(app: AppCtx): WindowManager {
	let m = managers.get(app);
	if (!m) {
		m = new WindowManager({ viewport: typeof innerWidth === 'number' ? { w: innerWidth, h: innerHeight } : undefined });
		managers.set(app, m);
		Object.defineProperty(app, 'windows', { value: m, configurable: true, enumerable: false });
	}
	return m;
}
