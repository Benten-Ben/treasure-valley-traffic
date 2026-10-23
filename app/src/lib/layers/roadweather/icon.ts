import type { LayerIcon } from '../icons.js';
import RoadWeatherIcon from './RoadWeatherIcon.svelte';

/** The weather layer's toolbar icon, apart from its always-loaded def (see ../icons.ts). */
export default { id: 'weather', icon: RoadWeatherIcon } satisfies LayerIcon;
