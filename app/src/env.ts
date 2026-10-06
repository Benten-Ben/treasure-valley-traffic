import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	DATABASE_URL: {
		description: 'PostgreSQL + PostGIS connection string. Camera features answer 503 without it.',
		schema: (value) => value || undefined
	},
	FRAMES_DIR: {
		description: 'Folder where captured camera frames (calibration reference images) are kept.',
		schema: (value) => value || '../data/frames'
	},
	TVT_FRAME_SOURCE: {
		description:
			"Where camera frames come from: '511' (default, 511 Idaho's republished images) or 'fixture' " +
			'(seeded frames under FRAMES_DIR/_fixture; nothing is fetched). Tests and build agents use fixture.',
		schema: (value): '511' | 'fixture' => {
			if (!value || value === '511') return '511';
			if (value === 'fixture') return 'fixture';
			throw new Error(`TVT_FRAME_SOURCE must be '511' or 'fixture', not '${value}'`);
		}
	}
});
