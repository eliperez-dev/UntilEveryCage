#!/usr/bin/env python3
"""Verify a promoted development baseline using aggregate-only, read-only SQL."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlsplit

import psycopg

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class BaselineError(ValueError):
    """Safe, payload-free verification failure."""


COUNT_FIELDS = ("public_rows", "mapped_rows", "named_rows", "unmapped_rows", "source_count")
CONTRACT_FIELDS = {"schema_version", "release_id", "profile", "manifest_sha256", "dataset_version",
                   "release_label", "release_channel", "expected"}


def load_contract(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BaselineError("baseline_contract_unavailable_or_invalid") from None
    if not isinstance(value, dict) or set(value) != CONTRACT_FIELDS:
        raise BaselineError("baseline_contract_shape_invalid")
    if value.get("schema_version") != "uec-development-baseline-v1":
        raise BaselineError("baseline_contract_version_invalid")
    if not isinstance(value.get("release_id"), str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", value["release_id"]):
        raise BaselineError("baseline_release_id_invalid")
    if value.get("profile") != "official":
        raise BaselineError("baseline_profile_invalid")
    if not isinstance(value.get("manifest_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["manifest_sha256"]):
        raise BaselineError("baseline_manifest_digest_invalid")
    for field in ("dataset_version", "release_channel"):
        if not isinstance(value.get(field), str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value[field]):
            raise BaselineError("baseline_release_metadata_invalid")
    if (not isinstance(value.get("release_label"), str) or not value["release_label"].strip()
            or len(value["release_label"]) > 200 or any(ord(char) < 32 for char in value["release_label"])):
        raise BaselineError("baseline_release_metadata_invalid")
    expected = value.get("expected")
    if not isinstance(expected, dict) or set(expected) != set(COUNT_FIELDS):
        raise BaselineError("baseline_expected_counts_invalid")
    if any(not isinstance(expected[key], int) or isinstance(expected[key], bool) or expected[key] < 0
           for key in COUNT_FIELDS):
        raise BaselineError("baseline_expected_counts_invalid")
    if (expected["mapped_rows"] + expected["unmapped_rows"] != expected["public_rows"]
            or expected["named_rows"] > expected["public_rows"]):
        raise BaselineError("baseline_expected_counts_inconsistent")
    return value


def validate_database_url(database_url: str) -> None:
    parsed = urlsplit(database_url)
    query_options = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if (parsed.scheme not in {"postgres", "postgresql"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or query_options.intersection({"host", "hostaddr", "service", "servicefile"})):
        raise BaselineError("database_must_be_loopback")
    if not parsed.path.strip("/"):
        raise BaselineError("database_name_missing")


def _migration_checksums() -> dict[str, str]:
    paths = sorted((ROOT / "pipeline" / "migrations").glob("*.sql"))
    if not paths:
        raise BaselineError("migration_files_unavailable")
    return {path.stem: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def _checksum_matches(recorded: str, content: bytes) -> bool:
    lf = content.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    return recorded in {hashlib.sha256(content).hexdigest(), hashlib.sha256(lf).hexdigest(),
                        hashlib.sha256(crlf).hexdigest()}


def verify_connection(connection, contract: dict, migrations: dict[str, str] | None = None) -> dict:
    migrations = migrations if migrations is not None else _migration_checksums()
    applied = connection.execute("SELECT version,sha256 FROM uec.schema_migrations ORDER BY version").fetchall()
    applied_map = {str(version): str(digest).strip() for version, digest in applied}
    if set(applied_map) != set(migrations) or any(
            not _checksum_matches(applied_map[version], (ROOT / "pipeline" / "migrations" / f"{version}.sql").read_bytes())
            for version in migrations):
        raise BaselineError("database_migrations_do_not_match_checkout")

    release = connection.execute("""SELECT release.status,release.profile,release.test_only,
            manifest.manifest,manifest.manifest_sha256,model.manifest_sha256,model.row_count
        FROM uec.releases release
        JOIN uec.release_manifests manifest USING (release_id)
        JOIN uec.public_discovery_read_models model USING (release_id)
        WHERE release.release_id=%s""", (contract["release_id"],)).fetchone()
    if release is None:
        raise BaselineError("promoted_release_or_read_model_missing")
    status, profile, test_only, manifest, stored_digest, model_digest, cached_row_count = release
    stored_digest, model_digest = str(stored_digest).strip(), str(model_digest).strip()
    if status != "promoted" or profile != contract["profile"] or test_only is not False:
        raise BaselineError("promoted_release_identity_mismatch")
    if not isinstance(manifest, dict):
        raise BaselineError("release_manifest_invalid")
    actual_digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                                              ensure_ascii=False).encode("utf-8")).hexdigest()
    if (actual_digest != stored_digest or model_digest != stored_digest
            or stored_digest != contract["manifest_sha256"]):
        raise BaselineError("release_manifest_digest_mismatch")
    expected_identity = {
        "release_id": contract["release_id"], "profile": contract["profile"],
        "release_status": "promoted", "test_only": False,
        "dataset_version": contract["dataset_version"], "release_label": contract["release_label"],
        "release_channel": contract["release_channel"],
    }
    if any(manifest.get(key) != value for key, value in expected_identity.items()):
        raise BaselineError("release_manifest_identity_mismatch")

    rows = connection.execute("""SELECT count(*)::bigint,
            count(*) FILTER (WHERE display_location IS NOT NULL AND display_precision <> 'unmapped')::bigint,
            count(*) FILTER (WHERE canonical_name IS NOT NULL AND BTRIM(canonical_name) <> '')::bigint,
            count(*) FILTER (WHERE display_location IS NULL OR display_precision = 'unmapped')::bigint,
            count(DISTINCT provenance_source_id)::bigint
        FROM uec.map_facilities_public_discovery_read_model
        WHERE release_id=%s""", (contract["release_id"],)).fetchone()
    actual = dict(zip(COUNT_FIELDS, map(int, rows)))
    if int(cached_row_count) < actual["public_rows"]:
        raise BaselineError("cached_read_model_count_below_public_projection")
    if actual != contract["expected"]:
        raise BaselineError("public_projection_counts_mismatch")
    return {"status": "verified", "release_id": contract["release_id"], "profile": profile,
            "manifest_sha256": stored_digest, "counts": actual}


def verify(database_url: str, contract: dict) -> dict:
    validate_database_url(database_url)
    try:
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                return verify_connection(connection, contract)
    except BaselineError:
        raise
    except Exception:
        # Database diagnostics can contain private connection details or data.
        raise BaselineError("database_baseline_check_failed") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-contract", type=Path, required=True)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"),
                        help="loopback database URL; defaults to UEC_DATABASE_URL (never printed)")
    args = parser.parse_args(argv)
    try:
        if not args.database_url:
            raise BaselineError("database_url_required")
        contract = load_contract(args.baseline_contract)
        report = verify(args.database_url, contract)
    except BaselineError as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
