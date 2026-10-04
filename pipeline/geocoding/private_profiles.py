"""Source-scoped private provider profile registry."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROFILE_PATH = Path(__file__).with_name("private-source-profiles.json")
ENABLED = "enabled-private-only"


def profiles() -> list[dict[str, Any]]:
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "private-geocoding-source-profiles-v1":
        raise ValueError("private geocoding profile schema is unsupported")
    rows = payload.get("profiles")
    if not isinstance(rows, list):
        raise ValueError("private geocoding profiles must be a list")
    seen_ids: set[str] = set()
    seen_sources: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("private geocoding profile must be an object")
        profile_id, source_id = row.get("profile_id"), row.get("source_id")
        if not isinstance(profile_id, str) or not profile_id or profile_id in seen_ids:
            raise ValueError("private geocoding profile IDs must be unique")
        if not isinstance(source_id, str) or not source_id or source_id in seen_sources:
            raise ValueError("private geocoding sources must have one profile each")
        if row.get("country_code") not in {"GB", "DK", "NL"}:
            raise ValueError("private Geoapify profile country is not enabled")
        if row.get("status") != ENABLED:
            raise ValueError("private Geoapify profile status is invalid")
        seen_ids.add(profile_id)
        seen_sources.add(source_id)
    return rows


def profile_for_source(source_id: str, *, enabled_only: bool = True) -> dict[str, Any] | None:
    for profile in profiles():
        if profile["source_id"] == source_id and (not enabled_only or profile["status"] == ENABLED):
            return profile
    return None


def profile_by_id(profile_id: str, *, enabled_only: bool = True) -> dict[str, Any] | None:
    for profile in profiles():
        if profile["profile_id"] == profile_id and (not enabled_only or profile["status"] == ENABLED):
            return profile
    return None
