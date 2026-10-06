/**
 * Photo textures for the photo planes (docs/14 §14.6, "The photo in the
 * cone"; §14.8, "Robustness").
 *
 * - One texture array of 16 layers (an LRU of at most 16 photos, about 30 MB
 *   with mipmaps), so every photo plane draws in one call.
 * - Pictures are decoded off the main thread by `createImageBitmap` (cropped,
 *   e.g. without the burned-in 511 bar, and resized to the layer size), and
 *   uploaded in the custom layer's `prerender`.
 * - The compressed bytes are kept, so a restored WebGL context gets every
 *   picture back without asking the server again.
 */
export const LAYERS = 16;
export const LAYER_W = 768;
export const LAYER_H = 480;
const LEVELS = 4;

export interface Crop {
	x: number;
	y: number;
	width: number;
	height: number;
}

interface Entry {
	key: string;
	blob: Blob;
	crop?: Crop;
	layer: number;
	used: number;
	/** Decoded and waiting for upload. */
	bitmap: ImageBitmap | null;
	uploaded: boolean;
	/** Bumped on every load, so a stale decode never lands. */
	gen: number;
}

/** The LRU's choice: an unused layer, else the least recently used entry's. */
export function pickLayer(entries: { layer: number; used: number }[], layers = LAYERS): number {
	const taken = new Set(entries.map((e) => e.layer));
	for (let l = 0; l < layers; l++) if (!taken.has(l)) return l;
	let oldest = entries[0];
	for (const e of entries) if (e.used < oldest.used) oldest = e;
	return oldest.layer;
}

export class PhotoTextures {
	#entries = new Map<string, Entry>();
	#gl: WebGL2RenderingContext | null = null;
	#texture: WebGLTexture | null = null;
	#tick = 0;
	/** Something new is waiting for prerender (the scene asks for a frame). */
	onReady: (() => void) | null = null;

	/** Load (or replace) the picture for `key` from a URL or a Blob. Resolves once it's decoded. */
	async load(key: string, src: string | Blob, crop?: Crop): Promise<void> {
		const blob = typeof src === 'string' ? await fetch(src).then((r) => (r.ok ? r.blob() : Promise.reject(new Error(`${r.status} for ${src}`)))) : src;
		let e = this.#entries.get(key);
		if (!e) {
			const layer = pickLayer([...this.#entries.values()]);
			for (const [k, other] of this.#entries) if (other.layer === layer) this.#drop(k);
			e = { key, blob, crop, layer, used: ++this.#tick, bitmap: null, uploaded: false, gen: 0 };
			this.#entries.set(key, e);
		} else {
			e.blob = blob;
			e.crop = crop;
			e.used = ++this.#tick;
		}
		await this.#decode(e);
	}

	async #decode(e: Entry): Promise<void> {
		const gen = ++e.gen;
		const opts: ImageBitmapOptions = { resizeWidth: LAYER_W, resizeHeight: LAYER_H, resizeQuality: 'high' };
		const bmp = e.crop ? await createImageBitmap(e.blob, e.crop.x, e.crop.y, e.crop.width, e.crop.height, opts) : await createImageBitmap(e.blob, opts);
		if (this.#entries.get(e.key) !== e || gen !== e.gen) {
			bmp.close();
			return;
		}
		e.bitmap?.close();
		e.bitmap = bmp;
		e.uploaded = false;
		this.onReady?.();
	}

	#drop(key: string): void {
		const e = this.#entries.get(key);
		e?.bitmap?.close();
		this.#entries.delete(key);
	}

	release(key: string): void {
		this.#drop(key);
	}

	/** The layer holding `key`'s picture (marking it used), or −1 while it isn't uploaded. */
	layer(key: string | undefined): number {
		const e = key ? this.#entries.get(key) : undefined;
		if (!e || !e.uploaded) return -1;
		e.used = ++this.#tick;
		return e.layer;
	}

	has(key: string): boolean {
		return this.#entries.has(key);
	}

	get size(): number {
		return this.#entries.size;
	}

	/** Upload what was decoded since the last frame (the custom layer's `prerender`). */
	prerender(gl: WebGL2RenderingContext): void {
		let changed = false;
		for (const e of this.#entries.values()) {
			if (!e.bitmap) continue;
			this.#ensure(gl);
			gl.bindTexture(gl.TEXTURE_2D_ARRAY, this.#texture);
			gl.texSubImage3D(gl.TEXTURE_2D_ARRAY, 0, 0, 0, e.layer, LAYER_W, LAYER_H, 1, gl.RGBA, gl.UNSIGNED_BYTE, e.bitmap);
			e.bitmap.close();
			e.bitmap = null;
			e.uploaded = true;
			changed = true;
		}
		if (changed) {
			gl.generateMipmap(gl.TEXTURE_2D_ARRAY);
			gl.bindTexture(gl.TEXTURE_2D_ARRAY, null);
		}
	}

	#ensure(gl: WebGL2RenderingContext): void {
		if (this.#gl === gl && this.#texture) return;
		this.#gl = gl;
		this.#texture = gl.createTexture();
		gl.bindTexture(gl.TEXTURE_2D_ARRAY, this.#texture);
		gl.texStorage3D(gl.TEXTURE_2D_ARRAY, LEVELS, gl.RGBA8, LAYER_W, LAYER_H, LAYERS);
		gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
		gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
		gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
		gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
	}

	/** Bind the array to the active texture unit (an empty one before any upload). */
	bind(gl: WebGL2RenderingContext): void {
		this.#ensure(gl);
		gl.bindTexture(gl.TEXTURE_2D_ARRAY, this.#texture);
	}

	/** The WebGL context was lost: decode everything again for the new one. */
	lose(): void {
		this.#texture = null;
		this.#gl = null;
		for (const e of this.#entries.values()) {
			e.uploaded = false;
			if (!e.bitmap) void this.#decode(e).catch(() => {});
		}
	}

	destroy(): void {
		if (this.#gl && this.#texture && !this.#gl.isContextLost()) this.#gl.deleteTexture(this.#texture);
		for (const k of [...this.#entries.keys()]) this.#drop(k);
		this.#texture = null;
		this.#gl = null;
	}
}
