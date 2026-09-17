#!/usr/bin/env python3
"""Promote a validated release to the active public release state."""

import argparse
import hashlib
import json
import os
import sys
from datetime import timezone
from pathlib import Path

import psycopg


def can_promote(status: str, test_only: bool = False) -> bool:
    return status == "validated" and not test_only


def canonical_json(manifest: dict) -> str:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_manifest(path: Path, result: dict) -> None:
    payload = canonical_json(result["manifest"]).encode("utf-8")
    if hashlib.sha256(payload).hexdigest() != result["manifest_sha256"]:
        raise ValueError("manifest digest does not match promotion result")
    with path.open("xb") as output:
        output.write(payload)


def inventory_artifacts(paths: list[Path], no_distributed_artifacts: bool) -> list[dict]:
    if no_distributed_artifacts == bool(paths):
        raise ValueError("declare --artifact for every distributed file or --no-distributed-artifacts")
    artifacts = []
    names = set()
    for path in paths:
        if not path.is_file():
            raise ValueError(f"distributed artifact is not a file: {path}")
        name = path.name
        if name in names:
            raise ValueError(f"duplicate distributed artifact name: {name}")
        names.add(name)
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as artifact:
            for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        artifacts.append({"name": name, "sha256": digest.hexdigest(), "byte_size": size})
    return sorted(artifacts, key=lambda artifact: artifact["name"])


def utc_iso(value) -> str:
    if value.tzinfo is None:
        raise ValueError("database timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def promote(database_url: str, release_id: str, artifacts: list[dict]) -> dict:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            target = connection.execute("SELECT status, profile, ruleset_version, test_only, summary FROM uec.releases WHERE release_id = %s FOR UPDATE", (release_id,)).fetchone()
            if not target:
                raise ValueError(f"release not found: {release_id}")
            if not can_promote(target[0], target[3]):
                if target[3]:
                    raise ValueError("test-only releases cannot be validated or promoted")
                raise ValueError(f"release must be validated before promotion; current status is {target[0]}")
            unsafe = connection.execute("""
                SELECT
                  count(*) FILTER (WHERE m.default_visible AND (g.status IS DISTINCT FROM 'accepted' OR g.result IS NULL)),
                  count(*) FILTER (WHERE o.classification_review_status <> 'approved' AND m.default_visible),
                  count(*) FILTER (WHERE r.release_id IS NULL OR r.publication_eligible IS DISTINCT FROM true OR r.privacy_screening_status IS DISTINCT FROM 'passed' OR r.maintainer_approval IS DISTINCT FROM 'approved'),
                  count(*) FILTER (WHERE s.source_record_id IS NOT NULL),
                  count(*) FILTER (WHERE m.default_visible AND (release.summary->'demonstration' IS NOT NULL AND release.summary->'demonstration'->>'rights_status' IS DISTINCT FROM 'cleared'))
                FROM uec.release_members m
                JOIN uec.releases release ON release.release_id = m.release_id
                JOIN uec.observations o ON o.observation_id = m.observation_id
                LEFT JOIN LATERAL (SELECT status, result FROM uec.geocode_results WHERE source_record_id=o.source_record_id ORDER BY queried_at DESC, geocode_result_id DESC LIMIT 1) g ON true
                LEFT JOIN uec.publication_review_release_current r
                  ON r.source_record_id=o.source_record_id AND r.release_id=m.release_id
                LEFT JOIN uec.public_access_restricted s ON s.source_record_id=o.source_record_id
                WHERE m.release_id=%s
            """, (release_id,)).fetchone()
            if any(unsafe):
                raise ValueError(f"release safety gates failed: coordinate_not_ready={unsafe[0]}, review_required={unsafe[1]}, publication_not_approved={unsafe[2]}, active_suppression={unsafe[3]}, rights_not_cleared={unsafe[4]}")
            demonstration = target[4].get("demonstration") if isinstance(target[4], dict) else None
            if demonstration is not None and demonstration.get("review_status") != "approved":
                raise ValueError("demonstration release requires an explicit recorded review")
            previous = connection.execute("SELECT release_id FROM uec.releases WHERE status = 'promoted' AND profile = %s AND release_id <> %s ORDER BY created_at DESC, release_id DESC LIMIT 1", (target[1], release_id)).fetchone()
            summary = connection.execute("""
                SELECT count(*), coalesce(array_agg(DISTINCT sr.source_id ORDER BY sr.source_id), ARRAY[]::text[])
                FROM uec.release_members m JOIN uec.observations o ON o.observation_id=m.observation_id
                JOIN uec.source_records sr ON sr.source_record_id=o.source_record_id
                WHERE m.release_id=%s AND m.default_visible
                  AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted x WHERE x.source_record_id=sr.source_record_id)
            """, (release_id,)).fetchone()
            coverage_rows = connection.execute("""
                SELECT sr.source_id, count(*)::int, min(artifact.retrieved_at), max(artifact.retrieved_at),
                       CASE WHEN source.attribution IS NULL OR btrim(source.attribution) = '' THEN 'unknown' ELSE 'attribution_required' END
                FROM uec.release_members m
                JOIN uec.observations o ON o.observation_id=m.observation_id
                JOIN uec.source_records sr ON sr.source_record_id=o.source_record_id
                JOIN uec.raw_artifacts artifact ON artifact.artifact_id=sr.artifact_id
                JOIN uec.sources source ON source.source_id=sr.source_id
                WHERE m.release_id=%s AND m.default_visible
                  AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted x WHERE x.source_record_id=sr.source_record_id)
                GROUP BY sr.source_id, source.attribution ORDER BY sr.source_id
            """, (release_id,)).fetchall()
            created_at = connection.execute("SELECT now()").fetchone()[0]
            if created_at.tzinfo is None:
                raise ValueError("database manifest creation time must include a timezone")
            source_coverage = [
                {"source_id": source_id, "row_count": row_count, "retrieved_at": {"first": utc_iso(first), "last": utc_iso(last)}, "rights_status": rights_status}
                for source_id, row_count, first, last, rights_status in coverage_rows
            ]
            retrieved_at = min((item["retrieved_at"]["first"] for item in source_coverage), default=utc_iso(created_at))
            manifest = {
                "manifest_version": "uec-release-manifest-v2",
                "data_product_version": "uec-public-data-product-v1",
                "release_id": release_id,
                "profile": target[1],
                "release_status": "promoted",
                "test_only": False,
                "ruleset_version": target[2],
                "schema_version": "uec-location-projection-v1",
                "generated_at": utc_iso(created_at),
                "retrieved_at": retrieved_at,
                "source_ids": summary[1],
                "source_coverage": source_coverage,
                "eligible_record_count": summary[0],
                "row_counts": {"eligible_rows": summary[0], "packaged_rows": summary[0]},
                "checksums": {"algorithm": "sha256", "distributed_artifacts": artifacts},
                "review_state": "privacy-screened; community claims may be unreviewed" if target[1] == "community" else "project-approved and privacy-screened",
                "publication_state": "project-published",
                "limitations": [
                    "Facility projection rows are not animal counts or a complete story-wide denominator.",
                    "Coordinates and addresses remain subject to current privacy and coarse-location rules.",
                    "Source origin and source availability do not certify factual accuracy or current operation.",
                    "Artifact checksums detect byte changes but do not establish factual accuracy or reuse rights.",
                ],
                "supersedes": previous[0] if previous else None,
                "rights_review": (demonstration or {}).get("rights_status") if demonstration else "not-recorded",
                "created_at": utc_iso(created_at),
                "distributed_artifacts": artifacts,
            }
            # Python's sorted-key JSON is the canonical representation shared by consumers.
            canonical = canonical_json(manifest)
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            connection.execute("INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256) VALUES (%s,%s,%s)", (release_id, canonical, digest))
            previous_rows = connection.execute("SELECT release_id FROM uec.releases WHERE status = 'promoted' AND profile = %s AND release_id <> %s", (target[1], release_id)).fetchall()
            connection.execute("UPDATE uec.releases SET status = 'validated' WHERE status = 'promoted' AND profile = %s AND release_id <> %s", (target[1], release_id))
            connection.execute("UPDATE uec.releases SET status = 'promoted' WHERE release_id = %s", (release_id,))
            return {"release_id": release_id, "status": "promoted", "previously_promoted": [row[0] for row in previous_rows], "manifest": manifest, "manifest_sha256": digest}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_id")
    parser.add_argument("--manifest", type=Path)
    artifacts = parser.add_mutually_exclusive_group(required=True)
    artifacts.add_argument("--artifact", type=Path, action="append", help="Distributed file to checksum; repeat for every file")
    artifacts.add_argument("--no-distributed-artifacts", action="store_true", help="Declare that this release has no distributed files")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    args = parser.parse_args()
    try:
        if args.manifest and (not args.manifest.parent.is_dir() or args.manifest.exists()):
            raise ValueError("manifest output requires an existing directory and a new file name")
        if args.manifest and args.artifact and args.manifest.resolve() in {path.resolve() for path in args.artifact}:
            raise ValueError("the output manifest cannot be one of its distributed artifacts")
        artifact_inventory = inventory_artifacts(args.artifact or [], args.no_distributed_artifacts)
        result = promote(args.database_url, args.release_id, artifact_inventory)
        serialized = json.dumps({key: value for key, value in result.items() if key != "manifest"}, indent=2) + "\n"
        print(serialized, end="")
        if args.manifest:
            write_manifest(args.manifest, result)
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, indent=2), file=sys.stderr)
        sys.exit(1)
