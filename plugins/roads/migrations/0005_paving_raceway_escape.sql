-- roads 0005: raceways and escape ramps in roads.osm_paving (Oct 22, 2026, issue #280; owner answer 9:
-- every OSM highway way has exactly one owner).
--
-- The partition (ingest/osm_extract.py owner()) gives highway=raceway and highway=escape to the osm_paving
-- consumer: built surfaces drawn by material, never routed. A raceway with lanes or turn tags stays
-- osm_valley's, so only the rest arrive here. Their `highway` and `kind` are the same value. 0002 is
-- applied, so its two checks are dropped and added again with the two values; the service-kinds check
-- (highway = 'service' exactly when the kind is a service kind) stays as it is.

alter table roads.osm_paving drop constraint osm_paving_kind_check;
alter table roads.osm_paving drop constraint osm_paving_highway_check;

alter table roads.osm_paving add constraint osm_paving_kind_check
  check (kind in ('service', 'driveway', 'parking_aisle', 'drive_through', 'emergency_access', 'sidewalk',
                  'crossing', 'access_aisle', 'traffic_island', 'raceway', 'escape'));
alter table roads.osm_paving add constraint osm_paving_highway_check
  check (highway in ('service', 'footway', 'path', 'cycleway', 'raceway', 'escape'));
