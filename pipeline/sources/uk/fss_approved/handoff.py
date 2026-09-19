"""Typed private candidate bridge for the synthetic FSS adapter."""
from __future__ import annotations
from pathlib import Path
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from .adapter import FssApprovedEstablishmentsAdapter

def write_private_handoff(raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict:
    """Validate artifact bytes and map approval_number to importer identity."""
    raw = Path(raw_path).read_bytes()
    import hashlib
    if hashlib.sha256(raw).hexdigest() != artifact.sha256 or len(raw) != artifact.byte_size:
        raise ValueError("source checksum or byte size mismatch")
    result = FssApprovedEstablishmentsAdapter().parse_bytes(raw)
    rows = []
    for record in result.accepted:
        normalized = dict(record["normalized"])
        normalized["establishment_id"] = normalized.pop("approval_number")
        rows.append({**record, "normalized": normalized})
    return write_handoff(run_dir, rows, artifact, source_id=FssApprovedEstablishmentsAdapter.source_id, profile="fss-approved")
