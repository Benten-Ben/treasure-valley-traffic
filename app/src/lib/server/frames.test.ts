import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mkdir, mkdtemp, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// Synthetic flat-color JPEGs made with ffmpeg (16×8 and 24×8). Not camera images.
const GRAY_16x8 = Buffer.from(
	'/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYwLjMxLjEwMgD/2wBDAAgoKC8oLzc3Nzc3N0E8QUNDQ0FBQUFDQ0NISEhVVVVISEhDQ0hIUFBVVVxfXFdXVVdfX2RkZHh4c3OMjJGsrM//xABMAAEBAAAAAAAAAAAAAAAAAAAAAwEBAQAAAAAAAAAAAAAAAAAAAgMQAQAAAAAAAAAAAAAAAAAAAAARAQAAAAAAAAAAAAAAAAAAAAD/wAARCAAIABADASIAAhEAAxEA/9oADAMBAAIRAxEAPwCwCJv/2Q==',
	'base64'
);
const TEAL_24x8 = Buffer.from(
	'/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYwLjMxLjEwMgD/2wBDAAgoKC8oLzc3Nzc3N0E8QUNDQ0FBQUFDQ0NISEhVVVVISEhDQ0hIUFBVVVxfXFdXVVdfX2RkZHh4c3OMjJGsrM//xABNAAEBAAAAAAAAAAAAAAAAAAAABAEBAQEAAAAAAAAAAAAAAAAAAAUGEAEAAAAAAAAAAAAAAAAAAAAAEQEAAAAAAAAAAAAAAAAAAAAA/8AAEQgACAAYAwEiAAIRAAMRAP/aAAwDAQACEQMRAD8AgAV2OAAf/9k=',
	'base64'
);

let dir: string;

/** Load frames.ts and the frame route with a given TVT_FRAME_SOURCE and a fake database. */
async function load(source: '511' | 'fixture') {
	vi.resetModules();
	// Live images off (CAMERA_IMAGES_ENABLED's default), so no body means today's capture.
	vi.doMock('$app/env/private', () => ({
		FRAMES_DIR: dir,
		TVT_FRAME_SOURCE: source,
		DATABASE_URL: 'postgres://unused',
		CAMERA_IMAGES_ENABLED: false,
		TVT_ARCHIVE: undefined
	}));
	// db()`select image_id …` → one view with image 752.
	vi.doMock('#lib/server/db.js', () => ({ db: () => async () => [{ image_id: 752 }] }));
	const frames = await import('./frames.js');
	const route = await import('../../routes/api/views/[id]/frame/+server.js');
	const post = (id: string) => route.POST({ params: { id } } as never);
	return { frames, post };
}

beforeEach(async () => {
	dir = await mkdtemp(join(tmpdir(), 'tvt-frames-'));
});

afterEach(async () => {
	vi.unstubAllGlobals();
	vi.doUnmock('$app/env/private');
	vi.doUnmock('#lib/server/db.js');
	await rm(dir, { recursive: true, force: true });
});

describe('POST /api/views/[id]/frame in fixture mode', () => {
	it('saves the seeded frame and never calls fetch', async () => {
		const fetchSpy = vi.fn(() => {
			throw new Error('network is off in tests');
		});
		vi.stubGlobal('fetch', fetchSpy);
		await mkdir(join(dir, '_fixture'), { recursive: true });
		await writeFile(join(dir, '_fixture', 'default.jpg'), GRAY_16x8);
		const { post } = await load('fixture');

		const res = await post('5');
		expect(res.status).toBe(200);
		const body = await res.json();
		expect(body).toMatchObject({ width: 16, height: 8 });
		expect(body.frame).toMatch(/^view-5\/.+\.jpg$/);
		expect(body.url).toBe(`/frames/${body.frame}`);
		expect(await readdir(join(dir, 'view-5'))).toHaveLength(1);
		expect(fetchSpy).not.toHaveBeenCalled();
	});

	it("prefers the view's own seeded frame, then the image's, then the default", async () => {
		vi.stubGlobal('fetch', () => {
			throw new Error('network is off in tests');
		});
		await mkdir(join(dir, '_fixture'), { recursive: true });
		await writeFile(join(dir, '_fixture', 'default.jpg'), GRAY_16x8);
		await writeFile(join(dir, '_fixture', 'image-752.jpg'), TEAL_24x8);
		const { post } = await load('fixture');
		expect(await (await post('9')).json()).toMatchObject({ width: 24 });
		await writeFile(join(dir, '_fixture', 'view-9.jpg'), GRAY_16x8);
		expect(await (await post('9')).json()).toMatchObject({ width: 16 });
	});

	it('answers 503 with a hint when nothing is seeded, still without fetching', async () => {
		const fetchSpy = vi.fn();
		vi.stubGlobal('fetch', fetchSpy);
		const { post } = await load('fixture');
		await expect(post('5')).rejects.toMatchObject({ status: 503 });
		expect(fetchSpy).not.toHaveBeenCalled();
	});
});

describe('POST /api/views/[id]/frame from 511', () => {
	it("fetches 511's republished image with our User-Agent", async () => {
		const fetchSpy = vi.fn(async (..._args: unknown[]) => new Response(TEAL_24x8));
		vi.stubGlobal('fetch', fetchSpy);
		const { post } = await load('511');
		const body = await (await post('5')).json();
		expect(body).toMatchObject({ width: 24, height: 8 });
		expect(fetchSpy).toHaveBeenCalledTimes(1);
		const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
		expect(url).toBe('https://511.idaho.gov/map/Cctv/752');
		expect((init.headers as Record<string, string>)['User-Agent']).toMatch(/treasure-valley-traffic/);
	});
});
