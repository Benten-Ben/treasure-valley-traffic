import { json } from '@sveltejs/kit';

// Used by the container health check (deploy/docker-compose.yml).
export function GET() {
	return json({ ok: true, time: new Date().toISOString() });
}
