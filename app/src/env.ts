import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	DATABASE_URL: {
		description: 'PostgreSQL + PostGIS connection string. Camera features answer 503 without it.',
		schema: (value) => value || undefined
	},
	FRAMES_DIR: {
		description: 'Folder where captured camera frames (calibration reference images) are kept.',
		schema: (value) => value || '../data/frames'
	}
});
