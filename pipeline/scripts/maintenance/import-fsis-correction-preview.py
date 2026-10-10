"""Append one hash-verified FSIS private-preview snapshot beside an approved V0 clone.

This creates only ``real_preview`` evidence.  It neither reads nor changes a
promoted release, release membership, manifest, or public projection.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
IMPORTER_PATH = ROOT / "pipeline/scripts/maintenance/import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("fsis_preview_importer", IMPORTER_PATH)
assert SPEC and SPEC.loader
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)

RUN_LEDGER_INSERT_SQL = """INSERT INTO real_preview.source_preview_runs(run_id,source_id,snapshot_sha256,source_url,retrieved_at,source_artifact_sha256,normalized_sha256,adapter_version,schema_version,input_count,accepted_count,quarantined_count,out_of_scope_count,imported_observation_count,facility_count,numeric_coordinate_count,coarse_placeable_count,unmapped_count,api_listable_count,map_visible_count,idempotent_replay,public_rows,runtime_details)
                      VALUES (%s,'us.fsis',%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,%s,%s,%s,%s,%s,%s,%s,false,0,%s) ON CONFLICT (run_id) DO NOTHING"""


def run_ledger_params(
    run_id: str, snapshot: str, url: str, retrieved: str, source_hash: str,
    normalized_hash: str, code: str, config: str, rows: int, observations: int,
    candidates: int, numeric: int, placeable: int, unplaceable: int,
) -> tuple[object, ...]:
    """Keep the correction-run ledger bindings in lockstep with its SQL."""
    return (
        run_id, snapshot, url, retrieved, source_hash, normalized_hash, code, config,
        rows, rows, observations, candidates, numeric, placeable, unplaceable,
        candidates, candidates - unplaceable,
        json.dumps({"fsis_correction_handoff": True, "fresh_live_run": False, "private_candidate": True}),
    )


def run(database_url: str, handoff: Path) -> dict[str, int | str]:
    manifest_path = handoff / "manifest.json"
    normalized = handoff / "normalized/records.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_hash, normalized_hash, rows, url, retrieved, code, config = IMPORTER.manifest_provenance(manifest)
    if manifest.get("source_id") != "us.fsis" or manifest.get("release_state") != "not-created":
        raise ValueError("fsis_handoff_identity_invalid")
    if IMPORTER.digest_file(normalized)[0] != normalized_hash or IMPORTER.count_jsonl_rows(normalized) != rows:
        raise ValueError("fsis_handoff_hash_or_count_invalid")
    policy = json.loads((ROOT / "pipeline/preview-enabled-sources.json").read_text(encoding="utf-8"))["sources"]["us.fsis"]
    IMPORTER.validate_preview_fields(normalized, set(policy["allowed_preview_fields"]))
    snapshot = IMPORTER.snapshot_identity({"us.fsis": (manifest_path, manifest)})
    run_id = f"fsis-correction-{snapshot[:20]}"
    with psycopg.connect(database_url) as db, db.transaction():
        if db.execute("SELECT current_database()").fetchone()[0] != "uec_v0_api_repair":
            raise ValueError("database_identity_invalid")
        before = db.execute("SELECT count(*) FROM uec.release_members").fetchone()[0]
        db.execute("INSERT INTO real_preview.imports(snapshot_sha256,observation_count) VALUES (%s,%s) ON CONFLICT DO NOTHING", (snapshot, rows))
        db.execute("""INSERT INTO real_preview.source_manifests(snapshot_sha256,source_id,source_artifact_sha256,normalized_sha256,normalized_rows,source_url,retrieved_at,code_version,config_version)
                      VALUES (%s,'us.fsis',%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", (snapshot, source_hash, normalized_hash, rows, url, retrieved, code, config))
        metrics = IMPORTER.import_rows(db, "us.fsis", normalized, rows, snapshot)
        observations, numeric, coarse, candidates, unmapped, _mapped, _groups, _x, _zero, _unknown, _provided, _keys, placeable, unplaceable = metrics
        db.execute(
            RUN_LEDGER_INSERT_SQL,
            run_ledger_params(
                run_id, snapshot, url, retrieved, source_hash, normalized_hash, code,
                config, rows, observations, candidates, numeric, placeable, unplaceable,
            ),
        )
        if db.execute("SELECT count(*) FROM uec.release_members").fetchone()[0] != before:
            raise ValueError("release_members_changed")
    return {"snapshot": snapshot, "rows": rows, "candidates": candidates, "numeric": numeric, "unmapped": unplaceable}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("database URL required")
    print(json.dumps(run(args.database_url, args.handoff), sort_keys=True))
