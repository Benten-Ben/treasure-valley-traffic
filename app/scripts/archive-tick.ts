#!/usr/bin/env node
/**
 * Append a frame to the fake capture archive, as the capture service would
 * (ingest/sources/idaho511_frames.py; docs/14 §14.11 "Seeded data").
 *
 *   node scripts/archive-tick.ts                    every image in $TVT_ARCHIVE
 *   node scripts/archive-tick.ts 656 674           just these images
 *   node scripts/archive-tick.ts --at 2026-10-06T15:12:40Z --root <archive>
 *
 * Layout (same as the real archive):
 *   <root>/cameras/jpeg/<image_id>/<local day>/<YYYYmmddTHHMMSSZ>.jpg
 *   <root>/cameras/jpeg/<image_id>/<local day>/index.csv   fetched_at,file,bytes,sha256
 * Local days are America/Boise. The new frame is the image's newest frame
 * with a JPEG comment saying when it was ticked, so its bytes (and sha256)
 * differ, as a real new picture's would.
 */
import { createHash } from 'node:crypto';
import { appendFileSync, existsSync, readdirSync, readFileSync, renameSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const INDEX = 'index.csv';
export const INDEX_HEADER = 'fetched_at,file,bytes,sha256';

/** YYYY-MM-DD in America/Boise. */
export function localDay(at: Date): string {
	return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Boise', year: 'numeric', month: '2-digit', day: '2-digit' }).format(at);
}

/** 20261006T151240Z */
export const stampOf = (at: Date) => at.toISOString().replace(/\.\d+Z$/, 'Z').replace(/[-:]/g, '');
/** 2026-10-06T15:12:40Z (index.csv's fetched_at) */
export const fetchedAtOf = (at: Date) => at.toISOString().replace(/\.\d+Z$/, 'Z');

export const jpegDir = (root: string, image: number | string, day: string) => join(root, 'cameras', 'jpeg', String(image), day);

/** A JPEG with a COM segment inserted after SOI: same picture, different bytes. */
export function withComment(jpeg: Uint8Array, text: string): Buffer {
	if (jpeg[0] !== 0xff || jpeg[1] !== 0xd8) throw new Error('not a JPEG');
	const body = Buffer.from(text, 'utf8');
	const seg = Buffer.alloc(4 + body.length);
	seg[0] = 0xff;
	seg[1] = 0xfe;
	seg.writeUInt16BE(body.length + 2, 2);
	body.copy(seg, 4);
	return Buffer.concat([jpeg.subarray(0, 2), seg, jpeg.subarray(2)]);
}

interface Row {
	fetched_at: string;
	file: string;
	bytes: string;
	sha256: string;
}

export function readIndex(file: string): Row[] {
	const [head, ...lines] = readFileSync(file, 'utf8').trim().split('\n');
	const keys = head.split(',');
	return lines.filter(Boolean).map((l) => Object.fromEntries(l.split(',').map((v, i) => [keys[i], v])) as unknown as Row);
}

/** The image's newest frame on any day: [day folder, row]. */
export function newestFrame(root: string, image: number | string): { dir: string; row: Row } | null {
	const base = join(root, 'cameras', 'jpeg', String(image));
	if (!existsSync(base)) return null;
	for (const day of readdirSync(base).filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d)).sort().reverse()) {
		const index = join(base, day, INDEX);
		if (!existsSync(index)) continue;
		const rows = readIndex(index);
		if (rows.length) return { dir: join(base, day), row: rows[rows.length - 1] };
	}
	return null;
}

export function imagesIn(root: string): number[] {
	const base = join(root, 'cameras', 'jpeg');
	if (!existsSync(base)) return [];
	return readdirSync(base).filter((d) => /^\d+$/.test(d)).map(Number).sort((a, b) => a - b);
}

/** Append one frame per image at time `at`. Returns what was written. */
export function tick(root: string, images: number[] = imagesIn(root), at = new Date()) {
	const out: { image: number; day: string; stamp: string; file: string; sha256: string }[] = [];
	for (const image of images) {
		const newest = newestFrame(root, image);
		if (!newest) throw new Error(`no frame to copy for image ${image} in ${root}`);
		const src = readFileSync(join(newest.dir, newest.row.file));
		let t = new Date(Math.floor(at.getTime() / 1000) * 1000);
		const day = localDay(t);
		const dir = jpegDir(root, image, day);
		mkdirSync(dir, { recursive: true });
		// Two ticks in one second: move on a second, as a later fetch would be.
		while (existsSync(join(dir, `${stampOf(t)}.jpg`))) t = new Date(t.getTime() + 1000);
		const stamp = stampOf(t);
		const bytes = withComment(src, `tvt archive-tick ${fetchedAtOf(t)} (synthetic test frame)`);
		const sha256 = createHash('sha256').update(bytes).digest('hex');
		const file = `${stamp}.jpg`;
		writeFileSync(join(dir, `${file}.part`), bytes);
		renameSync(join(dir, `${file}.part`), join(dir, file));
		const index = join(dir, INDEX);
		if (!existsSync(index)) writeFileSync(index, `${INDEX_HEADER}\n`);
		appendFileSync(index, `${fetchedAtOf(t)},${file},${bytes.length},${sha256}\n`);
		out.push({ image, day, stamp, file: join(dir, file), sha256 });
	}
	return out;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	const args = process.argv.slice(2);
	const opt = (name: string) => {
		const i = args.indexOf(name);
		if (i === -1) return undefined;
		const [v] = args.splice(i, 2).slice(1);
		return v;
	};
	const at = opt('--at');
	let root = opt('--root');
	if (!root) {
		const { harnessEnv } = await import('./harness-env.mjs');
		root = harnessEnv().TVT_ARCHIVE;
	}
	const images = args.length ? args.map(Number) : undefined;
	const done = tick(root, images, at ? new Date(at) : new Date());
	console.log(`ticked ${done.length} image(s) in ${root}${done.length === 1 ? `: ${done[0].file}` : ''}`);
}
