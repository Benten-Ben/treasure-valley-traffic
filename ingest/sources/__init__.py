"""Registered sources, in the order `run all` uses (cameras before their views)."""

from . import achd_cameras, idaho511_views

SOURCES = {m.SOURCE["name"]: m for m in (achd_cameras, idaho511_views)}
