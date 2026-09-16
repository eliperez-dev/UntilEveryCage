#!/usr/bin/env python3
"""Run deterministic, synthetic V2 discovery query-plan and scale checks.

The benchmark uses only PostgreSQL TEMP tables. Closing the connection drops
all generated data, so this script cannot contaminate the application's ``uec``
schema. Output is an aggregate report: it never prints query rows or plan
constants.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_SCALES = (100_000, 1_000_000)
MAX_SCALE = 2_000_000

GRAPH_INDEXES = {
    "bench_graph_edge_public_idx",
    "bench_graph_claim_public_idx",
}

QUERY_SPECS = (
    {"name": "list", "sql": """
        SELECT ordinal FROM bench_discovery_scale
        WHERE country_code = 'DK' ORDER BY facility_id LIMIT 50
    """, "params": (), "expected_indexes": ("bench_discovery_country_cursor_idx", "bench_discovery_facility_pk")},
    {"name": "pagination", "sql": """
        SELECT ordinal FROM bench_discovery_scale
        WHERE country_code = 'DK'
          AND facility_id > '00000000-0000-4000-8000-000000050000'::uuid
        ORDER BY facility_id LIMIT 50
    """, "params": (), "expected_indexes": ("bench_discovery_country_cursor_idx", "bench_discovery_facility_pk")},
    {"name": "filters", "sql": """
        SELECT ordinal FROM bench_discovery_scale
        WHERE country_code = 'DK' AND category = 'slaughter'
        ORDER BY facility_id LIMIT 50
    """, "params": (), "expected_indexes": ("bench_discovery_country_category_cursor_idx", "bench_discovery_facility_pk")},
    {"name": "text_filter", "sql": """
        SELECT ordinal FROM bench_discovery_scale
        WHERE lower(canonical_name) LIKE 'synthetic facility 999%%'
        ORDER BY facility_id LIMIT 50
    """, "params": (), "expected_indexes": ("bench_discovery_name_idx",)},
    {"name": "bbox", "sql": """
        SELECT ordinal FROM bench_discovery_scale
        WHERE location && ST_MakeEnvelope(-10, 45, -9.99, 45.01, 4326)::geography
        LIMIT 50
    """, "params": (), "expected_indexes": ("bench_discovery_location_idx",)},
    {"name": "radius", "sql": """
        SELECT ordinal FROM bench_discovery_scale
        WHERE ST_DWithin(location, ST_SetSRID(ST_Point(-5, 50), 4326)::geography, 50000)
        ORDER BY facility_id LIMIT 50
    """, "params": (), "expected_indexes": ("bench_discovery_location_idx",)},
    {"name": "detail", "sql": """
        SELECT ordinal FROM bench_discovery_scale
        WHERE facility_id = '00000000-0000-4000-8000-000000050000'::uuid
    """, "params": (), "expected_indexes": ("bench_discovery_facility_pk",)},
    {"name": "graph_ready", "sql": """
        SELECT edge.ordinal
        FROM bench_graph_edges_scale edge
        JOIN bench_graph_claims_scale claim
          ON claim.edge_ordinal = edge.ordinal AND claim.release_ordinal = edge.release_ordinal
        WHERE edge.release_ordinal = 1 AND edge.release_status = 'promoted'
          AND edge.publication_status = 'released' AND edge.storage_state = 'released'
          AND edge.review_state = 'accepted' AND edge.privacy_status = 'passed'
          AND edge.source_restricted = false
          AND claim.publication_status = 'released' AND claim.storage_state = 'released'
          AND claim.review_state = 'accepted' AND claim.privacy_status = 'passed'
          AND claim.source_restricted = false
        ORDER BY edge.ordinal LIMIT 50
    """, "params": (), "expected_indexes": GRAPH_INDEXES},
)


def _validate_scales(scales: list[int]) -> tuple[int, ...]:
    if not scales:
        raise ValueError("at least one scale is required")
    if any(scale < 1 or scale > MAX_SCALE for scale in scales):
        raise ValueError(f"scales must be between 1 and {MAX_SCALE:,}")
    if len(set(scales)) != len(scales):
        raise ValueError("scales must be unique")
    return tuple(scales)


def _json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def summarize_plan(payload: Any) -> dict[str, Any]:
    """Reduce EXPLAIN JSON to row-free operational measurements."""
    document = _json_value(payload)
    if not isinstance(document, list) or not document or not isinstance(document[0], dict):
        raise ValueError("unexpected EXPLAIN JSON envelope")
    root = document[0].get("Plan")
    if not isinstance(root, dict):
        raise ValueError("EXPLAIN JSON did not contain a plan")
    node_types: set[str] = set()
    index_names: set[str] = set()
    sequential_scans = 0
    shared_hit_blocks = 0
    shared_read_blocks = 0
    actual_rows = 0

    def visit(node: dict[str, Any]) -> None:
        nonlocal sequential_scans, shared_hit_blocks, shared_read_blocks, actual_rows
        node_type = node.get("Node Type")
        if isinstance(node_type, str):
            node_types.add(node_type)
            sequential_scans += node_type == "Seq Scan"
        if isinstance(node.get("Index Name"), str):
            index_names.add(node["Index Name"])
        shared_hit_blocks += int(node.get("Shared Hit Blocks", 0) or 0)
        shared_read_blocks += int(node.get("Shared Read Blocks", 0) or 0)
        if isinstance(node.get("Actual Rows"), (int, float)):
            actual_rows = int(node["Actual Rows"])
        for child in node.get("Plans", []):
            if isinstance(child, dict):
                visit(child)

    visit(root)
    actual_rows = int(root.get("Actual Rows", 0) or 0)
    report = {
        "planning_ms": float(document[0].get("Planning Time", 0.0)),
        "execution_ms": float(document[0].get("Execution Time", 0.0)),
        "actual_rows": actual_rows,
        "node_types": sorted(node_types),
        "index_names": sorted(index_names),
        "sequential_scan_nodes": sequential_scans,
        "shared_hit_blocks": shared_hit_blocks,
        "shared_read_blocks": shared_read_blocks,
    }
    forbidden = ("facility_id", "canonical_name", "source_record", "address", "coordinate")
    if any(term in json.dumps(report).lower() for term in forbidden):
        raise ValueError("row-bearing or private field leaked into plan summary")
    return report


def _create_tables(connection: Any, scale: int) -> None:
    connection.execute("""
        CREATE TEMP TABLE bench_discovery_scale AS
        SELECT n AS ordinal,
               format('00000000-0000-4000-8000-%%s', lpad(n::text, 12, '0'))::uuid AS facility_id,
               format('Synthetic facility %%s', n) AS canonical_name,
               CASE WHEN n %% 2 = 0 THEN 'DK' ELSE 'SE' END AS country_code,
               CASE n %% 4 WHEN 0 THEN 'slaughter' WHEN 1 THEN 'fish_processing'
                 WHEN 2 THEN 'logistics_and_storage' ELSE 'retail_and_prepared_food' END AS category,
               ST_SetSRID(ST_Point(-10 + (n %% 2000) / 100.0, 45 + (n %% 1000) / 100.0), 4326)::geography AS location
        FROM generate_series(1, %s) AS n
    """, (scale,))
    connection.execute("ALTER TABLE bench_discovery_scale ADD CONSTRAINT bench_discovery_facility_pk PRIMARY KEY (facility_id)")
    connection.execute("CREATE INDEX bench_discovery_country_cursor_idx ON bench_discovery_scale (country_code, facility_id)")
    connection.execute("CREATE INDEX bench_discovery_country_category_cursor_idx ON bench_discovery_scale (country_code, category, facility_id)")
    connection.execute("CREATE INDEX bench_discovery_name_idx ON bench_discovery_scale (lower(canonical_name) text_pattern_ops)")
    connection.execute("CREATE INDEX bench_discovery_location_idx ON bench_discovery_scale USING GIST (location)")
    connection.execute("""
        CREATE TEMP TABLE bench_graph_edges_scale AS
        SELECT n AS ordinal, 1 AS release_ordinal, 'promoted'::text AS release_status,
               'released'::text AS publication_status, 'released'::text AS storage_state,
               'accepted'::text AS review_state, 'passed'::text AS privacy_status,
               (n %% 17 = 0) AS source_restricted
        FROM generate_series(1, %s) AS n
    """, (scale,))
    connection.execute("""
        CREATE TEMP TABLE bench_graph_claims_scale AS
        SELECT n AS edge_ordinal, 1 AS release_ordinal,
               'released'::text AS publication_status, 'released'::text AS storage_state,
               'accepted'::text AS review_state, 'passed'::text AS privacy_status,
               (n %% 17 = 0) AS source_restricted
        FROM generate_series(1, %s) AS n
    """, (scale,))
    connection.execute("CREATE INDEX bench_graph_edge_public_idx ON bench_graph_edges_scale (release_ordinal, publication_status, storage_state, review_state, privacy_status, source_restricted, ordinal)")
    connection.execute("CREATE INDEX bench_graph_claim_public_idx ON bench_graph_claims_scale (release_ordinal, publication_status, storage_state, review_state, privacy_status, source_restricted, edge_ordinal)")
    connection.execute("ANALYZE bench_discovery_scale")
    connection.execute("ANALYZE bench_graph_edges_scale")
    connection.execute("ANALYZE bench_graph_claims_scale")
    connection.commit()


def _run_scale(connection: Any, scale: int, check_plans: bool) -> dict[str, Any]:
    _create_tables(connection, scale)
    queries: list[dict[str, Any]] = []
    for spec in QUERY_SPECS:
        row = connection.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + spec["sql"], spec["params"]).fetchone()
        summary = summarize_plan(row[0])
        expected = set(spec["expected_indexes"])
        used = set(summary["index_names"])
        matching_indexes = sorted(expected & used)
        plan_check = {"expected_index_family": sorted(expected), "matching_indexes": matching_indexes, "passed": bool(matching_indexes)}
        if check_plans and not plan_check["passed"]:
            raise RuntimeError(f"{spec['name']} plan did not use an expected index; used={sorted(used)}")
        if summary["actual_rows"] > 50:
            raise RuntimeError(f"{spec['name']} exceeded the bounded page size")
        queries.append({"name": spec["name"], **summary, "plan_check": plan_check})
    return {"observations": scale, "queries": queries}


def run(database_url: str, scales: tuple[int, ...], check_plans: bool = True) -> dict[str, Any]:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("install pipeline/requirements.txt before running the benchmark") from exc
    reports = []
    for scale in scales:
        with psycopg.connect(database_url) as connection:
            reports.append(_run_scale(connection, scale, check_plans))
    return {"schema_version": 1, "synthetic_only": True, "temporary_tables": True, "query_count_per_scale": len(QUERY_SPECS), "scales": reports}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--scales", nargs="+", type=int, default=list(DEFAULT_SCALES))
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--skip-plan-checks", action="store_true")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    try:
        report = run(args.database_url, _validate_scales(args.scales), not args.skip_plan_checks)
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(serialized, encoding="utf-8")
    sys.stdout.write(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
