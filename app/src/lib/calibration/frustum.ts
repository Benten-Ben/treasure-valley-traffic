/**
 * The camera's frustum (docs/14 §14.6: "What a camera looks like", "The photo
 * in the cone" and "Look through"; WP13). Pure functions on the solver's one
 * camera model, `axes()`, so the 3D head, the view cone, the photo plane,
 * look-through and the solver can't disagree.
 *
 * Local frames are the solver's: metres east and north of a point, with z the
 * absolute height (`toLocal` and `fromLocal`).
 */
import { axes, barPx, fromLocal, toLocal, type ImageSize, type LngLatZ, type Pixel, type Pose, type Vec } from './solver.js';

export type Vec3 = Vec;

const D2R = Math.PI / 180;
const R2D = 180 / Math.PI;
const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));

/** Focal length in pixels for a vertical field of view (degrees) and an image height. */
export function focalPx(vfov: number, height: number): number {
	return height / 2 / Math.tan((vfov * D2R) / 2);
}

/** The ray through an image pixel, east/north/up: `forward + x·right + y·down` (not unit length). */
export function pixelRay(pose: Pose, size: ImageSize, px: Pixel): Vec3 {
	const [right, down, fwd] = axes(pose.heading, pose.tilt, pose.roll);
	const f = focalPx(pose.vfov, size.height);
	const x = (px[0] - size.width / 2) / f;
	const y = (px[1] - size.height / 2) / f;
	return [0, 1, 2].map((i) => fwd[i] + x * right[i] + y * down[i]) as Vec3;
}

/** The pixel a direction from the camera (east/north/up) lands on, or null when it points behind it. */
export function rayPixel(pose: Pose, size: ImageSize, dir: Vec3): Pixel | null {
	const [right, down, fwd] = axes(pose.heading, pose.tilt, pose.roll);
	const z = dot(dir, fwd);
	if (z <= 1e-12) return null;
	const f = focalPx(pose.vfov, size.height);
	return [size.width / 2 + (f * dot(dir, right)) / z, size.height / 2 + (f * dot(dir, down)) / z];
}

/**
 * `perEdge` pixels along each image edge, clockwise from the top-left
 * corner (top, right, bottom, left), so the corners are at 0, n, 2n and 3n.
 */
export function borderPixels(size: ImageSize, perEdge = 8): Pixel[] {
	const { width: w, height: h } = size;
	const out: Pixel[] = [];
	for (let k = 0; k < perEdge; k++) out.push([(w * k) / perEdge, 0]);
	for (let k = 0; k < perEdge; k++) out.push([w, (h * k) / perEdge]);
	for (let k = 0; k < perEdge; k++) out.push([w - (w * k) / perEdge, h]);
	for (let k = 0; k < perEdge; k++) out.push([0, h - (h * k) / perEdge]);
	return out;
}

/** The view cone's shape (§14.6): 8 rays per image edge; sky rays end 120 m out; the ground is cut where the footprint is (250 m). */
export const CONE = { perEdge: 8, skyM: 120, maxGroundM: 250 } as const;

export interface ViewCone {
	apex: LngLatZ;
	/** The 32 ray ends (lon, lat, true height), clockwise from the top-left corner. */
	ends: LngLatZ[];
	/** Whether each end lies on the ground plane. */
	onGround: boolean[];
	/** The four corner rays' ends: top-left, top-right, bottom-right, bottom-left. */
	corners: LngLatZ[];
}

/**
 * The view cone (§14.6, "One camera model"): the apex at the camera and a ray
 * through each border pixel, ending where it meets the ground plane at
 * `groundZ` (the calibration's ground height), or 120 m along it when it
 * points above the horizon. A ground point further than the footprint's
 * cut-off (250 m) is pulled in along the ground to the cut-off, as
 * `footprint()` does, so the cone meets the draped footprint.
 */
export function viewCone(pose: Pose, size: ImageSize, groundZ: number, o: Partial<typeof CONE> = {}): ViewCone {
	const perEdge = o.perEdge ?? CONE.perEdge;
	const skyM = o.skyM ?? CONE.skyM;
	const maxGroundM = o.maxGroundM ?? CONE.maxGroundM;
	const origin: [number, number] = [pose.lon, pose.lat];
	const ends: LngLatZ[] = [];
	const onGround: boolean[] = [];
	for (const px of borderPixels(size, perEdge)) {
		const r = pixelRay(pose, size, px);
		let v: Vec3 | null = null;
		if (r[2] < -1e-9) {
			const s = (groundZ - pose.alt) / r[2];
			if (s > 0) {
				const d = Math.hypot(s * r[0], s * r[1]);
				const k = d > maxGroundM ? maxGroundM / d : 1;
				v = [s * r[0] * k, s * r[1] * k, groundZ];
			}
		}
		onGround.push(v !== null);
		if (!v) {
			const n = Math.hypot(r[0], r[1], r[2]);
			v = [(r[0] / n) * skyM, (r[1] / n) * skyM, pose.alt + (r[2] / n) * skyM];
		}
		ends.push(fromLocal(origin, v));
	}
	return { apex: [pose.lon, pose.lat, pose.alt], ends, onGround, corners: [0, 1, 2, 3].map((k) => ends[k * perEdge]) };
}

// --- the photo plane ----------------------------------------------------------------

export interface Crop {
	x: number;
	y: number;
	width: number;
	height: number;
}

/**
 * A photo plane (§14.6, "The photo in the cone"): perpendicular to the view
 * axis, its corners at `apex + d·(forward + (cx ± tx)·right + (cy ± ty)·down)`.
 * For the whole image, `tx = tan(vfov/2)·W/H`, `ty = tan(vfov/2)` and the
 * centre (cx, cy) is 0; a crop moves and shrinks it.
 */
export interface PhotoPlane {
	right: Vec3;
	down: Vec3;
	forward: Vec3;
	/** Half the crop's width and height, in tangent units. */
	tx: number;
	ty: number;
	/** The crop's centre, in tangent units (0, 0 when it's centred on the image). */
	cx: number;
	cy: number;
}

export function photoPlane(pose: Pose, size: ImageSize, crop: Crop = { x: 0, y: 0, width: size.width, height: size.height }): PhotoPlane {
	const [right, down, forward] = axes(pose.heading, pose.tilt, pose.roll);
	const f = focalPx(pose.vfov, size.height);
	const u0 = (crop.x - size.width / 2) / f;
	const u1 = (crop.x + crop.width - size.width / 2) / f;
	const v0 = (crop.y - size.height / 2) / f;
	const v1 = (crop.y + crop.height - size.height / 2) / f;
	return { right, down, forward, tx: (u1 - u0) / 2, ty: (v1 - v0) / 2, cx: (u0 + u1) / 2, cy: (v0 + v1) / 2 };
}

/**
 * The part of a frame a photo plane shows: everything but the burned-in 511
 * bar (`barPx`). `centred` also trims as much from the top, so the crop stays
 * centred on the view axis: the floating photo is sized by the scene (which
 * only knows planes centred on their apex's axis), while look-through, which
 * sets the plane's distance itself, shows the whole picture above the bar.
 */
export function photoCrop(size: ImageSize, centred: boolean): Crop {
	const bar = barPx(size.width, size.height);
	return centred
		? { x: 0, y: bar, width: size.width, height: size.height - 2 * bar }
		: { x: 0, y: 0, width: size.width, height: size.height - bar };
}

/**
 * Where the scene's apex goes for a plane at distance d: the scene draws
 * planes centred on their apex's view axis, so an off-centre crop moves the
 * apex by `d·(cx·right + cy·down)`. The camera's own apex when the crop is
 * centred.
 */
export function planeApex(pose: Pose, plane: PhotoPlane, d: number): LngLatZ {
	const off = [0, 1, 2].map((i) => d * (plane.cx * plane.right[i] + plane.cy * plane.down[i]));
	return fromLocal([pose.lon, pose.lat], [off[0], off[1], pose.alt + off[2]]);
}

/** The plane's corners at distance d (top-left, top-right, bottom-right, bottom-left), lon/lat/true height. */
export function planeCorners(pose: Pose, plane: PhotoPlane, d: number): LngLatZ[] {
	const corner = (sx: number, sy: number): LngLatZ => {
		const v = [0, 1, 2].map((i) => d * (plane.forward[i] + (plane.cx + sx * plane.tx) * plane.right[i] + (plane.cy + sy * plane.ty) * plane.down[i]));
		return fromLocal([pose.lon, pose.lat], [v[0], v[1], pose.alt + v[2]]);
	};
	return [corner(-1, -1), corner(1, -1), corner(1, 1), corner(-1, 1)];
}

// --- look-through: fitting the picture -----------------------------------------------------

export interface Box {
	x: number;
	y: number;
	width: number;
	height: number;
}

/**
 * Where the picture sits on a W×H canvas while looking through (§14.6
 * "Look through", step 4): letterboxed at its aspect, centred, with
 * `h_img = min(0.92·H, 0.96·W·h/w)`.
 */
export function letterbox(W: number, H: number, size: ImageSize): Box {
	const height = Math.min(0.92 * H, (0.96 * W * size.height) / size.width);
	const width = (height * size.width) / size.height;
	return { x: (W - width) / 2, y: (H - height) / 2, width, height };
}

/** The map's vertical field of view (degrees) that makes a picture of field of view `vfov` fill a box `hImg` tall on an H-tall canvas: `2·atan(tan(Vc/2)·H/h_img)`. */
export function mapFov(vfov: number, H: number, hImg: number): number {
	return 2 * Math.atan((Math.tan((vfov * D2R) / 2) * H) / hImg) * R2D;
}

/** An image pixel's place on screen, in the letterbox. */
export function imageToScreen(px: Pixel, size: ImageSize, box: Box): [number, number] {
	return [box.x + (px[0] * box.width) / size.width, box.y + (px[1] * box.height) / size.height];
}

// --- the map camera -------------------------------------------------------------------------

export const EARTH_RADIUS = 6371008.8;
export const TILE_SIZE = 512;
/** MapLibre's roll has the solver's sign (settled by measurement on the seeds, docs/14 §14.9 "Seed registration"). */
export const ROLL_SIGN = 1;

const circumference = (lat: number) => 2 * Math.PI * EARTH_RADIUS * Math.cos(lat * D2R);
export const mercatorX = (lng: number) => (180 + lng) / 360;
export const mercatorY = (lat: number) => (180 - R2D * Math.log(Math.tan(Math.PI / 4 + (lat * D2R) / 2))) / 360;
const lngOf = (x: number) => x * 360 - 180;
const latOf = (y: number) => 2 * R2D * Math.atan(Math.exp((180 - y * 360) * D2R)) - 90;

/** MapLibre's world pixels per metre at a zoom and latitude (512 px tiles). */
export function pxPerMetre(zoom: number, lat: number): number {
	return (TILE_SIZE * 2 ** zoom) / circumference(lat);
}

/** The public state of the map's camera (all from MapLibre getters, plus the canvas's CSS height). */
export interface MapCamera {
	center: [number, number];
	/** getCenterElevation(), metres as drawn. */
	elevation: number;
	zoom: number;
	pitch: number;
	bearing: number;
	/** getVerticalFieldOfView(), degrees. */
	fov: number;
	/** The canvas's CSS height, px. */
	height: number;
}

/**
 * Where the map's eye is (lon, lat, metres), worked out from its public
 * state the way MapLibre 6.12 places it (`getCameraLngLat`,
 * `getCameraAltitude`): back from the centre along the view direction by the
 * camera-to-centre distance. Look-through reads it back after placing the
 * camera (step 7).
 */
export function eyeOf(c: MapCamera): LngLatZ {
	const ppm = pxPerMetre(c.zoom, c.center[1]);
	const dist = ((0.5 / Math.tan((c.fov * D2R) / 2)) * c.height) / ppm;
	const p = c.pitch * D2R;
	const b = c.bearing * D2R;
	const dm = dist / circumference(c.center[1]);
	const x = mercatorX(c.center[0]) - dm * Math.sin(p) * Math.sin(b);
	const y = mercatorY(c.center[1]) + dm * Math.sin(p) * Math.cos(b);
	return [lngOf(x), latOf(y), Math.cos(p) * dist + c.elevation];
}

/** The eye-to-centre distance of a map camera, metres. */
export function centreDistance(c: Pick<MapCamera, 'zoom' | 'fov' | 'height' | 'center'>): number {
	return ((0.5 / Math.tan((c.fov * D2R) / 2)) * c.height) / pxPerMetre(c.zoom, c.center[1]);
}

/**
 * MapLibre 6.12's near clipping distance in metres: its Mercator transform
 * puts the near plane at `height / 50` world pixels, so in metres it grows
 * with the eye-to-centre distance (step 8, "Why the max").
 */
export function nearMetres(height: number, zoom: number, lat: number): number {
	return height / 50 / pxPerMetre(zoom, lat);
}

/** The look-through photo plane's distance from the eye: `max(2 m, 2 × near)`, so the near plane never clips it. */
export function photoDistance(near: number): number {
	return Math.max(2, 2 * near);
}

/** Straight-line distance between two points, metres. */
export function metresBetween(a: LngLatZ, b: LngLatZ): number {
	const v = toLocal([a[0], a[1]], b);
	return Math.hypot(v[0], v[1], v[2] - a[2]);
}

/** Ground distance between two points, metres. */
export function groundMetres(a: readonly [number, number] | LngLatZ, b: readonly [number, number] | LngLatZ): number {
	const v = toLocal([a[0], a[1]], [b[0], b[1], 0]);
	return Math.hypot(v[0], v[1]);
}

// --- look-through: the map camera's pose, flights and the fade --------------------------------------

/** The map's camera as an eye and a rotation, MapLibre's way (bearing; pitch from straight down; roll; fov). */
export interface EyePose {
	lng: number;
	lat: number;
	alt: number;
	bearing: number;
	pitch: number;
	roll: number;
	fov: number;
}

/** A calibrated pose as the map camera: bearing = heading, pitch = 90 − tilt, roll by the measured sign, at field of view `fov`. */
export function eyePose(pose: Pose, fov: number): EyePose {
	return { lng: pose.lon, lat: pose.lat, alt: pose.alt, bearing: pose.heading, pitch: 90 - pose.tilt, roll: ROLL_SIGN * pose.roll, fov };
}

/** The view direction for a bearing and a pitch (0 = straight down), east/north/up. */
export function viewDirection(bearing: number, pitch: number): Vec3 {
	const b = bearing * D2R;
	const p = pitch * D2R;
	return [Math.sin(p) * Math.sin(b), Math.sin(p) * Math.cos(b), -Math.cos(p)];
}

/** a − b in degrees, in (−180, 180]. */
export function angleDiff(a: number, b: number): number {
	const d = (((a - b) % 360) + 540) % 360 - 180;
	return d === -180 ? 180 : d;
}

/** Ease in and out (cubic). */
export const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

/** Flights longer than this arc up (§14.6 step 6), metres; and by this much at the middle. */
export const ARC = { minM: 300, heightM: 40 } as const;

/**
 * The map camera part-way (t from 0 to 1, already eased) between two poses:
 * the eye along a straight line, arcing 40 m up in the middle when the flight
 * is longer than 300 m; bearing and roll the short way round; pitch and field
 * of view straight.
 */
export function interpolate(a: EyePose, b: EyePose, t: number): EyePose {
	const v = toLocal([a.lng, a.lat], [b.lng, b.lat, b.alt]);
	const ground = Math.hypot(v[0], v[1]);
	const [lng, lat] = fromLocal([a.lng, a.lat], [v[0] * t, v[1] * t, 0]);
	const arc = ground > ARC.minM ? ARC.heightM * Math.sin(Math.PI * t) : 0;
	return {
		lng,
		lat,
		alt: a.alt + (b.alt - a.alt) * t + arc,
		bearing: a.bearing + angleDiff(b.bearing, a.bearing) * t,
		pitch: a.pitch + (b.pitch - a.pitch) * t,
		roll: a.roll + angleDiff(b.roll, a.roll) * t,
		fov: a.fov + (b.fov - a.fov) * t
	};
}

/** The fade's scales (§14.6 step 10): 4° of turn, 8% of D of eye shift, 3° of roll, 0.15 of ln(fov ratio). */
export const FADE = { angleDeg: 4, shiftOfD: 0.08, rollDeg: 3, lnFov: 0.15 } as const;

/**
 * D for the fade: how far the camera looks to the ground along its axis,
 * `(alt − ground)/sin(tilt)`. A camera at or above the horizon counts as
 * looking at a 2° tilt, so D stays finite.
 */
export function axisDistance(pose: Pose, groundZ: number): number {
	return Math.max(1, pose.alt - groundZ) / Math.sin(Math.max(pose.tilt, 2) * D2R);
}

/**
 * How far the user has moved the map camera from the pose (§14.6 step 10):
 * `e = max(Δangle/4°, |eye shift|/(0.08·D), |Δroll|/3°, |ln(fov ratio)|/0.15)`.
 * 0 at the pose; the picture is gone at 1.
 */
export function deviation(now: EyePose, pose: EyePose, D: number): number {
	const a = viewDirection(now.bearing, now.pitch);
	const b = viewDirection(pose.bearing, pose.pitch);
	const angle = Math.acos(clamp(dot(a, b), -1, 1)) * R2D;
	const shift = metresBetween([pose.lng, pose.lat, pose.alt], [now.lng, now.lat, now.alt]);
	const roll = Math.abs(angleDiff(now.roll, pose.roll));
	const fov = Math.abs(Math.log(now.fov / pose.fov));
	return Math.max(angle / FADE.angleDeg, shift / (FADE.shiftOfD * D), roll / FADE.rollDeg, fov / FADE.lnFov);
}

/** The picture's opacity for a deviation and the slider (0–1): `clamp(1 − e) × slider`. */
export function fadeOpacity(e: number, slider: number): number {
	return clamp(1 - e, 0, 1) * clamp(slider, 0, 1);
}
