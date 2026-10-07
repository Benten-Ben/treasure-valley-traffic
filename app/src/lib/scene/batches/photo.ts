import { SpriteAtlas } from '#lib/gl/atlas.js';
import { GrowableBuffer } from '#lib/gl/buffer.js';
import { createProgram, type Program } from '#lib/gl/program.js';
import { CREAM, INK } from '#lib/overlay/sprites.js';
import type { PhotoTextures } from '../textures.js';

/**
 * Photo planes (docs/14 §14.6, "The photo in the cone"; §14.8, "Drawing":
 * last, after the cones). A framed quad inside the view cone: the front shows
 * the picture (a layer of the photo texture array) with a thin cream frame,
 * and the back is a cream panel with the camera's name. Blended, no depth
 * writes; planes that ask for it (look-through) draw without the depth test,
 * so nothing in front can cut them.
 */
export const PHOTO_FLOATS = 11; // position 3, uv 2, layer 1, back label rect 4, opacity 1

const VERTEX = `#version 300 es
layout(location = 0) in vec3 a_pos;
layout(location = 1) in vec2 a_uv;
layout(location = 2) in float a_layer;
layout(location = 3) in vec4 a_back;
layout(location = 4) in float a_opacity;
uniform mat4 u_m;
out vec2 v_uv;
out float v_layer;
out vec4 v_back;
out float v_opacity;
void main() {
	gl_Position = u_m * vec4(a_pos, 1.0);
	v_uv = a_uv;
	v_layer = a_layer;
	v_back = a_back;
	v_opacity = a_opacity;
}`;

const FRAGMENT = `#version 300 es
precision highp float;
precision mediump sampler2DArray;
in vec2 v_uv;
in float v_layer;
in vec4 v_back;
in float v_opacity;
uniform sampler2DArray u_photos;
uniform sampler2D u_labels;
uniform float u_edge;
out vec4 color;
const vec3 CREAM = vec3(1.0, 0.984, 0.957);
void main() {
	vec4 c;
	if (gl_FrontFacing) {
		float e = min(min(v_uv.x, 1.0 - v_uv.x), min(v_uv.y, 1.0 - v_uv.y));
		if (e < u_edge || v_layer < 0.0) c = vec4(CREAM, 1.0);
		else c = vec4(texture(u_photos, vec3(v_uv, v_layer)).rgb, 1.0);
	} else {
		// The back: a cream panel with the name, unmirrored.
		vec4 l = texture(u_labels, mix(v_back.xy, v_back.zw, vec2(1.0 - v_uv.x, v_uv.y)));
		c = vec4(CREAM * (1.0 - l.a) + l.rgb, 1.0);
	}
	color = c * v_opacity;
}`;

export class PhotoBatch {
	#gl: WebGL2RenderingContext;
	#p: Program;
	#buf: GrowableBuffer;
	#vao: WebGLVertexArrayObject;
	readonly labels: SpriteAtlas;

	constructor(gl: WebGL2RenderingContext, labels: SpriteAtlas) {
		this.#gl = gl;
		this.labels = labels;
		this.#p = createProgram(gl, VERTEX, FRAGMENT, [], ['u_m', 'u_photos', 'u_labels', 'u_edge']);
		this.#buf = new GrowableBuffer(gl);
		const vao = gl.createVertexArray();
		if (!vao) throw new Error('no vertex array');
		this.#vao = vao;
		gl.bindVertexArray(vao);
		gl.bindBuffer(gl.ARRAY_BUFFER, this.#buf.buffer);
		const stride = PHOTO_FLOATS * 4;
		for (const [loc, size, offset] of [
			[0, 3, 0],
			[1, 2, 3],
			[2, 1, 5],
			[3, 4, 6],
			[4, 1, 10]
		]) {
			gl.enableVertexAttribArray(loc);
			gl.vertexAttribPointer(loc, size, gl.FLOAT, false, stride, offset * 4);
		}
		gl.bindVertexArray(null);
	}

	/** The back panel's label sprite for a name; returns its rect in atlas uv. */
	label(text: string): [number, number, number, number] {
		const key = `photo-back:${text}`;
		const r = this.labels.ensure({
			key,
			width: 192,
			height: 118,
			draw(g) {
				g.fillStyle = CREAM;
				g.fillRect(0, 0, 192, 118);
				g.fillStyle = INK;
				g.font = '600 15px Overpass, system-ui, sans-serif';
				g.textAlign = 'center';
				g.textBaseline = 'middle';
				const words = text.split(/\s+/);
				const lines: string[] = [];
				for (const w of words) {
					const last = lines.at(-1);
					if (last && g.measureText(`${last} ${w}`).width <= 172) lines[lines.length - 1] = `${last} ${w}`;
					else lines.push(w);
				}
				const shown = lines.slice(0, 4);
				shown.forEach((l, i) => g.fillText(l, 96, 59 + (i - (shown.length - 1) / 2) * 19, 176));
			}
		});
		if (!r) return [0, 0, 0, 0];
		const w = this.labels.width;
		const h = this.labels.height;
		return [r.x / w, r.y / h, (r.x + r.w) / w, (r.y + r.h) / h];
	}

	/** Upload the frame's vertices (once, before drawing ranges of them). */
	upload(d: { f32: Float32Array; n: number }): void {
		if (d.n) this.#buf.upload(d.f32, d.n * PHOTO_FLOATS);
	}

	/**
	 * Draw `count` uploaded vertices from vertex `first` (6 a plane).
	 * Blending on, depth writes off; the caller sets the depth test.
	 */
	draw(first: number, count: number, m32: Float32Array, textures: PhotoTextures, edge = 0.012): number {
		if (!count) return 0;
		const gl = this.#gl;
		gl.useProgram(this.#p.program);
		gl.uniformMatrix4fv(this.#p.uniforms.u_m, false, m32);
		gl.uniform1f(this.#p.uniforms.u_edge, edge);
		gl.activeTexture(gl.TEXTURE0);
		textures.bind(gl);
		gl.uniform1i(this.#p.uniforms.u_photos, 0);
		gl.activeTexture(gl.TEXTURE1);
		this.labels.bind(gl);
		gl.uniform1i(this.#p.uniforms.u_labels, 1);
		gl.activeTexture(gl.TEXTURE0);
		gl.bindVertexArray(this.#vao);
		gl.drawArrays(gl.TRIANGLES, first, count);
		gl.bindVertexArray(null);
		return 1;
	}

	destroy(): void {
		const gl = this.#gl;
		if (gl.isContextLost()) return;
		gl.deleteProgram(this.#p.program);
		gl.deleteVertexArray(this.#vao);
		this.#buf.destroy();
	}
}
