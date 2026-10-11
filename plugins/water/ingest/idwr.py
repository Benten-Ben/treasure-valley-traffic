"""IDWR's two layers the canal cards read: irrigation organizations and the season of use (decisions 19b and 19d).

Both are FeatureServer layers on gis.idwr.idaho.gov, read with the shared ArcGIS reader (ingest/arcgis.py: the ID
list, then the features by ID range, a pause between requests; robots.txt checked by ingest/http.py). Checked Oct 11,
2026 through ingest/http.py with our User-Agent:
- robots.txt: the host answers /robots.txt with a 302 to an HTML "Not Found" page at error.idaho.gov, which we read
  as no rules;
- terms: each item's licenseInfo is IDWR's disclaimer ("making this data available as a public service ... assumes
  no legal responsibility for the accuracy or completeness"), with no licence granted. accessInformation: IDWR. So
  the data is INTERNAL (plugin.json republish "internal"), credited to IDWR, kept in side tables that cards read and
  never in an export or the base map (the bake's NEVER list refuses any input from an `idwr_*` source), and a
  courtesy note to IDWR covering both layers is drafted with the private files for the owner to send;
- the layers are Query and Extract only, with no edit capabilities; 59 organizations and 4 season zones touch the
  map box; maxRecordCount 2,000.

Each run reads the features touching the map box (whole), stores each version in raw.record (by OBJECTID) and the
current state in its table (replaced whole; a snapshot with less than half the rows we hold is refused), and marks
water-build out of date when anything changed. The organizations' `Owner` field is never requested.
"""

from ingest import arcgis, db

BOX = (-117.05, 43.00, -115.95, 43.85)      # the map box: the 59 organizations decision 19b approved
PRECISION = 6                               # decimal degrees (0.1 m)
BUILD = "water-build"


def fetch(layer, label, fields):
    """(features, bytes, status, robots) for the box, only `fields` (and OBJECTID) requested."""
    return arcgis.fetch_layer(layer, label, box=BOX, precision=PRECISION, fields=list(fields), batch=500)


def records(features, parse):
    """[(OBJECTID, payload, GeoJSON)] from Esri features; parse(attrs) gives the payload (the fields we keep)."""
    out = []
    for f in features:
        attrs = f.get("attributes") or {}
        oid = arcgis.object_id(attrs, "OBJECTID")
        geom = arcgis.esri_geometry(f.get("geometry"))
        if oid is None or geom is None:
            continue
        payload = parse(attrs)
        payload["geom_digest"] = arcgis.geom_digest(geom)
        out.append((oid, payload, geom))
    return out


def store(conn, source, table, insert_sql, rows, fetch_id, seen_at, label):
    """raw.record versions, then the table replaced whole. rows: [(oid, payload, geom, values for insert_sql)].
    Returns stats."""
    held = conn.execute(f"select count(*) from {table}").fetchone()[0]
    if not rows or len(rows) < db.SNAPSHOT_MIN_SHARE * held:
        raise RuntimeError(f"{label}: only {len(rows)} features against {held} held; not taken as a full snapshot")
    new, same, removed = db.upsert_records(conn, source, [(str(oid), p, g) for oid, p, g, _ in rows], fetch_id,
                                           seen_at, complete=True)
    conn.execute(f"delete from {table}")
    for oid, payload, geom, values in rows:
        conn.execute(insert_sql, values)
    changed = bool(new or removed)
    if changed and conn.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]:
        from ingest import builds
        builds.mark(conn, BUILD, by=source, reason=f"{label}: {new} new or changed, {removed} removed")
    return {"features": len(rows), "versions new": new, "unchanged": same, "removed": removed}
