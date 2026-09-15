"""Restricted country view over the distinct UK FSS and FSA source outputs."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from pipeline.common.adapter_registry import load as load_registry
from pipeline.common.orchestrator import ORCHESTRATOR_VERSION

ROOT = Path(__file__).parents[3]
REGISTRY_PATH = ROOT / "adapter-capabilities.json"
EXPECTED_SCHEMA = {
    "fss_approved_establishments": "fss-scotland-approved-v1",
    "fsa_approved_establishments": "fsa-uk-approved-v1",
}


class CompositionError(ValueError):
    """Inputs cannot safely form a country review view."""


def _atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise CompositionError(f"source output unavailable: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _verified_records(path: Path, manifest: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
    if path.name != "records.jsonl" or path.parent.name != "normalized":
        raise CompositionError(f"invalid normalized output path for {source_id}")
    manifest_path = path.parent.parent / "manifest.json"
    if not manifest_path.exists():
        raise CompositionError(f"source manifest unavailable for {source_id}")
    if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        raise CompositionError(f"source manifest mismatch for {source_id}")
    if not path.exists() or not isinstance(manifest.get("normalized_sha256"), str):
        raise CompositionError(f"normalized output unverifiable for {source_id}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["normalized_sha256"]:
        raise CompositionError(f"normalized output checksum mismatch for {source_id}")
    records = _read_jsonl(path)
    if len(records) != manifest.get("normalized_rows") or any(record.get("source_id") != source_id for record in records):
        raise CompositionError(f"normalized output identity/count mismatch for {source_id}")
    return records


def _key(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _source_record_id(source_id: str, record: dict[str, Any]) -> str | None:
    normalized = record.get("normalized", {})
    field = "approval_number" if source_id == "fss_approved_establishments" else "establishment_id"
    value = normalized.get(field)
    return value if isinstance(value, str) else None


def _possible_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = left["source_record"], right["source_record"]
    na, nb = a.get("normalized", {}), b.get("normalized", {})
    if left["source_id"] == right["source_id"] or na.get("nation") == nb.get("nation"):
        return False
    return bool(_key(na.get("trading_name")) and _key(na.get("trading_name")) == _key(nb.get("trading_name"))
        and _key(na.get("postcode")) and _key(na.get("postcode")) == _key(nb.get("postcode")))


def compose_sources(inputs: list[dict[str, Any]], output_dir: str | Path,
                    suppressed: set[tuple[str, str, str]] | None = None,
                    prior_view: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compose source outputs without merging them; output remains non-release."""
    if not inputs:
        raise CompositionError("at least one source output is required")
    registry = load_registry(REGISTRY_PATH)
    registered = {entry["source_id"]: entry for entry in registry["adapters"]}
    seen_sources: set[str] = set()
    source_states: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    try:
        for item in inputs:
            source_id = item.get("source_id")
            manifest = item.get("manifest") or {}
            if source_id in seen_sources:
                raise CompositionError(f"duplicate source input: {source_id}")
            if source_id not in EXPECTED_SCHEMA or source_id not in registered:
                raise CompositionError(f"unregistered source: {source_id}")
            if manifest.get("schema_version") != EXPECTED_SCHEMA[source_id]:
                raise CompositionError(f"incompatible schema/version for {source_id}")
            if manifest.get("source_id") != source_id:
                raise CompositionError(f"source manifest identity mismatch for {source_id}")
            if manifest.get("release_state") != "not-created":
                raise CompositionError(f"source is not restricted/reviewable: {source_id}")
            records = _verified_records(Path(item["normalized_path"]), manifest, source_id)
            seen_sources.add(source_id)
            source_state = {
                "terms_state": item.get("terms_state", "unresolved"),
                "review_state": item.get("review_state", "human-review-required"),
                "acquisition_state": item.get("acquisition_state", "synthetic-only"),
                "manifest": manifest,
            }
            source_states[source_id] = source_state
            for record in records:
                record_id = _source_record_id(source_id, record)
                normalized = record.get("normalized", {})
                nation = normalized.get("nation")
                if not record_id or not isinstance(nation, str) or not nation.strip():
                    raise CompositionError(f"source record lacks nation-qualified identifier: {source_id}")
                nation = nation.strip()
                if (source_id, nation, record_id) in (suppressed or set()):
                    continue
                items.append({"source_id": source_id, "nation": nation, "source_record_id": record_id,
                              "source_record": record, "source_state": source_state})
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise CompositionError("invalid source output") from exc

    items.sort(key=lambda row: (row["source_id"], row["nation"], row["source_record_id"], row["source_record"]["source_row"]))
    signals = []
    for index, left in enumerate(items):
        for right in items[index + 1:]:
            if _possible_match(left, right):
                signals.append({"type": "possible_match_review", "record_refs": [
                    {"source_id": left["source_id"], "nation": left["nation"], "source_record_id": left["source_record_id"]},
                    {"source_id": right["source_id"], "nation": right["nation"], "source_record_id": right["source_record_id"]}],
                    "basis": "exact normalized trading name and postcode; no automatic merge"})
    terms_blockers = sorted(f"{source_id}:{state['terms_state']}" for source_id, state in source_states.items()
                            if state["terms_state"] != "confirmed")
    review_blockers = sorted(f"{source_id}:review-required" for source_id, state in source_states.items()
                             if state["review_state"] != "project-approved")
    blockers = terms_blockers + review_blockers
    output = Path(output_dir)
    _write_jsonl(output / "reviewable" / "records.jsonl", items)
    _write_jsonl(output / "reviewable" / "possible-match-signals.jsonl", signals)
    _write_jsonl(output / "quarantined" / "records.jsonl", [])
    (output / "released").mkdir(parents=True, exist_ok=True)
    manifest = {"composition_id": hashlib.sha256(json.dumps({"items": items, "source_states": source_states}, sort_keys=True, default=list).encode()).hexdigest(),
                "orchestrator_version": ORCHESTRATOR_VERSION, "source_ids": sorted(seen_sources),
                "source_states": source_states,
                "input_rows": sum(state["manifest"]["normalized_rows"] for state in source_states.values()),
                "reviewable_rows": len(items),
                "suppressed_rows": sum(state["manifest"]["normalized_rows"] for state in source_states.values()) - len(items),
                "possible_match_signals": len(signals),
                "terms_state": "blocked" if terms_blockers else "confirmed",
                "review_state": "blocked" if review_blockers else "project-approved",
                "release_state": "not-created", "candidate_created": False,
                "publication_state": "human-gate-required", "blockers": blockers}
    _atomic(output / "manifest.json", (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    _atomic(output / "status.json", (json.dumps({"status": "reviewable-restricted", "manifest": manifest,
                                                    "prior_view": prior_view}, ensure_ascii=False,
                                                   sort_keys=True, indent=2) + "\n").encode())
    return manifest


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    _atomic(path, b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, default=list) + "\n").encode() for row in rows))
