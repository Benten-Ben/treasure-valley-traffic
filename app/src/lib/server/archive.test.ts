import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { appendFile, mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Archive, cadenceClass, isJpeg, jpegSize, localDay, parseIndexRow, previousDay } from './archive.js';
import { GRAY_16x8, TEAL_24x8, sha } from './live-fixtures.test-util.js';

// 12:00 MDT on Oct 6, 2026: local day 2026-10-06, yesterday 2026-10-05.
const NOW = Date.parse('2026-10-06T18:00:00Z');
let root: string;

/** A frame the way idaho511_frames.py saves it: the JPEG, then a CRLF row in index.csv. */
async function save(image: number, day: string, stamp: string, bytes: Buffer, header = false) {
	const dir = join(root, 'cameras', 'jpeg', String(image), day);
	await mkdir(dir, { recursive: true });
	await writeFile(join(dir, `${stamp}.jpg`), bytes);
	const fetched = `${stamp.slice(0, 4)}-${stamp.slice(4, 6)}-${stamp.slice(6, 8)}T${stamp.slice(9, 11)}:${stamp.slice(11, 13)}:${stamp.slice(13, 15)}Z`;
	if (header) await writeFile(join(dir, 'index.csv'), 'fetched_at,file,bytes,sha256\r\n');
	await appendFile(join(dir, 'index.csv'), `${fetched},${stamp}.jpg,${bytes.length},${sha(bytes)}\r\n`);
}

beforeEach(async () => {
	root = await mkdtemp(join(tmpdir(), 'tvt-archive-'));
});
afterEach(async () => {
	await rm(root, { recursive: true, force: true });
});

describe('days', () => {
	it('uses Boise local days, and steps back a calendar day across DST and month ends', () => {
		expect(localDay(NOW)).toBe('2026-10-06');
		expect(localDay(Date.parse('2026-10-07T05:59:00Z'))).toBe('2026-10-06'); // 23:59 MDT
		expect(previousDay('2026-11-02')).toBe('2026-11-01'); // the day after the clocks go back
		expect(previousDay('2026-03-01')).toBe('2026-02-28');
		expect(previousDay('2027-01-01')).toBe('2026-12-31');
	});
});

describe('index rows and JPEGs', () => {
	it('parses rows with CRLF and rejects the header and broken lines', () => {
		expect(parseIndexRow(`2026-10-06T15:12:40Z,20261006T151240Z.jpg,48754,${'a'.repeat(64)}\r`)).toEqual({
			fetchedAt: Date.parse('2026-10-06T15:12:40Z') / 1000,
			stamp: '20261006T151240Z',
			bytes: 48754,
			sha: 'a'.repeat(64)
		});
		expect(parseIndexRow('fetched_at,file,bytes,sha256')).toBeNull();
		expect(parseIndexRow('2026-10-06T15:12:40Z,20261006T1512')).toBeNull();
	});

	it('reads sizes and completeness', () => {
		expect(jpegSize(GRAY_16x8)).toEqual({ width: 16, height: 8 });
		expect(isJpeg(GRAY_16x8)).toBe(true);
		expect(isJpeg(GRAY_16x8.subarray(0, GRAY_16x8.length - 2))).toBe(false);
		expect(cadenceClass(50)).toBe('key');
		expect(cadenceClass(600)).toBe('road_weather');
	});
});

describe('Archive.newest', () => {
	it("gives today's last row, with its seen time, sha and size", async () => {
		await save(656, '2026-10-06', '20261006T175000Z', GRAY_16x8, true);
		await save(656, '2026-10-06', '20261006T175050Z', TEAL_24x8);
		const a = new Archive({ root });
		const { recorded, frame } = await a.newest(656, NOW);
		expect(recorded).toBe(true);
		expect(frame).toEqual({
			image: 656,
			day: '2026-10-06',
			stamp: '20261006T175050Z',
			firstSeenAt: Date.parse('2026-10-06T17:50:50Z') / 1000,
			bytes: TEAL_24x8.length,
			sha: sha(TEAL_24x8),
			width: 24,
			height: 8
		});
	});

	it("falls back to yesterday's index, and says when an image isn't recorded", async () => {
		await save(656, '2026-10-05', '20261006T055000Z', GRAY_16x8, true);
		const a = new Archive({ root });
		expect((await a.newest(656, NOW)).frame?.day).toBe('2026-10-05');
		expect(await a.newest(999, NOW)).toEqual({ recorded: false, frame: null });
		// A header-only index for today still falls back to yesterday's frame.
		await mkdir(join(root, 'cameras', 'jpeg', '656', '2026-10-06'), { recursive: true });
		await writeFile(join(root, 'cameras', 'jpeg', '656', '2026-10-06', 'index.csv'), 'fetched_at,file,bytes,sha256\r\n');
		expect((await a.newest(656, NOW)).frame?.day).toBe('2026-10-05');
	});

	it('serves a new index row at the next request, and reads nothing for 100 requests while unchanged', async () => {
		await save(656, '2026-10-06', '20261006T175000Z', GRAY_16x8, true);
		await save(674, '2026-10-06', '20261006T175001Z', GRAY_16x8, true);
		const a = new Archive({ root });
		await a.newest(656, NOW);
		await a.newest(674, NOW);
		const reads = a.counts.reads;
		for (let i = 0; i < 100; i++) {
			await a.newest(656, NOW);
			await a.newest(674, NOW);
		}
		expect(a.counts.reads - reads).toBe(0);

		await save(656, '2026-10-06', '20261006T175050Z', TEAL_24x8);
		expect((await a.newest(656, NOW)).frame?.stamp).toBe('20261006T175050Z');
		expect((await a.newest(674, NOW)).frame?.stamp).toBe('20261006T175001Z');
	});

	it('ignores a row still being written', async () => {
		await save(656, '2026-10-06', '20261006T175000Z', GRAY_16x8, true);
		await appendFile(join(root, 'cameras', 'jpeg', '656', '2026-10-06', 'index.csv'), '2026-10-06T17:50:50Z,20261006T1750');
		expect((await new Archive({ root }).newest(656, NOW)).frame?.stamp).toBe('20261006T175000Z');
	});

	it('reads frames by reference and refuses anything outside the archive', async () => {
		await save(656, '2026-10-06', '20261006T175000Z', GRAY_16x8, true);
		const a = new Archive({ root });
		expect(Buffer.compare(Buffer.from((await a.readFrame({ image: 656, day: '2026-10-06', stamp: '20261006T175000Z' }))!), GRAY_16x8)).toBe(0);
		expect(await a.readFrame({ image: 656, day: '2026-10-06', stamp: '20261006T000000Z' })).toBeNull();
		expect(a.framePath({ image: 656, day: '../../x', stamp: '20261006T175000Z' })).toBeNull();
		expect(a.framePath({ image: 656, day: '2026-10-06', stamp: '../../../etc/passwd' })).toBeNull();
		expect(a.framePath({ image: -1, day: '2026-10-06', stamp: '20261006T175000Z' })).toBeNull();
		expect(new Archive({ root: undefined }).framePath({ image: 656, day: '2026-10-06', stamp: '20261006T175000Z' })).toBeNull();
	});
});

describe('Archive.services', () => {
	async function status(name: string, body: unknown) {
		await mkdir(join(root, 'cameras', 'status'), { recursive: true });
		await writeFile(join(root, 'cameras', 'status', name), typeof body === 'string' ? body : JSON.stringify(body));
	}

	it('reads each status file, says whether capture is alive, and lists at most every 15 s', async () => {
		const t = NOW / 1000;
		await status('key_cameras.json', { tag: 'key_cameras', cadence_s: 50, image_ids: [656, 674], heartbeat: t - 30, paused_low_disk: false });
		await status('regional-cameras.json', { tag: 'regional-cameras', cadence_s: 600, image_ids: [9001], heartbeat: t - 3600, paused_low_disk: true });
		await status('broken.json', '{"tag": "half-writ');
		const a = new Archive({ root });
		expect(await a.services(NOW)).toEqual([
			{ tag: 'key_cameras', cadenceS: 50, imageIds: [656, 674], heartbeat: t - 30, pausedLowDisk: false, alive: true },
			{ tag: 'regional-cameras', cadenceS: 600, imageIds: [9001], heartbeat: t - 3600, pausedLowDisk: true, alive: false }
		]);
		const reads = a.counts.reads;
		await status('key_cameras.json', { tag: 'key_cameras', cadence_s: 50, image_ids: [656], heartbeat: t, paused_low_disk: false });
		expect((await a.services(NOW + 10_000))[0].imageIds).toEqual([656, 674]); // still the 15 s listing
		expect(a.counts.reads).toBe(reads);
		expect((await a.services(NOW + 15_000))[0].imageIds).toEqual([656]);
		// Unchanged files aren't read again: the listing, plus the one changed file.
		expect(a.counts.reads - reads).toBe(2);
	});

	it('has no services without a status folder or an archive', async () => {
		expect(await new Archive({ root }).services(NOW)).toEqual([]);
		expect(await new Archive({ root: undefined }).services(NOW)).toEqual([]);
	});
});
