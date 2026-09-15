"""Fail-closed validation for the private production-shaped environment.

This is an operator/deployment check, not publication approval. It validates
configuration, migration inventory, an independently stored restriction ledger,
the post-restore replay snapshot, and a trusted release manifest. Diagnostics
contain only counts, versions, and status; never print database URLs or rows.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


class PrivateEnvironmentError(ValueError):
    """The private environment is unavailable or unsafe to start."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ledger_digest(ledger: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json({
        "schema_version": ledger.get("schema_version"),
        "revision": ledger.get("revision"),
        "active_restrictions": ledger.get("active_restrictions"),
    }).encode("utf-8")).hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise PrivateEnvironmentError(f"{label} is unavailable")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PrivateEnvironmentError(f"{label} is invalid") from exc
    if not isinstance(value, dict):
        raise PrivateEnvironmentError(f"{label} must be an object")
    return value


def verify_ledger_replay(ledger_path: Path, snapshot_path: Path) -> dict[str, Any]:
    if ledger_path.resolve() == snapshot_path.resolve():
        raise PrivateEnvironmentError("restriction ledger and restored snapshot must be separate files")
    ledger = read_json(ledger_path, "restriction ledger")
    if ledger.get("schema_version") != 1 or not isinstance(ledger.get("revision"), str) or not ledger["revision"]:
        raise PrivateEnvironmentError("restriction ledger schema or revision is unsupported")
    if ledger.get("ledger_sha256") != ledger_digest(ledger):
        raise PrivateEnvironmentError("restriction ledger digest is invalid")
    restrictions = ledger.get("active_restrictions")
    if not isinstance(restrictions, list) or any(
        not isinstance(row, dict)
        or any(not isinstance(row.get(key), str) or not row[key] for key in ("source_id", "source_record_key", "scope"))
        or row.get("action") != "suppress"
        for row in restrictions
    ):
        raise PrivateEnvironmentError("restriction ledger references are invalid")
    snapshot = read_json(snapshot_path, "restored restriction snapshot")
    if snapshot.get("ledger_revision") != ledger["revision"] or snapshot.get("ledger_sha256") != ledger["ledger_sha256"]:
        raise PrivateEnvironmentError("restored restriction state is stale")
    expected = {canonical_json(row) for row in restrictions}
    applied = snapshot.get("active_restrictions")
    if not isinstance(applied, list) or {canonical_json(row) for row in applied} != expected or len(applied) != len(expected):
        raise PrivateEnvironmentError("restored restrictions do not match current ledger")
    if any(not isinstance(row, dict) or row.get("action") != "suppress" for row in applied):
        raise PrivateEnvironmentError("restored restriction action is unsupported")
    return {"revision": ledger["revision"], "active_restriction_count": len(restrictions)}


def validate_proxy_config(mode: str, trust_proxy: str | None, trusted_cidrs: str | None) -> dict[str, Any]:
    if trust_proxy is None and mode == "development":
        trust = False
    elif trust_proxy in {"true", "false"}:
        trust = trust_proxy == "true"
    elif trust_proxy is None:
        raise PrivateEnvironmentError("UEC_TRUST_PROXY must be explicitly set in production")
    else:
        raise PrivateEnvironmentError("UEC_TRUST_PROXY must be true or false")
    networks = []
    for raw in (trusted_cidrs or "").split(","):
        raw = raw.strip()
        if raw:
            try:
                networks.append(ipaddress.ip_network(raw, strict=False))
            except ValueError as exc:
                raise PrivateEnvironmentError("UEC_TRUSTED_PROXY_CIDRS contains an invalid network") from exc
    if trust and not networks:
        raise PrivateEnvironmentError("UEC_TRUSTED_PROXY_CIDRS is required when proxy trust is enabled")
    if not trust and networks:
        raise PrivateEnvironmentError("UEC_TRUSTED_PROXY_CIDRS requires UEC_TRUST_PROXY=true")
    return {"trust_forwarded_for": trust, "trusted_proxy_network_count": len(networks)}


def validate_runtime_config(values: dict[str, str | None], production: bool = True) -> dict[str, Any]:
    mode = values.get("UEC_RUNTIME_MODE")
    if production and mode != "production":
        raise PrivateEnvironmentError("UEC_RUNTIME_MODE must be production for this gate")
    if mode not in {"development", "production"}:
        raise PrivateEnvironmentError("UEC_RUNTIME_MODE must be development or production")
    if mode == "production" and not (values.get("UEC_DATABASE_URL") or "").strip():
        raise PrivateEnvironmentError("UEC_DATABASE_URL is required in production")
    origins = [origin.strip() for origin in (values.get("UEC_CORS_ORIGINS") or "").split(",") if origin.strip()]
    if mode == "production" and not origins:
        raise PrivateEnvironmentError("UEC_CORS_ORIGINS is required in production")
    for origin in origins:
        if "*" in origin or not re.match(r"^https?://[^/?#]+$", origin):
            raise PrivateEnvironmentError("UEC_CORS_ORIGINS must contain bare http(s) origins")
    proxy = validate_proxy_config(mode, values.get("UEC_TRUST_PROXY"), values.get("UEC_TRUSTED_PROXY_CIDRS"))
    return {"runtime_mode": mode, "cors_origin_count": len(origins), **proxy}


def validate_migrations(directory: Path) -> dict[str, Any]:
    paths = sorted(directory.glob("*.sql"))
    if not paths:
        raise PrivateEnvironmentError("no SQL migrations found")
    stems = [path.stem for path in paths]
    if len(stems) != len(set(stems)):
        raise PrivateEnvironmentError("migration identifiers are duplicated")
    if any(not path.read_text(encoding="utf-8").strip() for path in paths):
        raise PrivateEnvironmentError("migration is empty")
    inventory = [{"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]
    return {"migration_count": len(paths), "migration_inventory_sha256": hashlib.sha256(canonical_json(inventory).encode()).hexdigest()}


def validate_release_manifest(path: Path, expected_digest: str) -> dict[str, Any]:
    manifest = read_json(path, "release manifest")
    actual = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
    if expected_digest != actual or len(expected_digest) != 64 or expected_digest.lower() != expected_digest:
        raise PrivateEnvironmentError("release manifest digest does not match trusted reference")
    for field in ("manifest_version", "release_id", "profile", "ruleset_version"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise PrivateEnvironmentError(f"release manifest field is missing: {field}")
    artifacts = manifest.get("distributed_artifacts", [])
    if not isinstance(artifacts, list):
        raise PrivateEnvironmentError("release manifest artifact inventory is invalid")
    names: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise PrivateEnvironmentError("release manifest artifact inventory is invalid")
        if not re.match(r"^[^/\\]+$", item["name"]):
            raise PrivateEnvironmentError("release manifest artifact name is unsafe")
        if not re.match(r"^[0-9a-f]{64}$", str(item.get("sha256", ""))) or not isinstance(item.get("byte_size"), int) or item["byte_size"] < 0:
            raise PrivateEnvironmentError("release manifest artifact checksum is invalid")
        names.append(item["name"])
    if len(names) != len(set(names)):
        raise PrivateEnvironmentError("release manifest artifact inventory is invalid")
    return {"manifest_version": manifest["manifest_version"], "release_id": manifest["release_id"], "profile": manifest["profile"], "artifact_count": len(artifacts), "manifest_sha256": actual}


def assert_clean_checkout(repository: Path) -> None:
    result = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=repository, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise PrivateEnvironmentError("clean-checkout status could not be read")
    if result.stdout.strip():
        raise PrivateEnvironmentError("checkout contains uncommitted or untracked files")


def run_gate(repository: Path, values: dict[str, str | None], ledger: Path, snapshot: Path, manifest: Path, manifest_digest: str, clean_checkout: bool = False) -> dict[str, Any]:
    if clean_checkout:
        assert_clean_checkout(repository)
    config = validate_runtime_config(values)
    migrations = validate_migrations(repository / "pipeline" / "migrations")
    replay = verify_ledger_replay(ledger, snapshot)
    release = validate_release_manifest(manifest, manifest_digest)
    return {"status": "pass", "checks": {**config, **migrations, "restriction_ledger": replay, "release_manifest": release}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--clean-checkout", action="store_true")
    args = parser.parse_args()
    values = {key: os.environ.get(key) for key in ("UEC_RUNTIME_MODE", "UEC_DATABASE_URL", "UEC_CORS_ORIGINS", "UEC_TRUST_PROXY", "UEC_TRUSTED_PROXY_CIDRS")}
    try:
        print(json.dumps(run_gate(args.repository, values, args.ledger, args.snapshot, args.manifest, args.manifest_sha256, args.clean_checkout), sort_keys=True))
        return 0
    except PrivateEnvironmentError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
