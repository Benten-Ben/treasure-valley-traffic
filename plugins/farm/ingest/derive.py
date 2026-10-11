"""What every crop-fields load works out afterwards, in the same transaction (farm-csb-load, farm-fields-load):

1. letters and group_now from the codes (farm.crop_class);
2. growth (growth.py) from the codes and COMPASS's new-construction permits inside each field (obs.building_permit,
   when the table is there: development's source, republish yes);
3. plats: the share of each field under COMPASS's plats (core.plat), by status, and the largest few;
4. the z8-10 dissolves (farm.field_lo): current fields dissolved by crop group per year, and by growth state,
   closed and simplified at each zoom's pixel, cut to its tile grid;
5. a new version of the crop-fields tiles (core.layer_version 'farm.crop_fields'), with its licence and credit.

Only current fields (valid_to is null) are worked on. Standard library plus psycopg; the geometry is PostGIS's.
"""

import json

from . import classes as C
from . import growth as G

TILE_LAYER = "farm.crop_fields"           # /api/farm/tiles/crop_fields (P3-app)
LO_ZOOMS = (10, 9, 8)                     # dissolved and generalised for these zooms
TILE_PX = 512                             # MapLibre draws a vector tile 512 px wide
WEB_MERCATOR_WIDTH = 40075016.685578488   # the EPSG:3857 world, metres
PLAT_STATUS = {"Approved": "approved", "Recorded": "approved", "Pending": "pending", "In Progress": "pending",
               "Built": "built"}
PLAT_MIN_SHARE = 0.01                     # smaller overlaps are edge slivers, not plats over the field
PLAT_KEEP = 3                             # the largest plats named in a field's detail

LICENSE = "public domain (USDA NASS CSB, CDL); Copernicus (Sentinel-2); none stated (COMPASS permits and plats)"
CREDIT = ("USDA NASS Crop Sequence Boundaries and Cropland Data Layer; Contains modified Copernicus Sentinel data "
          "2025; COMPASS (permits and plats)")


def pixel_m(z):
    """One pixel of a 512 px tile at zoom z, in Web Mercator metres."""
    return WEB_MERCATOR_WIDTH / (TILE_PX * 2 ** z)


def has_table(conn, name):
    return conn.execute("select to_regclass(%s) is not null", (name,)).fetchone()[0]


def letters_and_groups(conn):
    """letters and group_now for every current field, from its codes."""
    return conn.execute(
        """update farm.field f set letters = s.letters, group_now = s.g
           from (select f.field_id,
                        string_agg(coalesce(c.letter, %s), '' order by u.i) as letters,
                        (array_agg(case when u.code = 0 then null else coalesce(c.grp, 'other') end
                                   order by u.i desc))[1] as g
                 from farm.field f cross join lateral unnest(f.crops) with ordinality u(code, i)
                 left join farm.crop_class c on c.code = u.code
                 where f.valid_to is null group by f.field_id) s
           where f.field_id = s.field_id""", (C.UNKNOWN_LETTER,)).rowcount


def permits(conn):
    """{field_id: {"n", "first", "last"}} for current fields with new-construction permits since their window began,
    or None when there's no permits table."""
    if not has_table(conn, "obs.building_permit"):
        return None
    rows = conn.execute(
        """select f.field_id, count(*), min(p.year), max(p.year)
           from farm.field f join obs.building_permit p on ST_Intersects(f.geom, p.geom)
           where f.valid_to is null and p.active and p.work = 'New Construction' and p.year >= f.first_year
           group by f.field_id""").fetchall()
    return {fid: {"n": n, "first": lo, "last": hi} for fid, n, lo, hi in rows}


def growth(conn, classes):
    """growth and growth_detail for every current field. Returns {state: count} and whether permits were known."""
    found = permits(conn)
    counts = {"farmed": 0, "built_over": 0, "being_built": 0}
    rows = []
    for fid, first_year, crops in conn.execute(
            "select field_id, first_year, crops from farm.field where valid_to is null"):
        p = None if found is None else found.get(fid, {"n": 0})
        state, detail = G.classify(crops, first_year, classes, p)
        counts[state] += 1
        rows.append((fid, state, json.dumps(detail)))
    with conn.cursor() as cur:
        cur.execute("create temporary table if not exists farm_growth_in (field_id text primary key, growth text, "
                    "detail jsonb) on commit drop")
        cur.execute("truncate farm_growth_in")
        with cur.copy("copy farm_growth_in (field_id, growth, detail) from stdin") as cp:
            for r in rows:
                cp.write_row(r)
        cur.execute("""update farm.field f set growth = g.growth, growth_detail = g.detail
                       from farm_growth_in g where f.field_id = g.field_id""")
    return counts, found is not None


def plats(conn):
    """plat for every current field: {"approved", "pending", "built" (shares of the field), "plats": [the largest
    few]}, or null with no plat over it. Returns the number of fields under a plat, or None with no plats table."""
    if not has_table(conn, "core.plat"):
        conn.execute("update farm.field set plat = null where valid_to is null")
        return None
    statuses = list(PLAT_STATUS)
    conn.execute(
        """create temporary table if not exists farm_plat_hit (field_id text, object_id int, name text, status text,
             cls text, applied_on date, geom geometry) on commit drop""")
    conn.execute("truncate farm_plat_hit")
    conn.execute(
        """insert into farm_plat_hit
           select f.field_id, p.object_id, p.name, p.status,
                  case when p.status in ('Approved', 'Recorded') then 'approved'
                       when p.status in ('Pending', 'In Progress') then 'pending' else 'built' end,
                  p.applied_on,
                  ST_Intersection(ST_Transform(f.geom, 32611), ST_Transform(ST_MakeValid(p.geom), 32611))
           from farm.field f join core.plat p on ST_Intersects(f.geom, p.geom)
           where f.valid_to is null and p.active and p.status = any(%s)""", (statuses,))
    conn.execute("update farm.field set plat = null where valid_to is null")
    return conn.execute(
        """with area as (select field_id, ST_Area(ST_Transform(geom, 32611)) as m2 from farm.field
                         where valid_to is null and field_id in (select field_id from farm_plat_hit)),
                cls as (select h.field_id, h.cls, ST_Area(ST_Union(h.geom)) / a.m2 as share
                        from farm_plat_hit h join area a using (field_id) group by h.field_id, h.cls, a.m2),
                one as (select h.field_id, h.object_id, h.name, h.status, h.applied_on,
                               ST_Area(h.geom) / a.m2 as share,
                               row_number() over (partition by h.field_id order by ST_Area(h.geom) desc,
                                                  h.object_id) as k
                        from farm_plat_hit h join area a using (field_id)),
                doc as (select c.field_id,
                               jsonb_build_object(
                                 'approved', round(coalesce(max(c.share) filter (where c.cls = 'approved'), 0)::numeric, 3),
                                 'pending', round(coalesce(max(c.share) filter (where c.cls = 'pending'), 0)::numeric, 3),
                                 'built', round(coalesce(max(c.share) filter (where c.cls = 'built'), 0)::numeric, 3),
                                 'plats', (select jsonb_agg(jsonb_build_object(
                                                   'id', o.object_id, 'name', o.name, 'status', o.status,
                                                   'applied_on', o.applied_on, 'share', round(o.share::numeric, 3))
                                                 order by o.k)
                                           from one o where o.field_id = c.field_id and o.k <= %s
                                             and o.share >= %s)) as plat
                        from cls c group by c.field_id
                        having max(c.share) >= %s)
           update farm.field f set plat = d.plat from doc d where f.field_id = d.field_id""",
        (PLAT_KEEP, PLAT_MIN_SHARE, PLAT_MIN_SHARE)).rowcount


def dissolves(conn):
    """Rebuild farm.field_lo: the current fields dissolved by crop group per year and by growth state (and 'plat':
    still farmed and at least half under an approved plat). For each zoom in LO_ZOOMS, finest first, the previous
    zoom's shapes are closed across gaps under a pixel (buffered out and back by half a pixel), simplified by half a
    pixel, and parts under half a square pixel dropped; then each part is cut to the zoom's tile grid. Returns
    {z: rows}."""
    groups = list(C.FARMED_GROUPS)
    conn.execute("delete from farm.field_lo")
    conn.execute(
        """create temporary table if not exists farm_lo_base (yr smallint, key text, now boolean, geom geometry)
           on commit drop""")
    conn.execute("truncate farm_lo_base")
    newest = conn.execute(
        "select max(first_year + cardinality(crops) - 1) from farm.field where valid_to is null").fetchone()[0]
    if newest is None:
        return {z: 0 for z in LO_ZOOMS}
    # One union per (year, group) and per growth state, at full detail, in Web Mercator.
    conn.execute(
        """insert into farm_lo_base (yr, key, now, geom)
           with f as (select ST_Transform(geom, 3857) as g, first_year, crops, group_now, growth, plat
                      from farm.field where valid_to is null),
                keyed as (
                  select (f.first_year + u.i - 1)::smallint as yr, c.grp as key, f.g
                  from f cross join lateral unnest(f.crops) with ordinality u(code, i)
                  join farm.crop_class c on c.code = u.code
                  where c.grp = any(%(groups)s)
                  union all
                  select null, f.growth, f.g from f where f.growth in ('built_over', 'being_built')
                  union all
                  select null, 'plat', f.g from f
                  where f.group_now = any(%(groups)s) and (f.plat ->> 'approved')::real >= 0.5)
           select yr, key, yr is null or yr = %(newest)s, ST_UnaryUnion(ST_Collect(g)) from keyed group by yr, key""",
        {"groups": groups, "newest": newest})
    out = {}
    for z in LO_ZOOMS:
        px = pixel_m(z)
        args = {"z": z, "half": px / 2, "min_area": px * px / 2, "tile": px * TILE_PX,
                "half_world": WEB_MERCATOR_WIDTH / 2}
        conn.execute(
            """update farm_lo_base b set geom = coalesce(
                 (select ST_Collect(d.geom)
                  from ST_Dump(ST_MakeValid(ST_SimplifyPreserveTopology(
                         ST_Buffer(ST_Buffer(b.geom, %(half)s, 'quad_segs=2'), -%(half)s, 'quad_segs=2'),
                         %(half)s))) d
                  where ST_GeometryType(d.geom) = 'ST_Polygon' and ST_Area(d.geom) >= %(min_area)s),
                 'GEOMETRYCOLLECTION EMPTY'::geometry)""", args)
        out[z] = conn.execute(
            """insert into farm.field_lo (z, x, y, yr, key, now, geom)
               select %(z)s, x, y, yr, key, now, ST_Multi(ST_Collect(g))
               from (select p.yr, p.key, p.now, x, y,
                            (ST_Dump(ST_CollectionExtract(
                               case when ST_CoveredBy(p.geom, ST_TileEnvelope(%(z)s, x, y)) then p.geom
                                    else ST_Intersection(p.geom, ST_TileEnvelope(%(z)s, x, y)) end, 3))).geom as g
                     from (select yr, key, now, (ST_Dump(geom)).geom as geom from farm_lo_base) p,
                          generate_series(floor((ST_XMin(p.geom) + %(half_world)s) / %(tile)s)::int,
                                          floor((ST_XMax(p.geom) + %(half_world)s) / %(tile)s)::int) x,
                          generate_series(floor((%(half_world)s - ST_YMax(p.geom)) / %(tile)s)::int,
                                          floor((%(half_world)s - ST_YMin(p.geom)) / %(tile)s)::int) y
                     where p.geom && ST_TileEnvelope(%(z)s, x, y)) c
               where not ST_IsEmpty(g)
               group by x, y, yr, key, now""", args).rowcount
    return out


def tile_version(conn, build, features, note):
    """A new version of the crop-fields tiles, when core.layer_version exists (migration 0020). Returns it or None."""
    if not has_table(conn, "core.layer_version"):
        return None
    from ingest import layer_version
    return layer_version.record(conn, TILE_LAYER, license=LICENSE, republish="yes", credit=CREDIT, build=build,
                                features=features, note=note)


def run(conn, build, note, classes=None):
    """Steps 1-5 above. Doesn't commit. Returns stats."""
    classes = classes or C.read()
    stats = {"fields (current)": conn.execute(
        "select count(*) from farm.field where valid_to is null").fetchone()[0]}
    letters_and_groups(conn)
    counts, known = growth(conn, classes)
    stats.update({"built over": counts["built_over"], "being built": counts["being_built"]})
    if not known:
        stats["permits"] = "no obs.building_permit: being_built not flagged"
    under = plats(conn)
    stats["under a plat"] = "no core.plat" if under is None else under
    lo = dissolves(conn)
    stats["dissolved rows"] = "/".join(f"z{z} {n}" for z, n in sorted(lo.items()))
    version = tile_version(conn, build, stats["fields (current)"], note)
    stats["tiles"] = f"{TILE_LAYER} {version}" if version else "no core.layer_version (migration 0020): no version"
    return stats
