"""Row-free US V1-to-pilot reconciliation using FSIS keys only."""
from __future__ import annotations

import json
from tempfile import TemporaryDirectory
from pathlib import Path
from typing import Any

from pipeline.reconciliation.crosswalk import compare_v1_v2


def build_v1_crosswalk(v1_path: str | Path, candidate_entities_path: str | Path) -> dict[str, Any]:
    """Compare legacy FSIS IDs to pilot facility IDs without merging records.

    The candidate file must already be the private adapter's entity JSONL. A
    shared ``establishment_id`` is an observation comparison key only; this
    function creates no identity or suppression decision.
    """
    v2_rows = []
    for line in Path(candidate_entities_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("entity_type") == "facility" and row.get("source_id") == "us.fsis":
            v2_rows.append({
                "source_record_key": row.get("source_native_id"),
                "normalized": {"coordinates": None, "classification": None, "effective_date": row.get("observation_date")},
            })
    # compare_v1_v2 accepts JSONL and emits only aggregates. A temporary file
    # would make this helper awkward for callers, so use its public semantics
    # through a deterministic in-memory-equivalent file beside the candidate.
    with TemporaryDirectory(prefix="uec-us-crosswalk-") as directory:
        temporary = Path(directory) / "candidate.jsonl"
        temporary.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in v2_rows), encoding="utf-8")
        report = compare_v1_v2(v1_path, temporary, v1_key="establishment_id", v2_key="source_record_key", v1_country="US", v2_source_id="us.fsis")
    report["matching"]["pilot_scope"] = "FSIS facility source-native establishment ID only"
    report["matching"]["identity_inheritance"] = False
    report["interpretation"]["v1_identity_assumptions_inherited"] = False
    return report
