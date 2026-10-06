#!/usr/bin/env node
/**
 * Local database clones for the UI v2 packages (docs/14 §14.10, "Rules").
 *
 *   node scripts/db.mjs template            create tvt_template from tvt (WP0 only, once)
 *   node scripts/db.mjs clone [name]        createdb -O tvt -T tvt_template <name> (default tvt_<wp>)
 *   node scripts/db.mjs drop [name]         drop a package clone
 *   node scripts/db.mjs migrate [name]      db/migrate.py, then db/pending/*.sql if that folder exists
 *   node scripts/db.mjs pending [name]      only db/pending/*.sql
 *   node scripts/db.mjs sql <name> <file>   run one SQL file in a transaction (tests and fixtures)
 *   node scripts/db.mjs url [name]          print the clone's DATABASE_URL
 *
 * The tvt role can't create databases, so creating and dropping run as the
 * postgres user over the local socket: directly when this runs as root
 * (createdb is started with postgres's uid, no shell involved), otherwise
 * through `sudo -n -u postgres` if that's allowed. Only names starting with
 * tvt_ are accepted, and tvt and tvt_template are never dropped.
 *
 * Nobody connects to tvt_template except to seed it (WP0); everyone else
 * only clones it, since a template with a connection open can't be cloned.
 */
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { databaseUrl, mainCheckout, packageName, APP_DIR } from './harness-env.mjs';

const REPO = join(APP_DIR, '..');
export const TEMPLATE = 'tvt_template';
const PROTECTED = new Set(['tvt', TEMPLATE, 'postgres', 'template0', 'template1']);

function fail(msg) {
	console.error(`db.mjs: ${msg}`);
	process.exit(1);
}

function checkName(name) {
	if (!/^tvt_[a-z0-9_]+$/.test(name)) fail(`refusing database name "${name}": use tvt_<something> (lowercase)`);
	return name;
}

function postgresIds() {
	const passwd = readFileSync('/etc/passwd', 'utf8').split('\n').find((l) => l.startsWith('postgres:'));
	if (!passwd) return null;
	const [, , uid, gid] = passwd.split(':');
	return { uid: Number(uid), gid: Number(gid) };
}

/** Run a PostgreSQL client tool as the postgres superuser (peer auth on the local socket). */
function asPostgres(tool, args) {
	const env = { PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8' };
	let r;
	if (process.getuid?.() === 0) {
		const ids = postgresIds();
		if (!ids) fail('no postgres user on this machine');
		r = spawnSync(tool, args, { uid: ids.uid, gid: ids.gid, cwd: '/tmp', env, encoding: 'utf8' });
	} else {
		r = spawnSync('sudo', ['-n', '-u', 'postgres', tool, ...args], { cwd: '/tmp', env, encoding: 'utf8' });
	}
	if (r.error) fail(`${tool}: ${r.error.message}`);
	if (r.status !== 0) fail(`${tool} ${args.join(' ')} failed:\n${r.stderr || r.stdout}`);
	return r.stdout;
}

function psqlAdmin(sql) {
	return asPostgres('psql', ['-X', '-v', 'ON_ERROR_STOP=1', '-At', '-d', 'postgres', '-c', sql]);
}

export function exists(name) {
	return psqlAdmin(`select 1 from pg_database where datname = '${checkName(name)}'`).trim() === '1';
}

export function clone(name, from = TEMPLATE) {
	checkName(name);
	if (exists(name)) {
		console.log(`${name} already exists (drop it first for a fresh copy)`);
		return;
	}
	asPostgres('createdb', ['-O', 'tvt', '-T', from, name]);
	console.log(`created ${name} from ${from}`);
}

export function drop(name) {
	checkName(name);
	if (PROTECTED.has(name)) fail(`refusing to drop ${name}`);
	asPostgres('dropdb', ['--if-exists', '--force', name]);
	console.log(`dropped ${name}`);
}

function psqlAs(name, args) {
	const url = databaseUrl(name, mainCheckout());
	return execFileSync('psql', ['-X', '-v', 'ON_ERROR_STOP=1', '-q', url, ...args], { encoding: 'utf8' });
}

/** Run a SQL file in one transaction on a clone. */
export function runSql(name, file) {
	checkName(name);
	if (name === TEMPLATE && !process.env.TVT_SEEDING_TEMPLATE) fail('only WP0 seeding touches tvt_template');
	psqlAs(name, ['-1', '-f', file]);
	console.log(`ran ${file} on ${name}`);
}

/**
 * db/pending/*.sql: migrations waiting for the owner (§14.10). Each is applied
 * once and recorded in ops.schema_migration under its own name and checksum,
 * exactly as db/migrate.py would record it after the move to db/migrations/.
 */
export function applyPending(name) {
	const dir = join(REPO, 'db', 'pending');
	if (!existsSync(dir)) {
		console.log('no db/pending/ folder: nothing pending');
		return;
	}
	const files = readdirSync(dir).filter((f) => /^\d{4}_.*\.sql$/.test(f)).sort();
	for (const f of files) {
		const sql = readFileSync(join(dir, f), 'utf8');
		const sum = createHash('sha256').update(sql).digest('hex');
		const done = psqlAs(name, ['-At', '-c', `select checksum from ops.schema_migration where name = '${f}'`]).trim();
		if (done) {
			if (done !== sum) fail(`${f} changed after it was applied to ${name}`);
			continue;
		}
		psqlAs(name, ['-1', '-f', join(dir, f), '-c',
			`insert into ops.schema_migration (name, checksum) values ('${f}', '${sum}')`]);
		console.log(`applied pending ${f} to ${name}`);
	}
}

export function migrate(name) {
	checkName(name);
	execFileSync('python3', [join(REPO, 'db', 'migrate.py')], {
		stdio: 'inherit',
		env: { ...process.env, DATABASE_URL: databaseUrl(name, mainCheckout()) }
	});
	applyPending(name);
}

const defaultName = () => {
	const wp = packageName();
	if (!wp) fail('no package found (branch wp/WPn or TVT_WP); name the database');
	return `tvt_${wp}`;
};

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
	const [cmd, arg, arg2] = process.argv.slice(2);
	switch (cmd) {
		case 'template':
			if (exists(TEMPLATE)) console.log(`${TEMPLATE} already exists`);
			else {
				asPostgres('createdb', ['-O', 'tvt', '-T', arg ?? 'tvt', TEMPLATE]);
				console.log(`created ${TEMPLATE} from ${arg ?? 'tvt'}`);
			}
			break;
		case 'clone':
			clone(arg ?? defaultName());
			break;
		case 'drop':
			drop(arg ?? defaultName());
			break;
		case 'migrate':
			migrate(arg ?? defaultName());
			break;
		case 'pending':
			applyPending(checkName(arg ?? defaultName()));
			break;
		case 'sql':
			if (!arg || !arg2) fail('usage: db.mjs sql <name> <file>');
			runSql(arg, arg2);
			break;
		case 'url':
			console.log(databaseUrl(checkName(arg ?? defaultName()), mainCheckout()));
			break;
		default:
			console.log(readFileSync(new URL(import.meta.url), 'utf8').split('*/')[0]);
			process.exit(cmd ? 1 : 0);
	}
}
