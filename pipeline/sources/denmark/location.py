"""Deterministic, source-owned Denmark location interpretation.

This module is intentionally local-only. Provider requests belong to the
separate geocode worker; source refresh may classify and emit queue candidates.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path


def normalize_locality(value: object) -> str:
    """Normalize for exact comparison while leaving original source text intact."""
    if value is None:
        return ""
    folded = unicodedata.normalize("NFKC", str(value)).casefold()
    return " ".join("".join(char if char.isalnum() else " " for char in folded).split())


def normalize_postal_code(value: object) -> str:
    if value is None:
        return ""
    return "".join(str(value).split())


def load_local_references(path: Path | None) -> list[dict]:
    """Read retained local reference JSONL, including fetch-stage city refs."""
    if path is None:
        return []
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                if row.get("country_code") == "DK" and row.get("city_name"):
                    rows.append(row)
    return rows


def _source_point_is_present(record: dict) -> bool:
    coordinates = record.get("coordinates") or {}
    return coordinates.get("latitude") not in (None, "") and coordinates.get("longitude") not in (None, "")


def classify_location(
    record: dict,
    references: list[dict] | None = None,
    *,
    privacy_status: str = "pending",
    dawa_terms_approved: bool = False,
    dawa_profile_approved: bool = False,
) -> dict:
    """Return candidate location fields without changing source coordinates.

    Reference coordinates are display-only coarse locality references. An
    exact DAWA job requires explicit privacy, terms, and profile gates.
    """
    address = record.get("address") or {}
    postal = normalize_postal_code(address.get("postal_code"))
    locality = normalize_locality(address.get("city"))
    all_refs = [row for row in (references or []) if row.get("country_code") == "DK"]

    postal_rows = [row for row in all_refs if postal and normalize_postal_code(row.get("postal_code")) == postal]
    candidates = []
    match_kind = "locality"
    conflict = False
    if postal and locality and postal_rows:
        candidates = [row for row in postal_rows if normalize_locality(row.get("city_name")) == locality]
        match_kind = "postal_and_locality"
        conflict = not candidates
    elif postal and not locality:
        candidates = postal_rows
        match_kind = "postal"
    elif locality:
        candidates = [row for row in all_refs if normalize_locality(row.get("city_name")) == locality]

    reference = candidates[0] if len(candidates) == 1 else None
    if _source_point_is_present(record):
        state = "source_coordinates_preserved"
        queue_eligible = False
    elif conflict:
        state = "postal_locality_conflict"
        queue_eligible = False
    elif len(candidates) > 1:
        state = "ambiguous_reference"
        queue_eligible = False
    elif reference:
        state = "coarse_reference_match"
        queue_eligible = False
    elif not postal and not locality and not (address.get("street") or "").strip():
        state = "insufficient_location_fields"
        queue_eligible = False
    else:
        state = "unresolved"
        queue_eligible = False

    exact_eligible = bool(
        not _source_point_is_present(record)
        and address.get("street")
        and postal
        and privacy_status == "eligible"
        and dawa_terms_approved
        and dawa_profile_approved
    )
    job_candidate = None
    candidate_state = "insufficient_location_fields"
    if address.get("street") and postal and not _source_point_is_present(record):
        if exact_eligible:
            candidate_state = "eligible_pending_queue"
        elif privacy_status != "eligible":
            candidate_state = "held_for_privacy_review"
        elif not dawa_terms_approved:
            candidate_state = "held_for_terms_review"
        elif not dawa_profile_approved:
            candidate_state = "held_for_profile_approval"
        else:
            candidate_state = "eligible_pending_queue"
        job_candidate = {
            "provider_id": "dk.dawa",
            "status": candidate_state,
            "eligible": exact_eligible,
            "address": {
                "street": address.get("street"),
                "postal_code": postal,
                "city": address.get("city"),
                "country_code": "DK",
            },
        }
    elif locality:
        candidate_state = "insufficient_exact_address"
        queue_eligible = True

    coarse = None
    if reference and reference.get("reference_latitude") is not None and reference.get("reference_longitude") is not None:
        coarse = {
            "latitude": reference["reference_latitude"],
            "longitude": reference["reference_longitude"],
            "precision": "locality_reference_coarse",
            "label": "locality reference center; not a facility point",
            "source": reference.get("reference_source"),
            "source_reference_id": reference.get("source_reference_id"),
            "match_kind": match_kind,
        }

    return {
        "state": state,
        "source_coordinates_preserved": True,
        "source_coordinate_method": (record.get("coordinates") or {}).get("method"),
        "normalized_postal_code": postal or None,
        "normalized_locality": locality or None,
        "coarse_display_reference": coarse,
        "exact_geocode_candidate": job_candidate,
        "exact_geocode_candidate_state": candidate_state,
        "exact_geocode_eligible": exact_eligible,
        "privacy_status": privacy_status,
        "dawa_terms_approved": bool(dawa_terms_approved),
        "dawa_profile_approved": bool(dawa_profile_approved),
        "publication_state": "blocked",
    }
