/**
 * Live camera images (docs/14 §14.6, "Live images"; §14.8 "APIs"). Built by
 * WP11, shown by WP12–WP14 and WP16.
 *
 * - GET /api/cameras/live?views=1,2,… (at most 12): the newest frame of each
 *   view, from the capture archive or the on-demand 511 fetcher. `no-store`.
 * - GET /api/cameras/status: capture state of every recorded view; memoized 15 s.
 * - POST /api/views/[id]/frame: keep the frame on screen as a calibration
 *   reference.
 *
 * Age is "seen" time: when our server first got that picture. The UI says
 * "seen", never "taken".
 *
 * Frozen contract (§14.10): only the wave integrator changes it.
 */
export const LIVE_CONTRACT = 1;

/** archive: the capture services' newest frame; 511: fetched on demand; none: nothing to show. */
export type LiveSource = 'archive' | '511' | 'none';

/** Which freshness thresholds apply (§14.6): key and on-demand ≤ 3/10 min; road weather ≤ 30/60 min. */
export type CadenceClass = 'key' | 'on_demand' | 'road_weather';

/**
 * - ok: a frame is available;
 * - waiting: being fetched, no frame yet;
 * - blocked: robots.txt doesn't allow it right now (5xx and network errors count);
 * - capped: the on-demand cap (12 images per 10 minutes) is reached;
 * - disabled: CAMERA_IMAGES_ENABLED is off;
 * - no_image: the view has no 511 image;
 * - error: something else failed (see `reason`).
 */
export type LiveState = 'ok' | 'waiting' | 'blocked' | 'capped' | 'disabled' | 'no_image' | 'error';

/** An archive frame's identity, for "Use this frame" (POST /api/views/[id]/frame). */
export interface ArchiveFrameRef {
	image: number;
	/** Local (America/Boise) day folder, YYYY-MM-DD. */
	day: string;
	/** File stamp, e.g. '20261006T151240Z'. */
	stamp: string;
}

export interface LiveFrame {
	/** /camera-frames/<image>/<day>/<stamp>.jpg or /api/views/<id>/live/<sha> (immutable). */
	url: string;
	/** When our server first got this picture, epoch s. */
	firstSeenAt: number;
	width: number;
	height: number;
	/** sha256 of the bytes, hex. */
	sha: string;
	/** Set for archive frames. */
	archive?: ArchiveFrameRef;
}

export interface LiveView {
	viewId: number;
	imageId: number | null;
	source: LiveSource;
	frame: LiveFrame | null;
	cadence: CadenceClass;
	/** Expected seconds between new pictures (about 50–60 for key and on-demand, 600 for road weather). */
	cadenceS: number;
	state: LiveState;
	/** Human-readable detail: for blocked, capped and error, and also given for waiting, no_image and disabled. */
	reason?: string;
}

export interface CamerasLive {
	contract: typeof LIVE_CONTRACT;
	/** Server time, epoch s. */
	now: number;
	/** Keyed by view id. Views not in core.camera_view are left out. */
	views: Record<string, LiveView>;
}

/** One capture service's status file (cameras/status/<tag>.json), as the app reads it. */
export interface CaptureService {
	tag: string;
	cadenceS: number;
	imageIds: number[];
	/** Last heartbeat, epoch s. */
	heartbeat: number;
	pausedLowDisk: boolean;
	/** Heartbeat within 3 cadences. */
	alive: boolean;
}

export interface CamerasStatus {
	contract: typeof LIVE_CONTRACT;
	now: number;
	/** CAMERA_IMAGES_ENABLED. */
	enabled: boolean;
	services: CaptureService[];
	/** Keyed by view id: every view a capture service records. */
	recorded: Record<string, { tag: string; cadence: CadenceClass; lastSeenAt: number | null }>;
}

/**
 * POST /api/views/[id]/frame body. `{sha}` for an on-demand 511 frame held in
 * memory, an archive reference, or no body for "the newest frame" (today's
 * calibrator and /v1; the seeded fixture in fixture mode). 410 when those
 * bytes are gone.
 */
export type SaveFrameRequest = { sha: string } | ArchiveFrameRef | Record<string, never>;

export interface SavedFrame {
	/** Path relative to FRAMES_DIR, stored as the calibration's reference_frame. */
	frame: string;
	/** /frames/<frame> */
	url: string;
	width: number;
	height: number;
	/** ISO time the frame was saved. */
	capturedAt: string;
}
