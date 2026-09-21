"""Private candidate-handoff bridge for the reviewed FSA monthly profile."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff

from .adapter import FsaApprovedEstablishmentsAdapter


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True, default=list) + "\n").encode()
        for row in rows
    )
    path.write_bytes(payload)


def write_private_monthly_handoff(
    raw_path: str | Path,
    run_dir: str | Path,
    artifact: SourceArtifact,
) -> dict[str, Any]:
    """Stage accepted FSA monthly rows through candidate-handoff-v1.

    This bridge is deliberately database-independent. It verifies acquisition
    facts, delegates field mapping and quarantine to the canonical adapter, and
    hands only accepted rows to the private contract. The adapter's normalized
    privacy/coordinate gates are preserved; this function never clears them.
    """
    raw = Path(raw_path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != artifact.sha256 or len(raw) != artifact.byte_size:
        raise ValueError("source checksum or byte size mismatch")

    result = FsaApprovedEstablishmentsAdapter().parse_bytes(raw)
    if result.profile != "monthly":
        raise ValueError("candidate handoff requires the FSA monthly profile")

    root = Path(run_dir)
    _write_jsonl(root / "quarantined" / "records.jsonl", list(result.quarantined))
    manifest = write_handoff(
        root,
        list(result.accepted),
        artifact,
        source_id=FsaApprovedEstablishmentsAdapter.source_id,
        profile="fsa-approved-monthly",
    )
    qa = {
        "profile": result.profile,
        "input_rows": len(result.accepted) + len(result.quarantined),
        "normalized_rows": len(result.accepted),
        "quarantined_rows": len(result.quarantined),
        "coverage_counts": result.coverage_counts or {},
        "anomaly_counts": result.anomaly_counts or {},
        "geocoding": "disabled",
    }
    (root / "qa.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "qa.json").write_text(json.dumps(qa, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {**manifest, "qa": qa}
