import type { CustomLayerInterface, CustomRenderMethodInput, Map } from 'maplibre-gl';
import { SpriteAtlas } from '#lib/gl/atlas.js';
import { ANCHORS } from '#lib/map/order.js';
import { ConeBatch } from './batches/cone.js';
import { MeshBatch } from './batches/mesh.js';
import { PhotoBatch } from './batches/photo.js';
import { ShadowBatch } from './batches/shadow.js';
import { allMeshes } from './meshes.js';

/**
 * The `scene-3d` custom layer (docs/14 §14.8, "The 3D engine"): slot 9, above
 * the buildings and below the 2D points, labels and overlay, with
 * `renderingMode: '3d'` so it shares the depth buffer with terrain and
 * buildings. GPU resources live in a `Gpu`, built on the first render with a
 * context and rebuilt after `webglcontextrestored` (MapLibre drops custom
 * layers when the context is lost, so the scene adds itself again).
 */
export const SCENE_LAYER = 'scene-3d';

export interface Gpu {
	gl: WebGL2RenderingContext;
	meshes: MeshBatch;
	shadows: ShadowBatch;
	cones: ConeBatch;
	photos: PhotoBatch;
}

export function createGpu(gl: WebGL2RenderingContext, labels: SpriteAtlas): Gpu {
	if (typeof WebGL2RenderingContext === 'undefined' || !(gl instanceof WebGL2RenderingContext)) throw new Error('WebGL2 is not available');
	return { gl, meshes: new MeshBatch(gl, allMeshes()), shadows: new ShadowBatch(gl), cones: new ConeBatch(gl), photos: new PhotoBatch(gl, labels) };
}

export function destroyGpu(g: Gpu | null): void {
	if (!g || g.gl.isContextLost()) return;
	g.meshes.destroy();
	g.shadows.destroy();
	g.cones.destroy();
	g.photos.destroy();
}

export interface LayerHandlers {
	onAdd(gl: WebGL2RenderingContext): void;
	onRemove(): void;
	prerender(gl: WebGL2RenderingContext, args: CustomRenderMethodInput): void;
	render(gl: WebGL2RenderingContext, args: CustomRenderMethodInput): void;
}

export function sceneLayer(h: LayerHandlers): CustomLayerInterface {
	return {
		id: SCENE_LAYER,
		type: 'custom',
		renderingMode: '3d',
		onAdd: (_m, gl) => h.onAdd(gl as WebGL2RenderingContext),
		onRemove: () => h.onRemove(),
		prerender: (gl, args) => h.prerender(gl as WebGL2RenderingContext, args),
		render: (gl, args) => h.render(gl as WebGL2RenderingContext, args)
	};
}

/** Add the layer in its slot (before `anchor:scene`), unless it's there. */
export function addSceneLayer(map: Map, layer: CustomLayerInterface): void {
	if (map.getLayer(SCENE_LAYER)) return;
	map.addLayer(layer, map.getLayer(ANCHORS.scene) ? ANCHORS.scene : undefined);
}
