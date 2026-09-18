"""Provider-neutral country geocoding reconnaissance contracts.

Profiles describe evidence and gates; they are not provider credentials, a
geocoding queue, a cache, or publication approval.  The validator is kept
dependency-free so CI can fail closed before a profile is used by a pipeline.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


GEOCODING_PROFILE_VERSION = "country-geocoding-profile-v1"
GEOCODING_REGISTRY_VERSION = "country-geocoding-profile-registry-v1"
RECON_REPORT_VERSION = "country-geocoding-recon-report-v1"

_AVAILABILITY = frozenset({"present", "mixed", "not_observed", "unknown"})
_PROVIDER_ROLES = frozenset({"national_authority", "government_lookup", "regional_fallback", "global_fallback"})
_PROVIDER_STATUS = frozenset({"reviewed", "conditional", "candidate", "blocked", "unknown"})
_FALLBACK_STATES = ("exact", "coarse", "restricted", "unmapped")
_ACQUISITION_POINTS = {"verified": 50, "artifact_private_only": 45, "not_run": 25, "blocked": 5}
_METADATA_POINTS = {"verified": 15, "partial": 8, "unknown": 0}
_ADAPTER_POINTS = {"implemented": 14, "implemented_partial": 12, "reference_only": 4, "not_started": 0}
_HEALTH_POINTS = {"healthy": 5, "unknown": 2, "not_run": 0}


class GeocodingProfileError(ValueError):
    """Raised when a geocoding profile or report is incomplete or unsafe."""


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GeocodingProfileError(f"{path} must be an object")
    return value


def _text(value: Mapping[str, Any], key: str, path: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise GeocodingProfileError(f"{path}.{key} must be a non-empty string")
    return result


def _list(value: Mapping[str, Any], key: str, path: str, *, nonempty: bool = True) -> list[Any]:
    result = value.get(key)
    if not isinstance(result, list) or (nonempty and not result):
        raise GeocodingProfileError(f"{path}.{key} must be a{' non-empty' if nonempty else 'n'} list")
    return result


def _bool(value: Mapping[str, Any], key: str, path: str, *, required: bool = True) -> None:
    if key not in value and not required:
        return
    if not isinstance(value.get(key), bool):
        raise GeocodingProfileError(f"{path}.{key} must be boolean")


def _reject_private_payloads(value: Any, path: str = "profile") -> None:
    """Reject shapes that could accidentally turn recon into a record store."""
    forbidden_keys = {
        "facility_rows", "record_rows", "source_values", "raw_response", "response_payload",
        "query_value", "raw_address", "latitude", "longitude", "lat", "lon",
    }
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in forbidden_keys:
                raise GeocodingProfileError(f"{path}.{key} is not allowed in a row-free profile")
            _reject_private_payloads(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_private_payloads(child, f"{path}[{index}]")


def _validate_provider(provider: Mapping[str, Any], path: str, provider_ids: set[str]) -> None:
    provider_id = _text(provider, "provider_id", path)
    if provider_id in provider_ids:
        raise GeocodingProfileError(f"duplicate provider_id: {provider_id}")
    provider_ids.add(provider_id)
    if provider.get("role") not in _PROVIDER_ROLES:
        raise GeocodingProfileError(f"{path}.role is unknown")
    if provider.get("status") not in _PROVIDER_STATUS:
        raise GeocodingProfileError(f"{path}.status is unknown")
    for key in ("name", "authority_or_operator", "coverage", "endpoint", "notes"):
        _text(provider, key, path)
    access = _mapping(provider.get("access"), f"{path}.access")
    for key in ("mode", "bulk_mode", "export_or_download", "cost_model"):
        _text(access, key, f"{path}.access")
    terms = _mapping(provider.get("terms"), f"{path}.terms")
    for key in ("license_status", "attribution", "caching", "redistribution", "retention", "logging", "residency"):
        _text(terms, key, f"{path}.terms")
    throughput = _mapping(provider.get("throughput"), f"{path}.throughput")
    for key in ("documented_limit", "recommended_rate", "duration_or_cost_estimate"):
        _text(throughput, key, f"{path}.throughput")
    confidence = _mapping(provider.get("confidence_mapping"), f"{path}.confidence_mapping")
    for key in ("accepted", "human_review", "rejected"):
        _list(confidence, key, f"{path}.confidence_mapping")
    docs = _list(provider, "evidence", path)
    if any(not isinstance(item, str) or not item.startswith(("https://", "http://", "docs/", "pipeline/")) for item in docs):
        raise GeocodingProfileError(f"{path}.evidence must contain URLs or repository paths")


def validate_profile(profile: Mapping[str, Any], *, known_source_ids: Iterable[str] | None = None) -> None:
    """Validate one country profile and its publication boundary."""
    if not isinstance(profile, Mapping):
        raise GeocodingProfileError("profile must be an object")
    path = f"profile[{profile.get('profile_id', '?')}]"
    if profile.get("profile_version") != GEOCODING_PROFILE_VERSION:
        raise GeocodingProfileError(f"{path}.profile_version must be {GEOCODING_PROFILE_VERSION}")
    for key in ("profile_id", "country_code", "display_name", "assessed_at", "assessment_scope", "publication_boundary"):
        _text(profile, key, path)
    source_ids = _list(profile, "source_ids", path)
    if any(not isinstance(item, str) or not item.strip() for item in source_ids) or len(set(source_ids)) != len(source_ids):
        raise GeocodingProfileError(f"{path}.source_ids must be unique non-empty strings")
    if known_source_ids is not None:
        unknown = sorted(set(source_ids) - set(known_source_ids))
        if unknown:
            raise GeocodingProfileError(f"{path}.source_ids are not in the source registry: {unknown}")

    if profile.get("country_code") != str(profile["country_code"]).upper():
        raise GeocodingProfileError(f"{path}.country_code must be uppercase")
    if profile.get("publication_boundary") != "blocked; profile is reconnaissance evidence only; no release eligibility is granted":
        raise GeocodingProfileError(f"{path}.publication_boundary must keep publication blocked")
    _bool(profile, "no_private_records_queried", path)
    if profile.get("no_private_records_queried") is not True:
        raise GeocodingProfileError(f"{path}.no_private_records_queried must be true")

    source_coordinates = _list(profile, "source_coordinate_evidence", path)
    seen_source_ids: set[str] = set()
    for index, item in enumerate(source_coordinates):
        item = _mapping(item, f"{path}.source_coordinate_evidence[{index}]")
        source_id = _text(item, "source_id", f"{path}.source_coordinate_evidence[{index}]")
        if source_id not in source_ids or source_id in seen_source_ids:
            raise GeocodingProfileError(f"{path}.source_coordinate_evidence has invalid or duplicate source_id: {source_id}")
        seen_source_ids.add(source_id)
        if item.get("availability") not in _AVAILABILITY:
            raise GeocodingProfileError(f"{path}.source_coordinate_evidence[{index}].availability is unknown")
        for key in ("field_names", "semantics", "precision", "expected_coverage", "review_state"):
            if key == "field_names":
                fields = _list(item, key, f"{path}.source_coordinate_evidence[{index}]")
                if any(not isinstance(field, str) for field in fields):
                    raise GeocodingProfileError(f"{path}.source_coordinate_evidence[{index}].field_names must be strings")
            else:
                _text(item, key, f"{path}.source_coordinate_evidence[{index}]")
        _bool(item, "never_overwrite_source", f"{path}.source_coordinate_evidence[{index}]")
        if item.get("never_overwrite_source") is not True:
            raise GeocodingProfileError(f"{path}.source_coordinate_evidence[{index}] must preserve source coordinates")
    if seen_source_ids != set(source_ids):
        raise GeocodingProfileError(f"{path}.source_coordinate_evidence must cover every source_id")

    address_model = _mapping(profile.get("address_model"), f"{path}.address_model")
    for key in ("structure", "language_scripts", "transliteration", "administrative_hierarchy", "locality_notes"):
        _text(address_model, key, f"{path}.address_model")

    authority = _mapping(profile.get("national_address_authority"), f"{path}.national_address_authority")
    authority_provider = _text(authority, "provider_id", f"{path}.national_address_authority")
    for key in ("authority", "role", "availability", "coordinate_semantics", "terms_status", "notes"):
        _text(authority, key, f"{path}.national_address_authority")

    providers = _list(profile, "providers", path)
    provider_ids: set[str] = set()
    for index, item in enumerate(providers):
        _validate_provider(_mapping(item, f"{path}.providers[{index}]"), f"{path}.providers[{index}]", provider_ids)
    if authority_provider not in provider_ids:
        raise GeocodingProfileError(f"{path}.national_address_authority.provider_id is not in providers")
    if not any(item.get("provider_id") == authority_provider and item.get("role") == "national_authority" for item in providers):
        raise GeocodingProfileError(f"{path}.national_address_authority provider must have national_authority role")
    global_provider_ids = {str(item.get("provider_id")) for item in providers if str(item.get("provider_id", "")).startswith("global.")}
    if not {"global.nominatim-self-hosted", "global.pelias-self-hosted"}.issubset(global_provider_ids):
        raise GeocodingProfileError(f"{path} must carry both reusable global fallback candidates")

    lookup_options = _list(profile, "government_open_data_options", path)
    for index, item in enumerate(lookup_options):
        item = _mapping(item, f"{path}.government_open_data_options[{index}]")
        _text(item, "provider_id", f"{path}.government_open_data_options[{index}]")
        _text(item, "scope", f"{path}.government_open_data_options[{index}]")
        _text(item, "access_and_export", f"{path}.government_open_data_options[{index}]")
        _text(item, "limitations", f"{path}.government_open_data_options[{index}]")

    query = _mapping(profile.get("query_minimization"), f"{path}.query_minimization")
    for key in ("allowed_components", "construction_steps", "never_send", "logging_boundary"):
        _list(query, key, f"{path}.query_minimization")
    _bool(query, "private_record_network_authorized", f"{path}.query_minimization")
    if query.get("private_record_network_authorized") is not False:
        raise GeocodingProfileError(f"{path}.query_minimization.private_record_network_authorized must be false")

    fallback = _list(profile, "fallback_chain", path)
    if [item.get("state") for item in fallback if isinstance(item, Mapping)] != list(_FALLBACK_STATES):
        raise GeocodingProfileError(f"{path}.fallback_chain must be ordered exact/coarse/restricted/unmapped")
    for index, item in enumerate(fallback):
        item = _mapping(item, f"{path}.fallback_chain[{index}]")
        if item.get("state") not in _FALLBACK_STATES or item.get("order") != index + 1:
            raise GeocodingProfileError(f"{path}.fallback_chain[{index}] has invalid state/order")
        ids = _list(item, "provider_ids", f"{path}.fallback_chain[{index}", nonempty=False)
        if any(provider_id not in provider_ids for provider_id in ids):
            raise GeocodingProfileError(f"{path}.fallback_chain[{index}] references an unknown provider")
        for key in ("entry_conditions", "exit_conditions"):
            _text(item, key, f"{path}.fallback_chain[{index}]")

    confidence = _mapping(profile.get("confidence_policy"), f"{path}.confidence_policy")
    for key in ("exact_acceptance", "coarse_acceptance", "human_review_threshold", "disagreement_rule", "moved_point_rule"):
        _text(confidence, key, f"{path}.confidence_policy")
    overrides = _list(confidence, "provider_overrides", f"{path}.confidence_policy")
    for index, item in enumerate(overrides):
        item = _mapping(item, f"{path}.confidence_policy.provider_overrides[{index}]")
        _text(item, "provider_id", f"{path}.confidence_policy.provider_overrides[{index}]")
        for key in ("accept", "review", "reject"):
            _text(item, key, f"{path}.confidence_policy.provider_overrides[{index}]")

    gates = _mapping(profile.get("review_gates"), f"{path}.review_gates")
    for key in ("terms_review", "privacy_review", "source_coordinate_review", "human_acceptance", "publication_separation"):
        _text(gates, key, f"{path}.review_gates")
    if gates.get("publication_separation") != "geocoding evidence never grants project approval or publication":
        raise GeocodingProfileError(f"{path}.review_gates.publication_separation is unsafe")

    resilience = _mapping(profile.get("resilience"), f"{path}.resilience")
    for key in ("disagreement", "moved_point", "outage", "replacement"):
        _text(resilience, key, f"{path}.resilience")
    estimate = _mapping(profile.get("operational_estimate"), f"{path}.operational_estimate")
    for key in ("unit", "duration_formula", "cost_formula", "parallelism_policy"):
        _text(estimate, key, f"{path}.operational_estimate")
    _list(profile, "unresolved_questions", path)
    _list(profile, "evidence", path)
    _reject_private_payloads(profile)


def validate_profiles(payload: Mapping[str, Any], *, known_source_ids: Iterable[str] | None = None) -> None:
    """Validate a profile registry and reject duplicate source ownership."""
    if payload.get("schema_version") != GEOCODING_REGISTRY_VERSION:
        raise GeocodingProfileError(f"schema_version must be {GEOCODING_REGISTRY_VERSION}")
    global_policy = _mapping(payload.get("global_fallback_policy"), "registry.global_fallback_policy")
    for key in ("default_candidate_provider", "backup_candidate_provider", "activation_state", "rationale"):
        _text(global_policy, key, "registry.global_fallback_policy")
    if global_policy.get("default_candidate_provider") != "global.nominatim-self-hosted" or global_policy.get("backup_candidate_provider") != "global.pelias-self-hosted":
        raise GeocodingProfileError("registry global fallback candidates must remain provider-neutral and self-hosted")
    profiles = _list(payload, "profiles", "registry")
    seen_profile_ids: set[str] = set()
    seen_source_ids: set[str] = set()
    for profile in profiles:
        profile = _mapping(profile, "registry.profile")
        validate_profile(profile, known_source_ids=known_source_ids)
        profile_id = str(profile["profile_id"])
        if profile_id in seen_profile_ids:
            raise GeocodingProfileError(f"duplicate profile_id: {profile_id}")
        seen_profile_ids.add(profile_id)
        overlap = seen_source_ids.intersection(profile["source_ids"])
        if overlap:
            raise GeocodingProfileError(f"source IDs assigned to multiple profiles: {sorted(overlap)}")
        seen_source_ids.update(profile["source_ids"])


def rank_sources(source_registry: Mapping[str, Any], status_registry: Mapping[str, Any], profiles: Iterable[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Rank every registered source using only deterministic status signals."""
    statuses = {item.get("source_id"): item for item in status_registry.get("sources", []) if isinstance(item, Mapping)}
    profiled = {source_id for profile in profiles for source_id in profile.get("source_ids", [])}
    ranked: list[dict[str, Any]] = []
    for source in source_registry.get("sources", []):
        source_id = str(source["source_id"])
        status = statuses.get(source_id, {})
        acquisition = str(status.get("acquisition", "not_run"))
        metadata = str(status.get("metadata", "unknown"))
        adapter = str(source.get("adapter_status", "not_started"))
        health = str(status.get("runtime_health", "not_run"))
        score = _ACQUISITION_POINTS.get(acquisition, 0) + _METADATA_POINTS.get(metadata, 0) + _ADAPTER_POINTS.get(adapter, 0) + _HEALTH_POINTS.get(health, 0)
        if acquisition == "blocked":
            score -= 10
        if source_id in profiled:
            score += 3
        if acquisition == "verified" and adapter in {"implemented", "implemented_partial"}:
            band = "deep-tranche"
        elif acquisition == "artifact_private_only" and adapter in {"implemented", "implemented_partial"}:
            band = "deep-tranche"
        elif acquisition in {"verified", "artifact_private_only"}:
            band = "next-tranche"
        elif metadata in {"verified", "partial"}:
            band = "reconnaissance-backlog"
        else:
            band = "unstarted-backlog"
        ranked.append({
            "source_id": source_id,
            "country_code": source_id.split(".", 1)[0].upper(),
            "score": score,
            "band": band,
            "profile_state": "deeply-assessed" if source_id in profiled else "profile-pending",
            "signals": {"metadata": metadata, "acquisition": acquisition, "adapter_status": adapter, "runtime_health": health},
            "next_action": str(status.get("next_action") or "Create a source-specific geocoding profile before acquisition or geocoding."),
        })
    return sorted(ranked, key=lambda item: (-item["score"], item["source_id"]))


def build_recon_report(source_registry: Mapping[str, Any], status_registry: Mapping[str, Any], profile_registry: Mapping[str, Any]) -> dict[str, Any]:
    """Build the row-free, deterministic ranking report."""
    validate_profiles(profile_registry, known_source_ids={item["source_id"] for item in source_registry.get("sources", [])})
    ranked = rank_sources(source_registry, status_registry, profile_registry["profiles"])
    deep = [item for item in ranked if item["profile_state"] == "deeply-assessed"]
    return {
        "report_version": RECON_REPORT_VERSION,
        "rows_included": False,
        "facility_or_address_payloads_included": False,
        "source_count": len(ranked),
        "profile_count": len(profile_registry["profiles"]),
        "deep_assessment_source_count": len(deep),
        "publication_boundary": "reconnaissance only; no profile, provider, source, or geocode result grants publication eligibility",
        "ranking_method": "status-only deterministic score: acquisition 0-50, metadata 0-15, adapter 0-14, runtime 0-5, blocked-acquisition penalty 10, assessed-profile tie-break bonus 3; ties sort by source_id",
        "ranked_backlog": ranked,
        "deep_tranche": [item["source_id"] for item in deep],
        "fallback_policy": "country/regional authority first; government/open-data coarse lookup second; reviewed regional candidate third; self-hosted or global fallback only after terms/privacy/rate review; otherwise restricted or unmapped",
    }
