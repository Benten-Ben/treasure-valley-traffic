-- water 0003: an index for a gauge's latest reading (issue #363).
--
-- The app's gauge, reach, body and structure cards ask for the newest NWPS observation of one gauge. Every
-- observation is a raw.record row (source 'nwps_gauges', source_id '<lid>@<time>', about 3,500 new rows a day) and the
-- only index there, record_current (source, source_id, last_seen desc), can't serve a `like` prefix under a non-C
-- collation. This partial expression index covers the lookup by the record's own lid and observation time.
create index if not exists record_nwps_gauge_reading
  on raw.record ((payload->>'lid'), (payload->>'t') desc)
  where source = 'nwps_gauges';
