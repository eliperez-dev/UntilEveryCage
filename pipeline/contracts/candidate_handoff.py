"""Versioned, source-agnostic private candidate handoff contract."""
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from typing import Any
from .adapter_contract import SourceArtifact

CONTRACT_VERSION = "candidate-handoff-v1"

def _atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(payload); os.replace(tmp, path)

def write_handoff(run_dir: str | Path, rows: list[dict[str, Any]], artifact: SourceArtifact,
                  *, source_id: str, profile: str = "default") -> dict[str, Any]:
    """Write importer-compatible JSONL/manifest, rejecting guessed identities."""
    for row in rows:
        normalized = row.get("normalized")
        if not isinstance(row.get("source_id"), str) or row.get("source_id") != source_id:
            raise ValueError("candidate row source_id does not match manifest")
        if row.get("source_row") is None or not isinstance(normalized, dict) or not normalized.get("establishment_id"):
            raise ValueError("candidate row requires source_row and normalized.establishment_id")
    payload = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, default=list) + "\n").encode() for row in rows)
    root = Path(run_dir); normalized_path = root / "normalized" / "records.jsonl"; _atomic(normalized_path, payload)
    manifest = {"contract_version": CONTRACT_VERSION, "profile": profile, "source_id": source_id,
                "source_url": artifact.source_url, "retrieved_at_utc": artifact.retrieved_at_utc,
                "checksum_sha256": artifact.sha256, "byte_size": artifact.byte_size,
                "code_version": artifact.code_version, "config_version": artifact.config_version,
                "coverage": artifact.coverage, "normalized_rows": len(rows),
                "normalized_sha256": hashlib.sha256(payload).hexdigest(),
                "release_state": "not-created", "publication_state": "private-candidate",
                "review_state": "review_required", "privacy_gate": "pending",
                "coordinate_gate": "review_required"}
    # The importer consumes the conventional manifest.json name.
    _atomic(root / "manifest.json", (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    return manifest
