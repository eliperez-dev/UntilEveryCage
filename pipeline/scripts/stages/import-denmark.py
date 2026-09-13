#!/usr/bin/env python3
"""Import classified Denmark staging data into PostgreSQL/PostGIS transactionally."""

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg


def now():
    return datetime.now(timezone.utc)


def metadata_value(metadata, *names):
    for name in names:
        if metadata.get(name) is not None:
            return metadata[name]
    return None


def point_from_geocode(item):
    # A provider's one-point response is evidence for review, not permission
    # to store/display a precise point. Only an explicit review decision can
    # advance it to an accepted coordinate.
    if item.get("acceptance") != "accepted_single_point" or item.get("coordinate_review_status") != "approved":
        return None
    response = item.get("response", [])
    results = response if isinstance(response, list) else response.get("results", [])
    if not results:
        return None
    return results[0].get("x"), results[0].get("y")


def geocode_status(item):
    review_status = item.get("coordinate_review_status")
    if review_status == "approved" and item.get("acceptance") == "accepted_single_point":
        return "accepted"
    if review_status == "review_required":
        return "review_required"
    return {
        "accepted_single_point": "review_required",
        "review_multiple_points": "review_required",
        "unresolved": "unresolved",
    }.get(item.get("acceptance"), "failed" if item.get("status") == "failed" else "unresolved")


def run(classified_path: Path, artifact_metadata_path: Path, geocode_path: Path | None, database_url: str, release_id: str):
    artifact = json.loads(artifact_metadata_path.read_text(encoding="utf-8"))
    geocodes = {}
    if geocode_path and geocode_path.exists():
        geocodes = {item["queue_key"]: item for item in (json.loads(line) for line in geocode_path.read_text(encoding="utf-8").splitlines() if line.strip())}
    run_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    checked_at = now()
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute("""
                INSERT INTO uec.sources(source_id, country_code, name, official_url, access_method, cadence, status, attribution)
                VALUES ('dk.smiley', 'DK', 'Find Smiley', %s, 'bulk_xml', 'weekly', 'active', 'Fødevarestyrelsen')
                ON CONFLICT (source_id) DO NOTHING
            """, (metadata_value(artifact, "source_url", "final_url", "requested_url"),))
            connection.execute("""
                INSERT INTO uec.acquisition_runs(run_id, source_id, checked_at, retrieved_at, ingested_at, status, source_url, code_version, config_version)
                VALUES (%s, 'dk.smiley', %s, %s, %s, 'changed', %s, 'import-denmark.py', 'denmark-classification-v1')
            """, (run_id, checked_at, artifact.get("retrieved_at_utc"), checked_at, metadata_value(artifact, "source_url", "final_url", "requested_url")))
            connection.execute("""
                INSERT INTO uec.raw_artifacts(artifact_id, storage_key, sha256, byte_size, media_type, retrieved_at)
                VALUES (%s, %s, %s, %s, 'application/xml', %s)
                ON CONFLICT (sha256) DO NOTHING
            """, (artifact_id, metadata_value(artifact, "artifact_path", "artifact"), artifact["sha256"], metadata_value(artifact, "bytes", "byte_size"), artifact["retrieved_at_utc"]))
            artifact_id = connection.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE sha256=%s", (artifact["sha256"],)).fetchone()[0]
            connection.execute("INSERT INTO uec.acquisition_run_artifacts(run_id, artifact_id) VALUES (%s, %s)", (run_id, artifact_id))
            connection.execute("INSERT INTO uec.releases(release_id, status, ruleset_version, summary) VALUES (%s, 'candidate', 'denmark-classification-v1', %s) ON CONFLICT DO NOTHING", (release_id, json.dumps({"source": "dk.smiley", "run_id": str(run_id)})))
            for line in classified_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                source_record_id = uuid.uuid5(uuid.NAMESPACE_URL, f"urn:uec:source-record:dk.smiley:{record['source_record_key']}:{artifact['sha256']}")
                facility_id = uuid.uuid5(uuid.NAMESPACE_URL, f"urn:uec:facility:dk.smiley:{record['source_record_key']}")
                observed_at = checked_at
                source_fields = record["source_fields"]
                address = record["address"]
                classification = record["classification"]
                geocode = geocodes.get(f"dk.smiley:{record['source_record_key']}")
                point = point_from_geocode(geocode) if geocode else None
                connection.execute("""
                    INSERT INTO uec.source_records(source_record_id, source_id, source_record_key, artifact_id, raw_fields, parsed_at)
                    VALUES (%s, 'dk.smiley', %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (source_record_id, record["source_record_key"], artifact_id, json.dumps(source_fields, ensure_ascii=False), checked_at))
                existing = connection.execute("SELECT source_record_id FROM uec.source_records WHERE source_id='dk.smiley' AND source_record_key=%s AND artifact_id=%s", (record["source_record_key"], artifact_id)).fetchone()
                source_record_id = existing[0]
                if geocode:
                    queried_at = geocode.get("queried_at_utc") or checked_at.isoformat()
                    geocode_id = uuid.uuid5(uuid.NAMESPACE_URL, f"urn:uec:geocode:{geocode['queue_key']}:{geocode.get('provider', 'unknown')}:{queried_at}")
                    connection.execute("""
                        INSERT INTO uec.geocode_results(geocode_result_id, source_record_id, provider_id, query, provider_address_id, result, match_method, status, attempt_number, retryable, response, queried_at)
                        VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s, %s, 1, %s, %s, %s)
                        ON CONFLICT (geocode_result_id) DO NOTHING
                    """, (geocode_id, source_record_id, geocode.get("provider", "unknown"), geocode.get("geocoder_query", ""), (geocode.get("response") or [{}])[0].get("id") if isinstance(geocode.get("response"), list) and geocode.get("response") else None, point[0] if point else None, point[1] if point else None, geocode.get("acceptance", "address"), geocode_status(geocode), geocode_status(geocode) == "failed", json.dumps(geocode, ensure_ascii=False), queried_at))
                connection.execute("""
                    INSERT INTO uec.facilities(facility_id, canonical_name, country_code, street_address, postal_code, city, location)
                    VALUES (%s, %s, 'DK', %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)
                    ON CONFLICT DO NOTHING
                """, (facility_id, record.get("name"), address.get("street"), address.get("postal_code"), address.get("city"), point[0] if point else None, point[1] if point else None))
                connection.execute("""
                    INSERT INTO uec.facility_source_links(facility_id, source_record_id, match_method, review_status)
                    VALUES (%s, %s, 'first_source_observation', 'automatic') ON CONFLICT DO NOTHING
                """, (facility_id, source_record_id))
                connection.execute("""
                    INSERT INTO uec.observations(observation_id, facility_id, source_record_id, observed_at, observation, classification, ruleset_id, rule_id, classification_category, classification_review_status, default_visible, optional_filter, coordinate, coordinate_method, coordinate_precision, coordinate_review_status, first_observed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (uuid.uuid5(uuid.NAMESPACE_URL, f"urn:uec:observation:dk.smiley:{record['source_record_key']}:{artifact['sha256']}"), facility_id, source_record_id, observed_at, json.dumps(record, ensure_ascii=False), json.dumps(classification), classification["ruleset_id"], classification["rule_id"], classification["category"], classification["review_status"], classification["default_visible"], classification.get("optional_filter"), point[0] if point else None, point[1] if point else None, "dawa" if point else None, "address_point" if point else None, "accepted" if point else "unresolved", observed_at))
                connection.execute("""
                    INSERT INTO uec.release_members(release_id, facility_id, observation_id, default_visible)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (release_id, facility_id, uuid.uuid5(uuid.NAMESPACE_URL, f"urn:uec:observation:dk.smiley:{record['source_record_key']}:{artifact['sha256']}"), classification["default_visible"] and not connection.execute("SELECT EXISTS (SELECT 1 FROM uec.public_access_restricted WHERE source_record_id = %s)", (source_record_id,)).fetchone()[0]))
    print(f"Imported Denmark run {run_id} as candidate release {release_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("classified", type=Path)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--geocodes", type=Path)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    parser.add_argument("--release-id", default="dk-2026-09-13-candidate")
    args = parser.parse_args()
    run(args.classified, args.artifact_metadata, args.geocodes, args.database_url, args.release_id)
