import { existsSync } from 'node:fs';
import type { IncomingMessage, ServerResponse } from 'node:http';
import sirv from 'sirv';

/**
 * The /tiles/ file server for `vite dev` and `vite preview`, mirroring what
 * Caddy does in production (deploy/Caddyfile; docs/14 §14.9 "Targets"), so
 * local byte and request counts mean something:
 *
 * - `public, max-age=3600` on every file;
 * - `no-cache` on manifest.json, so a rebuilt basemap is picked up at once;
 * - a `.gz` sibling (precompressed glyphs) is served with
 *   `Content-Encoding: gzip` to clients that accept it (Caddy's
 *   `file_server { precompressed gzip }`);
 * - ETags and HTTP range requests (PMTiles needs ranges);
 * - a plain 404 for anything missing.
 *
 * The file list is read once at startup (sirv's production mode), so restart
 * the dev server after rebuilding the basemap. When Caddy's tiles config
 * changes (WP5), this changes with it.
 */
export const TILES_CACHE_CONTROL = 'public, max-age=3600';
export const MANIFEST_CACHE_CONTROL = 'no-cache';

type Handler = (req: IncomingMessage, res: ServerResponse, next?: () => void) => void;

function notFound(res: ServerResponse) {
	res.statusCode = 404;
	res.setHeader('Content-Type', 'text/plain; charset=utf-8');
	res.end('Not found');
}

export function tilesHandler(dir: string): Handler {
	if (!existsSync(dir)) {
		console.warn(`tiles: ${dir} doesn't exist; /tiles/ answers 404 (build the basemap or set TILES_DIR)`);
		return (_req, res) => notFound(res);
	}
	const serve = sirv(dir, {
		dev: false,
		etag: true,
		gzip: true,
		extensions: [],
		setHeaders(res, pathname) {
			res.setHeader('Cache-Control', pathname === '/manifest.json' ? MANIFEST_CACHE_CONTROL : TILES_CACHE_CONTROL);
			// sirv's type table doesn't know these two.
			if (pathname.endsWith('.pbf')) res.setHeader('Content-Type', 'application/x-protobuf');
			else if (pathname.endsWith('.pmtiles')) res.setHeader('Content-Type', 'application/octet-stream');
		}
	});
	return (req, res) => serve(req, res, () => notFound(res));
}
