-- 0002: cameras, their image views, calibrations, and links from source
-- records to our entities (docs/12 §12.5). Intersections come in a later
-- migration and will be linked to cameras then.

-- How each source record maps to one of our entities.
create table core.source_link (
  source        text not null references ops.source,
  source_id     text not null,
  entity        text not null check (entity in
                  ('intersection', 'approach', 'camera', 'camera_view', 'count_station', 'road_segment', 'stop')),
  entity_id     bigint not null,
  method        text not null,                    -- 'achd_cam_id', 'nearest_200m', 'manual', ...
  distance_m    real,
  confidence    real check (confidence between 0 and 1),
  linked_at     timestamptz not null default now(),
  primary key (source, source_id, entity)
);

-- A physical camera (usually on top of a corner pole).
create table core.camera (
  id            bigint generated always as identity primary key,
  name          text not null,
  pole_geom     geometry(Point, 4326),            -- ACHD's point; calibration refines the position
  achd_cam_id   int unique,
  active        boolean not null default true,    -- false once it disappears from ACHD's list
  first_seen    timestamptz not null default now(),
  last_seen     timestamptz not null default now()
);
create index camera_geom on core.camera using gist (pole_geom);

-- One image stream from a camera. A pan-tilt-zoom preset counts as a view.
create table core.camera_view (
  id            bigint generated always as identity primary key,
  camera_id     bigint not null references core.camera,
  image_id      int unique,                       -- 511 Idaho /map/Cctv/<image_id>
  source        text not null references ops.source,
  status        text,                             -- e.g. 511's Enabled / Disabled
  direction     text,                             -- coarse facing, if the source gives one
  description   text,
  sort_order    int not null default 0
);

-- A solved camera pose for one view. Versioned: a new calibration closes the
-- previous one, so history is kept.
--
-- Camera model (docs/11): a pinhole camera with square pixels and the
-- principal point at the image center, plus optional radial distortion k1.
-- heading_deg is the compass bearing the camera looks along (0 = north,
-- clockwise), tilt_deg is degrees below the horizon, and roll_deg turns the
-- image clockwise about the view axis.
create table core.camera_calibration (
  id            bigint generated always as identity primary key,
  view_id       bigint not null references core.camera_view,
  valid         tstzrange not null default tstzrange(now(), null),
  position      geometry(PointZ, 4326) not null,  -- camera lon, lat, height (m above sea level)
  heading_deg   real not null,
  tilt_deg      real not null,
  roll_deg      real not null default 0,
  vfov_deg      real not null,
  k1            real,
  image_width   int not null,
  image_height  int not null,
  point_pairs   jsonb not null,                   -- [{"pixel": [x, y], "ground": [lon, lat, z]}, ...]
  rms_error_px  real not null,
  reference_frame text not null,                  -- the saved frame the points were clicked on
  notes         text,
  created_by    text not null,                    -- 'manual' or a pipeline version
  created_at    timestamptz not null default now()
);
-- At most one current calibration per view.
create unique index calibration_current on core.camera_calibration (view_id) where upper_inf(valid);
