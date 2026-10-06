/**
 * Shared WebGL2 helpers (docs/14 §14.8): programs. Used by the overlay and
 * the 3D scene, never by MapLibre's own layers.
 */
export interface Program {
	program: WebGLProgram;
	attribs: Record<string, number>;
	uniforms: Record<string, WebGLUniformLocation | null>;
}

function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
	const shader = gl.createShader(type);
	if (!shader) throw new Error('could not create a shader');
	gl.shaderSource(shader, source);
	gl.compileShader(shader);
	if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS) && !gl.isContextLost()) {
		const log = gl.getShaderInfoLog(shader);
		gl.deleteShader(shader);
		throw new Error(`shader failed to compile: ${log}`);
	}
	return shader;
}

/** Compile and link a program, and look up the named attributes and uniforms. */
export function createProgram(
	gl: WebGL2RenderingContext,
	vertex: string,
	fragment: string,
	attribs: string[],
	uniforms: string[]
): Program {
	const vs = compile(gl, gl.VERTEX_SHADER, vertex);
	const fs = compile(gl, gl.FRAGMENT_SHADER, fragment);
	const program = gl.createProgram();
	if (!program) throw new Error('could not create a program');
	gl.attachShader(program, vs);
	gl.attachShader(program, fs);
	gl.linkProgram(program);
	gl.deleteShader(vs);
	gl.deleteShader(fs);
	if (!gl.getProgramParameter(program, gl.LINK_STATUS) && !gl.isContextLost()) {
		const log = gl.getProgramInfoLog(program);
		gl.deleteProgram(program);
		throw new Error(`program failed to link: ${log}`);
	}
	return {
		program,
		attribs: Object.fromEntries(attribs.map((a) => [a, gl.getAttribLocation(program, a)])),
		uniforms: Object.fromEntries(uniforms.map((u) => [u, gl.getUniformLocation(program, u)]))
	};
}
