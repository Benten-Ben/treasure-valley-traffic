-- Test fixture: one ribbon segment from a made-up build, so /api/meta has a build to report.
insert into core.transit_ribbon (segment_id, geom, routes, length_m, hub, build)
values (1, ST_GeomFromText('LINESTRING(-116.2 43.6, -116.201 43.601)', 4326), '{9}', 137, false, 'harness-test-build');
