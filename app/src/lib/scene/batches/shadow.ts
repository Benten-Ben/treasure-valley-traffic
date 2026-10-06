import { GrowableBuffer, staticBuffer } from '#lib/gl/buffer.js';
import { createProgram, type Program } from '#lib/gl/program.js';

/**
 * Blob shadows (docs/14 §14.8, "Drawing": opaque models, then blob shadows):
 * a soft ink ellipse on the ground under each model that asks for one,
 * blended, with depth test on and depth writes off. One instanced draw.
 */
export const SHADOW_FLOATS = 8; // centre 3, half-length vector 2, half-width vector 2, opacity 1

const VERTEX = `#version 300 es
layout(location = 0) in vec2 a_corner;
layout(location = 1) in vec3 i_center;
layout(location = 2) in vec2 i_ax;
layout(location = 3) in vec2 i_ay;
layout(location = 4) in float i_opacity;
uniform mat4 u_m;
out vec2 v_uv;
out float v_opacity;
void main() {
	vec2 xy = i_center.xy + i_ax * a_corner.y + i_ay * a_corner.x;
	gl_Position = u_m * vec4(xy, i_center.z, 1.0);
	v_uv = a_corner;
	v_opacity = i_opacity;
}`;

const FRAGMENT = `#version 300 es
precision mediump float;
in vec2 v_uv;
in float v_opacity;
out vec4 color;
void main() {
	float a = v_opacity * 0.3 * (1.0 - smoothstep(0.35, 1.0, length(v_uv)));
	color = vec4(vec3(0.169, 0.165, 0.2) * a, a);
}`;

export class ShadowData {
	f32 = new Float32Array(SHADOW_FLOATS * 64);
	n = 0;

	reset(): void {
		this.n = 0;
	}

	push(): number {
		if ((this.n + 1) * SHADOW_FLOATS > this.f32.length) {
			const next = new Float32Array(this.f32.length * 2);
			next.set(this.f32);
			this.f32 = next;
		}
		return this.n++ * SHADOW_FLOATS;
	}
}

export class ShadowBatch {
	#gl: WebGL2RenderingContext;
	#p: Program;
	#vao: WebGLVertexArrayObject;
	#corners: WebGLBuffer;
	#instances: GrowableBuffer;

	constructor(gl: WebGL2RenderingContext) {
		this.#gl = gl;
		this.#p = createProgram(gl, VERTEX, FRAGMENT, [], ['u_m']);
		const vao = gl.createVertexArray();
		if (!vao) throw new Error('no vertex array');
		this.#vao = vao;
		gl.bindVertexArray(vao);
		this.#corners = staticBuffer(gl, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]));
		gl.enableVertexAttribArray(0);
		gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
		this.#instances = new GrowableBuffer(gl);
		gl.bindBuffer(gl.ARRAY_BUFFER, this.#instances.buffer);
		const stride = SHADOW_FLOATS * 4;
		const attr = (loc: number, size: number, offset: number) => {
			gl.enableVertexAttribArray(loc);
			gl.vertexAttribPointer(loc, size, gl.FLOAT, false, stride, offset * 4);
			gl.vertexAttribDivisor(loc, 1);
		};
		attr(1, 3, 0);
		attr(2, 2, 3);
		attr(3, 2, 5);
		attr(4, 1, 7);
		gl.bindVertexArray(null);
	}

	/** Blended, depth-tested, no depth writes. Returns draw calls made. */
	draw(d: ShadowData, m32: Float32Array): number {
		if (!d.n) return 0;
		const gl = this.#gl;
		gl.useProgram(this.#p.program);
		gl.uniformMatrix4fv(this.#p.uniforms.u_m, false, m32);
		gl.bindVertexArray(this.#vao);
		this.#instances.upload(d.f32, d.n * SHADOW_FLOATS);
		gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, d.n);
		gl.bindVertexArray(null);
		return 1;
	}

	destroy(): void {
		const gl = this.#gl;
		if (gl.isContextLost()) return;
		gl.deleteProgram(this.#p.program);
		gl.deleteVertexArray(this.#vao);
		gl.deleteBuffer(this.#corners);
		this.#instances.destroy();
	}
}
