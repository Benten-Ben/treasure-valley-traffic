/**
 * The layer icons (always loaded: the layer defs carry them): Phosphor (MIT, https://phosphoricons.com),
 * duotone weight (docs/13 §13.7, docs/14 §14.3).
 *
 * phosphor-svelte's components carry all six weights of every icon, about
 * 1 KB gzip each, which the initial bundle can't afford (docs/14 §14.9:
 * 330 KB with the overlay). So the toolbar's and top bar's icons keep only
 * their duotone paths here, copied from phosphor-svelte; `icons.test.ts`
 * checks them against the installed package, so they can't drift. Lazily
 * loaded parts of the app can deep-import phosphor-svelte components
 * directly (`phosphor-svelte/lib/<Name>Icon`); `Icon.svelte` draws either.
 */
export interface IconData {
	/** phosphor-svelte's name, without the `Icon` suffix. */
	name: string;
	/** The duotone weight's light (20% opacity) path. */
	tone: string;
	/** The duotone weight's line path. */
	line: string;
}

export const BUS: IconData = {
	name: 'Bus',
	tone: 'M48,184H88v24a8,8,0,0,1-8,8H56a8,8,0,0,1-8-8Zm120,24a8,8,0,0,0,8,8h24a8,8,0,0,0,8-8V184H168ZM48,72v40H208V72Z',
	line: 'M184,32H72A32,32,0,0,0,40,64V208a16,16,0,0,0,16,16H80a16,16,0,0,0,16-16V192h64v16a16,16,0,0,0,16,16h24a16,16,0,0,0,16-16V64A32,32,0,0,0,184,32ZM56,176V120H200v56Zm0-96H200v24H56ZM72,48H184a16,16,0,0,1,16,16H56A16,16,0,0,1,72,48Zm8,160H56V192H80Zm96,0V192h24v16Zm-72-60a12,12,0,1,1-12-12A12,12,0,0,1,104,148Zm72,0a12,12,0,1,1-12-12A12,12,0,0,1,176,148Zm72-68v24a8,8,0,0,1-16,0V80a8,8,0,0,1,16,0ZM24,80v24a8,8,0,0,1-16,0V80a8,8,0,0,1,16,0Z'
};

export const ROAD_HORIZON: IconData = {
	name: 'RoadHorizon',
	tone: 'M232,192H24L96,64h64Z',
	line: 'M235.92,199A8,8,0,0,1,225,195.92L155.32,72H136v8a8,8,0,0,1-16,0V72H100.68L31,195.92A8,8,0,0,1,17,188.08L82.32,72H24a8,8,0,0,1,0-16H232a8,8,0,0,1,0,16H173.68L239,188.08A8,8,0,0,1,235.92,199ZM128,112a8,8,0,0,0-8,8v16a8,8,0,0,0,16,0V120A8,8,0,0,0,128,112Zm0,56a8,8,0,0,0-8,8v16a8,8,0,0,0,16,0V176A8,8,0,0,0,128,168Z'
};

export const SECURITY_CAMERA: IconData = {
	name: 'SecurityCamera',
	tone: 'M221.66,85.66l-120,120a8,8,0,0,1-11.32,0L52.69,168,184,36.69l37.66,37.65A8,8,0,0,1,221.66,85.66Z',
	line: 'M248,136a8,8,0,0,0-8,8v16H195.31L177,141.66l50.34-50.35a16,16,0,0,0,0-22.62l-56-56a16,16,0,0,0-22.63,0L2.92,158.94A10,10,0,0,0,10,176H49.37l35.32,35.31a16,16,0,0,0,22.62,0L165.66,153,184,171.31A15.86,15.86,0,0,0,195.31,176H240v16a8,8,0,0,0,16,0V144A8,8,0,0,0,248,136ZM160,24l12.69,12.69L49.37,160H24.46ZM96,200,64,168,184,48l32,32Z'
};

export const LAYER_ICONS: readonly IconData[] = [BUS, ROAD_HORIZON, SECURITY_CAMERA];
