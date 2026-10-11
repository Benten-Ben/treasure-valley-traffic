"""OpenStreetMap hedges: a check for the shrub build (docs/19 §19.8).

ODbL: credit "© OpenStreetMap contributors". Mapped hedges (barrier=hedge) come from the held Idaho extract through
core's OpenStreetMap loader and are stored with the fences plugin's barriers, never drawn as fences; the shrub build
checks its shrubs against them (decided Oct 8: hedges are a shrub check). Listed in plugin.json as a manual source, for
its licence: this module makes no network requests and has no schedule. The shrub build isn't written yet, so nothing in
this plugin reads them so far."""

SOURCE = {
    "name": "osm_hedges",
    "title": "OpenStreetMap hedges: a check for the shrubs",
    "url": "https://www.openstreetmap.org/copyright",
    "access": "open",
    "schedule": None,   # the extract is downloaded and loaded by hand (roads' osm_valley)
    "license": "ODbL",
    "credit": "© OpenStreetMap contributors",
    "notes": "barrier=hedge ways, read through the fences plugin's table once it exists; a check, never drawn.",
}
