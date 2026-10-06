-- 0016: two lane inventories whose own IDs turned out not to name one row
-- each (found on the first loads, Oct 6, 2026). Both tables are new in 0011
-- and written only by their ingestors (itd_hpms, compass_centerline); rows
-- they stored under the old keys are dropped here, with their matches, and
-- the next run reloads them.

-- ITD HPMS: one EventID can cover several separate pieces of a route (same
-- values, different measures; 16 of 637 turn-lane events in the valley).
-- Each piece is keyed by source_id, '<EventID>@<RouteID>:<FromMeasure>'
-- (raw.record and core.segment_match use the same key); event_id stays
-- ITD's EventID, which a few rows lack.

delete from core.segment_match where source like 'itd\_hpms\_%';
delete from core.hpms_section;

alter table core.hpms_section drop constraint hpms_section_kind_event_id_key;
alter table core.hpms_section alter column event_id drop not null;
alter table core.hpms_section add column source_id text not null;
alter table core.hpms_section add constraint hpms_section_kind_source_id_key unique (kind, source_id);
create index hpms_section_event on core.hpms_section (kind, event_id);

-- COMPASS's RegionalCenterline pieces are keyed by globalid, not pm_id.
-- pm_id names a travel-model link, not a segment: 62,213 centerline pieces
-- carry 26,912 pm_ids, and the pieces of one link can have different lanes.
-- Even ACHD's PermID repeats (40,075 PermIDs on 58,574 pieces: COMPASS splits
-- ACHD's segments where its links end). Only globalid is unique, so each
-- piece is keyed by it, and pm_id stays, indexed, as the join to COMPASS's
-- counts, crashes and travel model (a few pieces have none).

delete from core.segment_match where source = 'compass_centerline';
delete from core.compass_segment;

alter table core.compass_segment drop constraint compass_segment_pm_id_key;
alter table core.compass_segment alter column pm_id drop not null;
alter table core.compass_segment add column global_id text not null;
alter table core.compass_segment add constraint compass_segment_global_id_key unique (global_id);
create index compass_segment_pm_id on core.compass_segment (pm_id);
