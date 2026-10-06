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

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from pipeline.common.source_rights import require_cleared
from pipeline.common.release_geometry import RELEASE_GATE_METRICS_SQL
from pipeline.scripts.maintenance import build_public_discovery_read_model as discovery


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


def validate_map_artifact(path: Path, release_id: str, profile: str, suppression_generation: int) -> dict:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if (artifact.get("schema_version") != "uec-public-map-artifact-v1"
            or artifact.get("release_id") != release_id
            or artifact.get("profile") != profile
            or artifact.get("source_layer") != "uec_map"
            or artifact.get("feature_schema_version") not in ("uec-map-feature-v1", "uec-map-feature-v2")):
        raise ValueError("map artifact identity or schema does not match the release")
    allowed_properties = ["feature_key", "kind", "count", "exact_count", "coarse_count", "next_zoom", "record_id", "category_key"]
    if artifact.get("feature_schema_version") == "uec-map-feature-v2":
        allowed_properties.append("category_keys_compact")
    if artifact.get("feature_properties") != allowed_properties:
        raise ValueError("map artifact feature property allowlist is invalid")
    if not artifact.get("count_semantics") or not artifact.get("feature_key_semantics") or not artifact.get("next_zoom_semantics"):
        raise ValueError("map artifact feature semantics are incomplete")
    if artifact.get("suppression_generation") != suppression_generation:
        raise ValueError("map artifacts were built against a stale suppression generation")
    if artifact.get("min_zoom") != 0 or artifact.get("max_zoom") != 14:
        raise ValueError("map artifact zoom range is unsupported")
    if not isinstance(artifact.get("generated_at"), str) or not isinstance(artifact.get("attribution"), list):
        raise ValueError("map artifact timestamp or attribution is invalid")
    bounds = artifact.get("bounds")
    if bounds is not None and (not isinstance(bounds, list) or len(bounds) != 4 or any(not isinstance(value, (int, float)) for value in bounds)):
        raise ValueError("map artifact bounds are invalid")
    if artifact.get("tile_url_template") != f"/api/v2/releases/{release_id}/map/tiles/{{z}}/{{x}}/{{y}}.mvt?profile={profile}":
        raise ValueError("map tile URL template is invalid")
    tiles = artifact.get("tiles")
    if not isinstance(tiles, list):
        raise ValueError("map tile inventory is missing")
    seen = set()
    for tile in tiles:
        try:
            z, x, y = (tile[name] for name in ("z", "x", "y"))
            digest = tile["sha256"]
            byte_size = tile["byte_size"]
        except (KeyError, TypeError):
            raise ValueError("map tile inventory entry is invalid") from None
        if any(not isinstance(value, int) for value in (z, x, y, byte_size)) or not 0 <= z <= 14 or not 0 <= x < 2**z or not 0 <= y < 2**z:
            raise ValueError("map tile coordinates or size are invalid")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("map tile checksum is invalid")
        if tile.get("etag") != f'"{digest}"':
            raise ValueError("map tile ETag does not match its checksum")
        key = (z, x, y)
        if key in seen:
            raise ValueError("map tile inventory contains duplicate coordinates")
        seen.add(key)
        tile_path = path.parent / str(z) / str(x) / f"{y}.mvt"
        if not tile_path.is_file():
            raise ValueError("map tile inventory references a missing tile")
        content = tile_path.read_bytes()
        if len(content) != byte_size or hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("map tile checksum does not match staged bytes")
    cache = artifact.get("cache_policy")
    if not isinstance(cache, dict) or not isinstance(cache.get("max_age_seconds"), int) or cache["max_age_seconds"] != 0:
        raise ValueError("map artifact cache policy is unbounded")
    if cache.get("cache_control") != f"public, max-age={cache['max_age_seconds']}, must-revalidate":
        raise ValueError("map artifact cache policy does not match its bounded TTL")
    return artifact


def utc_iso(value) -> str:
    if value.tzinfo is None:
        raise ValueError("database timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _same_immutable_manifest(existing: dict, proposed: dict) -> bool:
    """Compare the release identity and every immutable publication input."""
    keys = (
        "manifest_version", "data_product_version", "release_id", "profile",
        "release_status", "test_only", "ruleset_version", "schema_version",
        "suppression_generation", "retrieved_at", "source_ids", "source_coverage",
        "eligible_record_count", "row_counts", "checksums", "review_state",
        "publication_state", "limitations", "rights_review", "source_rights_gate",
        "distributed_artifacts", "map_artifact",
    )
    return all(existing.get(key) == proposed.get(key) for key in keys)


def promote(database_url: str, release_id: str, artifacts: list[dict], map_artifact: dict | None = None,
            *, _fail_after_read_model_rows: int | None = None) -> dict:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            profile_row = connection.execute(
                "SELECT profile FROM uec.releases WHERE release_id=%s", (release_id,)
            ).fetchone()
            if not profile_row:
                raise ValueError(f"release not found: {release_id}")
            # Serialize activation by profile before locking release rows. The
            # namespace separates this lock from unrelated advisory-lock users.
            connection.execute(
                "SELECT pg_advisory_xact_lock(82017, hashtext(%s))", (profile_row[0],)
            )
            target = connection.execute("SELECT status, profile, ruleset_version, test_only, summary FROM uec.releases WHERE release_id = %s FOR UPDATE", (release_id,)).fetchone()
            if not target:
                raise ValueError(f"release not found: {release_id}")
            if target[1] != profile_row[0]:
                raise ValueError("release profile changed during activation")
            if not can_promote(target[0], target[3]):
                if target[3]:
                    raise ValueError("test-only releases cannot be validated or promoted")
                raise ValueError(f"release must be validated before promotion; current status is {target[0]}")
            rights_gate = require_cleared(connection, release_id)
            unsafe = connection.execute("""
                SELECT
                  count(*) FILTER (WHERE m.default_visible AND (
                    g.status IS NULL
                    OR g.status = 'failed'
                    OR (g.status = 'accepted' AND (
                        g.result IS NULL
                        OR (ST_X(g.result::geometry) = 0 AND ST_Y(g.result::geometry) = 0)
                    ))
                    OR (g.status = 'unresolved' AND g.result IS NOT NULL)
                    OR (g.status = 'review_required' AND city.reference_location IS NOT NULL
                        AND ST_X(city.reference_location::geometry) = 0
                        AND ST_Y(city.reference_location::geometry) = 0)
                  )),
                  count(*) FILTER (WHERE o.classification_review_status <> 'approved' AND m.default_visible),
                  count(*) FILTER (WHERE r.release_id IS NULL OR r.publication_eligible IS DISTINCT FROM true OR r.privacy_screening_status IS DISTINCT FROM 'passed' OR r.maintainer_approval IS DISTINCT FROM 'approved'),
                  count(*) FILTER (WHERE s.source_record_id IS NOT NULL),
                  count(*) FILTER (WHERE m.default_visible AND (release.summary->'demonstration' IS NOT NULL AND release.summary->'demonstration'->>'rights_status' IS DISTINCT FROM 'cleared'))
                FROM uec.release_members m
                JOIN uec.releases release ON release.release_id = m.release_id
                JOIN uec.observations o ON o.observation_id = m.observation_id
                LEFT JOIN LATERAL (SELECT status, result FROM uec.geocode_results WHERE source_record_id=o.source_record_id ORDER BY queried_at DESC, geocode_result_id DESC LIMIT 1) g ON true
                LEFT JOIN uec.facilities facility ON facility.facility_id=m.facility_id
                LEFT JOIN LATERAL (
                  SELECT reference_location FROM uec.city_reference_points
                  WHERE country_code=facility.country_code
                    AND lower(city_name)=lower(facility.city)
                    AND (postal_code IS NULL OR postal_code=facility.postal_code)
                  ORDER BY postal_code NULLS LAST LIMIT 1
                ) city ON true
                LEFT JOIN uec.publication_review_release_current r
                  ON r.source_record_id=o.source_record_id AND r.release_id=m.release_id
                LEFT JOIN uec.public_access_restricted s ON s.source_record_id=o.source_record_id
                WHERE m.release_id=%s
            """, (release_id,)).fetchone()
            geometry_metrics = connection.execute(
                RELEASE_GATE_METRICS_SQL, (release_id, release_id, release_id)
            ).fetchone()
            unsafe = (geometry_metrics[9], geometry_metrics[4], geometry_metrics[10],
                      geometry_metrics[11], geometry_metrics[12])
            if not geometry_metrics[1]:
                raise ValueError("release has no public-eligible visible members")
            if any(unsafe) or rights_gate["blockers"]:
                raise ValueError(f"release safety gates failed: coordinate_not_ready={unsafe[0]}, review_required={unsafe[1]}, publication_not_approved={unsafe[2]}, active_suppression={unsafe[3]}, rights_not_cleared={unsafe[4] + len(rights_gate['blockers'])}")
            demonstration = target[4].get("demonstration") if isinstance(target[4], dict) else None
            if demonstration is not None and demonstration.get("review_status") != "approved":
                raise ValueError("demonstration release requires an explicit recorded review")
            previous = connection.execute(
                "SELECT release_id FROM uec.releases WHERE status='promoted' AND profile=%s AND release_id<>%s FOR UPDATE",
                (target[1], release_id),
            ).fetchall()
            if len(previous) > 1:
                raise ValueError("multiple active releases exist for this profile; activation is unsafe")
            previous = previous[0] if previous else None
            if previous:
                active_manifest_sha = discovery._release_manifest(connection, previous[0])
                active_model = connection.execute(
                    """SELECT model.manifest_sha256, model.row_count,
                              (SELECT count(*) FROM uec.public_discovery_read_model_rows stored_row
                               WHERE stored_row.release_id=model.release_id)
                       FROM uec.public_discovery_read_models model
                       WHERE model.release_id=%s""",
                    (previous[0],),
                ).fetchone()
                if (not active_model or active_model[0] != active_manifest_sha
                        or active_model[1] != active_model[2]):
                    raise ValueError("current promoted release has no complete usable read model")
            summary = connection.execute("""
                SELECT count(*), coalesce(array_agg(DISTINCT sr.source_id ORDER BY sr.source_id), ARRAY[]::text[])
                FROM uec.release_members m JOIN uec.observations o ON o.observation_id=m.observation_id
                JOIN uec.source_records sr ON sr.source_record_id=o.source_record_id
                WHERE m.release_id=%s AND m.default_visible
                  AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted x WHERE x.source_record_id=sr.source_record_id)
            """, (release_id,)).fetchone()
            coverage_rows = connection.execute("""
                SELECT sr.source_id, count(*)::int, min(artifact.retrieved_at), max(artifact.retrieved_at), source.attribution
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
            suppression_generation = connection.execute(
                "SELECT generation FROM uec.public_suppression_generation"
            ).fetchone()[0]
            if map_artifact is not None:
                if map_artifact.get("profile") != target[1] or map_artifact.get("suppression_generation") != suppression_generation:
                    raise ValueError("map artifacts are profile-mismatched or stale")
            source_coverage = [
                {"source_id": source_id, "row_count": row_count, "retrieved_at": {"first": utc_iso(first), "last": utc_iso(last)}, "rights_status": "cleared", "attribution": attribution}
                for source_id, row_count, first, last, attribution in coverage_rows
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
                "suppression_generation": suppression_generation,
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
                "source_rights_gate": "cleared",
                "created_at": utc_iso(created_at),
                "distributed_artifacts": artifacts,
            }
            if map_artifact is not None:
                manifest["map_artifact"] = map_artifact
            prior_manifest_row = connection.execute(
                "SELECT manifest::text, manifest_sha256 FROM uec.release_manifests WHERE release_id=%s",
                (release_id,),
            ).fetchone()
            if prior_manifest_row:
                prior_manifest = json.loads(prior_manifest_row[0])
                prior_digest = hashlib.sha256(canonical_json(prior_manifest).encode("utf-8")).hexdigest()
                if prior_digest != prior_manifest_row[1]:
                    raise ValueError("existing immutable manifest checksum is invalid")
                if not _same_immutable_manifest(prior_manifest, manifest):
                    raise ValueError("existing immutable manifest does not match current release inputs, rights, suppression, or artifacts")
                manifest = prior_manifest
                digest = prior_manifest_row[1]
            else:
                canonical = canonical_json(manifest)
                digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                connection.execute(
                    "INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256) VALUES (%s,%s,%s)",
                    (release_id, canonical, digest),
                )
            previous_rows = [previous[0]] if previous else []
            connection.execute("UPDATE uec.releases SET status = 'validated' WHERE status = 'promoted' AND profile = %s AND release_id <> %s", (target[1], release_id))
            connection.execute("UPDATE uec.releases SET status = 'promoted' WHERE release_id = %s", (release_id,))
            read_model = discovery.build_in_transaction(
                connection, release_id, fail_after_rows=_fail_after_read_model_rows
            )
            return {"release_id": release_id, "status": "promoted", "previously_promoted": previous_rows,
                    "manifest": manifest, "manifest_sha256": digest, "read_model": read_model}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_id")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--map-artifact-manifest", type=Path, help="Validated private MVT manifest produced before promotion")
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
        map_artifact = None
        if args.map_artifact_manifest:
            with psycopg.connect(args.database_url) as connection:
                release = connection.execute("SELECT status,test_only,profile FROM uec.releases WHERE release_id=%s", (args.release_id,)).fetchone()
                generation = connection.execute("SELECT generation FROM uec.public_suppression_generation").fetchone()[0]
            if not release or release[0] != "validated" or release[1]:
                raise ValueError("map manifest is accepted only for a validated non-test release")
            map_artifact = validate_map_artifact(args.map_artifact_manifest, args.release_id, release[2], generation)
        result = promote(args.database_url, args.release_id, artifact_inventory, map_artifact)
        serialized = json.dumps({key: value for key, value in result.items() if key != "manifest"}, indent=2) + "\n"
        print(serialized, end="")
        if args.manifest:
            write_manifest(args.manifest, result)
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, indent=2), file=sys.stderr)
        sys.exit(1)
