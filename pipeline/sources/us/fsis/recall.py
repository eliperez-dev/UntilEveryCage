"""Private, fail-closed adapter for the FSIS recall API export.

Recall records are evidence of a public-health action, not findings of
wrongdoing.  Establishment-number joins are source-scoped candidates only;
firm/name/address matches are deliberately quarantined.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.common.graph_candidate import build_graph_candidate
from pipeline.common.graph_candidates import write_graph_candidates


SOURCE_ID = "us.fsis.recall"
API_URL = "https://www.fsis.usda.gov/fsis/api/recall/v/1"


def _text(value: Any) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("results") or payload.get("recalls") or payload.get("data")
    else:
        rows = None
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("FSIS recall payload has no supported record array")
    return rows


def _establishment_number(row: dict[str, Any]) -> str | None:
    for key in ("establishment_number", "establishmentNumber", "establishment", "establishment_no"):
        value = _text(row.get(key))
        if value:
            return value
    text = " ".join(str(row.get(key, "")) for key in ("establishment_name", "firm", "company", "reason"))
    # Source text such as "EST. 1234" is retained as an explicit source clue,
    # but never treated as a join when multiple identifiers occur.
    import re
    # Digits in names/reasons are not identity evidence. Require an explicit
    # establishment marker before creating a source-local join.
    matches = sorted(set(re.findall(r"\bEST\.?\s*(\d{1,6})\b", text, re.I)))
    return matches[0] if len(matches) == 1 else None


def parse_bytes(content: bytes, *, retrieved_at: str = "unknown-retrieval-date") -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed FSIS recall JSON") from exc
    rows = _records(payload)
    accepted, quarantined = [], []
    for index, row in enumerate(rows, start=1):
        recall_id = _text(row.get("recall_number") or row.get("recallNumber") or row.get("recall_id"))
        reasons: list[str] = []
        if not recall_id:
            reasons.append("missing_recall_identifier")
        establishment = _establishment_number(row)
        if not establishment:
            reasons.append("unresolved_establishment_identifier")
        record = {
            "source_id": SOURCE_ID,
            "source_row": index,
            "source_record_key": recall_id or f"row-{index}",
            "source_values": row,
            "normalized": {
                "recall_number": recall_id,
                "establishment_number": establishment,
                "recall_date": _text(row.get("recall_date") or row.get("recallDate")),
                "status": _text(row.get("status") or row.get("recall_status")),
                "firm": _text(row.get("firm") or row.get("company") or row.get("establishment_name")),
                "retrieved_at": retrieved_at,
                "evidence_type": "fsis_recall",
                "review_state": "review_required",
                "publication_gate": "blocked",
            },
        }
        (quarantined if reasons else accepted).append({"reasons": reasons, "record": record} if reasons else record)
    return {"accepted": accepted, "quarantined": quarantined, "input_rows": len(rows), "source_sha256": hashlib.sha256(content).hexdigest()}


def build_recall_candidate(record: dict[str, Any], *, artifact_sha256: str, observed_at: str) -> dict[str, Any]:
    normalized = record["normalized"]
    if not normalized.get("establishment_number"):
        raise ValueError("recall candidate requires an explicit establishment number")
    candidate = build_graph_candidate(
        {"source_id": SOURCE_ID, "source_record_key": record["source_record_key"], "source_row": record["source_row"],
         "source_values": record["source_values"], "normalized": {"establishment_id": normalized["establishment_number"], "name": normalized.get("firm"), "observed_at": observed_at}},
        artifact_sha256=artifact_sha256, observed_at=observed_at)
    facility_ref = candidate["facilities"][0]["local_ref"]
    candidate["claims"].append({"claim_domain": "violation", "claim_kind": "fsis_recall_action", "facility_ref": facility_ref,
        "value_state": "known", "value": {"recall_number": normalized["recall_number"], "status": normalized.get("status"), "recall_date": normalized.get("recall_date"), "evidence_type": "fsis_recall"},
        "observed_at": observed_at, "confidence": None, "review_state": "review_required",
        "support": [{"source_record_key": record["source_record_key"]}, {"artifact_sha256": artifact_sha256}]})
    candidate["contradiction_state"] = "none-observed"
    from pipeline.contracts.graph_candidate_handoff import validate_graph_candidate
    validate_graph_candidate(candidate)
    return candidate


def write_private_run(content: bytes, run_dir: str | Path, *, retrieved_at: str, source_url: str = API_URL) -> dict[str, Any]:
    parsed = parse_bytes(content, retrieved_at=retrieved_at)
    digest = hashlib.sha256(content).hexdigest()
    root = Path(run_dir); root.mkdir(parents=True, exist_ok=True)
    (root / "raw.json").write_bytes(content)
    (root / "parsed.json").write_text(json.dumps(parsed, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    candidates = [build_recall_candidate(r, artifact_sha256=digest, observed_at=retrieved_at) for r in parsed["accepted"]]
    manifest = write_graph_candidates(root / "graph", candidates)
    manifest.update({"source_id": SOURCE_ID, "source_url": source_url, "artifact_sha256": digest, "input_rows": parsed["input_rows"],
                     "accepted_rows": len(parsed["accepted"]), "quarantined_rows": len(parsed["quarantined"]), "publication_status": "not_eligible"})
    (root / "aggregate-manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest
