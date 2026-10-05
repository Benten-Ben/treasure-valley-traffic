import { error } from '@sveltejs/kit';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, normalize, resolve, sep } from 'node:path';
import { FRAMES_DIR } from '$app/env/private';

const USER_AGENT =
	'treasure-valley-traffic/0.2 (public-interest research; +https://github.com/Benten-Ben/treasure-valley-traffic)';

/** 511 Idaho's republished camera images: the allowed route (docs/11 §11.2). */
export const imageUrl = (imageId: number) => `https://511.idaho.gov/map/Cctv/${imageId}`;

const root = () => resolve(FRAMES_DIR);

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

/** Fetch the current image for a view once and keep it as a reference frame. */
export async function captureFrame(viewId: number, imageId: number) {
	const res = await fetch(imageUrl(imageId), { headers: { 'User-Agent': USER_AGENT } });
	if (!res.ok) error(502, `511 Idaho answered ${res.status} for image ${imageId}`);
	const buf = new Uint8Array(await res.arrayBuffer());
	const size = jpegSize(buf);
	if (!size) error(502, `511 Idaho's image ${imageId} isn't a readable JPEG`);
	const stamp = new Date().toISOString().replace(/[:.]/g, '-');
	const rel = `view-${viewId}/${stamp}.jpg`;
	await mkdir(join(root(), `view-${viewId}`), { recursive: true });
	await writeFile(join(root(), rel), buf);
	return { frame: rel, url: `/frames/${rel}`, ...size, capturedAt: new Date().toISOString() };
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
