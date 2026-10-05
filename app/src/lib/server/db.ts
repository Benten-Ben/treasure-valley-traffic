import { error } from '@sveltejs/kit';
import postgres from 'postgres';
import { DATABASE_URL } from '$app/env/private';

let sql: postgres.Sql | undefined;

/** The shared connection pool. Throws a 503 if no database is configured. */
export function db(): postgres.Sql {
	if (!DATABASE_URL) error(503, 'The database is not configured (set DATABASE_URL).');
	sql ??= postgres(DATABASE_URL, { max: 5, idle_timeout: 30 });
	return sql;
}
