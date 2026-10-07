import { ROAD_HORIZON, type IconData } from '#lib/ui/icons.js';

/**
 * The road-weather icon (docs/14 §14.6, "Road weather": "a thermometer-and-road
 * icon"): two Phosphor (MIT) duotone icons, ThermometerSimple and
 * RoadHorizon, set side by side in one 256 × 256 box. The paths are copied
 * from phosphor-svelte and checked against it by `icons.test.ts`, so this
 * always-loaded file carries only the paths. The toolbar draws it as SVG
 * (RoadWeatherIcon.svelte), the map's station badges on a canvas (badges.ts).
 */
export const THERMOMETER: IconData = {
	name: 'ThermometerSimple',
	tone: 'M160,138V48a32,32,0,0,0-64,0v90a56,56,0,1,0,64,0Zm-32,70a24,24,0,1,1,24-24A24,24,0,0,1,128,208Z',
	line: 'M136,153V88a8,8,0,0,0-16,0v65a32,32,0,1,0,16,0Zm-8,47a16,16,0,1,1,16-16A16,16,0,0,1,128,200Zm40-66V48a40,40,0,0,0-80,0v86a64,64,0,1,0,80,0Zm-40,98a48,48,0,0,1-27.42-87.4A8,8,0,0,0,104,138V48a24,24,0,0,1,48,0v90a8,8,0,0,0,3.42,6.56A48,48,0,0,1,128,232Z'
};

export { ROAD_HORIZON };

/** One part of the composite: an icon, scaled by `scale` and moved by (x, y), in the 256 box. */
export interface IconPart {
	icon: IconData;
	scale: number;
	x: number;
	y: number;
}

/** The thermometer upper left, the road lower right; together they span about x 8–246, y 22–231. */
export const ROAD_WEATHER_ICON: readonly IconPart[] = [
	{ icon: THERMOMETER, scale: 0.72, x: -38, y: 16 },
	{ icon: ROAD_HORIZON, scale: 0.62, x: 98, y: 108 }
];

/** SVG `transform` for a part. */
export const partTransform = (p: IconPart) => `translate(${p.x} ${p.y}) scale(${p.scale})`;
