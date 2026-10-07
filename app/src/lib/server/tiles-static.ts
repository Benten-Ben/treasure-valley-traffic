import { createReadStream, existsSync, statSync, type BigIntStats } from 'node:fs';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { extname, join, resolve, sep } from 'node:path';

/**
 * The /tiles/ file server for `vite dev` and `vite preview`, mirroring what
 * Caddy's `file_server` does in production (deploy/Caddyfile; docs/14 §14.9
 * "Targets"), so local byte, request and cache numbers mean something:
 *
 * - `public, max-age=3600` on every file, `no-cache` on manifest.json;
 * - a `.gz` sibling (precompressed glyphs) is served with
 *   `Content-Encoding: gzip` to clients that accept it
 *   (`file_server { precompressed gzip }`), as Caddy serves a sidecar: the
 *   sidecar's ETag, the original's Last-Modified, no `Accept-Ranges`; and
 *   `Vary: Accept-Encoding` on every file (Caddy 2.7 on);
 * - Caddy's strong ETag (`"<mtime ns, base 36><size, base 36>"`), so
 *   pmtiles can check archive versions and Chrome caches byte ranges as it
 *   would in production; Last-Modified; 304 for If-None-Match and
 *   If-Modified-Since;
 * - single byte ranges, suffix ranges, If-Range and 416, as Go's
 *   http.ServeContent answers them;
 * - a plain 404 for anything missing or outside the folder.
 *
 * WP5's Caddy edits (no-cache manifest, `precompressed gzip`) are mirrored
 * here; when Caddy's tiles config changes again, this changes with it.
 */
export const TILES_CACHE_CONTROL = 'public, max-age=3600';
export const MANIFEST_CACHE_CONTROL = 'no-cache';

type Handler = (req: IncomingMessage, res: ServerResponse, next?: () => void) => void;

const TYPES: Record<string, string> = {
	'.json': 'application/json',
	'.pbf': 'application/x-protobuf',
	'.pmtiles': 'application/octet-stream',
	'.png': 'image/png',
	'.txt': 'text/plain; charset=utf-8'
};

/** Caddy's ETag for a file (modules/caddyhttp/fileserver: calculateEtag). */
export function caddyEtag(s: BigIntStats): string {
	return `"${s.mtimeNs.toString(36)}${s.size.toString(36)}"`;
}

function plain(res: ServerResponse, status: number, text: string) {
	res.statusCode = status;
	res.setHeader('Content-Type', 'text/plain; charset=utf-8');
	res.end(text);
}

/** One satisfiable range [start, end] (inclusive), 'unsatisfiable', or null for the whole file. */
export function parseRange(header: string | undefined, size: number): [number, number] | 'unsatisfiable' | null {
	if (!header) return null;
	const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
	if (!m || (m[1] === '' && m[2] === '')) return null; // malformed or several ranges: the whole file
	if (m[1] === '') {
		const n = Number(m[2]);
		if (n === 0) return 'unsatisfiable';
		return [Math.max(0, size - n), size - 1];
	}
	const start = Number(m[1]);
	if (start >= size) return 'unsatisfiable';
	const end = m[2] === '' ? size - 1 : Math.min(Number(m[2]), size - 1);
	return end < start ? null : [start, end];
}

const etagMatches = (list: string, etag: string) =>
	list.split(',').some((t) => {
		const v = t.trim();
		return v === '*' || v.replace(/^W\//, '') === etag;
	});

export function tilesHandler(dir: string): Handler {
	const root = resolve(dir);
	if (!existsSync(root)) {
		console.warn(`tiles: ${root} doesn't exist; /tiles/ answers 404 (build the basemap or set TILES_DIR)`);
		return (_req, res) => plain(res, 404, 'Not found');
	}
	return (req, res) => {
		if (req.method !== 'GET' && req.method !== 'HEAD') {
			res.setHeader('Allow', 'GET, HEAD');
			return plain(res, 405, 'Method not allowed');
		}
		let pathname: string;
		try {
			pathname = decodeURIComponent(new URL(req.url ?? '/', 'http://x').pathname);
		} catch {
			return plain(res, 400, 'Bad path');
		}
		const file = resolve(join(root, pathname));
		if (pathname.includes('\0') || !file.startsWith(root + sep)) return plain(res, 404, 'Not found');
		let st: BigIntStats;
		try {
			st = statSync(file, { bigint: true });
		} catch {
			return plain(res, 404, 'Not found');
		}
		if (!st.isFile()) return plain(res, 404, 'Not found');

		// Precompressed sibling: Caddy takes the sidecar's ETag, but keeps the original's modification time.
		let body = file;
		const gz = `${file}.gz`;
		const modified = new Date(Number(st.mtimeMs));
		modified.setMilliseconds(0);
		let sidecar = false;
		if (/\bgzip\b/.test(String(req.headers['accept-encoding'] ?? '')) && existsSync(gz)) {
			body = gz;
			sidecar = true;
			st = statSync(gz, { bigint: true });
			res.setHeader('Content-Encoding', 'gzip');
		}
		const size = Number(st.size);
		const etag = caddyEtag(st);
		res.setHeader('Vary', 'Accept-Encoding');
		res.setHeader('Cache-Control', pathname === '/manifest.json' ? MANIFEST_CACHE_CONTROL : TILES_CACHE_CONTROL);
		res.setHeader('ETag', etag);
		res.setHeader('Last-Modified', modified.toUTCString());
		if (!sidecar) res.setHeader('Accept-Ranges', 'bytes');
		res.setHeader('Content-Type', TYPES[extname(file)] ?? 'application/octet-stream');

		const inm = req.headers['if-none-match'];
		const ims = req.headers['if-modified-since'];
		if ((inm && etagMatches(String(inm), etag)) || (!inm && ims && Date.parse(String(ims)) >= modified.getTime())) {
			res.removeHeader('Content-Type');
			res.statusCode = 304;
			return res.end();
		}

		// If-Range: a range only applies while the representation is unchanged.
		const ifRange = req.headers['if-range'];
		const rangeHeader = ifRange && String(ifRange) !== etag && Date.parse(String(ifRange)) !== modified.getTime()
			? undefined
			: req.headers.range;
		const range = parseRange(rangeHeader, size);
		if (range === 'unsatisfiable') {
			res.setHeader('Content-Range', `bytes */${size}`);
			return plain(res, 416, 'Range not satisfiable');
		}
		const [start, end] = range ?? [0, size - 1];
		res.statusCode = range ? 206 : 200;
		if (range) res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`);
		res.setHeader('Content-Length', size === 0 ? 0 : end - start + 1);
		if (req.method === 'HEAD' || size === 0) return res.end();
		const stream = createReadStream(body, { start, end });
		stream.on('error', () => res.destroy());
		stream.pipe(res);
	};
}
