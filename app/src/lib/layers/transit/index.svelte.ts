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
 */

const BUS_GROUP = 'transit-buses';
const HEADING_GROUP = 'transit-heading';
const RING_GROUP = 'transit-selected';
const HEADING = 'transit-heading';
const RING = 'transit-ring';
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
			pick: (f: MapGeoJSONFeature) => {
				const s = this.network?.stops[Number(f.properties?.sid) - 1];
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

	route(id: string | null | undefined): NetworkRoute | undefined {
		return id ? this.#byId.get(id) : undefined;
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
		addSlotted(map, networkLayers(), def.order, (l, before) => scope.addLayer(l, before));
		this.#useOverlay = ctx.overlay.ok;
		if (this.#useOverlay) {
			const o = ctx.overlay;
			o.sprite(headingSprite());
			o.sprite(ringSprite(RING, 44));
			o.set(HEADING_GROUP, [], { z: 9 });
			o.set(BUS_GROUP, [], { z: 10, priority: PRIORITY.bus });
			o.set(RING_GROUP, [], { z: 11 });
			scope.defer(() => {
				for (const g of [HEADING_GROUP, BUS_GROUP, RING_GROUP]) o.remove(g);
			});
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
		if (!this.#useOverlay) for (const id of FALLBACK_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis(on));
		if (on) {
			this.poller.start();
			this.#build();
			this.#second();
			if (this.#useOverlay) this.#kick();
			else this.#startFallback();
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
			}
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
			const old = this.#runtime.get(vid);
			const pos: [number, number] = old?.pos ?? [0, 0];
			const bus: OverlayInstance = { id: vid, lng: pos[0], lat: pos[1], sprite: solid, opacity: 0, pick: this.busSelection(vid), radius: 14 };
			const head: OverlayInstance = { id: vid, lng: pos[0], lat: pos[1], sprite: HEADING, rotate: old?.heading ?? 0, rotateWithMap: true, opacity: 0 };
			runtime.set(vid, { bus, head, heading: old?.heading ?? null, turnedAt: old?.turnedAt ?? performance.now(), pos, solid, hollow, routeId: v?.routeId ?? null });
			buses.push(bus);
			heads.push(head);
		}
		this.#runtime = runtime;
		this.#busList = buses;
		this.#headList = heads;
		o.set(BUS_GROUP, buses);
		o.set(HEADING_GROUP, heads);
		this.#updateRing();
		this.#kick();
	}

	/** Ask for frames again (the frame function then decides how many). */
	#kick() {
		if (!this.#useOverlay || !this.#visible || !this.#ctx || hidden()) return;
		this.#idle = false;
		this.#ctx.overlay.update(BUS_GROUP, this.#frame);
	}

	/**
	 * Per rendered frame: every bus at the playhead (no setData, no Svelte
	 * state). Returns the fastest on-screen speed (m/s), so the loop gives
	 * about half a pixel per frame, or false when nothing on screen moves.
	 */
	#frame = (): number | false => {
		const clock = this.clock;
		const map = this.#scope?.map;
		if (!clock || !map || !this.#visible) return false;
		const T = clock.playhead();
		const now = performance.now();
		const b = map.getBounds();
		const [w, s, e, n] = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
		const spot = this.spot;
		const at = this.#at;
		let fastest = 0;
		for (const [vid, rt] of this.#runtime) {
			const track = this.feed.tracks.get(vid);
			if (!track) continue;
			positionAt(track, T, at);
			const dim = spot !== null && rt.routeId !== spot ? 0.3 : 1;
			const shown = at.state !== 'hidden';
			rt.pos[0] = at.lon;
			rt.pos[1] = at.lat;
			rt.bus.lng = rt.head.lng = at.lon;
			rt.bus.lat = rt.head.lat = at.lat;
			rt.bus.sprite = at.state === 'stale' ? rt.hollow : rt.solid;
			rt.bus.opacity = shown ? at.opacity * dim : 0;
			rt.heading = smoothAngle(rt.heading, at.heading, now - rt.turnedAt);
			rt.turnedAt = now;
			rt.head.rotate = rt.heading ?? 0;
			rt.head.opacity = shown && rt.heading !== null ? (at.state === 'stale' ? 0.35 : 1) * at.opacity * dim : 0;
			if (at.speed > 0 && shown && at.lon >= w && at.lon <= e && at.lat >= s && at.lat <= n) fastest = Math.max(fastest, at.speed);
		}
		for (const r of this.#ring) {
			const rt = this.#runtime.get(r.id);
			if (!rt) continue;
			r.lng = rt.pos[0];
			r.lat = rt.pos[1];
			r.opacity = (rt.bus.opacity ?? 0) > 0 ? 1 : 0;
		}
		this.#idle = fastest === 0;
		return fastest > 0 ? fastest : false;
	};

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
					y: drawn.get(id)?.y ?? null
				}));
			},
			running: () => [...self.running].sort(),
			playhead: () => self.clock?.playhead() ?? null,
			/** Whether the buses are asking the render loop for frames. */
			animating: () => self.#visible && self.#useOverlay && !self.#idle,
			overlay: () => self.#useOverlay
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
