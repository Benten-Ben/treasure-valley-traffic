# End-to-end specs and the package harness

The UI v2 harness (docs/14 §14.10 "Rules", §14.11). Everything below works
from the main checkout or any worktree; run it from `app/`.

## Set up a package

```bash
node scripts/db.mjs clone              # tvt_<wp> from tvt_template (wp from the branch, wp/WP3 → wp3)
node scripts/db.mjs migrate            # db/migrate.py on the clone (new migrations), plus db/pending/ if any
npm run seed                           # seeded frames and fake archive into data/dev/<wp>/, ticked to now
node scripts/harness-env.mjs           # show the environment (password masked)
```

`tvt_template` is the local database plus WP0's seeds. Only clone it; never
connect to it (a template with a connection open can't be cloned). Creating
and dropping databases runs as the postgres user inside `db.mjs` (the `tvt`
role can't), so no `su` is needed. Drop your clone when you're done:
`node scripts/db.mjs drop`.

The environment (`TILES_DIR`, `FRAMES_DIR`, `TVT_ARCHIVE`, `DATABASE_URL`,
`TVT_FRAME_SOURCE=fixture`, `CAMERA_IMAGES_ENABLED=true`,
`TVT_E2E_REQUIRE_DATA=1`, port 5201 + n) comes from
`scripts/harness-env.mjs`. Values already set in the environment win. To run
any command with it, without `source`:

```bash
node scripts/harness-env.mjs -- vite dev --port {port} --strictPort   # or: npm run dev:wp
npm run preview:wp                                                    # build if stale, then vite preview
```

## Run specs

```bash
npm run test:e2e -- --grep @wp3        # one package's specs
npm run test:e2e                       # everything
```

The config builds when sources changed (`TVT_E2E_BUILD=1` forces it,
`TVT_E2E_BUILD=0` skips it) and serves the build with `vite preview` on the
package port. The reporter ends with the counts the hand-back needs, overall
and per tag, and writes them to `data/dev/<wp>/e2e-summary.json`.

## Write specs

- Import `test`, `expect`, `mapReady`, `seeds` and `screenPath` from
  `./fixtures.js`, not from `@playwright/test`.
- Tag every test with its package: `test('…', { tag: '@wp3' }, …)`. A
  package's tag must run more than zero tests, with none skipped.
- Missing data (manifest, seeded frames, archive, a database that answers)
  skips a spec outside the workflow and fails it with
  `TVT_E2E_REQUIRE_DATA=1`. Don't add your own skips for data.
- The browser resolves only localhost (`lockedArgs` in the config), and the
  `offsite` fixture lists any request to another origin. Don't use
  `page.route` for that: routing turns the HTTP cache off, which breaks
  cache and round-trip measurements.
- `mapReady(page)` waits for `__tvt.ready` once WP1 provides it, and until
  then for the canvas plus a quiet network.
- The seeds: `seeds()` returns `data/dev/<wp>/seed.json`: four synthetic
  calibrations (`key`, `roll`, `low-tilt`, `hd`) with their view and camera
  ids, poses, frames rendered from our own map, and how well each registers
  (map.project against the solver's pixels). Use these, never a real
  camera image.
- A POST from a test needs `headers: { origin }` (SvelteKit's CSRF check);
  the browser sends it by itself.
- Evidence (screenshots, numbers) goes under `screenPath(name)`, which is
  `data/dev/screens/<wp>/`.
- Expected-to-fail specs (`test.fail`) mark targets a later package meets:
  `persistent` and the data-start check (WP1), the first-load budget (WP5).
  The package that meets one removes its `test.fail` line.

## Other tools

- `node scripts/perf.mjs --budget` (S1–S3, S6; `--runs`, `--scenarios`) and
  `node scripts/bundle-budget.mjs`: docs/14 §14.9.
- `node scripts/archive-tick.ts [image …]`: append a new frame to the fake
  archive, as the capture service would.
- `python3 ../tools/check_public.py`: what would be pushed, checked for
  private material.
