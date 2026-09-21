"""Known-connection controls for the D6 real-source graph rehearsal.

Controls are derived from source assertions and source-native identifiers, not
from names, addresses, coordinates, or a guessed cross-source identity.  The
function in this module may inspect restricted local handoffs, but the
committed result is deliberately row-free: only counts, source scopes, and a
digest of control keys are written to the repository.

The default private staging location is on the larger data drive.  Callers
may override it for a disposable run; no private payload is ever written by
``write_control_manifest``.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


CONTROL_VERSION = "d6-known-connection-controls-v1"
PRIVATE_STAGING_ROOT = Path("D:/UntilEveryCage-private/d6-graph-mvp")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _identifier_pairs(record: Mapping[str, Any]) -> list[tuple[str, str]]:
    normalized = record.get("normalized")
    if not isinstance(normalized, Mapping):
        return []
    ids = normalized.get("source_native_ids")
    if isinstance(ids, Mapping):
        return sorted((str(key), str(value)) for key, value in ids.items() if _text(key) and _text(value))
    pairs: list[tuple[str, str]] = []
    for key in ("establishment_id", "approval_number", "source_observation_key", "certificate_number", "customer_number"):
        value = _text(normalized.get(key))
        if value:
            pairs.append((key, value))
    return pairs


def _control_key(kind: str, source_id: str, left: str, right: str, method: str) -> str:
    material = "|".join((kind, source_id, left, right, method))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _digest(keys: Iterable[str]) -> str:
    payload = "\n".join(sorted(keys)).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def derive_known_connection_controls(
    *,
    graph_candidates: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    evidence_rows: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    facility_records: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Derive positive and negative controls without returning row payloads.

    ``graph_candidates`` should be the private output of source adapters.  An
    asserted organization/facility relationship is a positive control because
    the source itself supplied both identifiers in one observation.  Evidence
    linkage candidates are similarly positive when they target their own
    source family.  APHIS-to-FSIS is always a negative control: the absence of
    a shared authoritative identifier is a deliberate product invariant.

    The optional ``facility_records`` input is used only to construct known
    negative controls for disjoint source identifiers; it is never serialized.
    """
    graph_candidates = graph_candidates or {}
    evidence_rows = evidence_rows or {}
    facility_records = facility_records or {}
    positives: list[dict[str, str]] = []
    negatives: list[dict[str, str]] = []

    for source_id, candidates in graph_candidates.items():
        for candidate in candidates:
            record_key = _text(candidate.get("source_record_key")) or "unknown"
            for relationship in candidate.get("relationships", ()) if isinstance(candidate.get("relationships"), list) else ():
                if not isinstance(relationship, Mapping):
                    continue
                if relationship.get("assertion_status") != "asserted":
                    continue
                positives.append({
                    "control_key": _control_key("positive", source_id, record_key, str(relationship.get("relationship_type") or "unknown"), "source_assertion"),
                    "source_id": source_id,
                    "method": "source_assertion",
                })

    for source_id, rows in evidence_rows.items():
        for row in rows:
            normalized = row.get("normalized") if isinstance(row, Mapping) else None
            if not isinstance(normalized, Mapping):
                continue
            source_key = _text(row.get("source_record_key") or normalized.get("source_observation_key"))
            for link in normalized.get("linkage_candidates", ()) if isinstance(normalized.get("linkage_candidates"), list) else ():
                if not isinstance(link, Mapping) or not _text(link.get("value")):
                    continue
                target_source = _text(link.get("target_source_id")) or source_id
                if target_source != source_id:
                    continue
                positives.append({
                    "control_key": _control_key("positive", source_id, source_key or "unknown", str(link.get("value")), "exact_source_identifier"),
                    "source_id": source_id,
                    "method": "exact_source_identifier",
                })

    # The US cross-source guard is a known negative, independent of whether
    # either private handoff is available in this run.
    if "us.aphis" in evidence_rows or "us.fsis" in facility_records or "us.fsis" in graph_candidates:
        negatives.append({
            "control_key": _control_key("negative", "us", "us.aphis", "us.fsis", "cross_source_identity_forbidden"),
            "source_id": "us.aphis↔us.fsis",
            "method": "cross_source_identity_forbidden",
        })

    # A pair of distinct source-native values is a stable negative control for
    # exact-ID matching.  Only aggregate metadata is returned.
    for source_id, records in facility_records.items():
        values = sorted({value for record in records for _, value in _identifier_pairs(record)})
        if len(values) >= 2:
            negatives.append({
                "control_key": _control_key("negative", source_id, values[0], values[1], "distinct_source_identifiers_do_not_match"),
                "source_id": source_id,
                "method": "distinct_source_identifiers_do_not_match",
            })

    positive_keys = [item["control_key"] for item in positives]
    negative_keys = [item["control_key"] for item in negatives]
    return {
        "schema_version": CONTROL_VERSION,
        "positive_controls": {
            "count": len(positives),
            "by_source": dict(sorted(Counter(item["source_id"] for item in positives).items())),
            "by_method": dict(sorted(Counter(item["method"] for item in positives).items())),
            "control_keys_sha256": _digest(positive_keys),
        },
        "negative_controls": {
            "count": len(negatives),
            "by_source": dict(sorted(Counter(item["source_id"] for item in negatives).items())),
            "by_method": dict(sorted(Counter(item["method"] for item in negatives).items())),
            "control_keys_sha256": _digest(negative_keys),
        },
        "invariants": {
            "automatic_aphis_fsis_links": 0,
            "names_addresses_coordinates_are_identity_evidence": False,
            "control_payloads_included": False,
            "publication_status": "not_eligible",
            "storage_state": "private",
        },
        "private_staging_root": str(PRIVATE_STAGING_ROOT),
    }


def write_control_manifest(path: str | Path, manifest: Mapping[str, Any]) -> Path:
    """Write an aggregate-only control manifest and reject row-bearing data."""
    value = json.loads(json.dumps(dict(manifest), ensure_ascii=False, sort_keys=True))
    forbidden_keys = {"source_values", "raw_rows", "records", "address", "coordinates", "latitude", "longitude"}

    def has_forbidden_key(item: Any) -> bool:
        if isinstance(item, Mapping):
            return any(str(key) in forbidden_keys or has_forbidden_key(child) for key, child in item.items())
        if isinstance(item, list):
            return any(has_forbidden_key(child) for child in item)
        return False

    if has_forbidden_key(value):
        raise ValueError("control manifest must remain aggregate-only")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return target


__all__ = ["CONTROL_VERSION", "PRIVATE_STAGING_ROOT", "derive_known_connection_controls", "write_control_manifest"]
