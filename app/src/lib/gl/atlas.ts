/**
 * One sprite atlas texture (shared WebGL2 helpers, docs/14 §14.8). Sprites
 * are drawn once with the canvas 2D API (route plates and numerals, rings,
 * badges) at the device pixel ratio, packed into shelves, and uploaded as one
 * premultiplied texture whenever something new was drawn. The draw functions
 * are kept, so a grown atlas or a restored WebGL context redraws everything.
 */

export interface SpriteDef {
	key: string;
	/** Size in CSS pixels. */
	width: number;
	height: number;
	/** Draw into a CSS-pixel space of width × height (already scaled for the pixel ratio). */
	draw(g: CanvasRenderingContext2D): void;
}

export interface Rect {
	x: number;
	y: number;
	w: number;
	h: number;
}

const PAD = 2;

/** Shelf packing in a fixed-width sheet that can only grow taller. */
export class ShelfPacker {
	#shelves: { y: number; h: number; x: number }[] = [];
	#bottom = 0;

	constructor(
		public width: number,
		public height: number
	) {}

	/** A place for a w × h rect (padded), or null when the sheet is full. */
	pack(w: number, h: number): { x: number; y: number } | null {
		const pw = w + PAD;
		const ph = h + PAD;
		if (pw > this.width) return null;
		for (const s of this.#shelves) {
			if (ph <= s.h && s.x + pw <= this.width) {
				const at = { x: s.x, y: s.y };
				s.x += pw;
				return at;
			}
		}
		if (this.#bottom + ph > this.height) return null;
		const shelf = { y: this.#bottom, h: ph, x: pw };
		this.#shelves.push(shelf);
		this.#bottom += ph;
		return { x: 0, y: shelf.y };
	}

	reset(height = this.height): void {
		this.height = height;
		this.#shelves = [];
		this.#bottom = 0;
	}
}

export const MAX_ATLAS = 4096;

export class SpriteAtlas {
	readonly pixelRatio: number;
	#canvas: HTMLCanvasElement | OffscreenCanvas;
	#g: CanvasRenderingContext2D;
	#packer: ShelfPacker;
	#defs = new Map<string, SpriteDef>();
	#rects = new Map<string, Rect>();
	#dirty = false;
	#texture: WebGLTexture | null = null;
	#gl: WebGL2RenderingContext | null = null;

	constructor(pixelRatio = 1, width = 1024, height = 512) {
		this.pixelRatio = pixelRatio;
		this.#canvas = typeof OffscreenCanvas !== 'undefined' ? new OffscreenCanvas(width, height) : Object.assign(document.createElement('canvas'), { width, height });
		this.#g = this.#canvas.getContext('2d') as CanvasRenderingContext2D;
		this.#packer = new ShelfPacker(width, height);
	}

	get width(): number {
		return this.#canvas.width;
	}

	get height(): number {
		return this.#canvas.height;
	}

	has(key: string): boolean {
		return this.#rects.has(key);
	}

	/** The sprite's place in device pixels, drawing it first if it's new. Null when it can't fit at all. */
	ensure(def: SpriteDef): Rect | null {
		const known = this.#rects.get(def.key);
		if (known) return known;
		this.#defs.set(def.key, def);
		if (!this.#place(def)) {
			if (!this.#grow()) {
				this.#defs.delete(def.key);
				return null;
			}
		}
		return this.#rects.get(def.key) ?? null;
	}

	rect(key: string): Rect | undefined {
		return this.#rects.get(key);
	}

	#place(def: SpriteDef): boolean {
		const pr = this.pixelRatio;
		const w = Math.ceil(def.width * pr);
		const h = Math.ceil(def.height * pr);
		const at = this.#packer.pack(w, h);
		if (!at) return false;
		const g = this.#g;
		g.save();
		g.clearRect(at.x, at.y, w, h);
		g.translate(at.x, at.y);
		g.scale(pr, pr);
		g.beginPath();
		def.draw(g);
		g.restore();
		this.#rects.set(def.key, { x: at.x, y: at.y, w, h });
		this.#dirty = true;
		return true;
	}

	/** Double the height and redraw everything; false at the size limit. */
	#grow(): boolean {
		if (this.#canvas.height >= MAX_ATLAS) return false;
		this.#canvas.height = Math.min(MAX_ATLAS, this.#canvas.height * 2);
		this.#packer.reset(this.#canvas.height);
		this.#rects.clear();
		for (const d of this.#defs.values()) if (!this.#place(d)) return this.#grow();
		this.#dirty = true;
		return true;
	}

	/** Bind the texture to the active unit, uploading what changed (or everything, for a new context). */
	bind(gl: WebGL2RenderingContext): void {
		if (this.#gl !== gl || !this.#texture) {
			this.#gl = gl;
			this.#texture = gl.createTexture();
			this.#dirty = true;
		}
		gl.bindTexture(gl.TEXTURE_2D, this.#texture);
		if (!this.#dirty) return;
		gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
		gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, this.#canvas as TexImageSource);
		gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
		this.#dirty = false;
	}

	/** Forget GPU state (the context was lost); the next bind re-uploads. */
	lose(): void {
		this.#texture = null;
		this.#gl = null;
	}

	destroy(): void {
		if (this.#gl && this.#texture) this.#gl.deleteTexture(this.#texture);
		this.lose();
	}
}
