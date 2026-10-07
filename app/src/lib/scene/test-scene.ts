import type { AppCtx } from '#lib/app/context.js';
import type { LngLatAlt, ProbeRow, Scene, SceneInstance, Vec3 } from './index.js';

/**
 * The scene's test page (`/?scene-test`, like the overlay's `?overlay-test`):
 * 1,000 bus models in a grid over the current view, which can be set moving,
 * and a showcase of every mesh, a cone, lines and a photo plane (a synthetic
 * test pattern, never a camera image) around the centre. The `scene` spec
 * (@wp9) measures placement against `map.project` through `probe()`, which
 * reads back the GPU's own placement by transform feedback.
 */
export interface ProbeSummary {
	n: number;
	/** Largest and mean distance between the GPU's anchor and map.project, px. */
	max: number;
	mean: number;
	/** The same for plain float32 Mercator (what RTC avoids), px. */
	mercMax: number;
	/** Largest |drawn base − queryTerrainElevation|, metres. */
	baseMax: number;
	rows: ProbeRow[];
}

export interface SceneTestHandle {
	count: number;
	ok(): boolean;
	error(): string | null;
	stats(): ReturnType<Scene['stats']>;
	/** Lay the grid out again over the current view (optionally only the middle `fraction` of it, and models at `scale`). */
	reset(fraction?: number, scale?: number): void;
	setMoving(on: boolean): void;
	/** Measure the grid on the next frame. Only rows inside the viewport (with `margin` px) count. */
	probe(margin?: number): Promise<ProbeSummary>;
	/** Every mesh, a cone, lines and a photo plane around the centre. */
	showcase(on: boolean): Promise<void>;
	placed(): { id: string; x: number; y: number; r: number }[];
	/** One instance at a screen point (for picking tests); returns its id. */
	placeAt(x: number, y: number): string;
	/** Remove the grid and any placed instances. */
	clear(): void;
}

const GROUP = 'scene-test';
const SHOW = 'scene-test-showcase';
const COLORS = ['#2b6cb0', '#d1495b', '#2a9d8f', '#e76f51', '#6a4c93', '#3d5a80'];

/** Camera axes in east/north/up for a heading, a tilt below the horizon and a roll (as the solver's axes()). */
function axes(heading: number, tilt: number, roll: number): [Vec3, Vec3, Vec3] {
	const h = (heading * Math.PI) / 180;
	const t = (tilt * Math.PI) / 180;
	const r = (roll * Math.PI) / 180;
	const fwd: Vec3 = [Math.sin(h) * Math.cos(t), Math.cos(h) * Math.cos(t), -Math.sin(t)];
	const right0: Vec3 = [Math.cos(h), -Math.sin(h), 0];
	const down0: Vec3 = [fwd[1] * right0[2] - fwd[2] * right0[1], fwd[2] * right0[0] - fwd[0] * right0[2], fwd[0] * right0[1] - fwd[1] * right0[0]];
	const right = [0, 1, 2].map((i) => right0[i] * Math.cos(r) + down0[i] * Math.sin(r)) as Vec3;
	const down = [0, 1, 2].map((i) => -right0[i] * Math.sin(r) + down0[i] * Math.cos(r)) as Vec3;
	return [right, down, fwd];
}

const R = 6371008.8;
function move(lng: number, lat: number, east: number, north: number): [number, number] {
	return [lng + ((east / (R * Math.cos((lat * Math.PI) / 180))) * 180) / Math.PI, lat + ((north / R) * 180) / Math.PI];
}

/** A synthetic test pattern (no camera image anywhere in tests). */
async function pattern(): Promise<Blob> {
	const c = new OffscreenCanvas(768, 480);
	const g = c.getContext('2d')!;
	const bars = ['#fffbf4', '#f2c14e', '#2a9d8f', '#4d9de0', '#d1495b', '#6a4c93', '#2b2a33'];
	bars.forEach((col, i) => {
		g.fillStyle = col;
		g.fillRect((i * 768) / bars.length, 0, 768 / bars.length + 1, 360);
	});
	g.fillStyle = '#2b2a33';
	g.fillRect(0, 360, 768, 120);
	g.fillStyle = '#fffbf4';
	g.font = 'bold 44px sans-serif';
	g.textAlign = 'center';
	g.fillText('SCENE TEST PATTERN', 384, 435);
	return c.convertToBlob({ type: 'image/png' });
}

export function startSceneTest(app: AppCtx, scene: Scene, count = 1000): SceneTestHandle {
	let instances: SceneInstance[] = [];
	let base: [number, number][] = [];
	let moving = false;
	let extra = 0;

	const pick = (i: number | string) => ({ kind: 'bus' as const, id: `s${i}`, layer: 'scene-test', title: `Test model ${i}`, fact: 'A scene test instance' });

	const reset = (fraction = 1, scale = 1) => {
		const map = app.map;
		if (!map) return;
		const canvas = map.getCanvas();
		const w = canvas.clientWidth;
		const h = canvas.clientHeight;
		const cols = 40;
		const rows = Math.ceil(count / cols);
		instances = [];
		base = [];
		const fx = 0.76 * fraction;
		const fy = 0.6 * fraction;
		for (let i = 0; i < count; i++) {
			// A grid over the middle of the screen (clear of the bars), unprojected onto the terrain.
			const x = w * (0.5 - fx / 2 + (fx * ((i % cols) + 0.5)) / cols);
			const y = h * (0.5 - fy / 2 + (fy * (Math.floor(i / cols) + 0.5)) / rows);
			const ll = map.unproject([x, y]);
			base.push([ll.lng, ll.lat]);
			instances.push({ id: `s${i}`, mesh: 'bus', lng: ll.lng, lat: ll.lat, heading: (i * 37) % 360, scale, color: COLORS[i % COLORS.length], minPx: 9, pick: pick(i) });
		}
		scene.set(GROUP, instances);
	};

	const update = (now: number) => {
		if (!moving) return false;
		const t = now / 1000;
		for (let k = 0; k < instances.length; k++) {
			instances[k].lng = base[k][0] + 0.0001 * Math.cos(t + k);
			instances[k].lat = base[k][1] + 0.00007 * Math.sin(t + k);
			instances[k].heading = ((t + k) * 180) / Math.PI + 90;
		}
		return 8;
	};

	const probe = async (margin = 0): Promise<ProbeSummary> => {
		const map = app.map!;
		const c = map.getCanvas();
		const [W, H] = [c.clientWidth, c.clientHeight];
		const all = await scene.probe('bus');
		const rows = all.filter((r) => /^s\d+$/.test(r.id) && r.rx >= -margin && r.ry >= -margin && r.rx <= W + margin && r.ry <= H + margin);
		let max = 0;
		let sum = 0;
		let mercMax = 0;
		let baseMax = 0;
		for (const r of rows) {
			const d = Math.hypot(r.x - r.rx, r.y - r.ry);
			max = Math.max(max, d);
			sum += d;
			mercMax = Math.max(mercMax, Math.hypot(r.mx - r.rx, r.my - r.ry));
			if (r.ground !== null) baseMax = Math.max(baseMax, Math.abs(r.z - r.ground));
		}
		return { n: rows.length, max, mean: rows.length ? sum / rows.length : 0, mercMax, baseMax, rows };
	};

	const showcase = async (on: boolean) => {
		if (!on) {
			scene.remove(SHOW);
			return;
		}
		const map = app.map!;
		const c = map.getCenter();
		const exag = app.exaggeration();
		const groundTrue = (lng: number, lat: number) => (map.queryTerrainElevation([lng, lat]) ?? 0) / (map.getTerrain() ? exag : 1);
		const at = (e: number, n: number) => move(c.lng, c.lat, e, n);
		const [bl, bt] = at(0, 0);
		const [sl, st] = at(16, -6);
		const [pl, pt] = at(-18, 14);
		const [nl, nt] = at(30, 22);
		const height = 11;
		const g = groundTrue(pl, pt);
		const [right, down, fwd] = axes(150, 24, 0);
		const apex: LngLatAlt = [pl, pt, g + height];
		const showcaseItems: SceneInstance[] = [
			{ id: 'show-bus', mesh: 'bus', lng: bl, lat: bt, heading: 35, color: '#2b6cb0', shadow: true, pick: { kind: 'bus', id: 'show-bus', layer: 'scene-test', title: 'Test bus', fact: 'A scene test instance' } },
			{ id: 'show-stop', mesh: 'stop', lng: sl, lat: st, heading: 35, slots: ['#d1495b', '#2b6cb0', null, '#2a9d8f'], pick: { kind: 'stop', id: 'show-stop', layer: 'scene-test', title: 'Test stop' } },
			{ id: 'show-pole', mesh: 'pole', lng: pl, lat: pt, scale: [1, 1, height - 0.3] },
			{ id: 'show-head', mesh: 'head', lng: pl, lat: pt, alt: g + height, basis: [right, down, fwd], minPx: 12, pick: { kind: 'camera', id: 'show-head', layer: 'scene-test', title: 'Test camera' } },
			{ id: 'show-pin', mesh: 'pin', lng: nl, lat: nt, color: '#e0a526', scale: 0.4, pick: { kind: 'camera', id: 'show-pin', layer: 'scene-test', title: 'Uncalibrated test camera' } }
		];
		// The cone: rays through the image border to the ground (a flat ground at g for the test).
		const ends: LngLatAlt[] = [];
		const tx = Math.tan((36.87 / 2) * (Math.PI / 180)) * (768 / 480);
		const ty = Math.tan((36.87 / 2) * (Math.PI / 180));
		const border: [number, number][] = [];
		for (let k = 0; k < 8; k++) border.push([-1 + (2 * k) / 8, -1]);
		for (let k = 0; k < 8; k++) border.push([1, -1 + (2 * k) / 8]);
		for (let k = 0; k < 8; k++) border.push([1 - (2 * k) / 8, 1]);
		for (let k = 0; k < 8; k++) border.push([-1, 1 - (2 * k) / 8]);
		const corners: LngLatAlt[] = [];
		for (const [sx, sy] of border) {
			const ray = [0, 1, 2].map((i) => fwd[i] + sx * tx * right[i] + sy * ty * down[i]);
			const t = ray[2] < -1e-3 ? Math.min(120, height / -ray[2]) : 120;
			const [el, et] = move(pl, pt, ray[0] * t, ray[1] * t);
			const end: LngLatAlt = [el, et, g + height + ray[2] * t];
			ends.push(end);
			if (Math.abs(sx) === 1 && Math.abs(sy) === 1) corners.push(end);
		}
		scene.set(SHOW, showcaseItems);
		scene.setCones(SHOW, [{ id: 'show-cone', apex, ends, color: '#2a9d8f', opacity: 0.16 }]);
		scene.setLines(SHOW, [
			...corners.map((p, i) => ({ id: `show-edge-${i}`, points: [apex, p], color: '#2b2a33', width: 1.5, opacity: 0.8 })),
			{ id: 'show-moved', points: [move(pl, pt, -6, -4), [pl, pt] as [number, number]], color: '#2b2a33', width: 1, opacity: 0.5 }
		]);
		await scene.textures.load('scene-test-pattern', await pattern());
		scene.setPhotos(SHOW, [{ id: 'show-photo', apex, right, down, forward: fwd, tx, ty, texture: 'scene-test-pattern', label: 'Test camera · scene', widthPx: 140 }]);
	};

	const placeAt = (x: number, y: number) => {
		const ll = app.map!.unproject([x, y]);
		const id = `p${extra++}`;
		instances.push({ id, mesh: 'bus', lng: ll.lng, lat: ll.lat, heading: 0, color: '#d1495b', minPx: 9, pick: { kind: 'bus', id, layer: 'scene-test', title: `Placed model ${id}`, fact: 'A scene test instance' } });
		scene.set(GROUP, instances);
		return id;
	};

	reset();
	return {
		count,
		ok: () => scene.ok,
		error: () => scene.error,
		stats: () => scene.stats(),
		reset,
		setMoving(on: boolean) {
			moving = on;
			scene.update(GROUP, on ? update : null);
		},
		probe,
		showcase,
		placed: () => scene.placed(),
		placeAt,
		clear() {
			instances = [];
			base = [];
			scene.set(GROUP, instances);
		}
	};
}
