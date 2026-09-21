"""Private, idempotent sink boundary for evidence-event handoffs.

This is intentionally a file-backed boundary for disposable/local rehearsals.
It accepts only the source-specific evidence handoff contract, never creates a
facility, graph edge, release, or public read model.  A later database sink can
implement the same aggregate-only result contract without changing adapters.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json


HANDOFF_VERSION = "us-aphis-observation-handoff-v1"
SINK_VERSION = "private-evidence-sink-v1"


def import_private_evidence(handoff_dir: str | Path, _database_url: str | None = None,
                            output_dir: str | Path | None = None) -> dict[str, Any]:
    """Materialize one evidence handoff idempotently into private staging."""
    root = Path(handoff_dir)
    manifest_path = root / "manifest.json"
    payload_path = root / "records.jsonl"
    if not manifest_path.is_file() or not payload_path.is_file():
        raise ValueError("evidence handoff requires manifest.json and records.jsonl")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract_version") != HANDOFF_VERSION:
        raise ValueError("facility handoff cannot enter the evidence sink")
    if manifest.get("entity_scope") != "evidence_event":
        raise ValueError("evidence handoff must declare entity_scope=evidence_event")
    payload = payload_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != manifest.get("normalized_sha256"):
        raise ValueError("evidence handoff checksum mismatch")
    target = Path(output_dir) if output_dir is not None else root.parent / "evidence-import"
    target_manifest_path = target / "manifest.json"
    if target_manifest_path.is_file():
        existing = json.loads(target_manifest_path.read_text(encoding="utf-8"))
        if existing.get("handoff_sha256") == digest:
            return {
                "contract_version": SINK_VERSION,
                "source_id": manifest.get("source_id"),
                "profile": manifest.get("profile"),
                "status": "already_present",
                "inserted_events": 0,
                "rerun_events": int(manifest.get("normalized_rows", 0)),
                "review_required": True,
                "publication_eligible_rows": 0,
                "graph_migration": False,
                "database_import": False,
                "storage": "private-file-staging",
                "public_exposure": False,
            }
    atomic_bytes(target / "records.jsonl", payload)
    sink_manifest = {
        "contract_version": SINK_VERSION,
        "source_id": manifest.get("source_id"),
        "profile": manifest.get("profile"),
        "handoff_sha256": digest,
        "event_count": int(manifest.get("normalized_rows", 0)),
        "status": "completed",
        "review_required": True,
        "publication_eligible_rows": 0,
        "graph_migration": False,
        "database_import": False,
        "storage": "private-file-staging",
        "release_state": "not-created",
        "publication_state": "private-candidate",
        "public_exposure": False,
    }
    atomic_json(target / "manifest.json", sink_manifest)
    return {
        "contract_version": SINK_VERSION,
        "source_id": manifest.get("source_id"),
        "profile": manifest.get("profile"),
        "status": "completed",
        "inserted_events": sink_manifest["event_count"],
        "rerun_events": 0,
        "review_required": True,
        "publication_eligible_rows": 0,
        "graph_migration": False,
        "database_import": False,
        "storage": "private-file-staging",
        "public_exposure": False,
    }
