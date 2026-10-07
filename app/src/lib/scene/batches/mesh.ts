import { GrowableBuffer, staticBuffer } from '#lib/gl/buffer.js';
import { createProgram, type Program } from '#lib/gl/program.js';
import { FLOATS_PER_VERTEX, type Mesh, type MeshKind } from '../meshes.js';

/**
 * Instanced meshes (docs/14 §14.8, "Drawing"): one instanced draw per mesh
 * type, all with one program. Instances carry float32 metres from the
 * frame's origin (rtc.ts), their model axes (rotation and scale), color and
 * opacity, four slot colors and a hover tint.
 *
 * Lighting is flat and high-ambient: faces darken at most 30%, and faces in
 * the instance's color (tint ≥ 1) at most 12%, so the validated route hue
 * survives. Opacity below 1 (the disc-to-model crossfade) is a screen-door
 * dither, which keeps depth right without sorting.
 */
export const INSTANCE_FLOATS = 21; // offset 3, axes 9, color 4, slots 4 (uint), hover 1

/** The placement every mesh shader and the probe share, so the probe measures what's drawn. */
const PLACE = `
layout(location = 4) in vec3 i_offset;
layout(location = 5) in vec3 i_bx;
layout(location = 6) in vec3 i_by;
layout(location = 7) in vec3 i_bz;
uniform mat4 u_m;
vec3 place(vec3 l) { return i_offset + i_bx * l.x + i_by * l.y + i_bz * l.z; }
`;

const VERTEX = `#version 300 es
layout(location = 0) in vec3 a_pos;
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec3 a_color;
layout(location = 3) in float a_tint;
${PLACE}
layout(location = 8) in vec4 i_color;
layout(location = 9) in uvec4 i_slots;
layout(location = 10) in float i_hover;
uniform vec3 u_light;
out vec3 v_color;
out float v_alpha;
vec3 unpack(uint c) { return vec3(float((c >> 24) & 255u), float((c >> 16) & 255u), float((c >> 8) & 255u)) / 255.0; }
void main() {
	gl_Position = u_m * vec4(place(a_pos), 1.0);
	vec3 n = normalize(i_bx * a_normal.x + i_by * a_normal.y + i_bz * a_normal.z);
	vec3 c = a_color;
	float alpha = i_color.a;
	float dark = 0.3;
	int t = int(a_tint + 0.5);
	if (t == 1) {
		c = i_color.rgb;
		dark = 0.12;
	} else if (t >= 2) {
		uint s = i_slots[t - 2];
		c = unpack(s);
		dark = 0.12;
		if ((s & 255u) == 0u) alpha = 0.0;
	}
	c *= 1.0 - dark * (1.0 - max(dot(n, u_light), 0.0));
	v_color = mix(c, vec3(1.0, 0.984, 0.957), 0.4 * i_hover);
	v_alpha = alpha;
}`;

const FRAGMENT = `#version 300 es
precision highp float;
in vec3 v_color;
in float v_alpha;
out vec4 color;
float bayer(ivec2 p) {
	int i = (p.x & 3) + 4 * (p.y & 3);
	int m[16] = int[16](0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5);
	return (float(m[i]) + 0.5) / 16.0;
}
void main() {
	if (v_alpha < 0.999 && v_alpha <= bayer(ivec2(gl_FragCoord.xy))) discard;
	color = vec4(v_color, 1.0);
}`;

/** Transform feedback of each instance's projected anchor (tests and the spike gate only). */
const PROBE_VERTEX = `#version 300 es
${PLACE}
uniform vec3 u_local;
out vec4 v_clip;
void main() {
	v_clip = u_m * vec4(place(u_local), 1.0);
	gl_Position = v_clip;
}`;

const PROBE_FRAGMENT = `#version 300 es
precision mediump float;
out vec4 color;
void main() { color = vec4(0.0); }`;

interface KindGpu {
	vao: WebGLVertexArrayObject;
	vbo: WebGLBuffer;
	ibo: WebGLBuffer;
	instances: GrowableBuffer;
	indexCount: number;
}

/** Instance data for one mesh kind this frame. */
export class InstanceData {
	buf = new ArrayBuffer(INSTANCE_FLOATS * 4 * 64);
	f32 = new Float32Array(this.buf);
	u32 = new Uint32Array(this.buf);
	n = 0;

	reset(): void {
		this.n = 0;
	}

	/** Room for one more; returns its float offset. */
	push(): number {
		if ((this.n + 1) * INSTANCE_FLOATS > this.f32.length) {
			const next = new ArrayBuffer(this.buf.byteLength * 2);
			new Uint8Array(next).set(new Uint8Array(this.buf));
			this.buf = next;
			this.f32 = new Float32Array(next);
			this.u32 = new Uint32Array(next);
		}
		return this.n++ * INSTANCE_FLOATS;
	}
}

export class MeshBatch {
	#gl: WebGL2RenderingContext;
	#program: Program;
	#probe: Program | null = null;
	#tf: WebGLTransformFeedback | null = null;
	#tfBuffer: WebGLBuffer | null = null;
	#tfBytes = 0;
	#kinds = new Map<MeshKind, KindGpu>();

	constructor(gl: WebGL2RenderingContext, meshes: Record<MeshKind, Mesh>) {
		this.#gl = gl;
		this.#program = createProgram(gl, VERTEX, FRAGMENT, [], ['u_m', 'u_light']);
		for (const [kind, mesh] of Object.entries(meshes) as [MeshKind, Mesh][]) this.#kinds.set(kind, this.#upload(mesh));
	}

	#upload(mesh: Mesh): KindGpu {
		const gl = this.#gl;
		const vao = gl.createVertexArray();
		if (!vao) throw new Error('no vertex array');
		gl.bindVertexArray(vao);
		const vbo = staticBuffer(gl, mesh.vertices);
		const stride = FLOATS_PER_VERTEX * 4;
		const vattr = (loc: number, size: number, offset: number) => {
			gl.enableVertexAttribArray(loc);
			gl.vertexAttribPointer(loc, size, gl.FLOAT, false, stride, offset * 4);
		};
		vattr(0, 3, 0);
		vattr(1, 3, 3);
		vattr(2, 3, 6);
		vattr(3, 1, 9);
		const ibo = staticBuffer(gl, mesh.indices, gl.ELEMENT_ARRAY_BUFFER);
		const instances = new GrowableBuffer(gl);
		gl.bindBuffer(gl.ARRAY_BUFFER, instances.buffer);
		const istride = INSTANCE_FLOATS * 4;
		const iattr = (loc: number, size: number, offset: number) => {
			gl.enableVertexAttribArray(loc);
			gl.vertexAttribPointer(loc, size, gl.FLOAT, false, istride, offset * 4);
			gl.vertexAttribDivisor(loc, 1);
		};
		iattr(4, 3, 0);
		iattr(5, 3, 3);
		iattr(6, 3, 6);
		iattr(7, 3, 9);
		iattr(8, 4, 12);
		gl.enableVertexAttribArray(9);
		gl.vertexAttribIPointer(9, 4, gl.UNSIGNED_INT, istride, 16 * 4);
		gl.vertexAttribDivisor(9, 1);
		iattr(10, 1, 20);
		gl.bindVertexArray(null);
		return { vao, vbo, ibo, instances, indexCount: mesh.indices.length };
	}

	/**
	 * Draw each kind's instances (opaque pass: depth test and write on, no
	 * blending). Returns the number of draw calls made.
	 */
	draw(data: Map<MeshKind, InstanceData>, m32: Float32Array, light: [number, number, number]): number {
		const gl = this.#gl;
		const p = this.#program;
		let calls = 0;
		gl.useProgram(p.program);
		gl.uniformMatrix4fv(p.uniforms.u_m, false, m32);
		gl.uniform3f(p.uniforms.u_light, light[0], light[1], light[2]);
		for (const [kind, d] of data) {
			if (!d.n) continue;
			const k = this.#kinds.get(kind);
			if (!k) continue;
			gl.bindVertexArray(k.vao);
			k.instances.upload(d.f32, d.n * INSTANCE_FLOATS);
			gl.drawElementsInstanced(gl.TRIANGLES, k.indexCount, gl.UNSIGNED_SHORT, 0, d.n);
			calls++;
		}
		gl.bindVertexArray(null);
		return calls;
	}

	/**
	 * Run the placement on the GPU for each instance of `kind` (already
	 * uploaded by `draw` this frame) at model point `local`, and read the clip
	 * positions back. Tests and the spike gate only: it stalls the pipeline.
	 */
	probe(kind: MeshKind, n: number, m32: Float32Array, local: [number, number, number] = [0, 0, 0]): Float32Array {
		const gl = this.#gl;
		const k = this.#kinds.get(kind);
		if (!k || !n) return new Float32Array(0);
		if (!this.#probe) {
			const vs = gl.createShader(gl.VERTEX_SHADER)!;
			gl.shaderSource(vs, PROBE_VERTEX);
			gl.compileShader(vs);
			const fs = gl.createShader(gl.FRAGMENT_SHADER)!;
			gl.shaderSource(fs, PROBE_FRAGMENT);
			gl.compileShader(fs);
			const program = gl.createProgram()!;
			gl.attachShader(program, vs);
			gl.attachShader(program, fs);
			gl.transformFeedbackVaryings(program, ['v_clip'], gl.SEPARATE_ATTRIBS);
			gl.linkProgram(program);
			if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(`probe failed to link: ${gl.getProgramInfoLog(program)} ${gl.getShaderInfoLog(vs)}`);
			this.#probe = { program, attribs: {}, uniforms: { u_m: gl.getUniformLocation(program, 'u_m'), u_local: gl.getUniformLocation(program, 'u_local') } };
			this.#tf = gl.createTransformFeedback();
			this.#tfBuffer = gl.createBuffer();
		}
		const bytes = n * 16;
		gl.bindBuffer(gl.TRANSFORM_FEEDBACK_BUFFER, this.#tfBuffer);
		if (bytes > this.#tfBytes) {
			this.#tfBytes = bytes;
			gl.bufferData(gl.TRANSFORM_FEEDBACK_BUFFER, bytes, gl.STREAM_READ);
		}
		gl.bindBuffer(gl.TRANSFORM_FEEDBACK_BUFFER, null);
		const pr = this.#probe;
		gl.useProgram(pr.program);
		gl.uniformMatrix4fv(pr.uniforms.u_m, false, m32);
		gl.uniform3f(pr.uniforms.u_local, local[0], local[1], local[2]);
		gl.bindVertexArray(k.vao);
		gl.enable(gl.RASTERIZER_DISCARD);
		gl.bindTransformFeedback(gl.TRANSFORM_FEEDBACK, this.#tf);
		gl.bindBufferBase(gl.TRANSFORM_FEEDBACK_BUFFER, 0, this.#tfBuffer);
		gl.beginTransformFeedback(gl.POINTS);
		gl.drawArraysInstanced(gl.POINTS, 0, 1, n);
		gl.endTransformFeedback();
		gl.bindBufferBase(gl.TRANSFORM_FEEDBACK_BUFFER, 0, null);
		gl.bindTransformFeedback(gl.TRANSFORM_FEEDBACK, null);
		gl.disable(gl.RASTERIZER_DISCARD);
		gl.bindVertexArray(null);
		const out = new Float32Array(n * 4);
		gl.bindBuffer(gl.COPY_READ_BUFFER, this.#tfBuffer);
		gl.getBufferSubData(gl.COPY_READ_BUFFER, 0, out);
		gl.bindBuffer(gl.COPY_READ_BUFFER, null);
		return out;
	}

	destroy(): void {
		const gl = this.#gl;
		if (gl.isContextLost()) return;
		gl.deleteProgram(this.#program.program);
		if (this.#probe) gl.deleteProgram(this.#probe.program);
		if (this.#tf) gl.deleteTransformFeedback(this.#tf);
		if (this.#tfBuffer) gl.deleteBuffer(this.#tfBuffer);
		for (const k of this.#kinds.values()) {
			gl.deleteVertexArray(k.vao);
			gl.deleteBuffer(k.vbo);
			gl.deleteBuffer(k.ibo);
			k.instances.destroy();
		}
		this.#kinds.clear();
	}
}
