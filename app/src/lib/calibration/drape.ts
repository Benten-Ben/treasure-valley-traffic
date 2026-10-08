/**
 * Drape a calibrated camera frame onto the ground (projecting it onto the
 * ground plane): the calibrator's check (docs/14 §14.6), no longer drawn on
 * the main map. For each pixel of a small north-up raster around the
 * camera, find where that ground point appears in the frame and sample it.
 *
 * Only the road surface lands in the right place: anything above it (cars,
 * poles, buildings) is smeared away from the camera, and detail thins with
 * distance, so the drape fades out toward maxDistance.
 */
import { barPx, fromLocal, project, toLocal, type ImageSize, type Pose } from './solver';

export interface Drape {
	url: string; // PNG data URL with transparency
	coordinates: [[number, number], [number, number], [number, number], [number, number]]; // NW, NE, SE, SW
}

export function drape(
	pose: Pose,
	size: ImageSize,
	pixels: ImageData,
	groundZ: number,
	footprintRing: [number, number][],
	{ maxDistance = 200, metersPerPixel = 0.25, fadeFrom = 0.6 } = {}
): Drape | null {
	const origin: [number, number] = [pose.lon, pose.lat];
	const local = footprintRing.map((p) => toLocal(origin, [p[0], p[1], groundZ]));
	const minE = Math.min(...local.map((v) => v[0])), maxE = Math.max(...local.map((v) => v[0]));
	const minN = Math.min(...local.map((v) => v[1])), maxN = Math.max(...local.map((v) => v[1]));
	const w = Math.min(2048, Math.ceil((maxE - minE) / metersPerPixel));
	const h = Math.min(2048, Math.ceil((maxN - minN) / metersPerPixel));
	if (w < 2 || h < 2) return null;
	const stepE = (maxE - minE) / w, stepN = (maxN - minN) / h;

	const canvas = document.createElement('canvas');
	canvas.width = w;
	canvas.height = h;
	const ctx = canvas.getContext('2d')!;
	const out = ctx.createImageData(w, h);
	const src = pixels.data, sw = pixels.width, sh = pixels.height;
	// The bottom timestamp bar (its height worked out per frame: the HD frames' is
	// about 86 px, not 36) and anything above the horizon aren't ground.
	const usableBottom = sh - (barPx(size.width, size.height) * sh) / size.height;

	for (let j = 0; j < h; j++) {
		const n = maxN - (j + 0.5) * stepN;
		for (let i = 0; i < w; i++) {
			const e = minE + (i + 0.5) * stepE;
			const dist = Math.hypot(e, n);
			if (dist > maxDistance) continue;
			const g = fromLocal(origin, [e, n, groundZ]);
			const q = project(pose, size, g);
			if (!q) continue;
			const x = (q[0] * sw) / size.width, y = (q[1] * sh) / size.height;
			if (x < 0 || y < 0 || x >= sw - 1 || y >= usableBottom) continue;
			// Bilinear sample.
			const x0 = Math.floor(x), y0 = Math.floor(y), fx = x - x0, fy = y - y0;
			const k00 = (y0 * sw + x0) * 4, k10 = k00 + 4, k01 = k00 + sw * 4, k11 = k01 + 4;
			const o = (j * w + i) * 4;
			for (let c = 0; c < 3; c++) {
				out.data[o + c] =
					src[k00 + c] * (1 - fx) * (1 - fy) + src[k10 + c] * fx * (1 - fy) +
					src[k01 + c] * (1 - fx) * fy + src[k11 + c] * fx * fy;
			}
			const fade = dist < maxDistance * fadeFrom ? 1 : 1 - (dist - maxDistance * fadeFrom) / (maxDistance * (1 - fadeFrom));
			out.data[o + 3] = Math.round(235 * fade);
		}
	}
	ctx.putImageData(out, 0, 0);
	const nw = fromLocal(origin, [minE, maxN, groundZ]), se = fromLocal(origin, [maxE, minN, groundZ]);
	return {
		url: canvas.toDataURL('image/png'),
		coordinates: [[nw[0], nw[1]], [se[0], nw[1]], [se[0], se[1]], [nw[0], se[1]]]
	};
}

/** Load an image URL (same origin) into ImageData. */
export async function imageData(url: string): Promise<ImageData> {
	const img = new Image();
	img.src = url;
	await img.decode();
	const c = document.createElement('canvas');
	c.width = img.naturalWidth;
	c.height = img.naturalHeight;
	const ctx = c.getContext('2d')!;
	ctx.drawImage(img, 0, 0);
	return ctx.getImageData(0, 0, c.width, c.height);
}
