import type { Pair, Pose } from '#lib/calibration/solver.js';

/**
 * What `GET /api/cameras/[id]` and `GET /api/cameras/views` answer (WP12;
 * docs/14 §14.8 "APIs"). Both are `no-cache` with an ETag.
 */
export interface CameraCalibration {
	id: number;
	pose: Pose;
	imageWidth: number;
	imageHeight: number;
	pairs: Pair[];
	rms: number | null;
	/** Reference frame, relative to FRAMES_DIR (served at /frames/…). */
	frame: string | null;
	createdAt: string;
}

export interface CameraDetailView {
	id: number;
	imageId: number | null;
	status: string | null;
	direction: string | null;
	description: string | null;
	sortOrder: number;
	calibration: CameraCalibration | null;
}

export interface CameraDetail {
	id: number;
	name: string;
	achdCamId: number | null;
	active: boolean;
	/** ACHD's point for the camera, [lon, lat]. */
	pole: [number, number];
	views: CameraDetailView[];
}

/** One row of `GET /api/cameras/views`. */
export interface CameraViewRow {
	id: number;
	cameraId: number;
	imageId: number | null;
	sortOrder: number;
	direction: string | null;
}

/** Fetch a camera's detail (revalidated each time: `no-cache` with an ETag). */
export async function fetchCamera(id: number, signal?: AbortSignal): Promise<CameraDetail> {
	const res = await fetch(`/api/cameras/${id}`, { signal });
	if (!res.ok) throw new Error((await res.json().catch(() => null))?.message ?? `HTTP ${res.status}`);
	return res.json();
}

/** A short label for a view: its direction, or "View n". */
export function viewLabel(v: Pick<CameraDetailView, 'direction' | 'description'>, i: number): string {
	return v.direction?.trim() || `View ${i + 1}`;
}
