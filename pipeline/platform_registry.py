"""Materialize the country/source platform from existing checked-in registries.

The source registry and source-status baseline remain the authoritative inputs.
This module joins them into a typed, country-aware view so new lanes do not
copy source rows into another file.  It is intentionally offline and never
fetches a source or grants release approval.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from pipeline.contracts.country_contract import COUNTRY_CONTRACT_VERSION, validate_country_contracts
from pipeline.contracts.readiness import readiness_from_status
from pipeline.source_registry import load_registry


ROOT = Path(__file__).resolve().parents[1]
PLATFORM_CONFIG_PATH = Path(__file__).with_name("platform_registry.json")
STATUS_PATH = ROOT / "docs" / "source-status.json"
PLATFORM_SCHEMA_VERSION = "country-source-platform-v1"


class PlatformRegistryError(ValueError):
    """Raised when the joined platform registry cannot be trusted."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlatformRegistryError(f"invalid registry input: {path}") from error
    if not isinstance(value, dict):
        raise PlatformRegistryError(f"registry input must be an object: {path}")
    return value


def _country_code(source_id: str) -> str:
    prefix = source_id.split(".", 1)[0].strip().upper()
    # Cross-border statistical sources are intentionally retained as EU rather
    # than being assigned to a country by inference.
    return "EU" if prefix == "EU" else prefix


def _source_readiness(status: Mapping[str, Any]) -> dict[str, Any]:
    return readiness_from_status(status).as_mapping()


def _source_record(source: Mapping[str, Any], status: Mapping[str, Any]) -> dict[str, Any]:
    source_id = str(source["source_id"])
    readiness = _source_readiness(status)
    terms = str(source.get("attribution_licensing_notes") or "unknown")
    return {
        "source_id": source_id,
        "country_code": _country_code(source_id),
        "jurisdiction_scope": source["jurisdiction_scope"],
        "source_url": source["url"],
        "access_method": source["access_method"],
        "cadence": source["cadence"],
        "coverage": {
            "scope_statement": source["jurisdiction_scope"],
            "completeness": "not-claimed",
            "included": [source["jurisdiction_scope"]],
            "excluded": ["unverified or out-of-scope populations", "private or restricted payloads"],
            "disappearance_semantics": "not-observed; never inferred as closure",
            "limitations": list(source.get("blockers") or []),
        },
        "attribution": {
            "source_origin": "government or documented secondary source; see source registry",
            "terms_status": "pending-human-review",
            "attribution_required": True,
            "notice": terms,
        },
        "status": {key: status.get(key) for key in (
            "metadata", "acquisition", "runtime_health", "publication_eligibility", "evidence", "next_action"
        )},
        "readiness": readiness,
        "owner_review": {"state": "awaiting-owner-review", "owner": None, "decision_id": None},
        "publication": {
            "state": "blocked",
            "approval_required": True,
            "reason": "No owner approval is recorded in the checked-in status baseline.",
        },
    }


def _country_contract(country_code: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    readiness_states = {str(source["readiness"]["state"]) for source in sources}
    if readiness_states and readiness_states.issubset({"awaiting-owner-review", "private-candidate", "private-validated"}):
        state = "awaiting-owner-review"
    elif "reconnaissance" in readiness_states and readiness_states.issubset({"reconnaissance", "blocked"}):
        state = "reconnaissance"
    elif "not-started" in readiness_states:
        state = "not-started"
    else:
        state = "blocked"
    reasons = sorted({reason for source in sources for reason in source["readiness"]["reasons"]})
    readiness = {
        "schema_version": "country-source-readiness-v1",
        "state": state,
        "owner_review": "awaiting-owner-review",
        "private_candidate": state == "awaiting-owner-review",
        "public_release_allowed": False,
        "reasons": reasons or ["owner review is not recorded"],
    }
    return {
        "contract_version": COUNTRY_CONTRACT_VERSION,
        "country_code": country_code,
        "display_name": country_code,
        "source_ids": [source["source_id"] for source in sources],
        "coverage": {
            "scope_statement": f"Structured source profiles currently registered for {country_code}; no national completeness claim.",
            "completeness": "not-claimed",
            "included": sorted({source["jurisdiction_scope"] for source in sources}),
            "excluded": ["sources not registered in this checkout", "unverified facility populations", "restricted or removed records"],
            "disappearance_semantics": "not-observed; never inferred as closure",
        },
        "attribution": {
            "source_origin": "source-specific; see each source record",
            "terms_status": "pending-human-review",
            "attribution_required": True,
            "notice": "Source attribution, reuse terms, and publication scope require owner review per source.",
        },
        "owner_review": {"state": "awaiting-owner-review", "owner": None, "decision_id": None},
        "publication": {
            "state": "blocked",
            "approval_required": True,
            "reason": "Country summaries are not publication approvals and must not promote source rows.",
        },
        "readiness": readiness,
    }


def build_platform_registry(*, source_path: Path | None = None, status_path: Path | None = None) -> dict[str, Any]:
    """Build and validate the joined source/country registry offline."""
    config = _read_json(PLATFORM_CONFIG_PATH)
    if config.get("schema_version") != PLATFORM_SCHEMA_VERSION:
        raise PlatformRegistryError(f"platform config must use {PLATFORM_SCHEMA_VERSION}")
    source_payload = load_registry(source_path or (ROOT / "pipeline" / "source_registry.json"))
    status_payload = _read_json(status_path or STATUS_PATH)
    statuses = status_payload.get("sources")
    if not isinstance(statuses, list):
        raise PlatformRegistryError("source status registry must contain a sources list")
    status_by_id = {item.get("source_id"): item for item in statuses if isinstance(item, dict)}
    source_ids = {item["source_id"] for item in source_payload["sources"]}
    if set(status_by_id) != source_ids:
        raise PlatformRegistryError("source registry and status registry IDs do not match exactly")

    source_records = [_source_record(source, status_by_id[source["source_id"]]) for source in source_payload["sources"]]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in source_records:
        grouped[source["country_code"]].append(source)
    countries = [_country_contract(code, sorted(items, key=lambda item: item["source_id"])) for code, items in sorted(grouped.items())]
    validate_country_contracts(countries, known_source_ids=source_ids)
    return {
        "schema_version": PLATFORM_SCHEMA_VERSION,
        "contract_versions": {"country": COUNTRY_CONTRACT_VERSION, "readiness": "country-source-readiness-v1"},
        "source_count": len(source_records),
        "country_count": len(countries),
        "scale_target": config.get("scale_target"),
        "sources": source_records,
        "countries": countries,
        "publication_boundary": "awaiting-owner-review; private staging may continue; no release approval or promotion is implied",
    }


def source_metadata(source_id: str) -> dict[str, Any] | None:
    """Return row-free platform metadata for a source, if it is registered."""
    registry = build_platform_registry()
    return next((source for source in registry["sources"] if source["source_id"] == source_id), None)


def write_platform_snapshot(path: Path) -> dict[str, Any]:
    """Materialize a reviewable row-free snapshot without changing release state."""
    snapshot = build_platform_registry()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshot
