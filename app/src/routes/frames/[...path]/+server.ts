import { readFrame } from '#lib/server/frames.js';

/** Saved reference frames. They never change once written. */
export async function GET({ params }) {
	const body = await readFrame(params.path);
	return new Response(body, {
		headers: { 'Content-Type': 'image/jpeg', 'Cache-Control': 'public, max-age=31536000, immutable' }
	});
}
