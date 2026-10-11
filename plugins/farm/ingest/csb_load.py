"""Load a Crop Sequence Boundaries edition: `python3 -m ingest farm-csb-load --gpkg FILE --edition NAME`.

FILE is the edition cut to the map box, as a GeoPackage (EPSG:5070, NASS's Albers), read with the standard library
(gpkg.py) and handed to PostGIS as WKB. Standard library plus psycopg:

    python3 -m ingest farm-csb-load --gpkg $TVT_SOURCES/csb/csb_mapbox.gpkg --edition csb-2018-2025-rev23 \\
        --published 2026-03-27 --last-modified 2026-05-15T17:58:04Z
    python3 -m ingest farm-csb-load --gpkg FILE --edition NAME --dry-run      # read and check only

In one transaction:
- the edition is recorded in farm.edition (the file's sha256, its years, the counts);
- each field is upserted into farm.field by its CSBID: the outline made valid and taken from NAD83 to WGS 84 with the
  null shift (the ground's datum policy, basemap/ground/grid.py), CSB's interior point, acres, county, and its CDL
  code per year;
- the long axis of each outline (its minimum-area rectangle in UTM 11N) gives the row bearing the ground textures
  crops along;
- fields of an older edition, another revision of this one or this one's earlier load that the file doesn't have are
  closed (valid_to), and linked to the fields that now cover them (successor); nothing is deleted;
- then derive.py: letters, growth, plats, the z8-10 dissolves and a new tile version.
The load is logged in ops.fetch under the source nass_csb (no request is made). Loading an edition older than one
already loaded is refused.

CSB's attributes: CSBID, CSBYEARS ("1825"), CSBACRES, CDL<year> for each year of the window, STATEFIPS, CNTYFIPS,
CNTY, ASD, INSIDE_X/INSIDE_Y (an interior point, in the file's CRS).
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timezone

from . import classes as C
from . import credits, derive, gpkg
from .sources import nass_csb

EDITION = re.compile(r"^csb-([0-9]{4})-([0-9]{4})(-[a-z0-9]+)?$")
YEAR_COLUMN = re.compile(r"^CDL([0-9]{4})$")
NAD83_EPSG = (5070, 4269, 26911, 6340, 3740)   # NAD83 CRSs taken with the null shift
SUCCESSOR_MIN_SHARE = 0.1                     # a newer field covering at least this share of an old one succeeds it
SUCCESSORS_KEPT = 5


class CsbError(ValueError):
    pass


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def edition_years(edition):
    m = EDITION.match(edition or "")
    if not m:
        raise CsbError(f"edition {edition!r} must look like csb-2018-2025 or csb-2018-2025-rev23")
    first, last = int(m.group(1)), int(m.group(2))
    if last < first + 1:
        raise CsbError(f"edition {edition!r}: the window needs at least two years")
    return first, last


def read(path, edition):
    """(layer info, rows) from an edition's GeoPackage, checked against the edition's window. Each row:
    {field_id, wkb, acres, state_fips, county_fips, county, asd, first_year, crops, inside_x, inside_y}."""
    first, last = edition_years(edition)
    with gpkg.open(path) as gp:
        layer = gp.layer()
        cols = dict(layer.columns)
        years = sorted(int(m.group(1)) for c in cols if (m := YEAR_COLUMN.match(c)))
        if years != list(range(first, last + 1)):
            raise CsbError(f"{path}: CDL year columns {years} aren't the edition's window {first}-{last}")
        need = ["CSBID", "CSBYEARS", "CSBACRES", "STATEFIPS", "CNTYFIPS", "CNTY", "ASD", "INSIDE_X", "INSIDE_Y"]
        missing = [c for c in need if c not in cols]
        if missing:
            raise CsbError(f"{path}: no column {', '.join(missing)}")
        if layer.epsg is None:
            raise CsbError(f"{path}: the layer's CRS isn't an EPSG one ({layer.organization} "
                           f"{layer.organization_id})")
        window = f"{first % 100:02d}{last % 100:02d}"
        rows, seen = [], set()
        for fid, a, wkb in layer.features(need + [f"CDL{y}" for y in years]):
            csbid = (a["CSBID"] or "").strip()
            if not re.fullmatch(r"[0-9]{6,20}", csbid):
                raise CsbError(f"feature {fid}: CSBID {a['CSBID']!r}")
            if csbid in seen:
                raise CsbError(f"CSBID {csbid} repeats")
            seen.add(csbid)
            if (a["CSBYEARS"] or "").strip() != window:
                raise CsbError(f"field {csbid}: CSBYEARS {a['CSBYEARS']!r} isn't the edition's {window}")
            if wkb is None:
                raise CsbError(f"field {csbid} has no geometry")
            crops = [int(a[f"CDL{y}"] or 0) for y in years]
            if not all(0 <= c <= 255 for c in crops):
                raise CsbError(f"field {csbid}: a CDL code out of 0-255 ({crops})")
            rows.append({"field_id": csbid, "wkb": wkb, "acres": a["CSBACRES"],
                         "state_fips": a["STATEFIPS"], "county_fips": a["CNTYFIPS"], "county": a["CNTY"],
                         "asd": a["ASD"], "first_year": first, "crops": crops,
                         "inside_x": a["INSIDE_X"], "inside_y": a["INSIDE_Y"]})
        if not rows:
            raise CsbError(f"{path}: no fields")
        info = {"layer": layer.name, "epsg": layer.epsg, "geometry_type": layer.geometry_type, "years": years}
    return info, rows


def source_proj(conn, epsg):
    """The PROJ string PostGIS transforms from: a NAD83 CRS with WGS 84's datum (the null shift), else None (the
    SRID's own)."""
    if epsg not in NAD83_EPSG:
        return None
    row = conn.execute("select proj4text from spatial_ref_sys where srid = %s", (epsg,)).fetchone()
    if not row or not row[0]:
        raise CsbError(f"PostGIS doesn't know EPSG:{epsg}")
    proj = re.sub(r"\+datum=NAD83\b", "+datum=WGS84", row[0])
    proj = re.sub(r"\+towgs84=[^ ]*", "", proj)
    if "+datum=WGS84" not in proj:
        proj = re.sub(r"\+ellps=GRS80\b", "+datum=WGS84", proj)
    if "+datum=WGS84" not in proj:
        raise CsbError(f"EPSG:{epsg}'s PROJ string has no NAD83 datum to replace: {row[0]}")
    return proj.strip()


def bearing_sql(azimuth):
    """SQL for a row bearing, degrees 0-180 from grid north, from an azimuth in radians. A mod just under 180 can
    round to 180 as a real; it wraps to 0 in the same expression, since farm.field's check (bearing < 180) is
    tested as each row is written."""
    b = f"mod(degrees({azimuth})::numeric, 180)::real"
    return f"(case when {b} >= 180 then 0::real else {b} end)"


def check_order(conn, edition, first, last):
    """Refuse an edition older than the newest one loaded (a reload of the same window is fine)."""
    newest = conn.execute("select edition, last_year from farm.edition order by last_year desc, loaded_at desc "
                          "limit 1").fetchone()
    if newest and newest[1] > last:
        raise CsbError(f"{newest[0]} (to {newest[1]}) is already loaded; refusing the older {edition}")


def load(conn, path, edition, published=None, last_modified=None, source_url=None, now=None, rows=None, info=None):
    """Load an edition. Doesn't commit. Returns stats."""
    now = now or datetime.now(timezone.utc)
    first, last = edition_years(edition)
    if rows is None:
        info, rows = read(path, edition)
    check_order(conn, edition, first, last)
    sha = sha256_of(path)
    classes = C.read()
    C.ensure(conn, classes)
    proj = source_proj(conn, info["epsg"])
    valid_from = published or now.date()
    credit = credits.csb(first, last)

    def tr(expr):
        return (f"ST_Transform({expr}, %(proj)s, 4326)" if proj
                else f"ST_Transform(ST_SetSRID({expr}, %(epsg)s), 4326)")

    with conn.cursor() as cur:
        cur.execute(
            """insert into farm.edition (edition, first_year, last_year, published, source_url, last_modified, file,
                 sha256, loaded_at, license, republish, credit)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (edition) do update set published = excluded.published, source_url = excluded.source_url,
                 last_modified = excluded.last_modified, file = excluded.file, sha256 = excluded.sha256,
                 loaded_at = excluded.loaded_at, license = excluded.license, republish = excluded.republish,
                 credit = excluded.credit""",
            (edition, first, last, published, source_url or nass_csb.SOURCE["url"], last_modified,
             os.path.abspath(path), sha, now, nass_csb.SOURCE["license"], nass_csb.REPUBLISH, credit))
        cur.execute("""create temporary table if not exists farm_csb_in (field_id text primary key, wkb bytea,
                         acres real, state_fips text, county_fips text, county text, asd text, first_year smallint,
                         crops smallint[], inside_x float8, inside_y float8) on commit drop""")
        cur.execute("truncate farm_csb_in")
        cols = ("field_id", "wkb", "acres", "state_fips", "county_fips", "county", "asd", "first_year", "crops",
                "inside_x", "inside_y")
        with cur.copy(f"copy farm_csb_in ({', '.join(cols)}) from stdin") as cp:
            for r in rows:
                cp.write_row(tuple(r[c] for c in cols))
        geom = tr("ST_CollectionExtract(ST_MakeValid(ST_GeomFromWKB(i.wkb)), 3)")
        point = tr("ST_MakePoint(i.inside_x, i.inside_y)")
        args = {"proj": proj, "epsg": info["epsg"], "edition": edition, "valid_from": valid_from}
        cur.execute("drop table if exists farm_csb_geom")
        cur.execute(
            f"""create temporary table farm_csb_geom on commit drop as
                select i.field_id, ST_Multi({geom}) as geom,
                       case when i.inside_x is null or i.inside_y is null then null else {point} end as label_pt,
                       not ST_IsValid(ST_GeomFromWKB(i.wkb)) as repaired
                from farm_csb_in i""", args)
        empty = cur.execute("select field_id from farm_csb_geom where geom is null or ST_IsEmpty(geom) "
                            "limit 3").fetchall()
        if empty:
            raise CsbError(f"fields with no area once made valid: {', '.join(r[0] for r in empty)}")
        repaired = cur.execute("select count(*) from farm_csb_geom where repaired").fetchone()[0]
        upserted = cur.execute(
            """insert into farm.field (field_id, edition, geom, label_pt, acres, state_fips, county_fips, county, asd,
                 first_year, crops, valid_from, valid_to, successor)
               select i.field_id, %(edition)s, g.geom,
                      case when g.label_pt is not null and ST_Intersects(g.label_pt, g.geom) then g.label_pt
                           else ST_PointOnSurface(g.geom) end,
                      i.acres, i.state_fips, i.county_fips, i.county, i.asd, i.first_year, i.crops,
                      %(valid_from)s, null, null
               from farm_csb_in i join farm_csb_geom g using (field_id)
               on conflict (field_id) do update set edition = excluded.edition, geom = excluded.geom,
                 label_pt = excluded.label_pt, acres = excluded.acres, state_fips = excluded.state_fips,
                 county_fips = excluded.county_fips, county = excluded.county, asd = excluded.asd,
                 first_year = excluded.first_year, crops = excluded.crops, valid_to = null, successor = null,
                 agree = case when farm.field.geom = excluded.geom then farm.field.agree end,
                 july = case when farm.field.geom = excluded.geom then farm.field.july end,
                 build_id = case when farm.field.geom = excluded.geom then farm.field.build_id end""",
            args).rowcount
        # The row bearing: the longer side of the minimum-area rectangle in UTM 11N, degrees from grid north, 0-180.
        side = """case when ST_Distance(ST_PointN(ST_ExteriorRing(r), 1), ST_PointN(ST_ExteriorRing(r), 2))
                            >= ST_Distance(ST_PointN(ST_ExteriorRing(r), 2), ST_PointN(ST_ExteriorRing(r), 3))
                       then ST_Azimuth(ST_PointN(ST_ExteriorRing(r), 1), ST_PointN(ST_ExteriorRing(r), 2))
                       else ST_Azimuth(ST_PointN(ST_ExteriorRing(r), 2), ST_PointN(ST_ExteriorRing(r), 3)) end"""
        cur.execute(
            f"""update farm.field f set bearing = s.bearing
                from (select field_id, case when GeometryType(r) = 'POLYGON' then {bearing_sql(side)} end as bearing
                      from (select field_id, ST_OrientedEnvelope(ST_Transform(geom, 32611)) as r
                            from farm.field where edition = %s) e) s
                where f.field_id = s.field_id""", (edition,))
        # Fields this file doesn't have, of this edition or an older one: closed, and linked to the file's fields
        # that cover them now (never to themselves). One of this edition's own fields that a reload drops closes on
        # the edition's date, an empty interval: as the edition now stands, it never had the field.
        closed = cur.execute(
            """with gone as (
                 select f.field_id from farm.field f join farm.edition e on e.edition = f.edition
                 where f.valid_to is null and e.last_year <= %(last)s
                   and not exists (select 1 from farm_csb_in i where i.field_id = f.field_id)),
               succ as (
                 select o.field_id, array_agg(n.field_id order by ST_Area(ST_Intersection(o.geom, n.geom)) desc)
                          as ids
                 from farm.field o join gone using (field_id)
                 join farm.field n on n.field_id in (select field_id from farm_csb_in) and n.field_id <> o.field_id
                   and ST_Intersects(o.geom, n.geom)
                   and ST_Area(ST_Intersection(o.geom, n.geom)) >= %(share)s * ST_Area(o.geom)
                 group by o.field_id)
               update farm.field f set valid_to = %(valid_from)s, successor = succ.ids[1:%(kept)s]
               from gone left join succ using (field_id)
               where f.field_id = gone.field_id""",
            {**args, "last": last, "share": SUCCESSOR_MIN_SHARE, "kept": SUCCESSORS_KEPT}).rowcount
        counts = {"fields": len(rows), "repaired": repaired, "closed": closed,
                  "acres": round(sum(r["acres"] or 0 for r in rows))}
        stats = {"edition": edition, "fields": len(rows), "repaired": repaired, "closed": closed}
        stats.update(derive.run(conn, f"farm-csb-load {edition}", f"farm-csb-load {edition}", classes))
        counts.update({k: v for k, v in stats.items() if k in ("built over", "being built")})
        cur.execute("update farm.edition set counts = %s::jsonb where edition = %s", (json.dumps(counts), edition))
    stats["upserted"] = upserted
    return stats


def run(conn, path, edition, **kw):
    """load() with the source registered and the load logged in ops.fetch; commits."""
    from ingest import db
    info, rows = read(path, edition)
    db.ensure_source(conn, nass_csb.SOURCE)
    with db.Fetch(conn, nass_csb.SOURCE["name"]) as f:       # no request made: robots and status stay empty
        f.bytes = os.path.getsize(path)
        stats = load(conn, path, edition, rows=rows, info=info, **kw)
        f.records = len(rows)
    return stats


def _date(s):
    return date.fromisoformat(s)


def _time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest farm-csb-load", description=__doc__.split("\n")[0])
    ap.add_argument("--gpkg", required=True, help="the edition cut to the map box (a GeoPackage, one feature table)")
    ap.add_argument("--edition", required=True, help="e.g. csb-2018-2025-rev23 (the window's years, then NASS's "
                                                     "file revision)")
    ap.add_argument("--published", type=_date, help="NASS's release date (YYYY-MM-DD); the fields' valid_from")
    ap.add_argument("--last-modified", type=_time, help="the national file's Last-Modified (ISO time)")
    ap.add_argument("--source-url", help="where the national file came from")
    ap.add_argument("--dry-run", action="store_true", help="read and check the file; write nothing")
    args = ap.parse_args(argv)
    try:
        if args.dry_run:
            info, rows = read(args.gpkg, args.edition)
            print(f"farm-csb-load (dry run): {args.edition}: {len(rows)} fields, layer {info['layer']} "
                  f"(EPSG:{info['epsg']}), years {info['years'][0]}-{info['years'][-1]}", flush=True)
            return 0
        from ingest import db
        with db.connect() as conn:
            stats = run(conn, args.gpkg, args.edition, published=args.published, last_modified=args.last_modified,
                        source_url=args.source_url)
            conn.commit()
            conn.execute("analyze farm.field, farm.field_lo")
            conn.commit()
    except (CsbError, gpkg.GpkgError, C.ClassesError) as err:
        print(f"farm-csb-load: {err}", file=sys.stderr, flush=True)
        return 1
    print("farm-csb-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
