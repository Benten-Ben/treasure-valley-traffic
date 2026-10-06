/**
 * A vertex buffer that grows to fit (shared WebGL2 helpers, docs/14 §14.8).
 * Instance data is rewritten every frame something moves, so it's a
 * DYNAMIC_DRAW buffer reallocated only when it must grow.
 */
export class GrowableBuffer {
	buffer: WebGLBuffer;
	#bytes = 0;

	constructor(
		private gl: WebGL2RenderingContext,
		private usage: number = gl.DYNAMIC_DRAW
	) {
		const b = gl.createBuffer();
		if (!b) throw new Error('could not create a buffer');
		this.buffer = b;
	}

	/** Upload `data` (bound to ARRAY_BUFFER afterwards). */
	upload(data: Float32Array, length = data.length): void {
		const gl = this.gl;
		gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
		const bytes = length * 4;
		if (bytes > this.#bytes) {
			this.#bytes = Math.max(bytes, this.#bytes * 2, 1024);
			gl.bufferData(gl.ARRAY_BUFFER, this.#bytes, this.usage);
		}
		gl.bufferSubData(gl.ARRAY_BUFFER, 0, data, 0, length);
	}

	destroy(): void {
		this.gl.deleteBuffer(this.buffer);
	}
}

/** A static buffer filled once. */
export function staticBuffer(gl: WebGL2RenderingContext, data: Float32Array | Uint16Array, target: number = gl.ARRAY_BUFFER): WebGLBuffer {
	const b = gl.createBuffer();
	if (!b) throw new Error('could not create a buffer');
	gl.bindBuffer(target, b);
	gl.bufferData(target, data, gl.STATIC_DRAW);
	return b;
}
