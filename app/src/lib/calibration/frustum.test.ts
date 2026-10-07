import { describe, expect, it } from 'vitest';
import {
	angleDiff,
	axisDistance,
	borderPixels,
	centreDistance,
	deviation,
	eyeOf,
	eyePose,
	fadeOpacity,
	focalPx,
	imageToScreen,
	interpolate,
	letterbox,
	mapFov,
	mercatorX,
	mercatorY,
	metresBetween,
	nearMetres,
	photoCrop,
	photoDistance,
	photoPlane,
	pixelRay,
	planeApex,
	planeCorners,
	pxPerMetre,
	rayPixel,
	viewCone,
	EARTH_RADIUS,
	TILE_SIZE,
	type EyePose,
	type Vec3
} from './frustum';
import { axes, barPx, fromLocal, pixelToGround, project, toLocal, type ImageSize, type LngLatZ, type Pose } from './solver';

// The four seeded cameras' shapes (app/scripts/seed-dev.ts): a key camera, one rolled, a low tilt and an HD frame.
const SD: ImageSize = { width: 768, height: 466 };
const HD: ImageSize = { width: 1920, height: 1166 };
const POSES: [string, Pose, ImageSize, number][] = [
	['key', { lon: -116.35476, lat: 43.61964, alt: 811.1, heading: 355, tilt: 20, roll: 0, vfov: 42 }, SD, 801.1],
	['roll −5', { lon: -116.20522, lat: 43.61215, alt: 828.87, heading: 150, tilt: 25, roll: -5, vfov: 45 }, SD, 820.87],
	['roll +5', { lon: -116.20522, lat: 43.61215, alt: 828.87, heading: 150, tilt: 25, roll: 5, vfov: 45 }, SD, 820.87],
	['low tilt', { lon: -116.28153, lat: 43.60513, alt: 834.91, heading: 268, tilt: 9, roll: 0, vfov: 30 }, SD, 823.91],
	['hd', { lon: -116.37459, lat: 43.59332, alt: 818.33, heading: 92, tilt: 16, roll: 0, vfov: 50 }, HD, 804.33]
];

/** A point `s` metres along a direction from the camera. */
function along(pose: Pose, dir: Vec3, s: number): LngLatZ {
	const n = Math.hypot(...dir);
	return fromLocal([pose.lon, pose.lat], [(dir[0] / n) * s, (dir[1] / n) * s, pose.alt + (dir[2] / n) * s]);
}

/** Every 32nd pixel of the image, plus its corners. */
function grid(size: ImageSize): [number, number][] {
	const out: [number, number][] = [];
	for (let y = 0; y <= size.height; y += Math.round(size.height / 9)) for (let x = 0; x <= size.width; x += Math.round(size.width / 11)) out.push([x, y]);
	out.push([0, 0], [size.width, 0], [size.width, size.height], [0, size.height]);
	return out;
}

describe('frustum: rays and pixels', () => {
	it.each(POSES)('a ray goes to its pixel and back within 0.01 px (%s)', (_name, pose, size) => {
		let worst = 0;
		for (const px of grid(size)) {
			const ray = pixelRay(pose, size, px);
			// Directly, and through a point on the ray (the solver's projection, in lon/lat).
			const back = rayPixel(pose, size, ray)!;
			worst = Math.max(worst, Math.hypot(back[0] - px[0], back[1] - px[1]));
			for (const s of [3, 40, 220]) {
				const q = project(pose, size, along(pose, ray, s))!;
				worst = Math.max(worst, Math.hypot(q[0] - px[0], q[1] - px[1]));
			}
		}
		expect(worst).toBeLessThan(0.01);
	});

	it('a direction behind the camera has no pixel', () => {
		const [, pose, size] = POSES[0];
		const [, , fwd] = axes(pose.heading, pose.tilt, pose.roll);
		expect(rayPixel(pose, size, [-fwd[0], -fwd[1], -fwd[2]])).toBeNull();
	});

	it('the axis goes through the image centre, and the focal length matches the field of view', () => {
		for (const [, pose, size] of POSES) {
			const c = rayPixel(pose, size, axes(pose.heading, pose.tilt, pose.roll)[2])!;
			expect(c[0]).toBeCloseTo(size.width / 2, 9);
			expect(c[1]).toBeCloseTo(size.height / 2, 9);
			const f = focalPx(pose.vfov, size.height);
			expect((2 * Math.atan(size.height / 2 / f) * 180) / Math.PI).toBeCloseTo(pose.vfov, 9);
		}
	});
});

describe('frustum: the view cone', () => {
	it('has 8 rays per edge, clockwise from the top-left, with the corners at 0, 8, 16 and 24', () => {
		const px = borderPixels(SD, 8);
		expect(px).toHaveLength(32);
		expect(px[0]).toEqual([0, 0]);
		expect(px[8]).toEqual([SD.width, 0]);
		expect(px[16]).toEqual([SD.width, SD.height]);
		expect(px[24]).toEqual([0, SD.height]);
	});

	it.each(POSES)('ends on the ground at the calibration height, or 120 m out above the horizon (%s)', (_name, pose, size, groundZ) => {
		const cone = viewCone(pose, size, groundZ);
		expect(cone.ends).toHaveLength(32);
		expect(cone.corners).toEqual([cone.ends[0], cone.ends[8], cone.ends[16], cone.ends[24]]);
		const border = borderPixels(size, 8);
		cone.ends.forEach((end, i) => {
			const local = toLocal([pose.lon, pose.lat], end);
			const ground = Math.hypot(local[0], local[1]);
			if (cone.onGround[i]) {
				expect(end[2]).toBeCloseTo(groundZ, 9);
				expect(ground).toBeLessThanOrEqual(250 + 1e-6);
				// Within the cut-off, the end is exactly where the border pixel's ray meets the ground.
				if (ground < 249.999) {
					const px = project(pose, size, end)!;
					expect(Math.hypot(px[0] - border[i][0], px[1] - border[i][1])).toBeLessThan(0.01);
					const g = pixelToGround(pose, size, border[i], groundZ)!;
					expect(metresBetween(g, end)).toBeLessThan(1e-3);
				}
			} else {
				expect(metresBetween([pose.lon, pose.lat, pose.alt], end)).toBeCloseTo(120, 6);
				// Still on its ray.
				const px = project(pose, size, end)!;
				expect(Math.hypot(px[0] - border[i][0], px[1] - border[i][1])).toBeLessThan(0.01);
			}
		});
	});

	it('the low-tilt camera sees sky along its top edge; a steep camera sees ground everywhere', () => {
		const low = viewCone(POSES[3][1], SD, POSES[3][3]);
		expect(low.onGround.slice(0, 8).every((g) => !g)).toBe(true);
		expect(low.onGround.slice(16, 24).every((g) => g)).toBe(true);
		const steep = viewCone({ ...POSES[0][1], tilt: 40 }, SD, POSES[0][3]);
		expect(steep.onGround.every((g) => g)).toBe(true);
	});
});

describe('frustum: the photo plane', () => {
	it.each(POSES)("the photo plane's corners project to the image corners (%s)", (_name, pose, size) => {
		for (const d of [0.5, 2, 2.3, 37]) {
			const plane = photoPlane(pose, size);
			expect(plane.cx).toBeCloseTo(0, 12);
			expect(plane.cy).toBeCloseTo(0, 12);
			expect(plane.ty).toBeCloseTo(Math.tan(((pose.vfov / 2) * Math.PI) / 180), 12);
			expect(plane.tx).toBeCloseTo((plane.ty * size.width) / size.height, 12);
			const want = [
				[0, 0],
				[size.width, 0],
				[size.width, size.height],
				[0, size.height]
			];
			planeCorners(pose, plane, d).forEach((c, i) => {
				const px = project(pose, size, c)!;
				expect(Math.hypot(px[0] - want[i][0], px[1] - want[i][1])).toBeLessThan(0.01);
			});
		}
	});

	it.each(POSES)("a cropped plane's corners project to the crop's corners, through the scene's apex (%s)", (_name, pose, size) => {
		for (const centred of [true, false]) {
			const crop = photoCrop(size, centred);
			const bar = barPx(size.width, size.height);
			expect(crop.y + crop.height).toBe(size.height - bar);
			expect(crop.y).toBe(centred ? bar : 0);
			const plane = photoPlane(pose, size, crop);
			if (centred) expect(Math.hypot(plane.cx, plane.cy)).toBeLessThan(1e-12);
			const d = 2.4;
			const corners = planeCorners(pose, plane, d);
			const want = [
				[crop.x, crop.y],
				[crop.x + crop.width, crop.y],
				[crop.x + crop.width, crop.y + crop.height],
				[crop.x, crop.y + crop.height]
			];
			corners.forEach((c, i) => {
				const px = project(pose, size, c)!;
				expect(Math.hypot(px[0] - want[i][0], px[1] - want[i][1])).toBeLessThan(0.01);
			});
			// The scene draws apex + d·(forward ± tx·right ± ty·down): with the moved apex, the same corners.
			const apex = planeApex(pose, plane, d);
			const local = toLocal([pose.lon, pose.lat], apex);
			[
				[-1, -1],
				[1, -1],
				[1, 1],
				[-1, 1]
			].forEach(([sx, sy], i) => {
				const v = [0, 1, 2].map((k) => (k === 2 ? apex[2] : local[k]) + d * (plane.forward[k] + sx * plane.tx * plane.right[k] + sy * plane.ty * plane.down[k]));
				const p = fromLocal([pose.lon, pose.lat], [v[0], v[1], v[2]]);
				expect(metresBetween(p, corners[i])).toBeLessThan(1e-6);
			});
		}
	});

	it('crops the 511 bar by its measured height', () => {
		expect(barPx(768, 466)).toBe(34);
		expect(barPx(1920, 1166)).toBe(86);
		// Not a 16:9 picture over a bar: 7.3% of the height.
		expect(barPx(704, 480)).toBe(35);
		expect(barPx(640, 360)).toBe(26);
	});
});

describe('frustum: look-through fitting', () => {
	it('letterboxes the picture at its aspect: h = min(0.92·H, 0.96·W·h/w)', () => {
		const tall = letterbox(1280, 800, SD);
		expect(tall.height).toBeCloseTo(736, 9);
		expect(tall.width / tall.height).toBeCloseTo(768 / 466, 9);
		expect(tall.x).toBeCloseTo((1280 - tall.width) / 2, 9);
		const narrow = letterbox(390, 844, SD);
		expect(narrow.width).toBeCloseTo(0.96 * 390, 9);
		expect(narrow.y).toBeCloseTo((844 - narrow.height) / 2, 9);
	});

	it.each(POSES)('with the map fov Vm, a ground point lands where its pixel does in the letterbox (%s)', (_name, pose, size, groundZ) => {
		const [W, H] = [1280, 800];
		const box = letterbox(W, H, size);
		const Vm = mapFov(pose.vfov, H, box.height);
		// The map camera at the pose with fov Vm on the whole canvas: a pinhole with the principal point at the centre.
		const fMap = focalPx(Vm, H);
		const [right, down, fwd] = axes(pose.heading, pose.tilt, pose.roll);
		for (const px of grid(size)) {
			const g = pixelToGround(pose, size, px, groundZ);
			if (!g) continue;
			const v = toLocal([pose.lon, pose.lat], g);
			const rel: Vec3 = [v[0], v[1], v[2] - pose.alt];
			const z = rel[0] * fwd[0] + rel[1] * fwd[1] + rel[2] * fwd[2];
			const screen = [W / 2 + (fMap * (rel[0] * right[0] + rel[1] * right[1] + rel[2] * right[2])) / z, H / 2 + (fMap * (rel[0] * down[0] + rel[1] * down[1] + rel[2] * down[2])) / z];
			const want = imageToScreen(px, size, box);
			expect(Math.hypot(screen[0] - want[0], screen[1] - want[1])).toBeLessThan(1e-6);
		}
	});
});

/** MapLibre 6.12's calculateCenterFromCameraLngLatAlt (mercator transform), for checking the readback. */
function centreFromEye(eye: LngLatZ, bearing: number, pitch: number, elevation: number, fov: number, height: number) {
	const D = Math.PI / 180;
	const dz = -Math.cos(pitch * D);
	const distanceToCenter = -(eye[2] - elevation) / dz;
	const x = Math.sin(pitch * D) * Math.sin(bearing * D);
	const y = -Math.sin(pitch * D) * Math.cos(bearing * D);
	const camX = mercatorX(eye[0]);
	const camY = mercatorY(eye[1]);
	const latOf = (my: number) => (360 / Math.PI) * Math.atan(Math.exp(((180 - my * 360) * Math.PI) / 180)) - 90;
	let metersPerMerc = 2 * Math.PI * EARTH_RADIUS * Math.cos(eye[1] * D);
	let cx = camX;
	let cy = camY;
	let dMerc = 0;
	for (let i = 0; i < 10; i++) {
		dMerc = distanceToCenter / metersPerMerc;
		cx = camX + x * dMerc;
		cy = camY + y * dMerc;
		metersPerMerc = 2 * Math.PI * EARTH_RADIUS * Math.cos(latOf(cy) * D);
	}
	const zoom = Math.log2(height / 2 / Math.tan((fov / 2) * D) / dMerc / TILE_SIZE);
	return { center: [cx * 360 - 180, latOf(cy)] as [number, number], zoom };
}

describe('frustum: reading the map camera back', () => {
	it.each(POSES)('eyeOf inverts MapLibre’s placement within a millimetre (%s)', (_name, pose, size, groundZ) => {
		const H = 800;
		const Vm = mapFov(pose.vfov, H, letterbox(1280, H, size).height);
		const e = eyePose(pose, Vm);
		const { center, zoom } = centreFromEye([pose.lon, pose.lat, pose.alt], e.bearing, e.pitch, groundZ, Vm, H);
		const eye = eyeOf({ center, elevation: groundZ, zoom, pitch: e.pitch, bearing: e.bearing, fov: Vm, height: H });
		expect(metresBetween(eye, [pose.lon, pose.lat, pose.alt])).toBeLessThan(1e-3);
		// The near plane, in metres: height/50 world px, so it grows with the eye-to-centre distance.
		const dist = centreDistance({ zoom, fov: Vm, height: H, center });
		expect(dist).toBeCloseTo((pose.alt - groundZ) / Math.sin((pose.tilt * Math.PI) / 180), 3);
		const near = nearMetres(H, zoom, center[1]);
		expect(near).toBeCloseTo((dist * Math.tan(((Vm / 2) * Math.PI) / 180)) / 25, 6);
		expect(photoDistance(near)).toBeGreaterThanOrEqual(2 * near);
		expect(photoDistance(near)).toBeGreaterThanOrEqual(2);
	});

	it("passes 2 m for a 12 m pole at a 5° tilt, so a plane at a fixed 2 m would be clipped (step 8's example)", () => {
		const pose: Pose = { lon: -116.3, lat: 43.6, alt: 812, heading: 0, tilt: 5, roll: 0, vfov: 42 };
		const H = 800;
		const Vm = mapFov(pose.vfov, H, letterbox(1280, H, SD).height);
		const { center, zoom } = centreFromEye([pose.lon, pose.lat, pose.alt], 0, 85, 800, Vm, H);
		const near = nearMetres(H, zoom, center[1]);
		expect(near).toBeGreaterThan(2);
		expect(near).toBeLessThan(2.6);
		expect(photoDistance(near)).toBeCloseTo(2 * near, 9);
	});

	it('pxPerMetre is MapLibre’s: 512 px tiles over the circumference at the latitude', () => {
		expect(pxPerMetre(0, 0)).toBeCloseTo(TILE_SIZE / (2 * Math.PI * EARTH_RADIUS), 15);
		expect(pxPerMetre(16, 60) / pxPerMetre(16, 0)).toBeCloseTo(2, 9);
	});
});

describe('frustum: flights and the fade', () => {
	const a: EyePose = { lng: -116.2, lat: 43.6, alt: 1100, bearing: 170, pitch: 50, roll: 0, fov: 36.87 };
	const b: EyePose = { lng: -116.201, lat: 43.6005, alt: 830, bearing: -170, pitch: 80, roll: -5, fov: 45 };

	it('starts and ends exactly at its poses, turning the short way round', () => {
		expect(interpolate(a, b, 0)).toEqual({ ...a });
		const end = interpolate(a, b, 1);
		expect(end.lng).toBeCloseTo(b.lng, 9);
		expect(end.lat).toBeCloseTo(b.lat, 9);
		expect(end.alt).toBeCloseTo(b.alt, 9);
		expect(angleDiff(end.bearing, b.bearing)).toBeCloseTo(0, 9);
		expect(end.pitch).toBeCloseTo(b.pitch, 9);
		expect(end.roll).toBeCloseTo(b.roll, 9);
		expect(end.fov).toBeCloseTo(b.fov, 9);
		// 170° → −170° goes through 180, not through 0.
		expect(Math.abs(angleDiff(interpolate(a, b, 0.5).bearing, 180))).toBeLessThan(1e-9);
	});

	it('arcs 40 m up only on flights longer than 300 m', () => {
		const short = interpolate(a, b, 0.5);
		expect(short.alt).toBeCloseTo((a.alt + b.alt) / 2, 9);
		const far: EyePose = { ...b, lng: -116.21 };
		const long = interpolate(a, far, 0.5);
		expect(long.alt).toBeCloseTo((a.alt + far.alt) / 2 + 40, 9);
	});

	it('the deviation is 0 at the pose and reaches 1 at 4°, 8% of D, 3° of roll or a 0.15 fov ratio', () => {
		const pose: Pose = { lon: -116.35476, lat: 43.61964, alt: 811.1, heading: 355, tilt: 20, roll: 0, vfov: 42 };
		const e = eyePose(pose, 45);
		const D = axisDistance(pose, 801.1);
		expect(D).toBeCloseTo(10 / Math.sin((20 * Math.PI) / 180), 6);
		expect(deviation(e, e, D)).toBeCloseTo(0, 6);
		expect(deviation({ ...e, bearing: e.bearing + 4 }, e, D)).toBeCloseTo(4 * Math.cos((20 * Math.PI) / 180) / 4, 2);
		expect(deviation({ ...e, pitch: e.pitch - 4 }, e, D)).toBeCloseTo(1, 6);
		const [lng, lat] = fromLocal([e.lng, e.lat], [0.08 * D, 0, 0]);
		expect(deviation({ ...e, lng, lat }, e, D)).toBeCloseTo(1, 4);
		expect(deviation({ ...e, roll: 3 }, e, D)).toBeCloseTo(1, 6);
		expect(deviation({ ...e, fov: e.fov * Math.exp(0.15) }, e, D)).toBeCloseTo(1, 6);
		expect(fadeOpacity(0, 0.5)).toBe(0.5);
		expect(fadeOpacity(0.25, 1)).toBeCloseTo(0.75, 9);
		expect(fadeOpacity(3, 1)).toBe(0);
	});
});
