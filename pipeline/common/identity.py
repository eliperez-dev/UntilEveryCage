"""Stable, source-qualified record identities for restricted pipeline runs."""

from __future__ import annotations

from typing import Any


UK_IDENTIFIERS = {
    "fss_approved_establishments": "approval_number",
    "fsa_approved_establishments": "establishment_id",
}


def record_key(record: dict[str, Any]) -> str | tuple[str, str, str]:
    """Keep UK establishment IDs distinct across feeds and nations.

    Other adapters currently use a record-level source_id. Do not infer a UK
    identity from a feed-level source_id when its nation or ID is missing.
    """
    source_id = record.get("source_id")
    if source_id in UK_IDENTIFIERS:
        normalized = record.get("normalized")
        if not isinstance(normalized, dict):
            raise ValueError("UK record lacks normalized identity")
        nation = normalized.get("nation")
        identifier = normalized.get(UK_IDENTIFIERS[source_id])
        if not isinstance(nation, str) or not nation.strip() or not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("UK record lacks nation-qualified identity")
        return source_id, nation.strip(), identifier.strip()
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("record lacks stable source_id")
    return source_id
