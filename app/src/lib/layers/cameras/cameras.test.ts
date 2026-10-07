import { describe, expect, it } from 'vitest';
import { ALL_LAYERS, cameraLayers, CAMERA_LAYERS, checkImage, FOOTPRINT_MINZOOM, metres, movedLines, notchImage, type Calibration } from './cameras.js';
import { cameraIdOf, cameraKey, flyTarget, landBeside, landing, paddedCentre } from './place.js';
import { clampZoom, IDENTITY, MAX_ZOOM, panBy, wheelFactor, zoomAt } from './zoom.js';

const cal = (id: number, cameraId: number, lon: number, lat: number): Calibration => ({
	calibrationId: id,
	viewId: id,
	cameraId,
	pose: { lon, lat, alt: 810, heading: 0, tilt: 20, roll: 0, vfov: 40 },
	size: { width: 768, height: 466 },
	groundZ: 800,
	frame: 'view-1/x.jpg'
});

describe('camera icons and footprints', () => {
	it('lists every layer, with icons in points and footprints from z14 in footprints', () => {
		const layers = cameraLayers();
		expect(layers.map((l) => l.layer.id).sort()).toEqual([...ALL_LAYERS].sort());
		for (const id of CAMERA_LAYERS) expect(layers.find((l) => l.layer.id === id)?.slot).toBe('points');
		for (const id of ['cones-fill', 'cones-line']) {
			const l = layers.find((x) => x.layer.id === id)!;
			expect(l.slot).toBe('footprints');
			expect(l.layer.minzoom).toBe(FOOTPRINT_MINZOOM);
		}
		// Fill 0.10 and line 0.8, 0.22 and 1.0 on hover (feature-state).
		const fill = layers.find((l) => l.layer.id === 'cones-fill')!.layer as { paint: Record<string, unknown> };
		expect(JSON.stringify(fill.paint['fill-opacity'])).toBe(JSON.stringify(['case', ['boolean', ['feature-state', 'hover'], false], 0.22, 0.1]));
		const line = layers.find((l) => l.layer.id === 'cones-line')!.layer as { paint: Record<string, unknown> };
		expect(JSON.stringify(line.paint['line-opacity'])).toBe(JSON.stringify(['case', ['boolean', ['feature-state', 'hover'], false], 1, 0.8]));
		// Every layer starts hidden.
		for (const l of layers) expect((l.layer as { layout?: { visibility?: string } }).layout?.visibility).toBe('none');
	});

	it('draws a ground line only where the solved position is more than 3 m from ACHD’s point', () => {
		const pole: [number, number] = [-116.2, 43.6];
		const poles = new Map([
			[1, pole],
			[2, pole]
		]);
		const near = cal(10, 1, pole[0] + 2 / (111_320 * Math.cos((43.6 * Math.PI) / 180)), pole[1]);
		const far = cal(11, 2, pole[0], pole[1] + 8 / 111_320);
		const fc = movedLines(poles, [near, far, cal(12, 3, 0, 0)]);
		expect(fc.features.map((f) => f.id)).toEqual([11]);
		expect((fc.features[0].properties as { metres: number }).metres).toBeCloseTo(8, 1);
		expect(metres(pole, [near.pose.lon, near.pose.lat])).toBeCloseTo(2, 2);
	});

	it('draws the recorded notch: ink inside a cream edge, with clear corners', () => {
		const n = notchImage(2);
		expect([n.width, n.height]).toEqual([14, 10]);
		expect(n.data.length).toBe(14 * 10 * 4);
		const px = (x: number, y: number) => [...n.data.subarray((y * n.width + x) * 4, (y * n.width + x) * 4 + 4)];
		expect(px(0, 0)[3]).toBe(0);
		expect(px(7, 5)).toEqual([0x2b, 0x2a, 0x33, 255]);
		expect(px(7, 0)).toEqual([0xff, 0xfb, 0xf4, 255]);
	});

	it('draws the calibrated check as an image (the basemap glyphs have no ✓): cream on clear', () => {
		const c = checkImage(2);
		expect([c.width, c.height]).toEqual([20, 20]);
		const alpha = (x: number, y: number) => c.data[(y * 20 + x) * 4 + 3];
		// On the stroke's corner (4.3, 7.3 CSS px), clear at the top left.
		expect(alpha(8, 14)).toBe(255);
		expect([...c.data.subarray((14 * 20 + 8) * 4, (14 * 20 + 8) * 4 + 3)]).toEqual([0xff, 0xfb, 0xf4]);
		expect(alpha(0, 0)).toBe(0);
		const layer = cameraLayers().find((l) => l.layer.id === 'cameras-calibrated-check')!.layer as { layout: Record<string, unknown> };
		expect(layer.layout['icon-image']).toBe('camera-check');
	});
});

describe('camera clicks', () => {
	it('fly to zoom 18 and pitch 50, keeping the bearing', () => {
		expect(flyTarget([-116.3, 43.6], -12)).toMatchObject({ center: [-116.3, 43.6], zoom: 18, pitch: 50, bearing: -12 });
	});

	it('open the window beside where the camera lands: the middle of the padded map', () => {
		expect(paddedCentre({ left: 0, top: 0, width: 1280, height: 800 }, { top: 0, right: 0, bottom: 0, left: 0 })).toEqual({ x: 640, y: 400 });
		expect(paddedCentre({ left: 0, top: 0, width: 1280, height: 800 }, { left: 312, right: 392 })).toEqual({ x: 600, y: 400 });
	});

	it('land the camera where its window fits between the legend and inspect columns', () => {
		const box = { left: 0, top: 0, width: 1280, height: 800 };
		// Free middle 312…888: the camera at 388, its 400 px window at 412…812.
		expect(landing(box, 400, 'desktop')).toEqual({ x: 388, y: 400 });
		expect(landing({ ...box, width: 1024 }, 400, 'desktop')).toBeNull();
		expect(landing({ ...box, width: 800 }, 400, 'tablet')).toBeNull();
		expect(landing({ left: 0, top: 0, width: 390, height: 844 }, 400, 'phone')).toEqual({ x: 195, y: 228 });
	});

	it('land a camera whose window is open 24 px left of it, or right when the left has no room', () => {
		const box = { left: 0, top: 0, width: 1280, height: 800 };
		expect(landBeside({ x: 412, y: 200, w: 400, h: 400 }, box)).toEqual({ x: 388, y: 400 });
		expect(landBeside({ x: 20, y: 200, w: 400, h: 400 }, box)).toEqual({ x: 444, y: 400 });
		expect(landBeside({ x: 412, y: 0, w: 400, h: 60 }, box).y).toBe(90);
	});

	it('key windows by camera', () => {
		expect(cameraKey(59)).toBe('camera:59');
		expect(cameraIdOf('camera:59')).toBe(59);
		expect(cameraIdOf('test:1')).toBeNull();
	});
});

describe('zoom and pan in the picture', () => {
	const W = 400;
	const H = 243;
	it('zooms about the pointer, up to 4×, and never past the picture’s edges', () => {
		const z = zoomAt(IDENTITY, 2, 100, 50, W, H);
		expect(z.s).toBe(2);
		// The point under the pointer stays put: (100 − x) / s is the same picture point as before.
		expect((100 - z.x) / z.s).toBeCloseTo(100, 6);
		expect((50 - z.y) / z.s).toBeCloseTo(50, 6);
		expect(zoomAt(z, 10, 0, 0, W, H).s).toBe(MAX_ZOOM);
		expect(zoomAt(z, 0.1, 0, 0, W, H)).toEqual(IDENTITY);
	});

	it('pans within the picture', () => {
		const z = zoomAt(IDENTITY, 2, 0, 0, W, H);
		expect(panBy(z, 50, 50, W, H)).toEqual({ s: 2, x: 0, y: 0 });
		const far = panBy(z, -10_000, -10_000, W, H);
		expect(far).toEqual({ s: 2, x: -W, y: -H });
		expect(clampZoom({ s: 1, x: -20, y: 5 }, W, H)).toEqual(IDENTITY);
	});

	it('turns wheel notches into steps', () => {
		expect(wheelFactor(-100)).toBeCloseTo(1.25, 6);
		expect(wheelFactor(100)).toBeCloseTo(0.8, 6);
	});
});
