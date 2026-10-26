-- Rust private-preview feeds and the v0 bridge read candidate cache columns
-- directly. Clear only cached DE provider points whose retained provider
-- evidence has a recorded non-matched Germany context audit. Evidence remains
-- append-only; the SQL candidate cache is brought in line with candidate_display.
DO $migration$
DECLARE
    installed_definition TEXT;
    marker TEXT := '    RAISE EXCEPTION ''real preview evidence is append-only'';';
    guarded_exception TEXT := $guard$
    IF TG_TABLE_SCHEMA = 'real_preview' AND TG_TABLE_NAME = 'candidates'
       AND TG_OP = 'UPDATE'
       AND (to_jsonb(OLD) - ARRAY['display_latitude','display_longitude','display_geometry_source'])
           = (to_jsonb(NEW) - ARRAY['display_latitude','display_longitude','display_geometry_source'])
       AND OLD.source_id = 'de.locations'
       AND OLD.location_class <> 'numeric_source_coordinate'
       AND OLD.display_latitude IS NOT NULL
       AND OLD.display_longitude IS NOT NULL
       AND OLD.display_geometry_source IS NOT NULL
       AND NEW.display_latitude IS NULL
       AND NEW.display_longitude IS NULL
       AND NEW.display_geometry_source IS NULL
       AND OLD.snapshot_sha256 = (
           SELECT run.snapshot_sha256
           FROM real_preview.source_preview_runs run
           WHERE run.source_id = 'de.locations'
           ORDER BY run.created_at DESC, run.run_id DESC
           LIMIT 1
       )
       AND EXISTS (
           SELECT 1
           FROM real_preview.geocode_display_evidence evidence
           JOIN real_preview.germany_geocode_context_audit audit
             ON audit.candidate_id = evidence.candidate_id
            AND audit.snapshot_sha256 = OLD.snapshot_sha256
            AND audit.geocode_result_id = evidence.geocode_result_id
            AND audit.outcome <> 'matched'
           WHERE evidence.candidate_id = OLD.candidate_id
             AND evidence.display_latitude = OLD.display_latitude
             AND evidence.display_longitude = OLD.display_longitude
             AND evidence.display_geometry_source = OLD.display_geometry_source
       )
       AND NOT EXISTS (
           SELECT 1
           FROM real_preview.geocode_display_evidence evidence
           JOIN real_preview.germany_geocode_context_audit audit
             ON audit.candidate_id = evidence.candidate_id
            AND audit.snapshot_sha256 = OLD.snapshot_sha256
            AND audit.geocode_result_id = evidence.geocode_result_id
            AND audit.outcome = 'matched'
           WHERE evidence.candidate_id = OLD.candidate_id
             AND evidence.display_latitude = OLD.display_latitude
             AND evidence.display_longitude = OLD.display_longitude
             AND evidence.display_geometry_source = OLD.display_geometry_source
       ) THEN
        RETURN NEW;
    END IF;
$guard$;
BEGIN
    IF to_regprocedure('real_preview.reject_mutation()') IS NULL
       OR to_regclass('real_preview.germany_geocode_context_audit') IS NULL
       OR to_regclass('real_preview.geocode_display_evidence') IS NULL THEN
        RAISE EXCEPTION 'Germany cache alignment prerequisites are missing';
    END IF;

    installed_definition := pg_get_functiondef('real_preview.reject_mutation()'::regprocedure);
    IF md5(installed_definition) <> 'cd250977853154d88600a40fee48d2b1' THEN
        RAISE EXCEPTION 'candidate mutation guard differs from reviewed installed definition';
    END IF;
    IF length(installed_definition) - length(replace(installed_definition, marker, '')) <> length(marker) THEN
        RAISE EXCEPTION 'candidate mutation guard insertion marker is not unique';
    END IF;

    EXECUTE replace(installed_definition, marker, guarded_exception || E'\n' || marker);
END
$migration$;

-- Repair only the current DE cache entries where the exact cached provider
-- evidence is audited non-matched and no matched result supports those same
-- cached coordinates/provenance. All raw evidence and audit outcomes remain.
UPDATE real_preview.candidates candidate
   SET display_latitude = NULL,
       display_longitude = NULL,
       display_geometry_source = NULL
 WHERE candidate.source_id = 'de.locations'
   AND candidate.location_class <> 'numeric_source_coordinate'
   AND candidate.snapshot_sha256 = (
       SELECT run.snapshot_sha256
       FROM real_preview.source_preview_runs run
       WHERE run.source_id = 'de.locations'
       ORDER BY run.created_at DESC, run.run_id DESC
       LIMIT 1
   )
   AND candidate.display_latitude IS NOT NULL
   AND candidate.display_longitude IS NOT NULL
   AND candidate.display_geometry_source IS NOT NULL
   AND EXISTS (
       SELECT 1
       FROM real_preview.geocode_display_evidence evidence
       JOIN real_preview.germany_geocode_context_audit audit
         ON audit.candidate_id = evidence.candidate_id
        AND audit.snapshot_sha256 = candidate.snapshot_sha256
        AND audit.geocode_result_id = evidence.geocode_result_id
        AND audit.outcome <> 'matched'
       WHERE evidence.candidate_id = candidate.candidate_id
         AND evidence.display_latitude = candidate.display_latitude
         AND evidence.display_longitude = candidate.display_longitude
         AND evidence.display_geometry_source = candidate.display_geometry_source
   )
   AND NOT EXISTS (
       SELECT 1
       FROM real_preview.geocode_display_evidence evidence
       JOIN real_preview.germany_geocode_context_audit audit
         ON audit.candidate_id = evidence.candidate_id
        AND audit.snapshot_sha256 = candidate.snapshot_sha256
        AND audit.geocode_result_id = evidence.geocode_result_id
        AND audit.outcome = 'matched'
       WHERE evidence.candidate_id = candidate.candidate_id
         AND evidence.display_latitude = candidate.display_latitude
         AND evidence.display_longitude = candidate.display_longitude
         AND evidence.display_geometry_source = candidate.display_geometry_source
   );
