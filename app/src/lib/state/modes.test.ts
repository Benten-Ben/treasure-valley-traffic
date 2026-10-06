import { describe, expect, it, vi } from 'vitest';
import { Modes } from './modes.svelte.js';
import type { ViewManager, ViewSnapshot } from './view.svelte.js';

const snap = (zoom: number): ViewSnapshot => ({
	center: [-116.2, 43.6],
	zoom,
	bearing: 0,
	pitch: 0,
	roll: 0,
	fov: 36.87,
	padding: { top: 0, right: 0, bottom: 0, left: 0 },
	maxZoom: 22,
	maxPitch: 75,
	centerClampedToGround: true,
	exaggeration: 1.3,
	parts: {}
});

function fakeView() {
	let zoom = 14;
	let suspended = 0;
	return {
		snapshot: vi.fn(() => snap(zoom)),
		restore: vi.fn((s: ViewSnapshot) => void (zoom = s.zoom)),
		suspend: vi.fn(() => void suspended++),
		resume: vi.fn(() => void (suspended = Math.max(0, suspended - 1))),
		touch: vi.fn(),
		get suspended() {
			return suspended > 0;
		},
		setZoom: (z: number) => (zoom = z),
		get zoom() {
			return zoom;
		}
	};
}

describe('Modes', () => {
	it('starts in Explore', () => {
		const m = new Modes(fakeView() as unknown as ViewManager);
		expect(m.current).toBe('explore');
		expect(m.is('explore')).toBe(true);
		expect(m.depth).toBe(0);
	});

	it('enter pushes a snapshot and suspends the hash; leave restores it exactly and resumes', () => {
		const v = fakeView();
		const m = new Modes(v as unknown as ViewManager);
		m.enter('calibrate');
		expect(m.current).toBe('calibrate');
		expect(v.suspended).toBe(true);
		v.setZoom(19);
		const s = m.leave('calibrate');
		expect(s?.zoom).toBe(14);
		expect(v.restore).toHaveBeenCalledWith(snap(14));
		expect(v.zoom).toBe(14);
		expect(v.suspended).toBe(false);
		expect(v.touch).toHaveBeenCalled();
		expect(m.current).toBe('explore');
	});

	it('takes a given snapshot for a deep link with no view of its own', () => {
		const v = fakeView();
		const m = new Modes(v as unknown as ViewManager);
		m.enter('calibrate', snap(16));
		expect(v.snapshot).not.toHaveBeenCalled();
		m.leave('calibrate');
		expect(v.zoom).toBe(16);
	});

	it('nests, and leaving an outer mode leaves the inner ones too', () => {
		const v = fakeView();
		const m = new Modes(v as unknown as ViewManager);
		m.enter('look');
		v.setZoom(18);
		m.enter('calibrate');
		expect(m.current).toBe('calibrate');
		expect(m.depth).toBe(2);
		expect(m.snapshotOf('look')?.zoom).toBe(14);
		m.leave('look');
		expect(m.current).toBe('explore');
		expect(v.zoom).toBe(14);
		expect(v.suspended).toBe(false);
	});

	it('leaving a mode that is not active does nothing', () => {
		const v = fakeView();
		const m = new Modes(v as unknown as ViewManager);
		expect(m.leave('calibrate')).toBeNull();
		expect(v.restore).not.toHaveBeenCalled();
	});
});
