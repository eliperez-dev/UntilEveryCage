"""Prepare one verified, bounded APHIS Class R private-preview handoff.

This helper never touches release tables or calls a geocoder. It verifies the
source-specific APHIS observation handoff, projects only explicit Class R
registrations, and writes a private preview packet for a later authorized DB
import.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any
import psycopg

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl
from pipeline.geocoding.source_queue import build_geocode_queue
from pipeline.sources.us.aphis.preview import AphisPreviewError, project_class_r_registrations

IMPORTER_PATH = ROOT / "pipeline/scripts/maintenance/import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("aphis_preview_importer", IMPORTER_PATH)
assert SPEC and SPEC.loader
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)

POLICY_PATH = ROOT / "pipeline/preview-enabled-sources.json"
HANDOFF_VERSION = "us-aphis-observation-handoff-v1"


def _load_handoff(handoff: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((handoff / "manifest.json").read_text(encoding="utf-8"))
    payload = (handoff / "records.jsonl").read_bytes()
    if (manifest.get("contract_version") != HANDOFF_VERSION
            or manifest.get("source_id") != "us.aphis"
            or manifest.get("profile") != "registrations"
            or manifest.get("release_state") != "not-created"
            or manifest.get("publication_state") != "private-candidate"):
        raise ValueError("aphis_handoff_identity_invalid")
    if hashlib.sha256(payload).hexdigest() != manifest.get("normalized_sha256"):
        raise ValueError("aphis_handoff_hash_invalid")
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]
    if len(rows) != manifest.get("normalized_rows"):
        raise ValueError("aphis_handoff_count_invalid")
    return manifest, rows


def prepare(handoff: Path, projection_dir: Path) -> dict[str, Any]:
    """Verify, project, and queue address-only work without provider calls."""
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))["sources"].get("us.aphis")
    if not isinstance(policy, dict) or policy.get("enabled") is not True or policy.get("public_release") is not False:
        raise ValueError("aphis_preview_policy_blocked")
    manifest, records = _load_handoff(handoff)
    rows = project_class_r_registrations(records)
    allowed = policy.get("allowed_preview_fields")
    if not isinstance(allowed, list):
        raise ValueError("aphis_preview_policy_invalid")
    normalized_path, normalized_sha256, _ = atomic_jsonl(projection_dir / "normalized" / "records.jsonl", rows)
    IMPORTER.validate_preview_fields(normalized_path, set(allowed))
    artifact = SourceArtifact(manifest["source_url"], manifest["retrieved_at_utc"], manifest["checksum_sha256"],
                              manifest["byte_size"], code_version=manifest["code_version"], config_version=manifest["config_version"])
    queue = build_geocode_queue(rows, artifact, projection_dir / "geocode-queue", country_name="United States")
    output = {"source_id": "us.aphis", "profile": "registrations", "source_artifact_sha256": manifest["checksum_sha256"],
              "normalized_sha256": normalized_sha256, "normalized_rows": len(rows),
              "geocode_queue": {key: queue[key] for key in ("records_seen", "records_queued", "geocoder_status_policy")},
              "public_release": False, "database_import": "requires_explicit_authorization"}
    atomic_json(projection_dir / "manifest.json", output)
    return output


def import_prepared(database_url: str, handoff: Path, projection_dir: Path) -> dict[str, Any]:
    """Write the prepared source-scoped preview only after explicit invocation."""
    result = prepare(handoff, projection_dir)
    manifest, _ = _load_handoff(handoff)
    normalized = projection_dir / "normalized" / "records.jsonl"
    snapshot = hashlib.sha256(("us-aphis-class-r-v1:" + result["normalized_sha256"]).encode()).hexdigest()
    rows = int(result["normalized_rows"])
    with psycopg.connect(database_url) as db, db.transaction():
        if db.execute("SELECT current_database()").fetchone()[0] != "uec_v0_api_repair":
            raise ValueError("database_identity_invalid")
        before = db.execute("SELECT count(*) FROM uec.release_members").fetchone()[0]
        db.execute("INSERT INTO real_preview.imports(snapshot_sha256,observation_count) VALUES (%s,%s) ON CONFLICT DO NOTHING", (snapshot, rows))
        db.execute("""INSERT INTO real_preview.source_manifests(snapshot_sha256,source_id,source_artifact_sha256,normalized_sha256,normalized_rows,source_url,retrieved_at,code_version,config_version)
                      VALUES (%s,'us.aphis',%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                   (snapshot, manifest["checksum_sha256"], result["normalized_sha256"], rows, manifest["source_url"], manifest["retrieved_at_utc"], manifest["code_version"], manifest["config_version"]))
        metrics = IMPORTER.import_rows(db, "us.aphis", normalized, rows, snapshot, None,
            json.loads(POLICY_PATH.read_text(encoding="utf-8"))["sources"]["us.aphis"]["display_policy"],
            manifest["checksum_sha256"], manifest["source_url"], IMPORTER.parse_observed_at(manifest["retrieved_at_utc"]), manifest["byte_size"])
        observations, numeric, coarse, candidates, unmapped, _mapped, _groups, _seen, _zero, _unknown, _provided, _keys, placeable, _unplaceable = metrics
        db.execute("""INSERT INTO real_preview.source_preview_runs(run_id,source_id,snapshot_sha256,source_url,retrieved_at,source_artifact_sha256,normalized_sha256,adapter_version,schema_version,input_count,accepted_count,quarantined_count,out_of_scope_count,imported_observation_count,facility_count,numeric_coordinate_count,coarse_placeable_count,unmapped_count,api_listable_count,map_visible_count,idempotent_replay,public_rows,runtime_details)
                      VALUES (%s,'us.aphis',%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,%s,%s,%s,%s,%s,%s,%s,false,0,%s) ON CONFLICT (run_id) DO NOTHING""",
            (f"aphis-class-r-{snapshot[:20]}", snapshot, manifest["source_url"], manifest["retrieved_at_utc"], manifest["checksum_sha256"], result["normalized_sha256"], manifest["code_version"], manifest["config_version"], rows, rows, observations, candidates, numeric, placeable, unmapped, candidates, candidates - unmapped, json.dumps({"bounded_class_r_registration_preview": True, "geocoder_called": False, "private_candidate": True})))
        if db.execute("SELECT count(*) FROM uec.release_members").fetchone()[0] != before:
            raise ValueError("release_members_changed")
    return {"snapshot": snapshot, "rows": rows, "candidates": candidates, "numeric": numeric, "coarse": coarse, "public_rows": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--projection-dir", type=Path, required=True)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    args = parser.parse_args()
    try:
        result = import_prepared(args.database_url, args.handoff, args.projection_dir) if args.database_url else prepare(args.handoff, args.projection_dir)
    except (AphisPreviewError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "imported" if args.database_url else "prepared", "normalized_rows": result.get("normalized_rows", result.get("rows"))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
