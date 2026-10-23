import type { Map as GlMap } from 'maplibre-gl';
import { untrack } from 'svelte';
import type { AppCtx } from '#lib/app/context.js';
import type { FlavorName } from '#lib/map/flavors.js';
import { BASE_CONTRIBUTIONS } from '#lib/base/registry.js';
import type { BaseState } from '#lib/base/types.js';
import { fillOwner, slotAllowed, slotFlags, type SlotGate } from '#lib/map/order.js';
import { BUILDINGS_LAYERS, flavorDiff, flavorKit } from '#lib/map/style.js';
import { ringSprite } from '#lib/overlay/sprites.js';
import {
	chooseLayers,
	DEFAULT_LAYERS,
	formatLayerList,
	LayerSet,
	sameSet,
	saveLayers,
	storedLayers
} from '#lib/state/layers.svelte.js';
import { readStored, writeStored } from '#lib/state/persisted.svelte.js';
import { getParam, parseHash } from '#lib/state/view.svelte.js';
import type { Chip, LayerDef, LayerId, LayerModule, LayerStatus, Selection } from './types.js';

/**
 * The layer manager (docs/14 §14.8, "Layer registry"; §14.3 "Layers and the
 * toolbar").
 *
 * - It owns the enabled set (with its memory in storage and the URL hash).
 * - A layer's module loads the first time it's switched on, or is prefetched
 *   (hidden) on the map's first `idle`, and then stays mounted: turning a
 *   layer off only hides it, so a second toggle makes no request.
 * - Toggle races: whatever finishes loading applies the set wanted *now*.
 * - While a mode (look-through, calibrate) owns the map, no data layer shows.
 * - Statuses for the toolbar and legends: idle, loading, ready, stale, error
 *   (with the reason, and Retry).
 * - It also holds the Base look (the Base popover): the basemap flavor
 *   (Valley or Clay, docs/14 §14.5; Auto means Clay whenever a data layer is
 *   on, except the layers that keep Valley: `LayerDef.keepsValley`, plan §3.6),
 *   buildings, terrain and labels.
 * - It applies the landscape contracts: the base contributions (`#lib/base`),
 *   the basemap groups a layer hides (`LayerDef.suppresses`), and the slot flags
 *   of the layers' area fills (aerial, one fill at a time, `offUnder`).
 */

export type Look = 'auto' | 'map' | 'clay';

export interface BaseSettings {
	look: Look;
	buildings: boolean;
	terrain: boolean;
	labels: 'full' | 'fewer';
}

const BASE_KEY = 'base';
const DEFAULT_BASE: BaseSettings = { look: 'auto', buildings: true, terrain: true, labels: 'full' };

const SELECTION_GROUP = 'selection';
const SELECTION_RING = 'selection-ring';

const isBase = (v: unknown): v is BaseSettings => {
	const b = v as BaseSettings;
	return !!b && ['auto', 'map', 'clay'].includes(b.look) && typeof b.buildings === 'boolean' && typeof b.terrain === 'boolean' && ['full', 'fewer'].includes(b.labels);
};

export class BaseLook {
	settings = $state<BaseSettings>({ ...DEFAULT_BASE });

	constructor() {
		const saved = readStored(BASE_KEY, isBase);
		if (saved) this.settings = { ...saved };
	}

	set<K extends keyof BaseSettings>(key: K, value: BaseSettings[K]): void {
		this.settings = { ...this.settings, [key]: value };
		writeStored(BASE_KEY, this.settings);
	}

	/**
	 * Whether the map wants the Clay flavor: Clay, or Auto while a data layer that doesn't keep Valley is on
	 * (`anyClayLayerOn`: Trees, Fences, Water and Lanes keep it; the first visit's Transit and Cameras don't).
	 */
	clay(anyClayLayerOn: boolean): boolean {
		const look = this.settings.look;
		return look === 'clay' || (look === 'auto' && anyClayLayerOn);
	}
}

export interface LayersInfo {
	enabled: LayerId[];
	shown: LayerId[];
	status: Record<string, LayerStatus>;
	errors: Record<string, string | null>;
	/** The Base look wants Clay (Clay, or Auto with a layer on that doesn't keep Valley). */
	clay: boolean;
	/** The flavor the map is drawn in now (a mode keeps the one it found). */
	flavor: FlavorName;
	selection: { kind: string; id: string; layer: string; title: string } | null;
	/** WP1's lens-era fields, kept for its specs: the layer acted on last, and whether Transit and Cameras loaded. */
	lens: LayerId | null;
	transit: boolean;
	cameras: boolean;
}

export class LayerManager {
	readonly defs: readonly LayerDef[];
	readonly set: LayerSet;
	readonly base = new BaseLook();
	/** Loaded modules (mounted, maybe hidden). */
	modules = $state.raw<Partial<Record<LayerId, LayerModule>>>({});
	#status = $state<Record<string, LayerStatus>>({});
	#errors = $state<Record<string, string | null>>({});
	#ctx: AppCtx;
	#loading = new Set<LayerId>();
	#unpick: Partial<Record<LayerId, () => void>> = {};
	#cleanup: (() => void)[] = [];
	#map: GlMap | null = null;
	#destroyed = false;
	#stopEffects: (() => void) | null = null;
	#shown = new Set<LayerId>();
	/** Slot-flagged layers this manager hid (so it can show them again). */
	#gated = new Set<string>();
	/** Base contributions whose `live` hook is running, with the hook's cleanup. */
	#live = new Map<string, () => void>();

	constructor(ctx: AppCtx, defs: readonly LayerDef[], hash = typeof location === 'undefined' ? '' : location.hash) {
		this.#ctx = ctx;
		this.defs = defs;
		const known = defs.map((d) => d.id);
		const url = getParam(parseHash(hash).params, 'layers');
		const { saved, legacyLens } = storedLayers();
		const chosen = chooseLayers({ url, saved, legacyLens, known });
		this.set = new LayerSet(chosen.ids);
		if (chosen.source === 'legacy') saveLayers(chosen.ids);
	}

	def(id: LayerId): LayerDef | undefined {
		return this.defs.find((d) => d.id === id);
	}

	/** true, or why the layer can't be used yet. */
	available(id: LayerId): true | string {
		return this.def(id)?.available(this.#ctx.meta) ?? 'Unknown layer';
	}

	status(id: LayerId): LayerStatus {
		if (this.#errors[id]) return 'error';
		const m = this.modules[id];
		// Once mounted, the module says (ready, stale, or error when its live feed fails).
		if (m && this.#status[id] === 'ready') return m.status;
		return this.#status[id] ?? 'idle';
	}

	error(id: LayerId): string | null {
		return this.#errors[id] ?? this.modules[id]?.error ?? null;
	}

	isOn(id: LayerId): boolean {
		return this.set.has(id);
	}

	/** The most recently turned-on layer that's still on (its legend is expanded). */
	get focus(): LayerId | null {
		return this.set.enabled.at(-1) ?? null;
	}

	/** Start: load the enabled layers now, prefetch the rest when the map is first idle, and keep visibility in step. */
	start(): void {
		const ctx = this.#ctx;
		for (const id of this.set.enabled) void this.#ensure(id);
		ctx.view.register('layers', {
			save: () => [...this.set.enabled],
			restore: (v) => {
				if (Array.isArray(v)) this.set.replace(v.filter((x): x is LayerId => this.defs.some((d) => d.id === x)));
			}
		});
		void ctx.styleReady
			.then((map) => {
				if (this.#destroyed) return;
				this.#map = map;
				this.#applyAll();
				// A lost WebGL context takes the style with it: leave the map alone until the restore's style has
				// loaded (ctx.styleReady resolves again), then put the base and the layers back as they are by then.
				const lost = () => {
					this.#map = null;
					void ctx.styleReady
						.then((m) => {
							if (this.#destroyed || this.#map) return;
							this.#map = m;
							this.#applyAll();
						})
						.catch(() => {});
				};
				map.on('webglcontextlost', lost);
				this.#cleanup.push(() => map.off('webglcontextlost', lost));
				const prefetch = () => {
					if (this.#destroyed) return;
					for (const d of this.defs) if (!this.set.has(d.id)) void this.#ensure(d.id);
				};
				map.once('idle', prefetch);
				this.#cleanup.push(() => map.off('idle', prefetch));
			})
			.catch(() => {});
		// The selection: each module hears of it, and a point gets the ink-and-cream ring (§14.3).
		ctx.overlay.sprite(ringSprite(SELECTION_RING, 36));
		ctx.overlay.set(SELECTION_GROUP, [], { z: 50 });
		this.#cleanup.push(
			ctx.selection.listen((s) => {
				for (const m of Object.values(this.modules)) m?.selected?.(s);
				ctx.overlay.set(SELECTION_GROUP, s?.at ? [{ id: 'selection', lng: s.at[0], lat: s.at[1], sprite: SELECTION_RING }] : []);
			}),
			() => ctx.overlay.remove(SELECTION_GROUP)
		);
		this.#stopEffects = $effect.root(() => {
			$effect(() => {
				const enabled = this.set.enabled;
				void ctx.modes.current;
				void ctx.aerial;
				void ctx.meta;
				void this.base.settings;
				void this.modules;
				untrack(() => {
					for (const id of enabled) void this.#ensure(id);
					this.#applyAll();
				});
			});
			$effect(() => {
				const enabled = this.set.enabled;
				untrack(() => this.#remember(enabled));
			});
		});
	}

	destroy(): void {
		this.#destroyed = true;
		this.#stopEffects?.();
		this.#stopDrape?.();
		for (const f of this.#cleanup.splice(0)) f();
		for (const f of this.#live.values()) f();
		this.#live.clear();
		for (const f of Object.values(this.#unpick)) f?.();
		for (const m of Object.values(this.modules)) m?.destroy();
		this.modules = {};
	}

	// --- the set ------------------------------------------------------------------

	toggle(id: LayerId): void {
		if (this.available(id) !== true) return;
		this.set.toggle(id);
	}

	setOn(id: LayerId, on: boolean): void {
		if (on && this.available(id) !== true) return;
		this.set.setOn(id, on);
	}

	solo(id: LayerId): void {
		if (this.available(id) !== true) return;
		this.set.solo(id);
	}

	allOff(): void {
		this.set.allOff();
	}

	/** Load the layer again after an error (or a failed chunk). */
	retry(id: LayerId): void {
		const m = this.modules[id];
		this.#unpick[id]?.();
		delete this.#unpick[id];
		if (m) {
			m.destroy();
			const { [id]: _gone, ...rest } = this.modules;
			void _gone;
			this.modules = rest;
		}
		this.#errors[id] = null;
		this.#status[id] = 'idle';
		void this.#ensure(id);
	}

	// --- what the chrome shows ------------------------------------------------------

	/** Stat chips for the top bar, in layer order: "—" while a layer that's on is still loading. */
	chips(): (Chip & { layer: LayerId })[] {
		const out: (Chip & { layer: LayerId })[] = [];
		for (const d of this.defs) {
			const m = this.modules[d.id];
			const chips = m?.chips?.();
			if (chips?.length) out.push(...chips.map((c) => ({ ...c, layer: d.id })));
			else if (this.set.has(d.id) && this.status(d.id) === 'loading')
				out.push({ id: d.id, layer: d.id, text: '—', title: `${d.title}: loading` });
		}
		return out;
	}

	info(): LayersInfo {
		const status: Record<string, LayerStatus> = {};
		const errors: Record<string, string | null> = {};
		for (const d of this.defs) {
			status[d.id] = this.status(d.id);
			errors[d.id] = this.error(d.id);
		}
		const sel = this.#ctx.selection.current;
		const ready = (id: LayerId) => ['ready', 'stale'].includes(this.status(id));
		return {
			enabled: [...this.set.enabled],
			shown: [...this.#shown],
			status,
			errors,
			clay: this.#wantsClay(),
			flavor: this.#map ? flavorKit().appliedFlavor(this.#map) : 'valley',
			selection: sel ? { kind: sel.kind, id: sel.id, layer: sel.layer, title: sel.title } : null,
			lens: this.set.last,
			transit: ready('transit'),
			cameras: ready('cameras')
		};
	}

	// --- loading and visibility -------------------------------------------------------

	async #ensure(id: LayerId): Promise<void> {
		if (this.#destroyed || this.modules[id] || this.#loading.has(id) || this.#errors[id]) return;
		const def = this.def(id);
		if (!def || def.available(this.#ctx.meta) !== true) return;
		this.#loading.add(id);
		this.#status[id] = 'loading';
		// Its data starts now, while its code loads.
		try {
			def.prefetch?.(this.#ctx);
		} catch {
			/* the module fetches for itself */
		}
		let mod: LayerModule;
		try {
			mod = await def.load();
		} catch (e) {
			this.#loading.delete(id);
			this.#status[id] = 'error';
			this.#errors[id] = `Reload to enable: ${def.title} failed to load (${e instanceof Error ? e.message : e}).`;
			return;
		}
		if (this.#destroyed) return mod.destroy();
		this.modules = { ...this.modules, [id]: mod };
		try {
			await mod.mount(this.#ctx);
		} catch (e) {
			this.#loading.delete(id);
			this.#status[id] = 'error';
			this.#errors[id] = mod.error ?? (e instanceof Error ? e.message : String(e));
			return;
		}
		this.#loading.delete(id);
		if (this.#destroyed) return;
		this.#unpick[id] = this.#ctx.picker.addLayers(id, mod.interactive);
		this.#status[id] = 'ready';
		mod.selected?.(this.#ctx.selection.current);
		this.#apply(id);
		this.#applyLandscape();
	}

	// Only Calibrate owns layer visibility (§14.3); look-through keeps the data layers drawn.
	#visible(id: LayerId): boolean {
		return this.#ctx.modes.current !== 'calibrate' && this.set.has(id);
	}

	#apply(id: LayerId) {
		const m = this.modules[id];
		// No map (no style yet, or the WebGL context is lost): applied when it's back.
		if (!m || this.#status[id] !== 'ready' || !this.#map) return;
		const on = this.#visible(id);
		if (on) this.#shown.add(id);
		else this.#shown.delete(id);
		m.setVisible(on);
		// Hiding the layer that owns the selection closes its card.
		const sel = this.#ctx.selection.current;
		if (!on && sel && sel.layer === id && this.#ctx.modes.current === 'explore') this.#ctx.selection.clear();
	}

	#applyAll() {
		for (const d of this.defs) this.#apply(d.id);
		this.#applyBase();
		this.#applyLandscape();
	}

	/**
	 * The landscape contracts, after the base pass: the base contributions (added, shown or hidden for this
	 * flavor, Aerial and layer set, their basemap groups hidden while they draw), the groups the layers on
	 * hide, and the slot flags of the layers' area fills.
	 */
	#applyLandscape() {
		const map = this.#map;
		const manifest = this.#ctx.manifest;
		if (!map || !manifest || this.#ctx.modes.current !== 'explore') return;
		const aerial = this.#ctx.aerial;
		const state: BaseState = { flavor: this.flavor, aerial, layers: new Set(this.set.enabled) };
		// (The flavors module loads with the basemap style, so it's here whenever a map is.)
		const kit = flavorKit();
		const ready = kit.syncContributions(map, manifest, location.origin, this.#ctx.meta, state);
		this.#startLive(ready);
		// Groups a layer hides while it's on (and shown: not under a mode that owns the map).
		for (const d of this.defs) {
			const owner = `layer:${d.id}`;
			if (d.suppresses?.length && this.#shown.has(d.id)) kit.suppressGroups(map, owner, d.suppresses);
			else kit.releaseGroups(map, owner);
		}
		this.#gateSlots(map, aerial);
	}

	/** Start the `live` hook of each base contribution that is built and on the map, once; stop the rest. */
	#startLive(ready: readonly string[]) {
		const map = this.#map;
		if (!map) return;
		for (const [id, stop] of this.#live) {
			if (ready.includes(id)) continue;
			stop();
			this.#live.delete(id);
		}
		for (const c of BASE_CONTRIBUTIONS) {
			if (!c.live || !ready.includes(c.id) || this.#live.has(c.id)) continue;
			this.#live.set(c.id, c.live({ map, app: this.#ctx, layerIds: c.layers.map((l) => l.id) }));
		}
	}

	/**
	 * Apply the slot flags (`SlottedLayer.aerial` and `areaFill`) to the layers modules added with them: a
	 * layer the flags don't allow is hidden; when they allow it again it is shown if its owner is shown.
	 * One area fill draws at a time: the owner turned on last that isn't off under a layer that's on.
	 */
	#gateSlots(map: GlMap, aerial: boolean) {
		const flags = slotFlags(map);
		if (!flags.size && !this.#gated.size) return;
		const owners = new Set<LayerId>();
		const fillsOff = new Set<LayerId>();
		for (const f of flags.values()) {
			if (!f.areaFill || !f.owner) continue;
			if (this.def(f.owner)?.offUnder?.some((u) => this.set.has(u) && this.#shown.has(u))) fillsOff.add(f.owner);
			else if (this.#shown.has(f.owner)) owners.add(f.owner);
		}
		const gate: SlotGate = { aerial, fillOwner: fillOwner(this.set.enabled, owners), fillsOff };
		for (const [id, f] of flags) {
			if (!map.getLayer(id)) continue;
			const ownerOn = f.owner ? this.#shown.has(f.owner) : true;
			if (!slotAllowed(f, gate)) {
				if (map.getLayoutProperty(id, 'visibility') !== 'none') {
					map.setLayoutProperty(id, 'visibility', 'none');
					this.#gated.add(id);
				}
			} else if (this.#gated.has(id) && ownerOn) {
				map.setLayoutProperty(id, 'visibility', 'visible');
				this.#gated.delete(id);
			}
		}
	}

	#remember(enabled: LayerId[]) {
		saveLayers(enabled);
		const value = sameSet(enabled, DEFAULT_LAYERS) ? null : formatLayerList(enabled);
		if (this.#ctx.view.getParam('layers') !== value) this.#ctx.view.setParam('layers', value);
	}

	// --- the base look ------------------------------------------------------------------

	/** The flavor the Base look wants (reactive): Clay, or Auto with a data layer on; otherwise Valley. */
	get flavor(): FlavorName {
		return this.#wantsClay() ? 'clay' : 'valley';
	}

	/** Auto's rule (plan §3.6): a layer is on whose def doesn't keep Valley. */
	#wantsClay(): boolean {
		return this.base.clay(this.set.enabled.some((id) => !this.def(id)?.keepsValley));
	}

	/** Whether a flavor was applied to this map yet (the first goes in instantly, before the first frame). */
	#flavored = false;
	/** Stops keeping the terrain drape fresh after a crossfade. */
	#stopDrape: (() => void) | null = null;

	#applyBase() {
		const map = this.#map;
		const manifest = this.#ctx.manifest;
		if (!map) return;
		const exploring = this.#ctx.modes.current === 'explore';
		const s = this.base.settings;
		const vis = (on: boolean) => (on ? 'visible' : 'none');
		const set = (id: string, on: boolean) => {
			if (map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== vis(on)) map.setLayoutProperty(id, 'visibility', vis(on));
		};
		// (The flavors module loads with the basemap style, so it's here whenever a map is.)
		const kit = flavorKit();
		// In a mode the base belongs to the mode (calibration turns Aerial on). It keeps the flavor it
		// found: switching would lay the basemap out again, which drops its cached tiles, and the way
		// back must find them (the persistent spec). It sees the photo in full color, though.
		kit.setTrueColorPhoto(map, !exploring);
		if (!exploring) return;
		// The flavor (§14.5): a 350 ms crossfade, instant under reduced motion and the first time.
		const flavor = this.flavor;
		if (manifest) {
			const duration = !this.#flavored || kit.prefersReducedMotion() ? 0 : kit.FLAVOR_FADE_MS;
			if (kit.applyFlavor(map, flavorDiff(manifest), flavor, { duration }) && duration) {
				// Frames for the whole crossfade, and a drape that follows it (terrain caches it otherwise).
				this.#ctx.loop.tween('flavor', duration + 100);
				this.#stopDrape?.();
				this.#stopDrape = kit.keepDrapeFresh(map, duration + 100);
			}
			this.#flavored = true;
		}
		// Clay's hidden labels, which "Labels: fewer" hides in either flavor.
		const hidden = kit.hiddenBaseLabels(flavor, s.labels);
		for (const id of kit.CLAY_HIDDEN) set(id, !hidden.has(id));
		for (const id of BUILDINGS_LAYERS) set(id, s.buildings);
		const m = this.#ctx.manifest;
		if (m?.terrain) {
			const t = map.getTerrain();
			if (s.terrain && !t) map.setTerrain({ source: 'terrain', exaggeration: m.terrain.exaggeration });
			else if (!s.terrain && t) map.setTerrain(null);
		}
	}

	/** Change a Base setting (the Base popover). */
	setBase<K extends keyof BaseSettings>(key: K, value: BaseSettings[K]): void {
		this.base.set(key, value);
	}
}
