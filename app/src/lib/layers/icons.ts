import type { LayerId } from './types.js';
import type { Icon } from './types.js';

/**
 * The layers' toolbar and legend icons. They live in `<layer>/icon.ts`, not in the always-loaded
 * `def.ts`: only the map chrome draws them, and that is its own chunk, so their path data (about
 * 3.4 KB gzip across the layers) stays out of the initial JavaScript (docs/14 §14.9). Like the
 * defs, each `icon.ts` is found by glob, so a package adds its icon by adding the file.
 */
export interface LayerIcon {
	id: LayerId;
	icon: Icon;
}

const found = import.meta.glob<{ default: LayerIcon }>('./*/icon.ts', { eager: true });

const ICONS = new Map<string, Icon>(Object.values(found).map((m) => [m.default.id, m.default.icon]));

/** A layer's icon (one the layer's def names itself wins). Only the chrome may import this file. */
export function layerIcon(def: { id: string; icon?: Icon }): Icon {
	return def.icon ?? ICONS.get(def.id) ?? ICONS.get('streets')!;
}
