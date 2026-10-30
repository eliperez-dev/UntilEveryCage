"""Read-only grid-coordinate hypotheses; never approve or display source points."""
import json
import os
from pathlib import Path


_COHORT = """WITH latest AS MATERIALIZED (
    SELECT snapshot_sha256 FROM real_preview.source_preview_runs
    WHERE source_id='fsa_approved_establishments' ORDER BY created_at DESC,run_id DESC LIMIT 1
), cohort AS MATERIALIZED (
    SELECT ca.candidate_id,(l.location_evidence#>>'{coordinates,x}')::FLOAT8 AS x,
           (l.location_evidence#>>'{coordinates,y}')::FLOAT8 AS y
    FROM real_preview.candidates ca JOIN latest USING(snapshot_sha256)
    JOIN real_preview.candidate_private_location_evidence l USING(candidate_id,snapshot_sha256,source_id)
    WHERE ca.source_id='fsa_approved_establishments' AND ca.country_code='GB' AND ca.default_map_scope
      AND l.location_evidence#>>'{coordinates,x}' IS NOT NULL
      AND l.location_evidence#>>'{coordinates,y}' IS NOT NULL
      AND NOT EXISTS(SELECT 1 FROM real_preview.enrichment_state_events s
          WHERE s.candidate_id=ca.candidate_id AND s.state_code='restricted')
      AND NOT EXISTS(SELECT 1 FROM real_preview.geocode_targets t JOIN uec.geocode_jobs j USING(job_id)
          JOIN uec.public_access_restricted r USING(source_record_id) WHERE t.candidate_id=ca.candidate_id)
) """


def audit(connection):
    connection.execute("SET TRANSACTION READ ONLY")
    connection.execute("SET LOCAL statement_timeout='60s'")
    if connection.execute("SELECT current_database()").fetchone()[0] != "uec_launch_sources_test_20261025":
        raise ValueError("wrong_disposable_database")
    raw=connection.execute(_COHORT+"""SELECT count(*),count(DISTINCT(x,y)),
        count(*) FILTER(WHERE x BETWEEN 0 AND 700000 AND y BETWEEN 0 AND 1300000),
        count(*) FILTER(WHERE x BETWEEN -8.7 AND 2.1 AND y BETWEEN 49.8 AND 60.9),
        count(*) FILTER(WHERE mod(x::NUMERIC,100)=0 AND mod(y::NUMERIC,100)=0)
        FROM cohort""").fetchone()
    hypotheses={}
    for name,srid,swapped in (("british_national_grid",27700,False),
                              ("swapped_british_grid",27700,True),
                              ("irish_grid",29903,False),("web_mercator",3857,False)):
        extent=connection.execute(_COHORT+""", points AS(
            SELECT ST_Transform(ST_SetSRID(ST_MakePoint(
                CASE WHEN %s THEN y ELSE x END,CASE WHEN %s THEN x ELSE y END),%s),4326) geom
            FROM cohort)
            SELECT count(*) FILTER(WHERE ST_X(geom) BETWEEN -8.7 AND 2.1
                AND ST_Y(geom) BETWEEN 49.8 AND 60.9) FROM points""",(swapped,swapped,srid)).fetchone()[0]
        hypotheses[name]={"inside_broad_uk_extent":extent}
    distances=connection.execute(_COHORT+""", compared AS(
        SELECT ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(c.x,c.y),27700),4326)::geography,
            ST_SetSRID(ST_MakePoint(e.display_longitude,e.display_latitude),4326)::geography) distance
        FROM cohort c JOIN LATERAL(
            SELECT display_latitude,display_longitude FROM real_preview.geocode_display_evidence e
            WHERE e.candidate_id=c.candidate_id AND e.display_precision='provider_address_point_high_confidence'
            ORDER BY e.created_at DESC LIMIT 1)e ON true)
        SELECT count(*),count(*) FILTER(WHERE distance<50),count(*) FILTER(WHERE distance<250),
               count(*) FILTER(WHERE distance<1000),count(*) FILTER(WHERE distance>=10000) FROM compared""").fetchone()
    return {"source_id":"fsa_approved_establishments","raw_coordinate_pairs":raw[0],
        "distinct_raw_pairs":raw[1],"within_british_grid_numeric_range":raw[2],
        "already_lon_lat_pairs":raw[3],"pairs_rounded_to_100m_grid":raw[4],
        "hypotheses":hypotheses,
        "british_grid_vs_existing_address_matches":dict(zip(
            ("compared","within_50m","within_250m","within_1km","at_least_10km_apart"),distances)),
        "publisher_crs_confirmed":False,"publisher_point_precision_confirmed":False,
        "points_promoted":0,"provider_calls":0,"database_writes":0}


if __name__=="__main__":
    import psycopg
    from pipeline.scripts.release_baseline import load_contract,validate_database_url,verify_connection
    try:
        url=os.environ["UEC_DATABASE_URL"];validate_database_url(url)
        with psycopg.connect(url) as connection:
            report=audit(connection)
            report["baseline"]=verify_connection(connection,load_contract(
                Path(__file__).parents[2]/"pipeline/contracts/development-baseline.json"))["status"]
            print(json.dumps(report,sort_keys=True))
    except Exception as error:
        print(json.dumps({"status":"failed","error_type":type(error).__name__}))
        raise SystemExit(1)
