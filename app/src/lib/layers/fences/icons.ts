import type { IconData } from '#lib/ui/icons.js';

/**
 * The Fences layer's icon: Phosphor's Wall (MIT), duotone, its paths copied from phosphor-svelte so the
 * always-loaded def carries only these (as `#lib/ui/icons.ts` does for the other layers); `fences.test.ts`
 * checks them against the installed package.
 */
export const WALL: IconData = {
	name: 'Wall',
	tone: 'M128,104H32V56h96Zm48,0v48H128v48h96V104Z',
	line: 'M224,48H32a8,8,0,0,0-8,8V200a8,8,0,0,0,8,8H224a8,8,0,0,0,8-8V56A8,8,0,0,0,224,48ZM88,144V112h80v32Zm-48,0V112H72v32Zm144-32h32v32H184Zm32-16H136V64h80ZM120,64V96H40V64ZM40,160h80v32H40Zm96,32V160h80v32Z'
};
