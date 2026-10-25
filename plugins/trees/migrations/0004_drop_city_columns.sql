-- Trees: drop the two City columns, catalogue and catalogue_id, that 0003 emptied and kept so that an app image built
-- before 0003 (which still selects them) kept working. Apply only once every running app image was built from a main
-- with #349 (its trees queries name neither column), so no image still selects them. Not reversible: the columns and
-- their (already empty) values are gone. The README's runbook for 0003 says which images ran when.

ALTER TABLE trees.tree DROP CONSTRAINT IF EXISTS tree_no_city_fields_check;
ALTER TABLE trees.tree DROP COLUMN catalogue;
ALTER TABLE trees.tree DROP COLUMN catalogue_id;
