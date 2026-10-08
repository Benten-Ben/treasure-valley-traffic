-- Trees (docs/19): every tree we find in the lidar, catalogued trees first. Our own lidar-derived data only:
-- a catalogue's attributes stay in the catalogue's (private) plugin and are joined by catalogue_id.
CREATE SCHEMA IF NOT EXISTS trees;

-- One build of one area: its settings, crown model and counts.
CREATE TABLE trees.build (
    build_id    text PRIMARY KEY,
    area        text NOT NULL,
    started_at  timestamptz NOT NULL,
    finished_at timestamptz,
    loaded_at   timestamptz NOT NULL DEFAULT now(),
    params      jsonb NOT NULL DEFAULT '{}',
    counts      jsonb NOT NULL DEFAULT '{}'
);

-- One row per tree. A rebuild of an area replaces its rows; the log keeps what we learned.
CREATE TABLE trees.tree (
    tree_id        text PRIMARY KEY,
    area           text NOT NULL,
    kind           text NOT NULL CHECK (kind IN ('catalogued', 'placed', 'estimated')),
    type           text NOT NULL CHECK (type IN ('broadleaf', 'conifer', 'narrow')),
    geom           geometry(Point, 4326) NOT NULL,      -- the crown's centre
    ground_m       real,                                -- ground elevation under it (NAVD88), when known
    height_m       real NOT NULL,
    crown_radius_m real NOT NULL,
    crown_a        real,                                -- top shape: z = H * (1 - a * (d/R)^n)
    crown_n        real,
    lidar          text,                                -- the survey its height comes from; null for 'estimated'
    catalogue      text,                                -- e.g. 'boise' (the private city_trees plugin)
    catalogue_id   text,
    fit            jsonb NOT NULL DEFAULT '{}',         -- how well it explains the lidar, or how far it sits from its trunk point
    build_id       text NOT NULL REFERENCES trees.build (build_id),
    CHECK ((kind = 'placed') = (catalogue IS NULL))
);
CREATE INDEX tree_geom_idx ON trees.tree USING gist (geom);
CREATE INDEX tree_area_idx ON trees.tree (area);
CREATE INDEX tree_catalogue_idx ON trees.tree (catalogue, catalogue_id);

-- What we know about a tree over time (shown in its panel). Survives rebuilds.
CREATE TABLE trees.tree_log (
    tree_id  text NOT NULL,
    at       timestamptz NOT NULL,
    event    text NOT NULL,
    detail   jsonb NOT NULL DEFAULT '{}',
    build_id text,
    PRIMARY KEY (tree_id, at, event)
);
