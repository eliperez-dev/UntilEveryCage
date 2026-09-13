-- Safe public query surface: only the explicitly promoted release is exposed.

CREATE OR REPLACE VIEW uec.map_facilities_public AS
SELECT *
FROM uec.map_facilities_release
WHERE release_status = 'promoted';

COMMENT ON VIEW uec.map_facilities_public IS
    'Default public map surface. Only promoted, release-visible observations with accepted coordinates are returned.';
