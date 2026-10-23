-- The public trees tables keep only trees found in the lidar (owner, Oct 22, answer 6 of the end-of-wave-1 decisions).
-- A City inventory's tree ids and trunk points, its trunk diameters and the link from a tree to its inventory entry
-- belong to the private plugin that owns the inventory (its own tables). Nothing is
-- kept here: a rebuild with the new build.py writes the lidar crowns as ordinary trees and the links as anchors.jsonl.
--
-- What this removes, in one transaction:
--   * trees of kind 'catalogued' and 'estimated', and any tree with a catalogue entry (their ids hold the City's ids;
--     their points are its trunk points), with their log events; every log event of an id of the inventory's form
--     (boise-...) and every one that carries a trunk diameter or a trunk-to-crown offset or says 'estimated'; and the
--     same keys from the fits that remain (no log event that carries one is left to strip);
--   * the columns catalogue and catalogue_id, their index and the check that tied them to kind;
--   * the build records' counts of catalogued and estimated trees and their inventory sources.
-- The areas that held such trees are empty or short until they are rebuilt (build.py --anchors, trees-load here, then
-- the private plugin's load): the runbook is in plugins/trees/README.md. Not reversible.

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
ALTER TABLE trees.tree DROP COLUMN IF EXISTS catalogue;
ALTER TABLE trees.tree DROP COLUMN IF EXISTS catalogue_id;
-- fail closed: a row of any other kind can't be written, whatever loads it
ALTER TABLE trees.tree ADD CONSTRAINT tree_kind_check CHECK (kind = 'placed');

UPDATE trees.build
   SET counts = counts - 'catalogued' - 'estimated',
       params = CASE WHEN jsonb_typeof(params -> 'sources') = 'array'
                     THEN jsonb_set(params, '{sources}',
                            COALESCE((SELECT jsonb_agg(e) FROM jsonb_array_elements(params -> 'sources') e
                                       WHERE e ->> 'source' NOT IN ('catalogue', 'urban_tree_database')), '[]'::jsonb))
                     ELSE params END
 WHERE counts ? 'catalogued' OR counts ? 'estimated' OR jsonb_typeof(params -> 'sources') = 'array';

COMMENT ON TABLE trees.tree IS 'Trees found in the lidar (docs/19). Holds nothing from a tree inventory; see plugins/trees/README.md.';
