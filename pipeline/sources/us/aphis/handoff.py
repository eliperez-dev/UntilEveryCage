"""Private APHIS observation handoff and disposable import packet.

The shared facility handoff is intentionally not used here: APHIS rows have
source-native certificate/customer identities and must not become facilities or
graph ownership edges without a separate reviewed link event.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json


HANDOFF_VERSION = "us-aphis-observation-handoff-v1"
IMPORT_VERSION = "us-aphis-private-candidate-import-v1"


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, default=list) + "\n").encode("utf-8") for row in rows)


def write_private_handoff(
    run_dir: str | Path,
    rows: list[dict[str, Any]],
    artifact: SourceArtifact,
    *,
    profile: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Write a source-specific private candidate handoff.

    This is a row-bearing restricted artifact. Its explicit entity scope keeps
    downstream importers from applying the facility-master contract.
    """
    payload = _jsonl(rows)
    root = Path(run_dir)
    atomic_bytes(root / "records.jsonl", payload)
    has_page_lineage = any(
        row.get("normalized", {}).get("source_capture_lineage") for row in rows
    )
    manifest = {
        "contract_version": HANDOFF_VERSION,
        "source_id": "us.aphis",
        "profile": profile,
        "source_url": artifact.source_url,
        "retrieved_at_utc": artifact.retrieved_at_utc,
        "checksum_sha256": artifact.sha256,
        "source_artifact_sha256": source_sha256,
        "source_artifact_classification": (
            "derived_staging_with_original_page_lineage"
            if has_page_lineage else "preserved_source_artifact"
        ),
        "source_row_lineage": (
            "normalized.source_capture_lineage links each derived row to original page ordinal, page hash, byte size, source row, source URL, and retrieval timestamp scope"
            if has_page_lineage else "not supplied"
        ),
        "byte_size": artifact.byte_size,
        "code_version": artifact.code_version,
        "config_version": artifact.config_version,
        "normalized_rows": len(rows),
        "normalized_sha256": hashlib.sha256(payload).hexdigest(),
        "entity_scope": "aphis_observation",
        "source_native_identity": ["certificate_number", "customer_number", "customer_number_x", "customer_number_y"],
        "graph_candidate_emission": False,
        "auto_merge": False,
        "release_state": "not-created",
        "publication_state": "private-candidate",
        "review_state": "review_required",
        "privacy_gate": "pending",
        "coordinate_gate": "review_required",
        "publication_eligible_rows": 0,
        "test_only": True,
        "row_payloads_included": True,
        "coverage": "APHIS profile observations only; no facility-master, laboratory, ownership, or cross-source identity claim",
    }
    atomic_json(root / "manifest.json", manifest)
    return manifest


def import_private_candidate(handoff_dir: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Materialize a deterministic private import packet, never a release.

    APHIS needs a source-specific importer because the generic facility
    importer requires ``normalized.establishment_id`` and would create an
    unintended facility. This packet is the explicit disposable/test-only
    import boundary for later review tooling and has no public/API side effect.
    """
    root = Path(handoff_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    payload = (root / "records.jsonl").read_bytes()
    if manifest.get("contract_version") != HANDOFF_VERSION:
        raise ValueError("unsupported APHIS handoff contract")
    if manifest.get("release_state") != "not-created" or manifest.get("publication_state") != "private-candidate":
        raise ValueError("APHIS handoff is not an unpromoted private candidate")
    if hashlib.sha256(payload).hexdigest() != manifest.get("normalized_sha256"):
        raise ValueError("APHIS handoff checksum mismatch")
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]
    if len(rows) != int(manifest.get("normalized_rows", -1)):
        raise ValueError("APHIS handoff row count mismatch")
    target = Path(output_dir) if output_dir is not None else root.parent / "candidate-import"
    atomic_bytes(target / "records.jsonl", payload)
    imported = {
        "contract_version": IMPORT_VERSION,
        "source_id": manifest["source_id"],
        "profile": manifest["profile"],
        "handoff_sha256": manifest["normalized_sha256"],
        "status": "completed",
        "imported_rows": len(rows),
        "rerun_imported_rows": 0,
        "default_visible_rows": 0,
        "publication_eligible_rows": 0,
        "public_exposure": False,
        "test_only": True,
        "database_import": False,
        "disposable_target": "source-specific private staging only",
        "identity_merge": False,
        "graph_edges_created": 0,
        "release_state": "not-created",
        "publication_state": "private-candidate",
    }
    atomic_json(target / "manifest.json", imported)
    return imported
