import { GrowableBuffer } from '#lib/gl/buffer.js';
import { createProgram, type Program } from '#lib/gl/program.js';

/**
 * View cones and edge lines (docs/14 §14.6, "What a camera looks like";
 * §14.8, "Drawing": cones are blended, with no depth write).
 *
 * - Cones: an apex and a ring of ray ends, fanned into translucent
 *   triangles. Each vertex is float32 metres from the frame's origin.
 * - Lines: segments of a fixed screen width (frustum edges to the footprint
 *   corners, the "moved camera" ground line), expanded in the vertex
 *   shader; an end behind the camera is clipped to just in front of it.
 *
 * One draw call each, for every cone and every line in the scene.
 */
export const CONE_FLOATS = 7; // position 3, premultiplied color 4
export const LINE_FLOATS = 13; // a 3, b 3, t 1, side 1, color 4, width 1

const CONE_VERTEX = `#version 300 es
layout(location = 0) in vec3 a_pos;
layout(location = 1) in vec4 a_color;
uniform mat4 u_m;
out vec4 v_color;
void main() {
	gl_Position = u_m * vec4(a_pos, 1.0);
	v_color = a_color;
}`;

const CONE_FRAGMENT = `#version 300 es
precision mediump float;
in vec4 v_color;
out vec4 color;
void main() { color = v_color; }`;

const LINE_VERTEX = `#version 300 es
layout(location = 0) in vec3 a_a;
layout(location = 1) in vec3 a_b;
layout(location = 2) in float a_t;
layout(location = 3) in float a_side;
layout(location = 4) in vec4 a_color;
layout(location = 5) in float a_width;
uniform mat4 u_m;
uniform vec2 u_viewport;
uniform float u_near;
out vec4 v_color;
void main() {
	vec4 ca = u_m * vec4(a_a, 1.0);
	vec4 cb = u_m * vec4(a_b, 1.0);
	if (ca.w < u_near && cb.w < u_near) { gl_Position = vec4(0.0, 0.0, 2.0, 1.0); v_color = vec4(0.0); return; }
	if (ca.w < u_near) ca = mix(ca, cb, (u_near - ca.w) / (cb.w - ca.w));
	if (cb.w < u_near) cb = mix(cb, ca, (u_near - cb.w) / (ca.w - cb.w));
	vec2 hv = u_viewport * 0.5;
	vec2 sa = ca.xy / ca.w * hv;
	vec2 sb = cb.xy / cb.w * hv;
	vec2 d = sb - sa;
	vec2 dir = length(d) > 1e-6 ? normalize(d) : vec2(1.0, 0.0);
	vec2 n = vec2(-dir.y, dir.x);
	vec4 c = a_t < 0.5 ? ca : cb;
	c.xy += n * a_side * a_width * 0.5 / hv * c.w;
	gl_Position = c;
	v_color = a_color;
}`;

/** A growable float array for a frame's vertices. */
export class Floats {
	f32: Float32Array;
	n = 0;

	constructor(
		public stride: number,
		initial = 256
	) {
		this.f32 = new Float32Array(stride * initial);
	}

	reset(): void {
		this.n = 0;
	}

	push(): number {
		if ((this.n + 1) * this.stride > this.f32.length) {
			const next = new Float32Array(this.f32.length * 2);
			next.set(this.f32);
			this.f32 = next;
		}
		return this.n++ * this.stride;
	}
}

function vao(gl: WebGL2RenderingContext, buffer: WebGLBuffer, stride: number, attrs: [number, number, number][]): WebGLVertexArrayObject {
	const v = gl.createVertexArray();
	if (!v) throw new Error('no vertex array');
	gl.bindVertexArray(v);
	gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
	for (const [loc, size, offset] of attrs) {
		gl.enableVertexAttribArray(loc);
		gl.vertexAttribPointer(loc, size, gl.FLOAT, false, stride * 4, offset * 4);
	}
	gl.bindVertexArray(null);
	return v;
}

export class ConeBatch {
	#gl: WebGL2RenderingContext;
	#cone: Program;
	#line: Program;
	#coneBuf: GrowableBuffer;
	#lineBuf: GrowableBuffer;
	#coneVao: WebGLVertexArrayObject;
	#lineVao: WebGLVertexArrayObject;

	constructor(gl: WebGL2RenderingContext) {
		this.#gl = gl;
		this.#cone = createProgram(gl, CONE_VERTEX, CONE_FRAGMENT, [], ['u_m']);
		this.#line = createProgram(gl, LINE_VERTEX, CONE_FRAGMENT, [], ['u_m', 'u_viewport', 'u_near']);
		this.#coneBuf = new GrowableBuffer(gl);
		this.#lineBuf = new GrowableBuffer(gl);
		this.#coneVao = vao(gl, this.#coneBuf.buffer, CONE_FLOATS, [
			[0, 3, 0],
			[1, 4, 3]
		]);
		this.#lineVao = vao(gl, this.#lineBuf.buffer, LINE_FLOATS, [
			[0, 3, 0],
			[1, 3, 3],
			[2, 1, 6],
			[3, 1, 7],
			[4, 4, 8],
			[5, 1, 12]
		]);
	}

	/** Cone triangles (blended, no depth write). Returns draw calls made. */
	drawCones(d: Floats, m32: Float32Array): number {
		if (!d.n) return 0;
		const gl = this.#gl;
		gl.useProgram(this.#cone.program);
		gl.uniformMatrix4fv(this.#cone.uniforms.u_m, false, m32);
		gl.bindVertexArray(this.#coneVao);
		this.#coneBuf.upload(d.f32, d.n * CONE_FLOATS);
		gl.drawArrays(gl.TRIANGLES, 0, d.n);
		gl.bindVertexArray(null);
		return 1;
	}

	/** Lines (6 vertices a segment). `near` is the clip w below which an end is behind the camera. */
	drawLines(d: Floats, m32: Float32Array, width: number, height: number, near: number): number {
		if (!d.n) return 0;
		const gl = this.#gl;
		gl.useProgram(this.#line.program);
		gl.uniformMatrix4fv(this.#line.uniforms.u_m, false, m32);
		gl.uniform2f(this.#line.uniforms.u_viewport, width, height);
		gl.uniform1f(this.#line.uniforms.u_near, near);
		gl.bindVertexArray(this.#lineVao);
		this.#lineBuf.upload(d.f32, d.n * LINE_FLOATS);
		gl.drawArrays(gl.TRIANGLES, 0, d.n);
		gl.bindVertexArray(null);
		return 1;
	}

	destroy(): void {
		const gl = this.#gl;
		if (gl.isContextLost()) return;
		gl.deleteProgram(this.#cone.program);
		gl.deleteProgram(this.#line.program);
		gl.deleteVertexArray(this.#coneVao);
		gl.deleteVertexArray(this.#lineVao);
		this.#coneBuf.destroy();
		this.#lineBuf.destroy();
	}
}
