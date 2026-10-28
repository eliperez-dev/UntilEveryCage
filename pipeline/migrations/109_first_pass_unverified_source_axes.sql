-- Unverified raw X/Y are retained evidence, not a reason to discard an
-- independently matched address. The capture still requires no usable source
-- coordinate and independently checks the source address and provider result.
DO $migration$
DECLARE
    definition TEXT;
    old_guard TEXT := $guard$               AND (jsonb_typeof(location.location_evidence->'coordinates') IS DISTINCT FROM 'object'
                    OR NOT (location.location_evidence->'coordinates' ?| ARRAY[
                        'latitude','longitude','x','y']))$guard$;
BEGIN
    IF to_regprocedure('real_preview.capture_locationiq_first_pass_private_display()') IS NULL THEN
        RETURN;
    END IF;
    definition := pg_get_functiondef('real_preview.capture_locationiq_first_pass_private_display()'::regprocedure);
    IF length(definition)-length(replace(definition,old_guard,'')) <> length(old_guard) THEN
        RAISE EXCEPTION 'first-pass raw-axis guard marker is not unique';
    END IF;
    EXECUTE replace(definition,old_guard,'');

    -- Replay only the display hook against retained accepted rows. A temporary
    -- table invokes it with the original result ID; no provider result, request,
    -- job event, source observation or public release is inserted or rewritten.
    CREATE TEMP TABLE uec_first_pass_109_replay
        (LIKE uec.geocode_results) ON COMMIT DROP;
    CREATE TRIGGER first_pass_109_retained_capture AFTER INSERT
        ON uec_first_pass_109_replay FOR EACH ROW
        EXECUTE FUNCTION real_preview.capture_locationiq_first_pass_private_display();
    INSERT INTO uec_first_pass_109_replay
    SELECT DISTINCT result.* FROM uec.geocode_results result
    JOIN uec.geocode_jobs job ON job.source_record_id=result.source_record_id
        AND job.provider_id=result.provider_id AND job.query=result.query
    JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
    WHERE result.provider_id='locationiq' AND result.status='accepted'
      AND left(result.query,1)='{'
      AND result.query::jsonb->>'schema_version'='uec-address-query-v1'
      AND NOT EXISTS (SELECT 1 FROM real_preview.geocode_display_evidence evidence
          WHERE evidence.candidate_id=target.candidate_id
            AND evidence.geocode_result_id=result.geocode_result_id);
END
$migration$;
