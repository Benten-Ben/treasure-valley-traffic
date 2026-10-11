"""OpenStreetMap hedges: a check for the shrub build (docs/19 §19.8).

ODbL: credit "© OpenStreetMap contributors". Mapped hedges (barrier=hedge ways and areas) are a check on the shrubs,
never drawn and never a source of shrubs (decided Oct 8). The shrubs' hedge check (`shrubs-hedge-check`) reads them,
the first that applies: a GeoJSON file of hedges (--hedges, e.g. from `osmium export`), the held Idaho extract filtered
by osmium (--extract), or the fences plugin's hedges once that plugin is built. It prints a report and stores nothing
in the database. Listed in plugin.json as a manual source, for its licence: this module makes no network requests and
has no schedule."""

SOURCE = {
    "name": "osm_hedges",
    "title": "OpenStreetMap hedges: a check for the shrubs",
    "url": "https://www.openstreetmap.org/copyright",
    "access": "open",
    "schedule": None,   # the extract is downloaded by hand (roads' osm_valley)
    "license": "ODbL",
    "credit": "© OpenStreetMap contributors",
    "notes": "barrier=hedge ways and areas, read by the shrubs' hedge check from a file, the held extract or the fences "
             "plugin's hedges; a check, never drawn or stored.",
}
