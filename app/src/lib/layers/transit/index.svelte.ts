import type { GeoJSONSource, Map, MapGeoJSONFeature, MissingStyleImageResolver } from 'maplibre-gl';
import type { Feature, MultiLineString, Point } from 'geojson';
import { untrack } from 'svelte';
import { MapScope } from '#lib/app/cleanup.js';
import type { AppCtx } from '#lib/app/context.js';
import type { NetworkRoute, TransitNetwork } from '#lib/contracts/network.js';
import type { TrackVehicle, Tracks } from '#lib/contracts/tracks.js';
import { addSlotted } from '#lib/map/order.js';
import { discSprite, ringSprite, type OverlayInstance, type SpriteDef } from '#lib/overlay/index.js';
import { clockOf, timeText, type Clock } from '#lib/state/clock.svelte.js';
import { Persisted } from '#lib/state/persisted.svelte.js';
import { Poller } from '#lib/state/poll.svelte.js';
import { take } from '../prefetch.js';
import { PRIORITY, type Badge, type Chip, type Interactive, type LayerModule, type LayerStatus, type Selection } from '../types.js';
import Card from './Card.svelte';
import def from './def.js';
import { followFor, type FollowLike } from './follow.svelte.js';
import { capsuleImage, pillImage, shieldImage } from './images.js';
import Legend from './Legend.svelte';
import {
	hubFeatures,
	idleStops,
	IMG,
	L,
	networkLayers,
	NETWORK_LAYERS,
	parseShield,
	ribbonFeatures,
	shieldFeatures,
	SOURCES,
	SPOT_STATE,
	stopFeatures
} from './network.js';
import { busAt, Feed, positionAt, runningAt, sameSet, smoothAngle, trail, type BusAt, type BusState } from './playback.js';
import { ageText, ARROW, arrowImage, CREAM, CREDIT, fallbackBusLayers, FALLBACK_LAYERS, INK, UNKNOWN_COLOR } from './transit.js';
import type { Scene, SceneInstance } from '#lib/scene/index.js';
import { bodyColor, busModel, BUS_LENGTH_M, lodAt, metresPerPx, modelFade, modelZoom, placeModel, plateAltitude, type BusModel, type GroundAt, type Lod } from './bus3d.js';
import { loadPlateFont, PLATE_BODY_H, PLATE_PAD, plateBodyWidth, plateKey, plateOffset, plateSize, plateSprite, type PlateLook } from './plates.js';
import { StopPosts, STOP_NAMES, stopNameLayer } from './stops3d.js';

/**
 * The Transit layer (docs/14 §14.4; WP8): side-by-side route ribbons from
 * /api/transit/network, and buses played back from /api/transit/tracks at
 * the clock's playhead, a little behind live.
 *
 * - **The network** is fetched once per ribbon build (`?v=`). Running,
 *   spotlight and hover are feature-state on the routes; a change in which
 *   routes run never touches the ribbon source.
 * - **The feed** polls every 10 s while shown and the tab is visible: a
 *   window of D + 6 min the first time (or after a pause in polling), then
 *   just the newest steps, merged by (bus, t0).
 * - **Buses** are discs with their route numbers in WP2's overlay, moved
 *   once per rendered frame by `overlay.update` (no `setData`), and asking
 *   the render loop for frames only while one moves on screen. If the
 *   overlay can't start, a MapLibre symbol layer draws them instead,
 *   refreshed twice a second, and the Transit button shows ▲.
 * - **Once a second** (the clock's tick): which routes run, the bus states
 *   the legend, chips and cards show, and the trails when they're on (the
 *   one line source that changes more than once per poll, at most once a
 *   second).
 * - Space (pause / play) and L (back to live) are registered while the
 *   layer is loaded.
 * - **3D buses and stops** (WP10, §14.4 "Buses and stops"): from about
 *   z15 a bus is a model in the 3D scene (lazy: asked for once the map is
 *   zoomed in near there), crossfading with its disc over 0.3 zoom, with its
 *   number plate above it in the overlay; from z16 a stop is a sign post
 *   with a flag per route. Positions are worked out once per rendered frame
 *   for both layers. If the scene can't start, buses stay discs and stops
 *   capsules at every zoom.
 */

const BUS_GROUP = 'transit-buses';
const HEADING_GROUP = 'transit-heading';
const RING_GROUP = 'transit-selected';
const PLATE_GROUP = 'transit-plates';
const HEADING = 'transit-heading';
const RING = 'transit-ring';
/** The scene's groups for bus models and stop posts. */
export const BUS3D_GROUP = 'transit-buses-3d';
export const STOPS3D_GROUP = 'transit-stops-3d';
/** Ask for the 3D scene once the map is zoomed in this far (models start about half a zoom later). */
const SCENE_FROM_ZOOM = 14.5;
/** Refresh which stop posts the scene gets at most this often while the map moves (ms). */
const NEAR_MS = 400;
/** Spotlight: other routes' discs and plates at this opacity. */
const DIM = 0.3;
/** Polls every 10 s while visible (§14.4 "Playback"). */
export const POLL_MS = 10_000;
/** The first poll's window beyond the delay (s), and the cap (s). */
const FIRST_EXTRA_S = 360;
const MAX_WINDOW_S = 900;
/** A later poll asks for this much (s) at least. */
const NEXT_WINDOW_S = 120;
/** Longer than this since the last poll (s): reload the whole window and replace. */
const RELOAD_AFTER_S = 30;
/** The feed is old (▲) once its newest fix is this old (s). */
const STALE_FEED_S = 120;
/** Trails redraw at most this often (ms; the clock ticks once a second, a little jitter allowed). */
const TRAILS_MS = 990;
/** The fallback layer's refresh (ms): at most twice a second. */
const FALLBACK_MS = 500;
const isBool = (v: unknown): v is boolean => typeof v === 'boolean';

/** The heading arrow as an overlay sprite: drawn at the top of a square centred on the bus, so turning it puts the arrow ahead. */
function headingSprite(): SpriteDef {
	const s = 44;
	return {
		key: HEADING,
		width: s,
		height: s,
		draw(g) {
			const c = s / 2;
			g.beginPath();
			g.moveTo(c, 1.5);
			g.lineTo(c + 6, 11);
			g.lineTo(c, 8.5);
			g.lineTo(c - 6, 11);
			g.closePath();
			g.lineJoin = 'round';
			g.lineWidth = 2.5;
			g.strokeStyle = CREAM;
			g.stroke();
			g.fillStyle = INK;
			g.fill();
		}
	};
}

/** "toward Towne Square Mall" (some headsigns already say "Toward"). */
export const towardText = (headsign: string) => (/^toward\b/i.test(headsign) ? headsign.replace(/^toward/i, 'toward') : `toward ${headsign}`);

/** A bus's plate (unknown routes: gray with "?", with a halo). */
export function busBadge(v: TrackVehicle | undefined): Badge {
	if (!v || !v.routeId) return { text: '?', color: v?.color ?? UNKNOWN_COLOR, textColor: v?.textColor ?? INK, halo: v?.halo ?? true };
	return { text: v.shortName ?? v.routeId, color: v.color ?? UNKNOWN_COLOR, textColor: v.textColor ?? INK, halo: v.halo };
}

export function routeBadge(r: NetworkRoute): Badge {
	return { text: r.shortName, color: r.color, textColor: r.textColor, halo: r.halo };
}

const discKey = (b: Badge, hollow: boolean) => `bus:${b.color}:${b.textColor}:${b.text}:${b.halo ? 1 : 0}:${hollow ? 'h' : 's'}`;

/** What the legend, chips and cards know about a bus, once a second. */
export interface BusSummary {
	vid: string;
	routeId: string | null;
	state: BusState;
	/** The newest fix at or before the playhead (epoch s). */
	fix: number;
	kind: BusAt['kind'];
	stepSpeed: number | null;
}

/** A bus that counts as on the map now: drawn and not stale. */
export const isShown = (s: BusState) => s !== 'hidden' && s !== 'stale';

interface BusRuntime {
	bus: OverlayInstance;
	head: OverlayInstance;
	/** Smoothed heading (degrees) and when it was last turned (ms). */
	heading: number | null;
	turnedAt: number;
	pos: [number, number];
	solid: string;
	hollow: string;
	routeId: string | null;
	// This frame's playback (worked out once per rendered frame, for the overlay and the scene).
	state: BusState;
	kind: BusAt['kind'];
	/** The playback's own opacity (a gap's fade-jump), 0 when hidden. */
	shown: number;
	/** The path heading this frame (unsmoothed), or null. */
	raw: number | null;
	speed: number;
	// WP10: the plate over the model, and the model.
	plate: OverlayInstance;
	plates: Record<`${PlateLook}${'' | ':sel'}`, string>;
	model: BusModel;
	color: string | null;
	ghost: string | null;
}

export class TransitModule implements LayerModule {
	status = $state<LayerStatus>('loading');
	error = $state<string | null>(null);
	updatedAt = $state<number | null>(null);
	network = $state.raw<TransitNetwork | null>(null);
	/** The buses as of the last poll. */
	vehicles = $state.raw<Record<string, TrackVehicle>>({});
	/** Routes running at the playhead (checked once a second). */
	running = $state.raw<ReadonlySet<string>>(new Set());
	/** Each known bus at the playhead (once a second). */
	buses = $state.raw<Record<string, BusSummary>>({});
	/** Newest fix of any bus, any age (epoch s). */
	lastFix = $state<number | null>(null);
	/** The spotlit route: every other one takes its ghost color. */
	spot = $state<string | null>(null);
	pollError = $state<string | null>(null);
	/** The follow API (WP3's, or the stand-in), once loaded. */
	follow = $state.raw<FollowLike | null>(null);
	/** Trails on or off (per viewer). */
	readonly trails = new Persisted<boolean>('transit-trails', false, isBool);
	clock: Clock | null = null;
	Legend = Legend;
	Card = Card;
	readonly poller = new Poller((signal) => this.#poll(signal), { interval: POLL_MS });
	readonly feed = new Feed();
	interactive: Interactive[] = [
		{
			layerIds: [L.routes],
			priority: PRIORITY.route,
			pick: (f: MapGeoJSONFeature) => {
				const r = this.route(String(f.properties?.routeId));
				return r ? this.routeSelection(r) : null;
			}
		},
		{
			layerIds: [L.hubs],
			priority: PRIORITY.hub,
			pick: (f: MapGeoJSONFeature) => {
				const h = this.network?.hubs[Number(f.properties?.hid) - 1];
				if (!h) return null;
				return {
					kind: 'hub',
					id: h.id,
					layer: 'transit',
					title: h.name,
					fact: `${h.routes.length} route${h.routes.length === 1 ? '' : 's'} meet here`,
					source: CREDIT,
					at: [h.lon, h.lat],
					data: h
				};
			}
		},
		{
			layerIds: [L.stops],
			priority: PRIORITY.stop,
			pick: (f: MapGeoJSONFeature) => this.stopSelection(Number(f.properties?.sid) - 1)
		},
		{
			// The fallback bus layer, only when the overlay can't start.
			layerIds: [FALLBACK_LAYERS[1]],
			priority: PRIORITY.bus,
			pick: (f: MapGeoJSONFeature) => this.busSelection(String(f.properties?.vehicleId))
		}
	];

	#ctx: AppCtx | null = null;
	#scope: MapScope | null = null;
	#visible = false;
	#destroyed = false;
	#useOverlay = false;
	#runtime = new globalThis.Map<string, BusRuntime>();
	#busList: OverlayInstance[] = [];
	#headList: OverlayInstance[] = [];
	#ring: OverlayInstance[] = [];
	#selectedBus: string | null = null;
	#lastPoll: number | null = null;
	#idle = true;
	#hovered: number[] = [];
	#trailsAt = -Infinity;
	/** The running set last shown on the map (null: none yet). */
	#shownRunning: ReadonlySet<string> | null = null;
	#stopTick: (() => void) | null = null;
	#releaseKeys: (() => void) | null = null;
	#fallbackTimer: ReturnType<typeof setInterval> | undefined;
	#at: BusAt = busAt();
	#byId = new globalThis.Map<string, NetworkRoute>();
	#byRid = new globalThis.Map<number, NetworkRoute>();
	// WP10: plates, models and posts.
	#plateList: OverlayInstance[] = [];
	/** The scene: asked for once zoomed in near z15 (none: not yet; failed: buses stay discs). */
	#scene: Scene | null = null;
	#sceneState: 'none' | 'loading' | 'ready' | 'failed' = 'none';
	#modelList: SceneInstance[] = [];
	#posts = new StopPosts();
	#postsOn = false;
	#modelsOn = false;
	#nearAt = -Infinity;
	/** Positions were worked out for the frame being drawn (reset on each `render`). */
	#advanced = false;
	#lod: Lod = lodAt(10, 43.6, 0, false);
	/** Fastest on-screen bus this frame (m/s). */
	#fastest = 0;
	/** Bumped when terrain data or settings change: the models' slopes are read again. */
	#terrainEpoch = 0;
	#ground: GroundAt | null = null;

	route(id: string | null | undefined): NetworkRoute | undefined {
		return id ? this.#byId.get(id) : undefined;
	}

	/** What a click on stop `i` (network order) selects: the capsule's and the post's alike. */
	stopSelection(i: number): Selection | null {
		const s = this.network?.stops[i];
		if (!s) return null;
		return {
			kind: 'stop',
			id: s.id,
			layer: 'transit',
			title: s.name ?? 'Stop',
			fact: `${s.routes.length} route${s.routes.length === 1 ? '' : 's'} stop here`,
			source: CREDIT,
			at: [s.lon, s.lat],
			data: s
		};
	}

	/** Buses per route at the playhead (shown, not stale; '?' for buses with no route). */
	busesByRoute(): Record<string, number> {
		const out: Record<string, number> = {};
		for (const b of Object.values(this.buses)) {
			if (!isShown(b.state)) continue;
			const k = b.routeId ?? '?';
			out[k] = (out[k] ?? 0) + 1;
		}
		return out;
	}

	routeSelection(r: NetworkRoute): Selection {
		const on = this.running.has(r.id);
		const n = this.busesByRoute()[r.id] ?? 0;
		return {
			kind: 'route',
			id: r.id,
			layer: 'transit',
			title: r.longName ? `${r.shortName} ${r.longName}` : `Route ${r.shortName}`,
			fact: on ? `Running now · ${n} bus${n === 1 ? '' : 'es'}` : 'Not running now',
			source: CREDIT,
			badge: routeBadge(r)
		};
	}

	busSelection(vid: string): Selection | null {
		const v = this.feed.vehicles[vid];
		const r = this.route(v?.routeId);
		const name = r?.longName ?? (v?.routeId ? `Route ${v.shortName ?? v.routeId}` : 'Route not reported');
		return {
			kind: 'bus',
			id: vid,
			layer: 'transit',
			title: `${name} · bus ${v?.label ?? vid}`,
			fact: v?.headsign ? towardText(v.headsign) : 'between reported positions',
			source: CREDIT,
			badge: busBadge(v),
			data: vid
		};
	}

	async mount(ctx: AppCtx): Promise<void> {
		this.#ctx = ctx;
		const clock = (this.clock = clockOf(ctx));
		this.#releaseKeys = clock.holdKeys();
		let net: TransitNetwork;
		try {
			const res = await take(await ctx.dataUrl('/api/transit/network', 'ribbons'));
			if (!res.ok) {
				const msg = (await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`;
				throw new Error(msg);
			}
			net = await res.json();
		} catch (e) {
			this.status = 'error';
			this.error = `Transit unavailable: ${e instanceof Error ? e.message : e}`;
			throw new Error(this.error);
		}
		const map = await ctx.styleReady;
		if (this.#destroyed) return;
		this.network = net;
		for (const r of net.routes) {
			this.#byId.set(r.id, r);
			this.#byRid.set(r.rid, r);
		}
		const scope = (this.#scope = new MapScope(map));
		scope.addSource(SOURCES.ribbons, { type: 'geojson', data: ribbonFeatures(net), promoteId: 'rid', attribution: CREDIT });
		scope.addSource(SOURCES.shields, { type: 'geojson', data: shieldFeatures(net, this.running) });
		scope.addSource(SOURCES.stops, { type: 'geojson', data: stopFeatures(net), promoteId: 'sid' });
		scope.addSource(SOURCES.hubs, { type: 'geojson', data: hubFeatures(net) });
		scope.addSource(SOURCES.trails, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
		const pill = pillImage();
		scope.addImage(IMG.pill, pill.data, pill.options);
		// Shields and capsules are drawn the first time a layer needs one. MapLibre has one resolver per
		// map: chain to whoever set one before, and put it back on cleanup.
		const before = (map as unknown as { _missingStyleImageResolver?: MissingStyleImageResolver | null })._missingStyleImageResolver ?? null;
		map.setMissingStyleImageResolver((id) => (this.#drawImage(map, id) ? undefined : before?.(id)));
		scope.defer(() => map.setMissingStyleImageResolver(before));
		addSlotted(map, [...networkLayers(), stopNameLayer(SOURCES.stops)], def.order, (l, before) => scope.addLayer(l, before));
		this.#useOverlay = ctx.overlay.ok;
		if (this.#useOverlay) {
			const o = ctx.overlay;
			o.sprite(headingSprite());
			o.sprite(ringSprite(RING, 44));
			o.set(HEADING_GROUP, [], { z: 9 });
			o.set(BUS_GROUP, [], { z: 10, priority: PRIORITY.bus });
			o.set(RING_GROUP, [], { z: 11 });
			o.set(PLATE_GROUP, [], { z: 12, priority: PRIORITY.bus });
			scope.defer(() => {
				for (const g of [HEADING_GROUP, BUS_GROUP, RING_GROUP, PLATE_GROUP]) o.remove(g);
			});
			loadPlateFont();
			// WP10: positions are worked out once per frame for the scene and the overlay; zooming decides
			// what's drawn; terrain changes make the models read their slopes again.
			scope.on('render', () => void (this.#advanced = false));
			scope.on('resize', () => this.#measure());
			scope.on('zoom', () => this.#onZoom());
			scope.on('move', () => this.#onMove(false));
			scope.on('moveend', () => this.#onMove(true));
			scope.on('terrain', () => this.#bumpTerrain());
			scope.on('sourcedata', (e: { sourceId?: string }) => {
				if (e.sourceId && e.sourceId === map.getTerrain()?.source) this.#bumpTerrain();
			});
			this.#bumpTerrain();
			scope.defer(() => this.#dropScene());
		} else {
			scope.addSource(SOURCES.buses, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
			scope.addImage(ARROW, arrowImage(), { pixelRatio: 2 });
			addSlotted(map, fallbackBusLayers(), def.order, (l, before) => scope.addLayer(l, before));
			this.error = `Buses are drawn by a fallback layer: ${ctx.overlay.error ?? 'the overlay couldn’t start'}.`;
		}
		// Hover widens a route 2 px.
		scope.defer(ctx.picker.onHover((h) => this.#hover(h?.selection ?? null)));
		void followFor(ctx).then((f) => {
			if (!this.#destroyed) this.follow = f;
		});
		this.#stopTick = $effect.root(() => {
			$effect(() => {
				void clock.tick;
				untrack(() => this.#second());
			});
		});
		// Back from a hidden tab: catch up at once (the poller reloads the window by itself).
		const onVisibility = () => {
			if (hidden()) return;
			this.#second();
			this.#kick();
		};
		document.addEventListener('visibilitychange', onVisibility);
		scope.defer(() => document.removeEventListener('visibilitychange', onVisibility));
		this.#installDebug();
		this.status = this.#useOverlay ? 'ready' : 'stale';
		this.updatedAt = Date.now();
		this.setVisible(this.#visible);
	}

	setVisible(on: boolean): void {
		this.#visible = on;
		const map = this.#scope?.map;
		if (!map) return;
		const vis = (v: boolean) => (v ? 'visible' : 'none');
		for (const id of NETWORK_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis(on && (id !== L.trails || this.trails.value)));
		if (map.getLayer(STOP_NAMES)) map.setLayoutProperty(STOP_NAMES, 'visibility', vis(on));
		if (!this.#useOverlay) for (const id of FALLBACK_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis(on));
		if (on) {
			this.poller.start();
			this.#build();
			this.#second();
			if (this.#useOverlay) {
				this.#onZoom();
				this.#onMove(true);
				this.#kick();
			} else this.#startFallback();
		} else {
			this.poller.stop();
			clearInterval(this.#fallbackTimer);
			this.#fallbackTimer = undefined;
			if (this.#useOverlay) {
				const o = this.#ctx!.overlay;
				o.update(BUS_GROUP, null);
				o.set(BUS_GROUP, []);
				o.set(HEADING_GROUP, []);
				o.set(RING_GROUP, []);
				o.set(PLATE_GROUP, []);
			}
			this.#showModels(false);
			this.#showPosts(false);
			this.#idle = true;
			if (this.follow?.current?.kind === 'bus') this.follow.stop();
		}
	}

	/** Trails on or off (remembered). */
	setTrails(on: boolean): void {
		this.trails.value = on;
		const map = this.#scope?.map;
		if (map?.getLayer(L.trails)) map.setLayoutProperty(L.trails, 'visibility', on && this.#visible ? 'visible' : 'none');
		if (on) this.#drawTrails();
	}

	/** Spotlight one route (every other takes its ghost color), or none. */
	spotlight(routeId: string | null): void {
		this.spot = routeId;
		const map = this.#scope?.map;
		if (!map || !this.network) return;
		for (const r of this.network.routes) map.setFeatureState({ source: SOURCES.ribbons, id: r.rid }, { spot: r.id === routeId, dim: routeId !== null && r.id !== routeId });
		map.setGlobalStateProperty(SPOT_STATE, routeId ?? '');
		this.#kick();
	}

	/** Select a route (spotlighting it) from the legend, or clear it. */
	selectRoute(routeId: string | null): void {
		const ctx = this.#ctx;
		if (!ctx) return;
		const r = this.route(routeId);
		if (r) ctx.selection.select(this.routeSelection(r));
		else if (ctx.selection.current?.layer === 'transit') ctx.selection.clear();
	}

	selected(s: Selection | null): void {
		const spot = s?.layer === 'transit' && s.kind === 'route' ? s.id : null;
		if (spot !== this.spot) this.spotlight(spot);
		this.#selectedBus = s?.layer === 'transit' && s.kind === 'bus' ? s.id : null;
		this.#updateRing();
		this.#kick();
	}

	/** The selection ring follows the selected bus (moved per frame with it). */
	#updateRing() {
		const vid = this.#selectedBus;
		const rt = vid ? this.#runtime.get(vid) : undefined;
		this.#ring = rt && vid ? [{ id: vid, lng: rt.pos[0], lat: rt.pos[1], sprite: RING, opacity: (rt.bus.opacity ?? 0) > 0 ? 1 : 0 }] : [];
		if (this.#useOverlay && this.#visible) this.#ctx?.overlay.set(RING_GROUP, this.#ring);
	}

	/** Follow a bus (the bus card's Follow); again to stop. */
	toggleFollow(vid: string): void {
		const f = this.follow;
		if (!f) return;
		if (f.is('bus', vid)) return f.stop();
		const v = this.feed.vehicles[vid];
		f.start({ kind: 'bus', id: vid, label: `bus ${v?.label ?? vid}`, position: () => this.position(vid) });
	}

	/** Where a bus is drawn now (lon, lat), or null when it isn't. */
	position(vid: string): [number, number] | null {
		const rt = this.#runtime.get(vid);
		if (!rt) return null;
		const s = this.buses[vid]?.state;
		return s === 'hidden' ? null : rt.pos;
	}

	chips(): Chip[] {
		if (this.status !== 'ready' && this.status !== 'stale') return [];
		const clock = this.clock;
		const now = clock ? clock.serverNow(clock.tick) : Date.now() / 1000;
		const shown = Object.values(this.buses).filter((b) => isShown(b.state)).length;
		const routes = this.network ? this.network.routes.length - this.network.dormant.length : 0;
		const age = this.lastFix === null ? null : now - this.lastFix;
		const stale = Boolean(this.pollError) || age === null || age >= STALE_FEED_S;
		const credit = `${CREDIT} · ${this.pollError ?? (age === null ? 'no bus has reported' : `newest fix ${ageText(age)}`)}`;
		const chips: Chip[] = [];
		if (!shown && (age === null || age > 15 * 60))
			chips.push({ id: 'no-buses', text: `No buses reporting${this.lastFix ? ` · last fix ${timeText(this.lastFix)}` : ''}`, title: credit, stale: true });
		else chips.push({ id: 'buses', text: `${shown} bus${shown === 1 ? '' : 'es'}`, title: credit, stale });
		chips.push({ id: 'routes', text: `${this.running.size}/${routes} routes running`, title: `${credit} · running: a bus in the last 15 min`, stale });
		return chips;
	}

	summary(): string | null {
		return this.network ? `${this.network.routes.length} routes` : null;
	}

	destroy(): void {
		this.#destroyed = true;
		this.poller.stop();
		clearInterval(this.#fallbackTimer);
		this.#stopTick?.();
		this.#stopTick = null;
		this.#releaseKeys?.();
		this.#releaseKeys = null;
		if (this.follow?.current?.kind === 'bus') this.follow.stop();
		this.#ctx?.overlay.update(BUS_GROUP, null);
		this.#scope?.dispose();
		this.#scope = null;
		if ((globalThis as { __tvtTransit?: unknown }).__tvtTransit === this.#debug) Reflect.deleteProperty(globalThis, '__tvtTransit');
	}

	// --- the feed -------------------------------------------------------------------------------------

	async #poll(signal: AbortSignal) {
		const clock = this.clock!;
		const server = clock.serverNow();
		const T = clock.playhead();
		const reload = this.#lastPoll === null || server - this.#lastPoll > RELOAD_AFTER_S;
		const windowS = Math.round(
			reload ? Math.min(MAX_WINDOW_S, Math.max(clock.delay, server - T) + FIRST_EXTRA_S) : Math.min(MAX_WINDOW_S, Math.max(NEXT_WINDOW_S, server - this.#lastPoll! + 60))
		);
		const at = clock.replayAt !== null ? `&at=${new Date(Math.floor(server) * 1000).toISOString()}` : '';
		try {
			const send = Date.now();
			const res = await fetch(`/api/transit/tracks?window=${windowS}${at}`, { signal });
			const receive = Date.now();
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const body: Tracks = await res.json();
			if (signal.aborted || this.#destroyed) return;
			clock.sample(body.now, send, receive);
			this.feed.merge(body, reload);
			this.feed.prune(clock.playhead());
			this.#lastPoll = body.now;
			this.vehicles = this.feed.vehicles;
			this.lastFix = body.lastFix;
			this.pollError = null;
			if (this.status === 'stale' && this.#useOverlay) this.status = 'ready';
			this.updatedAt = Date.now();
			clock.feed = { lastFix: body.lastFix, ok: true, at: Date.now() };
			this.#build();
			this.#second();
		} catch (err) {
			if (signal.aborted) return;
			this.pollError = `Live buses unavailable: ${err instanceof Error ? err.message : err}`;
			this.status = 'stale';
			clock.feed = { lastFix: this.lastFix, ok: false, at: Date.now() };
			throw err;
		}
	}

	// --- once a second ----------------------------------------------------------------------------------

	#second() {
		const clock = this.clock;
		if (!clock || !this.network || this.#destroyed) return;
		const T = clock.playhead();
		const running = runningAt(this.feed.routeRuns, T);
		if (!sameSet(running, this.running)) this.running = running;
		const buses: Record<string, BusSummary> = {};
		let moving = false;
		let changed = false;
		const before = this.buses;
		for (const [vid, track] of this.feed.tracks) {
			const at = positionAt(track, T, this.#at);
			const v = this.feed.vehicles[vid];
			buses[vid] = { vid, routeId: v?.routeId ?? null, state: at.state, fix: at.fix, kind: at.kind, stepSpeed: at.stepSpeed };
			if (at.state === 'moving' || at.state === 'gap') moving = true;
			if (before[vid]?.state !== at.state) changed = true;
		}
		this.buses = buses;
		// Nothing touches the map while the layer is off or the tab is hidden: the loop stays stopped.
		if (!this.#visible || hidden()) return;
		this.#applyRunning();
		if (this.trails.value) this.#drawTrails();
		// Something moves (or changed look) while the frame loop sleeps: wake it.
		if (this.#useOverlay && this.#idle && (moving || changed)) this.#kick();
	}

	/**
	 * Show which routes run: feature-state on the ribbons and stops, and the
	 * shields' badges, for whatever changed since it was last shown. Never
	 * the ribbon source.
	 */
	#applyRunning() {
		const map = this.#scope?.map;
		const net = this.network;
		const running = this.running;
		const was = this.#shownRunning;
		if (!map || !net || (was && sameSet(running, was))) return;
		for (const r of net.routes) {
			const on = running.has(r.id);
			if (!was || on !== was.has(r.id)) map.setFeatureState({ source: SOURCES.ribbons, id: r.rid }, { active: on });
		}
		const idleNow = idleStops(net, running);
		const idleWas = was ? idleStops(net, was) : null;
		idleNow.forEach((idle, i) => {
			if (!idleWas || idle !== idleWas[i]) map.setFeatureState({ source: SOURCES.stops, id: i + 1 }, { idle });
		});
		// The shields were built with nothing running (at mount).
		if (was || running.size) (map.getSource(SOURCES.shields) as GeoJSONSource | undefined)?.setData(shieldFeatures(net, running));
		this.#shownRunning = running;
		// The posts' flags: route color while running, ghost when not (instance data, no setData).
		if (this.#sceneState === 'ready') {
			this.#posts.setRunning(running, this.#byId);
			if (this.#postsOn) map.triggerRepaint();
		}
	}

	/** The trails' line source, at most once a second (§14.4: the one exception to "once per poll"). */
	#drawTrails() {
		const map = this.#scope?.map;
		const clock = this.clock;
		if (!map || !clock) return;
		const now = performance.now();
		if (now - this.#trailsAt < TRAILS_MS) return;
		this.#trailsAt = now;
		const T = clock.playhead();
		const features: Feature<MultiLineString>[] = [];
		for (const [vid, track] of this.feed.tracks) {
			const lines = trail(track, T, positionAt(track, T, this.#at));
			if (!lines.length) continue;
			features.push({
				type: 'Feature',
				geometry: { type: 'MultiLineString', coordinates: lines.map((l) => toPairs(l)) },
				properties: { vid }
			});
		}
		(map.getSource(SOURCES.trails) as GeoJSONSource | undefined)?.setData({ type: 'FeatureCollection', features });
	}

	// --- buses in the overlay -------------------------------------------------------------------------

	/** Rebuild the bus instances (after a poll, or when shown): never per frame. */
	#build() {
		const ctx = this.#ctx;
		if (!ctx || !this.#useOverlay) return;
		const o = ctx.overlay;
		if (!this.#visible) return;
		const runtime = new globalThis.Map<string, BusRuntime>();
		const buses: OverlayInstance[] = [];
		const heads: OverlayInstance[] = [];
		for (const vid of this.feed.tracks.keys()) {
			const v = this.feed.vehicles[vid];
			const b = busBadge(v);
			const solid = discKey(b, false);
			const hollow = discKey(b, true);
			if (!o.hasSprite(solid)) o.sprite(discSprite({ key: solid, text: b.text, color: b.color, textColor: b.textColor, halo: b.halo }));
			if (!o.hasSprite(hollow)) o.sprite(discSprite({ key: hollow, text: b.text, color: b.color, textColor: b.textColor, hollow: true, halo: false }));
			const plates = this.#plateSprites(b);
			const old = this.#runtime.get(vid);
			const pos: [number, number] = old?.pos ?? [0, 0];
			const pick = this.busSelection(vid);
			const bus: OverlayInstance = { id: vid, lng: pos[0], lat: pos[1], sprite: solid, opacity: 0, pick, radius: 14 };
			const head: OverlayInstance = { id: vid, lng: pos[0], lat: pos[1], sprite: HEADING, rotate: old?.heading ?? 0, rotateWithMap: true, opacity: 0 };
			const plate: OverlayInstance = { id: vid, lng: pos[0], lat: pos[1], sprite: plates.solid, opacity: 0, pick, radius: plateSize(b.text).width / 2 - 4 };
			const r = this.route(v?.routeId);
			runtime.set(vid, {
				bus,
				head,
				heading: old?.heading ?? null,
				turnedAt: old?.turnedAt ?? performance.now(),
				pos,
				solid,
				hollow,
				routeId: v?.routeId ?? null,
				state: old?.state ?? 'hidden',
				kind: old?.kind ?? null,
				shown: old?.shown ?? 0,
				raw: old?.raw ?? null,
				speed: old?.speed ?? 0,
				plate,
				plates,
				model: busModel(vid, pick, old?.model),
				color: r?.color ?? v?.color ?? null,
				ghost: r?.ghost ?? null
			});
			buses.push(bus);
			heads.push(head);
		}
		this.#runtime = runtime;
		this.#busList = buses;
		this.#headList = heads;
		this.#plateList = [];
		o.set(BUS_GROUP, buses);
		o.set(HEADING_GROUP, heads);
		o.set(PLATE_GROUP, this.#plateList);
		this.#updateRing();
		this.#kick();
	}

	/** A bus's plate sprites (solid and hollow, plain and selected), registered once per badge. */
	#plateSprites(b: Badge): BusRuntime['plates'] {
		const o = this.#ctx!.overlay;
		const out = {} as BusRuntime['plates'];
		for (const look of ['solid', 'hollow'] as const)
			for (const sel of [false, true]) {
				const key = plateKey(b, look, sel);
				if (!o.hasSprite(key)) o.sprite(plateSprite({ key, text: b.text, color: b.color, textColor: b.textColor, halo: b.halo, look, selected: sel }));
				out[`${look}${sel ? ':sel' : ''}`] = key;
			}
		return out;
	}

	/** Ask for frames again (the frame function then decides how many). */
	#kick() {
		if (!this.#useOverlay || !this.#visible || !this.#ctx || hidden()) return;
		this.#idle = false;
		this.#ctx.overlay.update(BUS_GROUP, this.#frame);
	}

	/**
	 * Once per rendered frame, for the scene's update and the overlay's
	 * (whichever runs first; reset on `render`): every bus at the playhead,
	 * the frame's level of detail and the fastest on-screen speed. No
	 * setData, no Svelte state. False when there's nothing to draw.
	 */
	#advance(): boolean {
		if (this.#advanced) return true;
		const clock = this.clock;
		const map = this.#scope?.map;
		if (!clock || !map || !this.#visible) return false;
		this.#advanced = true;
		const T = (this.#frameT = clock.playhead());
		const now = performance.now();
		const zoom = map.getZoom();
		const centre = map.getCenter();
		this.#lod = lodAt(zoom, centre.lat, map.getPitch(), this.#modelsOn);
		// On screen: where the overlay put each bus last frame (it projects them all, terrain included).
		// Before its first frame, the map's bounds stand in.
		const onScreen = this.#onScreen;
		onScreen.clear();
		if (!this.#size.w) this.#measure();
		const { w: W, h: H } = this.#size;
		const placed = this.#ctx!.overlay.positions(BUS_GROUP);
		for (const p of placed) if (p.x >= 0 && p.y >= 0 && p.x <= W && p.y <= H) onScreen.add(p.id);
		const b = placed.length ? null : map.getBounds();
		const at = this.#at;
		let fastest = 0;
		for (const [vid, rt] of this.#runtime) {
			const track = this.feed.tracks.get(vid);
			if (!track) {
				rt.state = 'hidden';
				rt.shown = 0;
				continue;
			}
			positionAt(track, T, at);
			const shown = at.state !== 'hidden';
			rt.pos[0] = at.lon;
			rt.pos[1] = at.lat;
			rt.state = at.state;
			rt.kind = at.kind;
			rt.shown = shown ? at.opacity : 0;
			rt.raw = at.heading;
			rt.speed = at.speed;
			rt.heading = smoothAngle(rt.heading, at.heading, now - rt.turnedAt);
			rt.turnedAt = now;
			const visible = b ? b.contains([at.lon, at.lat]) : onScreen.has(vid);
			if (at.speed > 0 && shown && visible) fastest = Math.max(fastest, at.speed);
		}
		this.#fastest = fastest;
		this.#idle = fastest === 0;
		return true;
	}

	#onScreen = new Set<string>();
	/** The playhead of the frame being drawn (epoch s). */
	#frameT = 0;
	/** The canvas size (CSS px), read on resize: reading it in a frame can force a layout. */
	#size = { w: 0, h: 0 };

	#measure() {
		const c = this.#scope?.map.getCanvas();
		if (c) this.#size = { w: c.clientWidth, h: c.clientHeight };
	}

	/**
	 * The overlay's update, per rendered frame: discs and heading arrows
	 * (fading out as models fade in), the selection ring, and the plates over
	 * the models. Returns the fastest on-screen speed (m/s), so the loop gives
	 * about half a pixel per frame, or false when nothing on screen moves.
	 */
	#frame = (): number | false => {
		if (!this.#advance()) return false;
		const lod = this.#lod;
		const spot = this.spot;
		const heads = this.#headList;
		const plates = this.#plateList;
		heads.length = 0;
		plates.length = 0;
		const offset = plateOffset(lod.clearance);
		for (const [vid, rt] of this.#runtime) {
			const dim = spot !== null && rt.routeId !== spot ? DIM : 1;
			const stale = rt.state === 'stale';
			rt.bus.lng = rt.head.lng = rt.pos[0];
			rt.bus.lat = rt.head.lat = rt.pos[1];
			rt.bus.sprite = stale ? rt.hollow : rt.solid;
			rt.bus.opacity = rt.shown * dim * lod.disc;
			if (lod.disc > 0) {
				rt.head.rotate = rt.heading ?? 0;
				rt.head.opacity = rt.shown && rt.heading !== null ? (stale ? 0.35 : 1) * rt.shown * dim * lod.disc : 0;
				heads.push(rt.head);
			}
			if (lod.fade > 0 && rt.shown > 0) {
				const sel = vid === this.#selectedBus;
				const p = rt.plate;
				p.lng = rt.pos[0];
				p.lat = rt.pos[1];
				p.sprite = rt.plates[`${stale ? 'hollow' : 'solid'}${sel ? ':sel' : ''}`];
				p.opacity = rt.shown * dim * lod.fade;
				p.altitude = plateAltitude(lod, sel);
				p.offset = offset;
				plates.push(p);
			}
		}
		for (const r of this.#ring) {
			const rt = this.#runtime.get(r.id);
			if (!rt) continue;
			r.lng = rt.pos[0];
			r.lat = rt.pos[1];
			r.opacity = (rt.bus.opacity ?? 0) > 0 ? lod.disc : 0;
		}
		return this.#fastest > 0 ? this.#fastest : false;
	};

	/**
	 * The scene's update for the bus models, per rendered frame: the shown
	 * buses' models (in place), on the drawn ground, turned to their path and
	 * pitched with its slope. Returns the fastest on-screen speed, like the
	 * overlay's (both ask the loop for the same rate).
	 */
	#frame3d = (_now: number, list: SceneInstance[]): number | false => {
		list.length = 0;
		if (!this.#advance()) return false;
		const lod = this.#lod;
		if (lod.fade <= 0) return false;
		const map = this.#scope!.map;
		const spot = this.spot;
		const now = performance.now();
		const ground = map.getTerrain() ? this.#ground : null;
		for (const [, rt] of this.#runtime) {
			const opacity = rt.shown * lod.fade;
			if (opacity <= 0) continue;
			const color = bodyColor({ routeId: rt.routeId, color: rt.color, ghost: rt.ghost, stale: rt.state === 'stale', dimmed: spot !== null && rt.routeId !== spot });
			list.push(
				placeModel(rt.model, { lng: rt.pos[0], lat: rt.pos[1], heading: rt.raw ?? rt.heading, color, opacity, scale: lod.scale, now, epoch: this.#terrainEpoch, ground })
			);
		}
		return this.#fastest > 0 ? this.#fastest : false;
	};

	// --- the 3D scene (WP10) ----------------------------------------------------------------------------

	#bumpTerrain() {
		this.#terrainEpoch++;
		const map = this.#scope?.map;
		this.#ground = map ? (p) => map.queryTerrainElevation(p) : null;
	}

	/** Zooming: ask for the scene near z15, and show models and posts by zoom. */
	#onZoom() {
		const map = this.#scope?.map;
		if (!map || !this.#visible || !this.#useOverlay) return;
		const zoom = map.getZoom();
		if (this.#sceneState === 'none' && zoom >= SCENE_FROM_ZOOM) this.#wantScene();
		if (this.#sceneState !== 'ready') return;
		const lat = map.getCenter().lat;
		this.#showModels(modelFade(zoom, lat) > 0);
		const posts = this.#posts.setZoom(zoom, lat);
		if (posts && !this.#postsOn) this.#near(map);
		this.#showPosts(posts);
	}

	/** Moving: refresh which stop posts the scene gets (now and then while moving, and at the end). */
	#onMove(end: boolean) {
		const map = this.#scope?.map;
		if (!map || !this.#postsOn) return;
		const now = performance.now();
		if (!end && now - this.#nearAt < NEAR_MS) return;
		this.#nearAt = now;
		this.#near(map);
		if (end) map.triggerRepaint();
	}

	/** The posts near the view: within the bounds, and twice the screen's half-diagonal of the centre. */
	#near(map: Map) {
		const c = map.getCenter();
		if (!this.#size.w) this.#measure();
		const radius = Math.hypot(this.#size.w, this.#size.h) * metresPerPx(map.getZoom(), c.lat);
		this.#posts.setNear(map.getBounds(), [c.lng, c.lat], radius);
	}

	#showModels(on: boolean) {
		const scene = this.#scene;
		const want = on && this.#visible && this.#sceneState === 'ready';
		if (!scene || want === this.#modelsOn) return;
		this.#modelsOn = want;
		scene.show(BUS3D_GROUP, want);
		if (want) this.#kick();
	}

	#showPosts(on: boolean) {
		const scene = this.#scene;
		const want = on && this.#visible && this.#sceneState === 'ready';
		if (!scene || want === this.#postsOn) return;
		this.#postsOn = want;
		scene.show(STOPS3D_GROUP, want);
	}

	/** Load the scene (never before the map's first idle: app.scene() waits for it). */
	#wantScene() {
		const ctx = this.#ctx;
		if (!ctx || this.#sceneState !== 'none') return;
		this.#sceneState = 'loading';
		ctx.scene().then(
			(scene) => this.#sceneReady(scene),
			(e) => {
				if (this.#destroyed) return;
				// Buses simply stay discs, and stops capsules, at every zoom.
				this.#sceneState = 'failed';
				console.warn(`Transit: 3D buses and stops are off: ${e instanceof Error ? e.message : e}`);
			}
		);
	}

	#sceneReady(scene: Scene) {
		const map = this.#scope?.map;
		const net = this.network;
		if (this.#destroyed || !map || !net) return;
		if (!scene.ok) {
			this.#sceneState = 'failed';
			return;
		}
		this.#scene = scene;
		this.#sceneState = 'ready';
		this.#posts.build(net.stops, (i) => this.stopSelection(i));
		this.#posts.setRunning(this.running, this.#byId);
		scene.set(BUS3D_GROUP, this.#modelList, { priority: PRIORITY.bus });
		scene.set(STOPS3D_GROUP, this.#posts.near, { priority: PRIORITY.stop });
		scene.show(BUS3D_GROUP, false);
		scene.show(STOPS3D_GROUP, false);
		scene.update(BUS3D_GROUP, this.#frame3d);
		this.#onZoom();
	}

	/** Take our groups out of the scene (the layer is going away). */
	#dropScene() {
		const scene = this.#scene;
		this.#scene = null;
		if (this.#sceneState === 'ready') this.#sceneState = 'none';
		this.#modelsOn = this.#postsOn = false;
		if (!scene) return;
		scene.remove(BUS3D_GROUP);
		scene.remove(STOPS3D_GROUP);
	}

	// --- the fallback symbol layer ----------------------------------------------------------------------

	#startFallback() {
		clearInterval(this.#fallbackTimer);
		const draw = () => {
			const map = this.#scope?.map;
			const clock = this.clock;
			if (!map || !clock || !this.#visible) return;
			const T = clock.playhead();
			const features: Feature<Point>[] = [];
			for (const [vid, track] of this.feed.tracks) {
				const at = positionAt(track, T, this.#at);
				if (at.state === 'hidden') continue;
				const v = this.feed.vehicles[vid];
				const badge = busBadge(v);
				const props: Record<string, unknown> = {
					vehicleId: vid,
					routeId: v?.routeId ?? '',
					number: badge.text,
					color: badge.color,
					textColor: badge.textColor,
					stale: at.state === 'stale'
				};
				if (at.heading !== null) props.bearing = at.heading;
				features.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [at.lon, at.lat] }, properties: props });
			}
			(map.getSource(SOURCES.buses) as GeoJSONSource | undefined)?.setData({ type: 'FeatureCollection', features });
		};
		draw();
		this.#fallbackTimer = setInterval(draw, FALLBACK_MS);
	}

	// --- hover, images, debug -------------------------------------------------------------------------

	#hover(sel: Selection | null) {
		const map = this.#scope?.map;
		if (!map) return;
		const ids: number[] = [];
		const add = (s: Selection) => {
			if (s.layer !== 'transit' || s.kind !== 'route') return;
			const r = this.route(s.id);
			if (r) ids.push(r.rid);
		};
		if (sel?.kind === 'routes') sel.items?.forEach(add);
		else if (sel) add(sel);
		if (ids.length === this.#hovered.length && ids.every((x, i) => x === this.#hovered[i])) return;
		for (const id of this.#hovered) if (!ids.includes(id)) map.setFeatureState({ source: SOURCES.ribbons, id }, { hover: false });
		for (const id of ids) map.setFeatureState({ source: SOURCES.ribbons, id }, { hover: true });
		this.#hovered = ids;
	}

	/** Draw one of this layer's images on demand; false when the name isn't ours. */
	#drawImage(map: Map, id: string): boolean {
		if (map.hasImage(id)) return true;
		let img: ReturnType<typeof shieldImage> | null = null;
		const shield = parseShield(id);
		if (shield) {
			const routes = shield.rids.map((rid) => this.#byRid.get(rid));
			if (routes.every(Boolean)) img = shieldImage(routes as NetworkRoute[], shield.running);
		} else if (id.startsWith(IMG.capsule)) {
			const n = Number(id.slice(IMG.capsule.length));
			if (Number.isInteger(n) && n > 0) img = capsuleImage(n);
		}
		if (!img) return false;
		// Added on demand; removed with the layer's other images on cleanup.
		this.#scope?.addImage(id, img.data, img.options);
		return true;
	}

	#debug: object | null = null;

	/** A read-only handle for tests and the console: `__tvtTransit`. */
	#installDebug() {
		const self = this;
		const handle = Object.freeze({
			/** Each bus as drawn in the last frame: id, lon, lat, state and its screen point (CSS px) when on screen. */
			buses() {
				const drawn = new globalThis.Map(self.#ctx?.overlay.positions(BUS_GROUP).map((p) => [p.id, p]) ?? []);
				return [...self.#runtime].map(([id, rt]) => ({
					id,
					lng: rt.pos[0],
					lat: rt.pos[1],
					state: self.buses[id]?.state ?? null,
					opacity: rt.bus.opacity,
					x: drawn.get(id)?.x ?? null,
					y: drawn.get(id)?.y ?? null,
					// WP10: speed (m/s) and the path heading this frame, the model's look, the plate's opacity.
					routeId: rt.routeId,
					speed: rt.speed,
					kind: rt.kind,
					raw: rt.raw,
					model: self.#modelsOn && self.#modelList.includes(rt.model.inst) ? (rt.model.inst.opacity ?? 0) : 0,
					heading3d: rt.model.heading,
					pitch3d: rt.model.inst.pitch ?? 0,
					color3d: rt.model.inst.color ?? null,
					plate: self.#plateList.includes(rt.plate) ? (rt.plate.opacity ?? 0) : 0,
					plateSprite: rt.plate.sprite,
					disc: rt.bus.sprite
				}));
			},
			running: () => [...self.running].sort(),
			playhead: () => self.clock?.playhead() ?? null,
			/** Whether the buses are asking the render loop for frames. */
			animating: () => self.#visible && self.#useOverlay && !self.#idle,
			overlay: () => self.#useOverlay,
			// WP10 ------------------------------------------------------------------------------------
			/** The 3D scene: none (not asked for yet), loading, ready or failed. */
			scene: () => self.#sceneState,
			/** The playhead of the last frame drawn (epoch s): what buses(), plates() and the models show. */
			frameT: () => self.#frameT,
			/** This frame's level of detail. */
			lod: () => ({ ...self.#lod, modelZoom: modelZoom(self.#scope?.map.getCenter().lat ?? 43.6), models: self.#modelsOn, posts: self.#postsOn }),
			/** The scene's own numbers (draw calls, instances, JS ms per frame and its p95), or null. */
			sceneStats: () => self.#scene?.stats() ?? null,
			/** Where each pickable 3D thing was drawn last frame. */
			placed: () => self.#scene?.placed() ?? [],
			/** Where each plate was drawn last frame (its anchor, CSS px), its sprite, and its body's box on screen. */
			plates: () => {
				const at = new globalThis.Map(self.#ctx?.overlay.positions(PLATE_GROUP).map((p) => [p.id, p]) ?? []);
				return self.#plateList.map((p) => {
					const a = at.get(p.id);
					const text = self.#runtime.get(p.id) ? busBadge(self.feed.vehicles[p.id]).text : '';
					const off = p.offset ?? [0, 0];
					const { width, height } = plateSize(text);
					// The sprite is centred on anchor + offset; the body sits PLATE_PAD in from its top left.
					const box = a ? { x: a.x + off[0] - width / 2 + PLATE_PAD, y: a.y + off[1] - height / 2 + PLATE_PAD, w: plateBodyWidth(text), h: PLATE_BODY_H } : null;
					return { id: p.id, sprite: p.sprite, opacity: p.opacity ?? 0, offset: off, altitude: p.altitude ?? 0, x: a?.x ?? null, y: a?.y ?? null, box };
				});
			},
			/** The stop posts handed to the scene now: how many, their scale and fade. */
			posts: () => ({ shown: self.#postsOn, near: self.#posts.near.length, all: self.#posts.all.length, scale: self.#posts.near[0]?.scale ?? null, opacity: self.#posts.near[0]?.opacity ?? null }),
			/**
			 * Each model's length on screen (px), measured on the GPU: the scene's
			 * probe projects the model's nose and tail (±6.1 m along it) with the
			 * mesh shader's own placement. Pause playback first, so nothing moves
			 * between the two probes.
			 */
			async modelLengths() {
				const scene = self.#scene;
				if (!scene) return [];
				const half = BUS_LENGTH_M / 2;
				const nose = await scene.probe('bus', [0, half, 0]);
				const tail = await scene.probe('bus', [0, -half, 0]);
				const back = new globalThis.Map(tail.map((r) => [r.id, r]));
				return nose
					.filter((r) => back.has(r.id))
					.map((r) => {
						const t = back.get(r.id)!;
						return { id: r.id, length: Math.hypot(r.x - t.x, r.y - t.y), x: (r.x + t.x) / 2, y: (r.y + t.y) / 2 };
					});
			}
		});
		Object.defineProperty(globalThis, '__tvtTransit', { value: handle, configurable: true, enumerable: false, writable: false });
		this.#debug = handle;
	}
}

const hidden = () => typeof document !== 'undefined' && document.visibilityState === 'hidden';

function toPairs(flat: number[]): [number, number][] {
	const out: [number, number][] = [];
	for (let i = 0; i + 1 < flat.length; i += 2) out.push([flat[i], flat[i + 1]]);
	return out;
}

export function create(): LayerModule {
	return new TransitModule();
}
