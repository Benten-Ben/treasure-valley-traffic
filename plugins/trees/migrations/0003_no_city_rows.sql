-- The public trees tables keep only trees found in the lidar (owner, Oct 22, answer 6 of the end-of-wave-1 decisions).
-- A City inventory's tree ids and trunk points, its trunk diameters and the link from a tree to its inventory entry
-- belong to the private plugin that owns the inventory (its own tables). Nothing is
-- kept here: a rebuild with the new build.py, without --anchors, writes the lidar crowns as ordinary trees; the private
-- plugin's matching (build.py --anchors with --private-out) runs separately afterwards and changes nothing public.
--
-- What this removes, in one transaction:
--   * trees of kind 'catalogued' and 'estimated', and any tree with a catalogue entry (their ids hold the City's ids;
--     their points are its trunk points), with their log events; every log event of an id of the inventory's form
--     (boise-...) and every one that carries a trunk diameter or a trunk-to-crown offset or says 'estimated'; and the
--     same keys from the fits that remain (no log event that carries one is left to strip);
--   * the values of the columns catalogue and catalogue_id (they stay, empty, so that an app image built before this
--     change, which still selects them, keeps working and gets nothing City-derived), their index and the check that tied
--     them to kind; a check now refuses any value in them, so nothing can write those fields again (a later migration
--     drops the columns once every app image is past this change);
--   * the build records' counts of catalogued and estimated trees (their tree count becomes the placed count), the
--     counts by type of a build that held them (they were taken over all its trees, so the inventory's genus typing is
--     in them and they can't be recomputed from what remains), and their inventory sources.
-- The areas that held such trees are short until they are rebuilt (build.py without --anchors, then trees-load here;
-- the private plugin's matching and load come after, separately, and change nothing public): the runbook is in
-- plugins/trees/README.md. Applied before those rebuilds load, the only effect is those transient gaps. Not reversible.

DELETE FROM trees.tree_log
 WHERE tree_id IN (SELECT tree_id FROM trees.tree WHERE kind <> 'placed' OR catalogue IS NOT NULL OR catalogue_id IS NOT NULL)
    OR tree_id LIKE 'boise-%'                      -- an inventory tree's id: its log survives a rebuild
    OR event = 'estimated'
    OR detail ? 'dbh_in' OR detail ? 'trunk_to_crown_m';

DELETE FROM trees.tree WHERE kind <> 'placed' OR catalogue IS NOT NULL OR catalogue_id IS NOT NULL;

UPDATE trees.tree SET fit = fit - 'dbh_in' - 'trunk_to_crown_m' WHERE fit ? 'dbh_in' OR fit ? 'trunk_to_crown_m';

DROP INDEX IF EXISTS trees.tree_catalogue_idx;
ALTER TABLE trees.tree DROP CONSTRAINT IF EXISTS tree_check;
ALTER TABLE trees.tree DROP CONSTRAINT IF EXISTS tree_kind_check;
-- the two fields stay as columns: every row that held a value is deleted above, so they are NULL everywhere, and a
-- check refuses any value in them from now on (adding it fails if a value were left)
ALTER TABLE trees.tree DROP CONSTRAINT IF EXISTS tree_no_city_fields_check;
ALTER TABLE trees.tree ADD CONSTRAINT tree_no_city_fields_check CHECK (catalogue IS NULL AND catalogue_id IS NULL);
-- fail closed: a row of any other kind can't be written, whatever loads it
ALTER TABLE trees.tree ADD CONSTRAINT tree_kind_check CHECK (kind = 'placed');

UPDATE trees.build
   SET counts = CASE WHEN COALESCE((counts ->> 'catalogued')::numeric, 0) > 0 OR COALESCE((counts ->> 'estimated')::numeric, 0) > 0
                     THEN CASE WHEN counts ? 'placed' THEN jsonb_set(counts - 'catalogued' - 'estimated' - 'types', '{trees}', counts -> 'placed')
                               ELSE counts - 'catalogued' - 'estimated' - 'types' END   -- the tree count is what it placed; the split by type was over every tree it held
                     WHEN counts ? 'catalogued' OR counts ? 'estimated'
                     THEN counts - 'catalogued' - 'estimated'   -- held no inventory trees (zero counts): its tree count and split are its own
                     ELSE counts END,
       params = CASE WHEN jsonb_typeof(params -> 'sources') = 'array'
                     THEN jsonb_set(params, '{sources}',
                            COALESCE((SELECT jsonb_agg(e) FROM jsonb_array_elements(params -> 'sources') e
                                       WHERE e ->> 'source' NOT IN ('catalogue', 'urban_tree_database')), '[]'::jsonb))
                     ELSE params END
 WHERE counts ? 'catalogued' OR counts ? 'estimated' OR jsonb_typeof(params -> 'sources') = 'array';

COMMENT ON TABLE trees.tree IS 'Trees found in the lidar (docs/19). Holds nothing from a tree inventory; see plugins/trees/README.md.';
