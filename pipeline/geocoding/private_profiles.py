"""Source-scoped private provider profile registry."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROFILE_PATH = Path(__file__).with_name("private-source-profiles.json")
ENABLED = "enabled-private-only"
SPAIN_ADDRESS_PROFILE_ID = "geoapify-es-aesan-rgseaa"
SPAIN_MUNICIPALITY_PROFILE_ID = "geoapify-es-aesan-verified-municipality"


def profiles() -> list[dict[str, Any]]:
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "private-geocoding-source-profiles-v1":
        raise ValueError("private geocoding profile schema is unsupported")
    rows = payload.get("profiles")
    if not isinstance(rows, list):
        raise ValueError("private geocoding profiles must be a list")
    seen_ids: set[str] = set()
    profiles_by_source: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("private geocoding profile must be an object")
        profile_id, source_id = row.get("profile_id"), row.get("source_id")
        if not isinstance(profile_id, str) or not profile_id or profile_id in seen_ids:
            raise ValueError("private geocoding profile IDs must be unique")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("private geocoding profile source is invalid")
        if row.get("country_code") not in {"GB", "DK", "NL", "US", "ES", "DE"}:
            raise ValueError("private Geoapify profile country is not enabled")
        if row.get("status") != ENABLED:
            raise ValueError("private Geoapify profile status is invalid")
        if profile_id in {SPAIN_ADDRESS_PROFILE_ID, SPAIN_MUNICIPALITY_PROFILE_ID} and (
                source_id != "es.locations" or row.get("country_code") != "ES"):
            raise ValueError("Spain private geocoding profile identity is invalid")
        seen_ids.add(profile_id)
        profiles_by_source.setdefault(source_id, []).append(row)
    for source_id, source_profiles in profiles_by_source.items():
        if source_id == "es.locations":
            by_id = {row["profile_id"]: row for row in source_profiles}
            if SPAIN_ADDRESS_PROFILE_ID not in by_id:
                raise ValueError("Spain address geocoding profile is required")
            if set(by_id) - {SPAIN_ADDRESS_PROFILE_ID, SPAIN_MUNICIPALITY_PROFILE_ID}:
                raise ValueError("Spain private geocoding profile ID is invalid")
            if len(source_profiles) > 2:
                raise ValueError("Spain private geocoding profile count is invalid")
            for row in source_profiles:
                if row.get("country_code") != "ES":
                    raise ValueError("Spain private geocoding profile country is invalid")
                expected_kind = ("verified_municipality_only"
                                 if row["profile_id"] == SPAIN_MUNICIPALITY_PROFILE_ID else None)
                if row.get("query_kind") != expected_kind:
                    raise ValueError("Spain private geocoding profile query kind is invalid")
        elif len(source_profiles) != 1:
            raise ValueError("private geocoding sources must have one profile each")
    return rows


def profile_for_source(source_id: str, *, enabled_only: bool = True) -> dict[str, Any] | None:
    for profile in profiles():
        if (profile["source_id"] == source_id
                and profile["profile_id"] != SPAIN_MUNICIPALITY_PROFILE_ID
                and (not enabled_only or profile["status"] == ENABLED)):
            return profile
    return None


def profile_by_id(profile_id: str, *, enabled_only: bool = True) -> dict[str, Any] | None:
    for profile in profiles():
        if profile["profile_id"] == profile_id and (not enabled_only or profile["status"] == ENABLED):
            return profile
    return None
