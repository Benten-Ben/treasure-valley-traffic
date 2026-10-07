"""COMPASS's development applications ("Preliminary Plats (Entitlements)"), weekly.

COMPASSData/PreliminaryPlats/0 on swidrdc.org (on COMPASS's open-data hub;
its disclaimer only): 1,061 polygons, mostly preliminary plats (720), also
PUDs, conditional uses and rezones, with homes planned, permitted and still to
build, commercial floor area and expected jobs -> core.plat. Comments aren't
fetched.

Field notes, checked Oct 6, 2026:
- Kept current: 56 applications dated 2026, 11 since Sep 1 (hence weekly).
  One is dated in the future (Oct 28, 2026); 67 have no date.
- The layer has no GlobalID field (its description, Oct 6, 2026), ProjectID
  isn't unique (65 repeated, 105 empty), and the layer is edited in place
  (OBJECTIDs 55-5435 for 1,061 rows), so its OBJECTID field is the key.
  If COMPASS ever reloads the layer, every plat gets a new key: the old rows
  are retired and new ones added.
- appdate is a day at midnight UTC; agency, type, status and landusetype are
  coded (agency codes read 'City of Caldwell').
"""

from .. import compass_layer as cl
from ..compass_layer import flag, integer, number, text

PATH = "COMPASSData/PreliminaryPlats/FeatureServer/0"

SOURCE = {
    "name": "compass_plats",
    "title": "COMPASS development applications (preliminary plats and other entitlements)",
    "url": cl.BASE + PATH,
    "access": "open",
    "schedule": "7 days",
    "retry_after": cl.RETRY_AFTER,
    "license": cl.HUB_LICENSE,
    "credit": cl.CREDIT,
    "notes": "Kept current by COMPASS (several new applications a month). Comments not fetched.",
}

PLATS = cl.layer_source("compass_plat", "COMPASS Preliminary Plats (Entitlements)", PATH, module="compass_plats")

FIELDS = ["objectid", "projectid", "taz", "dev_name", "agency", "appdate", "type", "status", "resunits_total",
          "sfunits", "mfunits", "thunits", "duplexunits", "sfpermitted", "mfpermitted", "thpermitted",
          "duplexpermitted", "totalunitsremain", "commerciallots", "commsqft", "totallots", "employment",
          "landusetype", "school", "jobs"]
COUNTS = {
    "units_total": "resunits_total", "units_single_family": "sfunits", "units_multifamily": "mfunits",
    "units_townhome": "thunits", "units_duplex": "duplexunits", "permitted_single_family": "sfpermitted",
    "permitted_multifamily": "mfpermitted", "permitted_townhome": "thpermitted",
    "permitted_duplex": "duplexpermitted", "units_remaining": "totalunitsremain", "total_lots": "totallots",
    "commercial_lots": "commerciallots", "employment": "employment",
}


def plat_row(props):
    return {
        "project_id": text(props.get("projectid")),
        "name": text(props.get("dev_name")),
        "agency": text(props.get("agency")),
        "kind": text(props.get("type")),
        "status": text(props.get("status")),
        "land_use": text(props.get("landusetype")),
        "applied_on": cl.epoch_date(props.get("appdate")),
        **{col: integer(props.get(f)) for col, f in COUNTS.items()},
        "commercial_sq_ft": number(props.get("commsqft")),
        "creates_jobs": flag(props.get("jobs")),
        "school": text(props.get("school")),
        "taz_id": integer(props.get("taz")),
    }


def store(conn, fetch_id, seen_at, got, today=None):
    items = [(integer(p.get(got.oid)), p, g) for p, g in got.rows]      # attribute names are lower case
    items = [i for i in items if i[0] is not None]
    cl.check_share(got, len(items), cl.current_records(conn, PLATS["name"]), "plats")
    stats = cl.store_records(conn, PLATS["name"], [(oid, cl.without(p, got.oid), g) for oid, p, g in items],
                             fetch_id, seen_at, got.complete)
    rows = [{"object_id": oid, **plat_row(p), "geom": g} for oid, p, g in items]
    cl.upsert(conn, "core.plat", ["object_id"], rows, seen_at, geom="multi")
    retired = cl.retire(conn, "core.plat", seen_at) if got.complete else 0
    today = today or seen_at.date()
    return {**stats, "stored": len(rows), "retired": retired,
            "without date": sum(1 for r in rows if r["applied_on"] is None),
            "dated in the future": sum(1 for r in rows if r["applied_on"] and r["applied_on"] > today)}


LAYERS = [cl.Layer("plats", PLATS, PATH, FIELDS, store)]


def run(conn):
    return cl.run(conn, SOURCE, LAYERS)
