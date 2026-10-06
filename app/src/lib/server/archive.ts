/**
 * The capture archive, read-only (docs/14 §14.6, "Live images"). The capture
 * services (ingest/sources/idaho511_frames.py) write
 *
 *   <root>/cameras/jpeg/<image_id>/<local day>/<YYYYmmddTHHMMSSZ>.jpg
 *   <root>/cameras/jpeg/<image_id>/<local day>/index.csv   fetched_at,file,bytes,sha256
 *   <root>/cameras/status/<tag>.json                        one per capture service, each cycle
 *
 * with local days in America/Boise. The app mounts only cameras/jpeg and
 * cameras/status, read-only.
 *
 * - **Newest frame:** the tail of today's index.csv for that image, falling
 *   back to yesterday's. An index is read only when its size or modification
 *   time changes, so views that haven't changed cost one stat and no read.
 * - **Status files:** which images each service records, its cadence, its
 *   heartbeat and whether it paused for low disk. Read only when they change,
 *   and the listing at most every 15 s.
 *
 * Frames are third-party images: they're served to the owner's own app and
 * never published or copied anywhere else.
 */
import { open, readdir, readFile, stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import type { ArchiveFrameRef, CadenceClass, CaptureService } from '#lib/contracts/live.js';

export const ARCHIVE_TZ = 'America/Boise';
export const INDEX = 'index.csv';
export const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;
export const STAMP_RE = /^\d{8}T\d{6}Z$/;
/** Status listings and the image listing are reused this long. */
export const LISTING_TTL_MS = 15_000;
/** Key cameras are fetched every 50 s; a service with this cadence or slower is a road-weather service. */
export const ROAD_WEATHER_CADENCE_S = 300;
export const KEY_CADENCE_S = 50;
/** Enough of index.csv's end for its last rows (a row is about 110 bytes). */
const TAIL_BYTES = 4096;
/** Enough of a 511 JPEG's start for its start-of-frame marker; the whole file is read only if it's further in. */
const HEAD_BYTES = 8192;

const dayFormat = new Intl.DateTimeFormat('en-CA', { timeZone: ARCHIVE_TZ, year: 'numeric', month: '2-digit', day: '2-digit' });

/** YYYY-MM-DD in America/Boise. */
export const localDay = (ms: number) => dayFormat.format(new Date(ms));

/** The calendar day before a YYYY-MM-DD day (safe across daylight-saving changes). */
export function previousDay(day: string): string {
	const [y, m, d] = day.split('-').map(Number);
	return new Date(Date.UTC(y, m - 1, d - 1)).toISOString().slice(0, 10);
}

/** Width and height from a JPEG's start-of-frame marker. */
export function jpegSize(buf: Uint8Array): { width: number; height: number } | null {
	if (buf[0] !== 0xff || buf[1] !== 0xd8) return null;
	let i = 2;
	while (i + 9 < buf.length && buf[i] === 0xff) {
		const marker = buf[i + 1];
		const len = (buf[i + 2] << 8) | buf[i + 3];
		if (marker >= 0xc0 && marker <= 0xc3) {
			return { height: (buf[i + 5] << 8) | buf[i + 6], width: (buf[i + 7] << 8) | buf[i + 8] };
		}
		i += 2 + len;
	}
	return null;
}

/** A complete JPEG: starts with SOI and has EOI near the end (as ingest's is_jpeg). */
export function isJpeg(buf: Uint8Array): boolean {
	if (buf.length < 4 || buf[0] !== 0xff || buf[1] !== 0xd8) return false;
	for (let i = buf.length - 2; i >= Math.max(0, buf.length - 64); i--) if (buf[i] === 0xff && buf[i + 1] === 0xd9) return true;
	return false;
}

export const cadenceClass = (cadenceS: number): CadenceClass => (cadenceS >= ROAD_WEATHER_CADENCE_S ? 'road_weather' : 'key');

/** The file system calls the archive makes. Tests swap in their own to count reads. */
export interface ArchiveFs {
	/** null when the file doesn't exist. */
	stat(path: string): Promise<{ size: number; mtimeMs: number } | null>;
	readRange(path: string, start: number, length: number): Promise<Uint8Array>;
	readFile(path: string): Promise<Uint8Array>;
	readdir(path: string): Promise<string[]>;
}

export const nodeFs: ArchiveFs = {
	async stat(path) {
		try {
			const s = await stat(path);
			return s.isFile() ? { size: s.size, mtimeMs: s.mtimeMs } : null;
		} catch {
			return null;
		}
	},
	async readRange(path, start, length) {
		const fh = await open(path, 'r');
		try {
			const buf = new Uint8Array(length);
			const { bytesRead } = await fh.read(buf, 0, length, start);
			return buf.subarray(0, bytesRead);
		} finally {
			await fh.close();
		}
	},
	async readFile(path) {
		return new Uint8Array(await readFile(path));
	},
	readdir: (path) => readdir(path)
};

/** One archive frame: its identity, when our capture first got it, and its size. */
export interface ArchiveFrame extends ArchiveFrameRef {
	/** index.csv's fetched_at, epoch s. */
	firstSeenAt: number;
	bytes: number;
	/** sha256 of the bytes, hex (from index.csv). */
	sha: string;
	width: number;
	height: number;
}

interface IndexRow {
	fetchedAt: number;
	stamp: string;
	bytes: number;
	sha: string;
}

/** One index.csv row (fetched_at,file,bytes,sha256), or null for the header or a broken line. */
export function parseIndexRow(line: string): IndexRow | null {
	const [fetched, file, bytes, sha] = line.trim().split(',');
	const m = /^(\d{8}T\d{6}Z)\.jpg$/.exec(file ?? '');
	const t = Date.parse(fetched ?? '');
	if (!m || !Number.isFinite(t) || !/^[0-9a-f]{64}$/.test(sha ?? '')) return null;
	return { fetchedAt: t / 1000, stamp: m[1], bytes: Number(bytes) || 0, sha };
}

/** A capture service's status file (written by ingest/sources/idaho511_frames.py), or null if it isn't one. */
export function parseStatus(obj: unknown, fileName: string): Omit<CaptureService, 'alive'> | null {
	if (!obj || typeof obj !== 'object') return null;
	const o = obj as Record<string, unknown>;
	const cadenceS = Number(o.cadence_s);
	const heartbeat = typeof o.heartbeat === 'number' ? o.heartbeat : Date.parse(String(o.heartbeat_at ?? '')) / 1000;
	if (!(cadenceS > 0) || !Number.isFinite(heartbeat)) return null;
	return {
		tag: typeof o.tag === 'string' && o.tag ? o.tag : fileName.replace(/\.json$/, ''),
		cadenceS,
		imageIds: Array.isArray(o.image_ids) ? o.image_ids.map(Number).filter(Number.isInteger) : [],
		heartbeat,
		pausedLowDisk: o.paused_low_disk === true
	};
}

/** Reads the capture archive. Every path it touches is inside the root's cameras/jpeg or cameras/status. */
export class Archive {
	readonly root: string | null;
	/** Calls made, for tests: stats, and reads (file contents and directory listings). */
	readonly counts = { stats: 0, reads: 0 };
	private readonly fs: ArchiveFs;
	private indexCache = new Map<string, { size: number; mtimeMs: number; frame: ArchiveFrame | null }>();
	private statusCache = new Map<string, { size: number; mtimeMs: number; parsed: Omit<CaptureService, 'alive'> | null }>();
	private servicesMemo: { at: number; value: CaptureService[] } | null = null;
	private imagesMemo: { at: number; value: number[] } | null = null;
	private cacheDay = '';

	constructor(opts: { root: string | null | undefined; fs?: ArchiveFs }) {
		this.root = opts.root ? resolve(opts.root) : null;
		this.fs = opts.fs ?? nodeFs;
	}

	get jpegRoot() {
		return this.root && join(this.root, 'cameras', 'jpeg');
	}

	get statusRoot() {
		return this.root && join(this.root, 'cameras', 'status');
	}

	private stat(path: string) {
		this.counts.stats++;
		return this.fs.stat(path);
	}

	private read<T>(p: Promise<T>): Promise<T> {
		this.counts.reads++;
		return p;
	}

	/** The JPEG for a frame reference, or null if the reference isn't well formed. */
	framePath(ref: ArchiveFrameRef): string | null {
		const jpeg = this.jpegRoot;
		if (!jpeg || !Number.isInteger(ref.image) || ref.image <= 0) return null;
		if (!DAY_RE.test(ref.day) || !STAMP_RE.test(ref.stamp)) return null;
		return join(jpeg, String(ref.image), ref.day, `${ref.stamp}.jpg`);
	}

	/** Whether a frame's file exists (one stat, no read). */
	async hasFrame(ref: ArchiveFrameRef): Promise<boolean> {
		const path = this.framePath(ref);
		return Boolean(path && (await this.stat(path)));
	}

	/** A frame's bytes, or null when it isn't there (never was, or trimmed). */
	async readFrame(ref: ArchiveFrameRef): Promise<Uint8Array | null> {
		const path = this.framePath(ref);
		if (!path || !(await this.stat(path))) return null;
		try {
			return await this.read(this.fs.readFile(path));
		} catch {
			return null;
		}
	}

	/**
	 * The image's newest frame: today's index.csv, else yesterday's. `recorded`
	 * says whether either index exists (the image is in the archive at all).
	 */
	async newest(image: number, nowMs: number): Promise<{ recorded: boolean; frame: ArchiveFrame | null }> {
		const jpeg = this.jpegRoot;
		if (!jpeg) return { recorded: false, frame: null };
		const today = localDay(nowMs);
		if (today !== this.cacheDay) this.pruneCache(today);
		let recorded = false;
		for (const day of [today, previousDay(today)]) {
			const path = join(jpeg, String(image), day, INDEX);
			const st = await this.stat(path);
			if (!st) continue;
			recorded = true;
			const hit = this.indexCache.get(path);
			let frame: ArchiveFrame | null;
			if (hit && hit.size === st.size && hit.mtimeMs === st.mtimeMs) frame = hit.frame;
			else {
				frame = await this.readNewest(image, day, path, st.size);
				this.indexCache.set(path, { size: st.size, mtimeMs: st.mtimeMs, frame });
			}
			if (frame) return { recorded, frame };
		}
		return { recorded, frame: null };
	}

	private pruneCache(today: string) {
		const keep = [today, previousDay(today)];
		for (const key of this.indexCache.keys()) if (!keep.some((d) => key.includes(`/${d}/`))) this.indexCache.delete(key);
		this.cacheDay = today;
	}

	private async readNewest(image: number, day: string, indexPath: string, size: number): Promise<ArchiveFrame | null> {
		const start = Math.max(0, size - TAIL_BYTES);
		let text: string;
		try {
			text = new TextDecoder().decode(await this.read(this.fs.readRange(indexPath, start, size - start)));
		} catch {
			return null;
		}
		const lines = text.split('\n');
		lines.pop(); // after the last newline: '' when complete, or a row still being written
		if (start > 0) lines.shift(); // may begin mid-row
		for (let i = lines.length - 1; i >= 0; i--) {
			const row = parseIndexRow(lines[i]);
			if (!row) continue;
			const ref = { image, day, stamp: row.stamp };
			const size = await this.frameSize(ref);
			return size ? { ...ref, firstSeenAt: row.fetchedAt, bytes: row.bytes, sha: row.sha, ...size } : null;
		}
		return null;
	}

	private async frameSize(ref: ArchiveFrameRef): Promise<{ width: number; height: number } | null> {
		const path = this.framePath(ref);
		if (!path) return null;
		try {
			const head = await this.read(this.fs.readRange(path, 0, HEAD_BYTES));
			return jpegSize(head) ?? jpegSize(await this.read(this.fs.readFile(path)));
		} catch {
			return null;
		}
	}

	/** Every capture service's status, with `alive` (heartbeat within 3 cadences). Listed at most every 15 s. */
	async services(nowMs: number): Promise<CaptureService[]> {
		if (this.servicesMemo && nowMs - this.servicesMemo.at < LISTING_TTL_MS) return this.servicesMemo.value;
		const dir = this.statusRoot;
		const out: CaptureService[] = [];
		let names: string[] = [];
		if (dir) {
			try {
				names = (await this.read(this.fs.readdir(dir))).filter((n) => /^[\w.-]+\.json$/.test(n)).sort();
			} catch {
				names = [];
			}
		}
		for (const name of names) {
			const path = join(dir!, name);
			const st = await this.stat(path);
			if (!st) continue;
			const hit = this.statusCache.get(path);
			let parsed: Omit<CaptureService, 'alive'> | null;
			if (hit && hit.size === st.size && hit.mtimeMs === st.mtimeMs) parsed = hit.parsed;
			else {
				try {
					parsed = parseStatus(JSON.parse(new TextDecoder().decode(await this.read(this.fs.readFile(path)))), name);
				} catch {
					parsed = null; // half-written or not ours: skipped until it changes
				}
				this.statusCache.set(path, { size: st.size, mtimeMs: st.mtimeMs, parsed });
			}
			if (parsed) out.push({ ...parsed, alive: nowMs / 1000 - parsed.heartbeat <= 3 * parsed.cadenceS });
		}
		this.servicesMemo = { at: nowMs, value: out };
		return out;
	}

	/** Image IDs with a folder in cameras/jpeg. Listed at most every 15 s. */
	async images(nowMs: number): Promise<number[]> {
		if (this.imagesMemo && nowMs - this.imagesMemo.at < LISTING_TTL_MS) return this.imagesMemo.value;
		let value: number[] = [];
		const jpeg = this.jpegRoot;
		if (jpeg) {
			try {
				value = (await this.read(this.fs.readdir(jpeg))).filter((n) => /^\d+$/.test(n)).map(Number);
			} catch {
				value = [];
			}
		}
		this.imagesMemo = { at: nowMs, value };
		return value;
	}
}
