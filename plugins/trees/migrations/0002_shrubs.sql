-- Shrubs (docs/19 §19.8): woody plants 0.3-2.4 m tall found in the lidar, one row per shrub, from the same lidar
-- products as the trees plus the summer photo's near-infrared. Our own data, from public sources only (USGS 3DEP lidar,
-- USDA NAIP; farm's crop cover to leave crops alone): nothing here comes from a tree catalogue.
--
-- Licence (plan C3): each build records the licence class, republish and credit of what it wrote, the strictest of its
-- inputs' by the export contract's rules (basemap/ground/manifest.py): today the lidar and NAIP (public domain) and
-- farm's crop cover (CSB and CDL, public domain; Sentinel-2, Copernicus), so licence Copernicus, republish yes. The
-- build refuses an input that may not be republished; a shrub's licence is its build's.
--
-- Rolling back (this migration only; trees.build, trees.tree and trees.tree_log stay), in one transaction:
--   drop view trees.shrub_area; drop table trees.shrub; drop table trees.shrub_build;
--   delete from ops.schema_migration where name = 'trees/0002_shrubs.sql';

-- One build of one area: where it looked (its lidar, less any part left to another area), what it read, its licence,
-- settings and counts (the crop check, the score). Builds stay as the area's history; an area's newest loaded build is
-- its current one.
CREATE TABLE trees.shrub_build (
    build_id    text PRIMARY KEY,
    area        text NOT NULL,
    started_at  timestamptz NOT NULL,
    finished_at timestamptz,
    loaded_at   timestamptz NOT NULL DEFAULT now(),
    geom        geometry(MultiPolygon, 4326) NOT NULL,
    inputs      jsonb NOT NULL DEFAULT '{}',   -- lidar, photo, crop: source or export, licence, files, sha256
    license     text NOT NULL CHECK (btrim(license) <> ''),   -- a licence class of basemap/ground/manifest.py
    republish   text NOT NULL CHECK (republish IN ('yes', 'aggregates', 'internal', 'no')),
    credit      text NOT NULL CHECK (btrim(credit) <> ''),
    params      jsonb NOT NULL DEFAULT '{}',
    counts      jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX shrub_build_area_idx ON trees.shrub_build (area, loaded_at DESC);

-- One row per shrub. A rebuild of an area replaces its rows.
CREATE TABLE trees.shrub (
    shrub_id  text PRIMARY KEY,                     -- '<area>-<easting dm>-<northing dm>' in the build's UTM grid
    area      text NOT NULL,
    look      text NOT NULL CHECK (look IN ('bush', 'sage')),   -- bush: green in the photo; sage: not green
    geom      geometry(Point, 4326) NOT NULL,       -- the shrub's centre
    ground_m  real,                                 -- ground elevation under it (the lidar's datum), when known
    height_m  real NOT NULL CHECK (height_m BETWEEN real '0.3' AND real '2.4'),   -- compared as real, as stored
    width_m   real NOT NULL CHECK (width_m > 0),    -- crown width (diameter)
    lidar     text,                                 -- the survey its height comes from
    fit       jsonb NOT NULL DEFAULT '{}',          -- cells, green share, split into how many, the model's width
    build_id  text NOT NULL REFERENCES trees.shrub_build (build_id)
);
CREATE INDEX shrub_geom_idx ON trees.shrub USING gist (geom);
CREATE INDEX shrub_area_idx ON trees.shrub (area);

-- Where shrubs are built: each area's current build, its outline (deserts with few shrubs included) and its licence.
CREATE VIEW trees.shrub_area AS
SELECT DISTINCT ON (area) area, build_id, geom, loaded_at, coalesce(finished_at, started_at) AS built_at,
       (counts ->> 'shrubs')::int AS shrubs, license, republish, credit
FROM trees.shrub_build
ORDER BY area, loaded_at DESC, build_id DESC;

COMMENT ON TABLE trees.shrub_build IS
  'Shrub builds (docs/19 §19.8): each area''s outline, inputs, settings and counts. Licence, republish and credit per '
  'row, the strictest of its inputs'' (plan C3): USGS 3DEP lidar and USDA NAIP (public domain) and farm''s crop cover '
  '(USDA NASS CSB and CDL, public domain; Copernicus Sentinel-2), so today Copernicus, republish yes, credit "U.S. '
  'Geological Survey, 3D Elevation Program; USDA NAIP" and the crop cover''s credits';
COMMENT ON TABLE trees.shrub IS
  'Shrubs found in the lidar (docs/19 §19.8), one row each: our own data from public inputs. Licence, republish and '
  'credit are its build''s (trees.shrub_build, by build_id); today Copernicus, republish yes';
COMMENT ON VIEW trees.shrub_area IS
  'Where shrubs are built: each area''s current build, outline, shrub count, licence, republish and credit (the '
  'credit the map shows with the shrubs)';
