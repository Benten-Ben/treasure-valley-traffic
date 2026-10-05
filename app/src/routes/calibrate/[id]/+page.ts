import { error } from '@sveltejs/kit';

// The calibrator needs WebGL and the browser, so it renders client-side only.
export const ssr = false;

export async function load({ fetch, params }) {
	const res = await fetch(`/api/cameras/${params.id}`);
	if (!res.ok) error(res.status, (await res.json().catch(() => null))?.message ?? 'Camera not found');
	return { camera: await res.json() };
}
