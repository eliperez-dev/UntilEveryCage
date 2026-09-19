#!/usr/bin/env python3
"""Compare synthetic nested and flattened public projection query plans.

The harness uses only a disposable local E2E database and emits plan metadata,
timings, and aggregate buffer/node counts. It never prints plan SQL, values, or
rows, so it is safe to use as a repeatable diagnostic artifact.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LOAD_SCRIPT = ROOT / "pipeline" / "scripts" / "benchmarks" / "run_api_load_rehearsal.py"
BUILD_SCRIPT = ROOT / "pipeline" / "scripts" / "maintenance" / "build_release_summary_component.py"
SPEC = importlib.util.spec_from_file_location("run_api_load_rehearsal", LOAD_SCRIPT)
assert SPEC and SPEC.loader
LOAD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LOAD
SPEC.loader.exec_module(LOAD)
BUILD_SPEC = importlib.util.spec_from_file_location("build_release_summary_component", BUILD_SCRIPT)
assert BUILD_SPEC and BUILD_SPEC.loader
BUILD = importlib.util.module_from_spec(BUILD_SPEC)
sys.modules[BUILD_SPEC.name] = BUILD
BUILD_SPEC.loader.exec_module(BUILD)

OLD_FACETS = """
SELECT country_code, classification_category, display_precision,
       lifecycle_status, provenance_origin_type, city, count(*)::bigint
FROM (
    SELECT display.country_code, display.city, display.display_precision,
           observation.classification_category,
           COALESCE(lifecycle.status, 'status_unknown') AS lifecycle_status,
           source.origin_type AS provenance_origin_type
    FROM uec.map_facilities_display AS display
    JOIN uec.publication_release_eligible_observations AS eligible
      ON eligible.release_id = display.release_id
     AND eligible.observation_id = display.observation_id
    JOIN uec.observations AS observation
      ON observation.observation_id = display.observation_id
    JOIN uec.source_records AS record
      ON record.source_record_id = display.source_record_id
    JOIN uec.sources AS source
      ON source.source_id = record.source_id
    JOIN uec.release_members AS member
      ON member.release_id = display.release_id
     AND member.observation_id = display.observation_id
    JOIN uec.releases AS release
      ON release.release_id = member.release_id
    JOIN uec.raw_artifacts AS artifact
      ON artifact.artifact_id = record.artifact_id
    JOIN uec.public_facility_observation_summary AS summary
      ON summary.release_id = display.release_id
     AND summary.facility_id = display.facility_id
    LEFT JOIN uec.facility_lifecycle_current AS lifecycle
      ON lifecycle.facility_id = display.facility_id
    WHERE display.release_id = 'load-promoted'
) history
GROUP BY country_code, classification_category, display_precision,
         lifecycle_status, provenance_origin_type, city
"""

NEW_FACETS = """
SELECT country_code, classification_category, display_precision,
       lifecycle_status, provenance_origin_type, city, count(*)::bigint
FROM uec.map_facilities_display_history
WHERE release_id = 'load-promoted'
GROUP BY country_code, classification_category, display_precision,
         lifecycle_status, provenance_origin_type, city
"""

OLD_LIST = """
SELECT history.facility_id, history.canonical_name, history.country_code,
       history.city, history.classification_category, history.display_precision
FROM (
    SELECT display.facility_id, display.canonical_name, display.country_code,
           display.city, display.display_precision,
           observation.classification_category,
           display.release_id, display.source_record_id
    FROM uec.map_facilities_display AS display
    JOIN uec.publication_release_eligible_observations AS eligible
      ON eligible.release_id = display.release_id
     AND eligible.observation_id = display.observation_id
    JOIN uec.observations AS observation
      ON observation.observation_id = display.observation_id
    JOIN uec.source_records AS record
      ON record.source_record_id = display.source_record_id
    JOIN uec.sources AS source
      ON source.source_id = record.source_id
    JOIN uec.release_members AS member
      ON member.release_id = display.release_id
     AND member.observation_id = display.observation_id
    JOIN uec.releases AS release
      ON release.release_id = member.release_id
    JOIN uec.raw_artifacts AS artifact
      ON artifact.artifact_id = record.artifact_id
    JOIN uec.public_facility_observation_summary AS summary
      ON summary.release_id = display.release_id
     AND summary.facility_id = display.facility_id
    LEFT JOIN uec.facility_lifecycle_current AS lifecycle
      ON lifecycle.facility_id = display.facility_id
    WHERE display.release_id = 'load-promoted'
) history
JOIN uec.publication_review_release_current AS review
  ON review.source_record_id = history.source_record_id
 AND review.release_id = history.release_id
ORDER BY history.facility_id
LIMIT 51
"""

NEW_LIST = """
SELECT history.facility_id, history.canonical_name, history.country_code,
       history.city, history.classification_category, history.display_precision
FROM uec.map_facilities_display_history AS history
JOIN uec.publication_review_release_current AS review
  ON review.source_record_id = history.source_record_id
 AND review.release_id = history.release_id
WHERE history.release_id = 'load-promoted'
ORDER BY history.facility_id
LIMIT 51
"""

ELIGIBILITY = """
SELECT member.release_id, member.facility_id, observation.observation_id,
       observation.source_record_id, observation.first_observed_at,
       observation.observed_at
FROM uec.release_members AS member
JOIN uec.releases AS release ON release.release_id = member.release_id
JOIN uec.observations AS observation ON observation.observation_id = member.observation_id
JOIN uec.source_records AS record ON record.source_record_id = observation.source_record_id
JOIN uec.sources AS source ON source.source_id = record.source_id
JOIN uec.publication_review_release_current AS review
  ON review.source_record_id = observation.source_record_id
 AND review.release_id = member.release_id
WHERE release.status = 'promoted'
  AND member.default_visible = true
  AND review.publication_eligible = true
  AND review.privacy_screening_status = 'passed'
  AND review.factual_review_status <> 'rejected'
  AND (review.maintainer_approval = 'approved'
       OR (release.profile = 'community' AND source.origin_type = 'user_submitted'
           AND review.factual_review_status = 'unreviewed'
           AND review.maintainer_approval = 'pending'))
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted AS restricted
      WHERE restricted.source_record_id = observation.source_record_id
  )
  AND member.release_id = 'load-promoted'
"""

COMPONENT_QUERIES = {
    "eligibility_gate": "SELECT count(*) FROM (" + ELIGIBILITY + ") eligible",
    "eligible_summary": """
SELECT count(*) FROM (
    SELECT eligible.release_id, eligible.facility_id,
           min(eligible.first_observed_at), max(eligible.observed_at), count(*)
    FROM (""" + ELIGIBILITY + """) eligible
    GROUP BY eligible.release_id, eligible.facility_id
) summary
""",
    "geocode_lookup": """
SELECT count(*)
FROM uec.observations observation
JOIN uec.source_records record ON record.source_record_id = observation.source_record_id
LEFT JOIN LATERAL (
    SELECT result FROM uec.geocode_results
    WHERE source_record_id = observation.source_record_id
    ORDER BY queried_at DESC, geocode_result_id DESC LIMIT 1
) latest ON true
WHERE record.source_id = 'load.synthetic'
""",
    "city_lookup": """
SELECT count(*)
FROM uec.facilities facility
LEFT JOIN LATERAL (
    SELECT reference_location
    FROM uec.city_reference_points
    WHERE country_code = facility.country_code
      AND lower(city_name) = lower(facility.city)
      AND (postal_code IS NULL OR postal_code = facility.postal_code)
    ORDER BY postal_code NULLS LAST LIMIT 1
) city ON true
WHERE facility.canonical_name LIKE 'Synthetic load facility %'
""",
    "lifecycle_lookup": """
SELECT count(*)
FROM uec.facilities facility
LEFT JOIN uec.facility_lifecycle_current lifecycle
  ON lifecycle.facility_id = facility.facility_id
WHERE facility.canonical_name LIKE 'Synthetic load facility %'
""",
    "spatial_filter": """
SELECT count(*)
FROM uec.map_facilities_display_history history
WHERE history.release_id = 'load-promoted'
  AND history.display_location && ST_MakeEnvelope(-10, 45, -9.99, 45.01, 4326)::geography
  AND ST_Intersects(history.display_location::geometry, ST_MakeEnvelope(-10, 45, -9.99, 45.01, 4326))
""",
    "pagination_sort": """
SELECT facility_id
FROM uec.map_facilities_display_history
WHERE release_id = 'load-promoted'
ORDER BY facility_id
LIMIT 51
""",
    "component_summary_candidate": """
SELECT count(*)
FROM uec.public_facility_observation_summary_component_candidate
WHERE release_id = 'load-promoted'
""",
}


def plan_summary(payload: list[Any]) -> dict[str, Any]:
    root = payload[0]
    plan = root["Plan"]
    nodes: Counter[str] = Counter()
    actual_rows = 0
    shared_hit = 0
    shared_read = 0
    temp_read = 0
    temp_written = 0
    expensive_nodes: list[dict[str, Any]] = []
    relation_times: Counter[str] = Counter()

    def visit(node: dict[str, Any]) -> None:
        nonlocal actual_rows, shared_hit, shared_read, temp_read, temp_written
        nodes[node.get("Node Type", "unknown")] += 1
        actual_rows = max(actual_rows, int(node.get("Actual Rows", 0)))
        shared_hit += int(node.get("Shared Hit Blocks", 0))
        shared_read += int(node.get("Shared Read Blocks", 0))
        temp_read += int(node.get("Temp Read Blocks", 0))
        temp_written += int(node.get("Temp Written Blocks", 0))
        if "Actual Total Time" in node:
            total_ms = float(node.get("Actual Total Time", 0)) * float(node.get("Actual Loops", 0))
            relation = node.get("Relation Name")
            if relation:
                relation_times[relation] += total_ms
            expensive_nodes.append({
                "node_type": node.get("Node Type", "unknown"),
                "relation": node.get("Relation Name"),
                "index": node.get("Index Name"),
                "loops": int(node.get("Actual Loops", 0)),
                "actual_rows": int(node.get("Actual Rows", 0)),
                "total_ms": round(total_ms, 3),
            })
        for child in node.get("Plans", []):
            visit(child)

    visit(plan)
    return {
        "planning_ms": round(float(root.get("Planning Time", 0)), 3),
        "execution_ms": round(float(root.get("Execution Time", 0)), 3),
        "actual_rows_max": actual_rows,
        "node_counts": dict(sorted(nodes.items())),
        "shared_hit_blocks": shared_hit,
        "shared_read_blocks": shared_read,
        "temp_read_blocks": temp_read,
        "temp_written_blocks": temp_written,
        "expensive_nodes": sorted(expensive_nodes, key=lambda node: node["total_ms"], reverse=True)[:12],
        "relation_total_ms": {name: round(value, 3) for name, value in relation_times.most_common()},
    }


def run_explain(connection: Any, query: str, analyze: bool) -> dict[str, Any]:
    option = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "BUFFERS, FORMAT JSON"
    payload = connection.execute("EXPLAIN (" + option + ") " + query).fetchone()[0]
    summary = plan_summary(payload)
    summary["analyzed"] = analyze
    return summary


def run(observations: int, include_components: bool = False) -> dict[str, Any]:
    import psycopg
    from pipeline.tests.e2e.fixture import E2EEnvironment

    env = E2EEnvironment().start()
    try:
        with psycopg.connect(env.database_url) as connection:
            LOAD.seed_public_projection(connection, observations)
        BUILD.build(env.database_url, "load-promoted")
        with psycopg.connect(env.database_url) as connection:
            queries = {
                "facets_before_nested": OLD_FACETS,
                "facets_after_flattened": NEW_FACETS,
                "list_before_nested": OLD_LIST,
                "list_after_flattened": NEW_LIST,
            }
            connection.execute("SET statement_timeout = '30s'")
            plans = {}
            for name, query in queries.items():
                # The nested pre-change facets plan is intentionally estimated
                # only: executing it can consume the entire bounded rehearsal
                # timeout even on the 1,000-row fixture. The flattened path is
                # measured with ANALYZE for before/after root-cause evidence.
                plans[name] = run_explain(connection, query, analyze="after" in name)
            if include_components:
                plans["components"] = {
                    name: run_explain(connection, query, analyze=True)
                    for name, query in COMPONENT_QUERIES.items()
                }
    finally:
        env.stop()
    return {"schema_version": 1, "synthetic_only": True, "observations": observations, "plans": plans}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=int, default=1_000)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--components", action="store_true", help="also analyze isolated eligibility, summary, lookup, spatial, and pagination components")
    args = parser.parse_args(argv)
    if not 1 <= args.observations <= LOAD.MAX_SEED:
        parser.error(f"observations must be between 1 and {LOAD.MAX_SEED:,}")
    report = run(args.observations, include_components=args.components)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        args.json_output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
