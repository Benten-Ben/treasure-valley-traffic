/**
 * Camera frames for the app (docs/14 §14.6 "Live images", §14.8 "APIs"):
 *
 * - **Live images** (`GET /api/cameras/live`, `/camera-frames/…`,
 *   `/api/views/[id]/live/[sha]`, `GET /api/cameras/status`): recorded views
 *   from the capture archive's newest frame (archive.ts), everything else
 *   from the on-demand 511 fetcher (live511.ts). All of it is behind
 *   CAMERA_IMAGES_ENABLED, off unless set: when it's off, these answer
 *   "disabled" or 404 and touch neither the archive nor 511.
 * - **Reference frames** for calibration (`POST /api/views/[id]/frame`,
 *   `/frames/…`): "Use this frame" copies exactly the bytes that were shown
 *   (an in-memory sha, or an archive frame) into FRAMES_DIR, or answers 410
 *   when they're gone. With no body it keeps the newest frame, as the /v1
 *   calibrator does.
 * - **Fixture mode** (TVT_FRAME_SOURCE=fixture): seeded frames from
 *   FRAMES_DIR/_fixture stand in for 511, in the no-body capture and in the
 *   on-demand fetcher, so tests and build agents never reach 511.
 *
 * Nothing is written to FRAMES_DIR except a frame chosen for calibration.
 */
import { error } from '@sveltejs/kit';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, normalize, resolve, sep } from 'node:path';
import { CAMERA_IMAGES_ENABLED, FRAMES_DIR, TVT_ARCHIVE, TVT_FRAME_SOURCE } from '$app/env/private';
import { db } from '#lib/server/db.js';
import { Archive, KEY_CADENCE_S, cadenceClass, jpegSize, type ArchiveFrame } from './archive.js';
import { LiveFetcher, imageUrl, type MemFrame } from './live511.js';
import { RobotsCache, USER_AGENT } from './robots.js';
import {
	LIVE_CONTRACT,
	type ArchiveFrameRef,
	type CamerasLive,
	type CamerasStatus,
	type LiveFrame,
	type LiveView,
	type SavedFrame
} from '#lib/contracts/live.js';

export { imageUrl, jpegSize };

const root = () => resolve(FRAMES_DIR);

/** At most this many views per /api/cameras/live request. */
export const MAX_LIVE_VIEWS = 12;
/** 511 republishes each image about every 59 s; we ask at most every 55 s. */
export const ON_DEMAND_CADENCE_S = 60;
/** The first frame for calibration comes from the archive only if seen this recently (§14.6). */
export const ARCHIVE_FRESH_FOR_CALIBRATION_S = 120;
const VIEWS_TTL_MS = 60_000;
const STATUS_TTL_MS = 15_000;
const FRAME_CACHE = 'private, max-age=31536000, immutable';
const OFF = 'Live camera images are off (CAMERA_IMAGES_ENABLED)';

/** CAMERA_IMAGES_ENABLED: off unless set. */
export const imagesEnabled = () => CAMERA_IMAGES_ENABLED === true;
const fixtureMode = () => TVT_FRAME_SOURCE === 'fixture';

/** Folder of seeded frames used in fixture mode (written by `npm run seed`). */
export const FIXTURE_DIR = '_fixture';

/**
 * Fixture mode (TVT_FRAME_SOURCE=fixture): a seeded frame instead of 511, so
 * tests and build agents never reach 511. Looks for view-<id>.jpg, then
 * image-<imageId>.jpg, then default.jpg in FRAMES_DIR/_fixture.
 */
async function fixtureFrame(viewId: number, imageId: number): Promise<Uint8Array> {
	for (const name of [`view-${viewId}.jpg`, `image-${imageId}.jpg`, 'default.jpg']) {
		try {
			return new Uint8Array(await readFile(join(root(), FIXTURE_DIR, name)));
		} catch {
			/* try the next one */
		}
	}
	error(503, `Fixture mode (TVT_FRAME_SOURCE=fixture) has no seeded frame in ${FIXTURE_DIR}/: run npm run seed`);
}

/** One request to 511 Idaho for an image's current picture, with our User-Agent. */
async function fetch511(imageId: number): Promise<Uint8Array> {
	const res = await fetch(imageUrl(imageId), { headers: { 'User-Agent': USER_AGENT }, signal: AbortSignal.timeout(20_000) });
	if (!res.ok) throw new Error(`511 Idaho answered ${res.status}`);
	return new Uint8Array(await res.arrayBuffer());
}

// ---------------------------------------------------------------------------
// The live-image services, created on first use.

let clock: () => number = Date.now;
let archiveInst: Archive | undefined;
let fetcherInst: LiveFetcher | undefined;
let viewsMemo: { at: number; byView: Map<number, number | null>; byImage: Map<number, number> } | undefined;
let statusMemo: { at: number; value: CamerasStatus } | undefined;

export function archive(): Archive {
	return (archiveInst ??= new Archive({ root: TVT_ARCHIVE }));
}

export function fetcher(): LiveFetcher {
	if (!fetcherInst) {
		const robots = new RobotsCache();
		fetcherInst = fixtureMode()
			? new LiveFetcher({ fetchImage: (image, viewId) => fixtureFrame(viewId, image), robots: null, now: () => clock() })
			: new LiveFetcher({
					fetchImage: (image) => fetch511(image),
					robots: (url) => robots.check(url),
					now: () => clock(),
					log: (m) => console.warn(`live511: ${m}`)
				});
	}
	return fetcherInst;
}

/** Tests: start over, optionally with a clock, archive or fetcher of their own. */
export function resetLive(over: { now?: () => number; archive?: Archive; fetcher?: LiveFetcher } = {}) {
	fetcherInst?.stop();
	clock = over.now ?? Date.now;
	archiveInst = over.archive;
	fetcherInst = over.fetcher;
	viewsMemo = undefined;
	statusMemo = undefined;
}

/** View id ↔ 511 image id for every row in core.camera_view, reused for a minute. */
export async function viewIndex(now = clock()) {
	if (viewsMemo && now - viewsMemo.at < VIEWS_TTL_MS) return viewsMemo;
	const rows = await db()`select id, image_id from core.camera_view`;
	const byView = new Map<number, number | null>();
	const byImage = new Map<number, number>();
	for (const r of rows) {
		const image = r.image_id === null || r.image_id === undefined ? null : Number(r.image_id);
		byView.set(Number(r.id), image);
		if (image !== null) byImage.set(image, Number(r.id));
	}
	viewsMemo = { at: now, byView, byImage };
	return viewsMemo;
}

/** `?views=1,2,…`: 1 to 12 distinct positive view ids; anything else is a 400. */
export function parseViews(raw: string | null): number[] {
	if (!raw) error(400, `Name the views: ?views=1,2,… (at most ${MAX_LIVE_VIEWS})`);
	const ids = [...new Set(raw.split(',').map((s) => s.trim()))];
	if (!ids.every((s) => /^\d{1,12}$/.test(s) && Number(s) > 0)) error(400, 'Views are positive whole numbers, comma-separated');
	if (ids.length > MAX_LIVE_VIEWS) error(400, `At most ${MAX_LIVE_VIEWS} views per request`);
	return ids.map(Number);
}

const archiveUrl = (f: ArchiveFrameRef) => `/camera-frames/${f.image}/${f.day}/${f.stamp}.jpg`;

function fromArchive(f: ArchiveFrame): LiveFrame {
	return {
		url: archiveUrl(f),
		firstSeenAt: f.firstSeenAt,
		width: f.width,
		height: f.height,
		sha: f.sha,
		archive: { image: f.image, day: f.day, stamp: f.stamp }
	};
}

function fromMemory(viewId: number, f: MemFrame): LiveFrame {
	return { url: `/api/views/${viewId}/live/${f.sha}`, firstSeenAt: f.firstSeenAt, width: f.width, height: f.height, sha: f.sha };
}

/** GET /api/cameras/live: the newest frame of each view. Views not in core.camera_view are left out. */
export async function liveViews(ids: number[]): Promise<CamerasLive> {
	const now = clock();
	const views: Record<string, LiveView> = {};
	if (!imagesEnabled()) {
		// Off: nothing is looked up, read or fetched.
		for (const id of ids) {
			views[id] = {
				viewId: id,
				imageId: null,
				source: 'none',
				frame: null,
				cadence: 'on_demand',
				cadenceS: ON_DEMAND_CADENCE_S,
				state: 'disabled',
				reason: OFF
			};
		}
		return { contract: LIVE_CONTRACT, now: now / 1000, views };
	}
	const { byView } = await viewIndex(now);
	const services = await archive().services(now);
	const serviceOf = new Map<number, { cadenceS: number }>();
	for (const s of services) for (const image of s.imageIds) if (!serviceOf.has(image)) serviceOf.set(image, s);

	await Promise.all(
		ids.map(async (id) => {
			if (!byView.has(id)) return;
			const image = byView.get(id) ?? null;
			if (image === null) {
				views[id] = {
					viewId: id,
					imageId: null,
					source: 'none',
					frame: null,
					cadence: 'on_demand',
					cadenceS: ON_DEMAND_CADENCE_S,
					state: 'no_image',
					reason: 'Not on 511 Idaho'
				};
				return;
			}
			const service = serviceOf.get(image);
			const rec = await archive().newest(image, now);
			if (rec.recorded || service) {
				// Recorded: the capture archive's newest frame. Never fetched from 511 here.
				const cadenceS = service?.cadenceS ?? KEY_CADENCE_S;
				views[id] = {
					viewId: id,
					imageId: image,
					source: 'archive',
					frame: rec.frame && fromArchive(rec.frame),
					cadence: cadenceClass(cadenceS),
					cadenceS,
					state: rec.frame ? 'ok' : 'waiting',
					...(rec.frame ? {} : { reason: 'No picture recorded today or yesterday yet' })
				};
				return;
			}
			const o = await fetcher().request(image, id);
			views[id] = {
				viewId: id,
				imageId: image,
				source: '511',
				frame: o.frame && fromMemory(id, o.frame),
				cadence: 'on_demand',
				cadenceS: ON_DEMAND_CADENCE_S,
				state: o.state,
				...(o.reason ? { reason: o.reason } : {})
			};
		})
	);
	return { contract: LIVE_CONTRACT, now: now / 1000, views };
}

/** GET /api/cameras/status: capture state of every recorded view, reused for 15 s. */
export async function cameraStatus(): Promise<CamerasStatus> {
	const now = clock();
	if (!imagesEnabled()) return { contract: LIVE_CONTRACT, now: now / 1000, enabled: false, services: [], recorded: {} };
	if (statusMemo && now - statusMemo.at < STATUS_TTL_MS) return statusMemo.value;
	const a = archive();
	const services = await a.services(now);
	const { byImage } = await viewIndex(now);
	const recordedBy = new Map<number, { tag: string; cadenceS: number }>();
	for (const s of services) for (const image of s.imageIds) if (!recordedBy.has(image)) recordedBy.set(image, s);
	// Images in the archive that no status file names (capture from before status files, or a missing file).
	for (const image of await a.images(now)) {
		if (!recordedBy.has(image) && byImage.has(image) && (await a.newest(image, now)).recorded)
			recordedBy.set(image, { tag: 'archive', cadenceS: KEY_CADENCE_S });
	}
	const recorded: CamerasStatus['recorded'] = {};
	await Promise.all(
		[...recordedBy].map(async ([image, s]) => {
			const view = byImage.get(image);
			if (view === undefined) return;
			const { frame } = await a.newest(image, now);
			recorded[view] = { tag: s.tag, cadence: cadenceClass(s.cadenceS), lastSeenAt: frame?.firstSeenAt ?? null };
		})
	);
	const value: CamerasStatus = { contract: LIVE_CONTRACT, now: now / 1000, enabled: true, services, recorded };
	statusMemo = { at: now, value };
	return value;
}

/** If-None-Match against one strong ETag (weak comparison, as RFC 9110 asks for If-None-Match). */
export function etagMatches(header: string | null, etag: string): boolean {
	if (!header) return false;
	if (header.trim() === '*') return true;
	return header.split(',').some((t) => t.trim().replace(/^W\//, '') === etag);
}

function frameResponse(bytes: Uint8Array | null, etag: string): Response {
	const headers: Record<string, string> = { 'Cache-Control': FRAME_CACHE, ETag: etag };
	if (!bytes) return new Response(null, { status: 304, headers });
	return new Response(bytes as Uint8Array<ArrayBuffer>, {
		headers: { ...headers, 'Content-Type': 'image/jpeg', 'Content-Length': String(bytes.length) }
	});
}

/** GET /camera-frames/<image>/<day>/<stamp>.jpg: an archive frame. They never change once written. */
export async function serveArchiveFrame(path: string, ifNoneMatch: string | null): Promise<Response> {
	if (!imagesEnabled()) error(404, OFF);
	const m = /^(\d{1,12})\/(\d{4}-\d{2}-\d{2})\/(\d{8}T\d{6}Z)\.jpg$/.exec(path);
	if (!m) error(404, 'No such frame');
	const ref = { image: Number(m[1]), day: m[2], stamp: m[3] };
	if (!(await viewIndex()).byImage.has(ref.image)) error(404, 'No such camera image');
	const etag = `"${ref.image}-${ref.stamp}"`;
	if (etagMatches(ifNoneMatch, etag)) {
		if (!(await archive().hasFrame(ref))) error(404, 'No such frame');
		return frameResponse(null, etag);
	}
	const bytes = await archive().readFrame(ref);
	if (!bytes) error(404, 'No such frame (it may have been trimmed from the archive)');
	return frameResponse(bytes, etag);
}

/** GET /api/views/[id]/live/[sha]: an on-demand 511 frame, while it's in memory. */
export async function serveLiveFrame(viewId: number, sha: string, ifNoneMatch: string | null): Promise<Response> {
	if (!imagesEnabled()) error(404, OFF);
	if (!Number.isInteger(viewId) || !/^[0-9a-f]{64}$/.test(sha)) error(404, 'No such frame');
	const image = (await viewIndex()).byView.get(viewId);
	if (image === undefined || image === null) error(404, 'No such view');
	const f = fetcher().frame(sha);
	if (f && f.image !== image) error(404, 'No such frame for this view');
	const etag = `"${sha}"`;
	// Named by its content: a client holding these bytes holds the right ones, even after they leave memory.
	if (etagMatches(ifNoneMatch, etag)) return frameResponse(null, etag);
	if (!f) error(404, 'That picture is no longer in memory');
	return frameResponse(f.bytes, etag);
}

// ---------------------------------------------------------------------------
// Reference frames for calibration.

/** What POST /api/views/[id]/frame was asked to keep. */
export type FrameChoice = { kind: 'newest' } | { kind: 'sha'; sha: string } | { kind: 'archive'; ref: ArchiveFrameRef };

/** The POST body: none or `{}` (the newest frame), `{sha}`, or `{image, day, stamp}`. Anything else is a 400. */
export function parseFrameChoice(body: unknown): FrameChoice {
	if (body === null || body === undefined) return { kind: 'newest' };
	if (typeof body !== 'object' || Array.isArray(body)) error(400, 'Send {sha} or {image, day, stamp}, or no body');
	const b = body as Record<string, unknown>;
	const keys = Object.keys(b);
	if (keys.length === 0) return { kind: 'newest' };
	if (keys.length === 1 && typeof b.sha === 'string') {
		if (!/^[0-9a-f]{64}$/.test(b.sha)) error(400, 'sha is 64 lowercase hex digits');
		return { kind: 'sha', sha: b.sha };
	}
	if (keys.length === 3 && 'image' in b && 'day' in b && 'stamp' in b) {
		const ref = { image: Number(b.image), day: String(b.day), stamp: String(b.stamp) };
		if (!Number.isInteger(ref.image) || ref.image <= 0 || !/^\d{4}-\d{2}-\d{2}$/.test(ref.day) || !/^\d{8}T\d{6}Z$/.test(ref.stamp))
			error(400, 'An archive frame is {image, day: YYYY-MM-DD, stamp: YYYYmmddTHHMMSSZ}');
		return { kind: 'archive', ref };
	}
	error(400, 'Send {sha} or {image, day, stamp}, or no body');
}

/** Write a frame into FRAMES_DIR as the view's reference. */
async function keepFrame(viewId: number, imageId: number, buf: Uint8Array): Promise<SavedFrame> {
	const size = jpegSize(buf);
	if (!size) error(502, `511 Idaho's image ${imageId} isn't a readable JPEG`);
	const stamp = new Date().toISOString().replace(/[:.]/g, '-');
	const rel = `view-${viewId}/${stamp}.jpg`;
	await mkdir(join(root(), `view-${viewId}`), { recursive: true });
	await writeFile(join(root(), rel), buf);
	return { frame: rel, url: `/frames/${rel}`, ...size, capturedAt: new Date().toISOString() };
}

/**
 * The image's newest picture for a new reference: the seeded fixture in
 * fixture mode. With live images on, the archive's newest frame if it was seen
 * within 2 minutes, else the on-demand fetcher (§14.6). Otherwise one request
 * to 511, as before live images.
 */
async function newestBytes(viewId: number, imageId: number): Promise<Uint8Array> {
	if (fixtureMode()) return fixtureFrame(viewId, imageId);
	if (imagesEnabled()) {
		const now = clock();
		const { frame } = await archive().newest(imageId, now);
		if (frame && now / 1000 - frame.firstSeenAt <= ARCHIVE_FRESH_FOR_CALIBRATION_S) {
			const bytes = await archive().readFrame(frame);
			if (bytes) return bytes;
		}
		const o = await fetcher().request(imageId, viewId, 15_000);
		if (o.state === 'ok' && o.frame) return o.frame.bytes;
		if (o.state === 'blocked') error(503, o.reason ?? "robots.txt doesn't allow it right now");
		if (o.state === 'capped') error(429, o.reason ?? 'On-demand limit reached');
		if (o.state === 'waiting') error(504, `511 Idaho hasn't answered for image ${imageId} yet`);
		error(502, o.reason ?? `511 Idaho's image ${imageId} couldn't be fetched`);
	}
	try {
		return await fetch511(imageId);
	} catch (err) {
		error(502, `${err instanceof Error ? err.message : String(err)} for image ${imageId}`);
	}
}

/** Fetch the current image for a view once and keep it as a reference frame. */
export async function captureFrame(viewId: number, imageId: number): Promise<SavedFrame> {
	return keepFrame(viewId, imageId, await newestBytes(viewId, imageId));
}

/**
 * POST /api/views/[id]/frame: keep exactly the frame the client names, or the
 * newest one with no body. 410 when the named bytes are gone (out of memory,
 * or trimmed from the archive).
 */
export async function saveFrame(viewId: number, imageId: number, choice: FrameChoice): Promise<SavedFrame> {
	if (choice.kind === 'newest') return captureFrame(viewId, imageId);
	if (!imagesEnabled()) error(404, `${OFF}: there's no shown frame to keep`);
	if (choice.kind === 'sha') {
		const f = fetcher().frame(choice.sha);
		if (!f) error(410, "That picture is no longer in the server's memory; pick the current frame again");
		if (f.image !== imageId) error(400, "That picture is from another camera's view");
		return keepFrame(viewId, imageId, f.bytes);
	}
	if (choice.ref.image !== imageId) error(400, "That picture is from another camera's view");
	const bytes = await archive().readFrame(choice.ref);
	if (!bytes) error(410, 'That picture has been trimmed from the archive; pick the current frame again');
	return keepFrame(viewId, imageId, bytes);
}

/** Resolve a stored frame path safely inside FRAMES_DIR. */
export function framePath(rel: string): string {
	const full = resolve(root(), normalize(rel));
	if (!full.startsWith(root() + sep)) error(400, 'Bad frame path');
	return full;
}

export async function readFrame(rel: string): Promise<ArrayBuffer> {
	try {
		const b = await readFile(framePath(rel));
		return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
	} catch {
		error(404, 'No such frame');
	}
}
