#!/usr/bin/env python3
"""Measure a private, non-authorizing prospective V1 cohort from r5.

This never creates a release, review, rights decision, manifest, or public
projection.  Its ignored output is an aggregate receipt whose freeze digest
must be consumed by the later reviewed candidate workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.common.prospective_release import measure  # noqa: E402


def _inventory_digest(inventory: object) -> str:
    if not isinstance(inventory, dict) or inventory.get("status") != "measured":
        raise ValueError("inventory must be measured")
    claimed = inventory.get("inventory_sha256")
    body = dict(inventory)
    body.pop("inventory_sha256", None)
    body.pop("read_at_utc", None)
    actual = hashlib.sha256((json.dumps(body, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")) + "\n").encode()).hexdigest()
    if claimed != actual:
        raise ValueError("inventory digest mismatch")
    return actual


def _safe_output(path: Path) -> Path:
    root = (ROOT / "data" / "reports").resolve(strict=True)
    target = path.resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError("output must be an ignored data/reports file") from error
    if path.is_symlink() or target.exists() or not target.parent.is_dir():
        raise ValueError("output must be a new non-symlink file in an existing reports directory")
    return target


def _database_url(value: str | None) -> str:
    if not value:
        raise ValueError("database URL is required")
    parsed = urlsplit(value)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("database must be loopback PostgreSQL")
    if parsed.path.lstrip("/") != "uec_v0_api_repair":
        raise ValueError("prospective measurement only accepts the retained development database")
    return value


def _frozen_database_url(value: str | None) -> str:
    if not value:
        raise ValueError("frozen baseline database URL is required")
    parsed = urlsplit(value)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path.lstrip("/") != "uec_v0_review_r3":
        raise ValueError("frozen baseline must be the loopback uec_v0_review_r3 database")
    return value


def _frozen_exclusions(connection) -> tuple[list[str], list[str], str]:
    rows = connection.execute("""
        WITH inherited AS (
          SELECT excluded.source_record_id::uuid AS source_record_id
            FROM uec.release_cohort_review_current scope
            CROSS JOIN LATERAL jsonb_array_elements_text(scope.excluded_source_record_ids) excluded(source_record_id)
           WHERE scope.release_id='v0-candidate-2026-10-04-r3'
        )
        SELECT DISTINCT record.source_id, observation.facility_id::text
          FROM inherited
          JOIN uec.source_records record USING (source_record_id)
          JOIN uec.observations observation USING (source_record_id)
         ORDER BY record.source_id, observation.facility_id::text
    """).fetchall()
    sources = [row[0] for row in rows]
    identities = [row[1] for row in rows]
    import hashlib
    digest = hashlib.sha256(("\n".join(f"{source}:{facility}" for source, facility in rows) + "\n").encode("utf-8")).hexdigest()
    if len(rows) != 553:
        raise ValueError("frozen inherited exclusion lineage count is not the approved 553")
    return sources, identities, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-release-id", required=True)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--frozen-database-url", default=os.environ.get("UEC_FROZEN_DATABASE_URL"))
    args = parser.parse_args(argv)
    try:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        digest = _inventory_digest(inventory)
        output = _safe_output(args.output)
        with psycopg.connect(_frozen_database_url(args.frozen_database_url)) as frozen:
            with frozen.transaction():
                frozen.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                inherited_sources, inherited_ids, inherited_digest = _frozen_exclusions(frozen)
        with psycopg.connect(_database_url(args.database_url)) as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                snapshot = measure(connection, digest, args.candidate_release_id, inherited_ids, inherited_digest, inherited_sources)
        output.write_text(json.dumps(snapshot, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"status": "measured", "freeze_proposal_sha256": snapshot["freeze_proposal_sha256"],
                          "candidate_count": snapshot["cohort"]["candidate_count"],
                          "mapped_candidate_count": snapshot["cohort"]["mapped_candidate_count"],
                          "unmapped_candidate_count": snapshot["cohort"]["unmapped_candidate_count"],
                          "conditional_geometry_valid_count": snapshot["cohort"]["conditional_geometry_valid_count"],
                          "public_authorized": False}, sort_keys=True))
    except (OSError, ValueError, psycopg.Error) as error:
        print(json.dumps({"status": "blocked", "reason": type(error).__name__}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
