"""Validation contract shared by country lanes.

The contract describes scope and gates; it does not contain facility rows.  A
country may have many source profiles, and each profile remains separately
traceable even when the country summary is materialized for an operator UI.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .readiness import ReadinessError, validate_readiness


COUNTRY_CONTRACT_VERSION = "country-contract-v1"
COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2,3}$")
OWNER_REVIEW_STATES = frozenset({"not-requested", "awaiting-owner-review", "approved", "rejected"})
PUBLICATION_STATES = frozenset({"blocked", "private-only", "approved-for-release", "published", "suppressed"})


class CountryContractError(ValueError):
    """Raised when a country contract is incomplete or unsafe."""


def _require_text(value: Mapping[str, Any], key: str, prefix: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise CountryContractError(f"{prefix}.{key} must be a non-empty string")
    return result


def _require_list(value: Mapping[str, Any], key: str, prefix: str) -> list[str]:
    result = value.get(key)
    if not isinstance(result, list) or not result or any(not isinstance(item, str) or not item.strip() for item in result):
        raise CountryContractError(f"{prefix}.{key} must be a non-empty list of strings")
    return result


def validate_country_contract(contract: Mapping[str, Any], *, known_source_ids: Iterable[str] | None = None) -> None:
    """Validate one source/country contract and all publication boundaries."""
    if not isinstance(contract, Mapping):
        raise CountryContractError("country contract must be an object")
    prefix = f"country[{contract.get('country_code', '?')}]"
    if contract.get("contract_version") != COUNTRY_CONTRACT_VERSION:
        raise CountryContractError(f"{prefix}.contract_version must be {COUNTRY_CONTRACT_VERSION}")
    code = _require_text(contract, "country_code", prefix)
    if not COUNTRY_CODE_RE.fullmatch(code):
        raise CountryContractError(f"{prefix}.country_code must be an uppercase ISO-like code")
    _require_text(contract, "display_name", prefix)
    _require_list(contract, "source_ids", prefix)
    source_ids = contract["source_ids"]
    if len(set(source_ids)) != len(source_ids):
        raise CountryContractError(f"{prefix}.source_ids must be unique")
    if known_source_ids is not None:
        unknown = sorted(set(source_ids) - set(known_source_ids))
        if unknown:
            raise CountryContractError(f"{prefix}.source_ids are not in the source registry: {unknown}")

    coverage = contract.get("coverage")
    if not isinstance(coverage, Mapping):
        raise CountryContractError(f"{prefix}.coverage must be an object")
    _require_text(coverage, "scope_statement", f"{prefix}.coverage")
    _require_text(coverage, "completeness", f"{prefix}.coverage")
    _require_list(coverage, "included", f"{prefix}.coverage")
    _require_list(coverage, "excluded", f"{prefix}.coverage")
    if coverage.get("disappearance_semantics") != "not-observed; never inferred as closure":
        raise CountryContractError(f"{prefix}.coverage.disappearance_semantics must preserve not-observed semantics")

    attribution = contract.get("attribution")
    if not isinstance(attribution, Mapping):
        raise CountryContractError(f"{prefix}.attribution must be an object")
    _require_text(attribution, "source_origin", f"{prefix}.attribution")
    _require_text(attribution, "terms_status", f"{prefix}.attribution")
    _require_text(attribution, "notice", f"{prefix}.attribution")
    if not isinstance(attribution.get("attribution_required"), bool):
        raise CountryContractError(f"{prefix}.attribution.attribution_required must be boolean")

    owner_review = contract.get("owner_review")
    if not isinstance(owner_review, Mapping):
        raise CountryContractError(f"{prefix}.owner_review must be an object")
    owner_state = _require_text(owner_review, "state", f"{prefix}.owner_review")
    if owner_state not in OWNER_REVIEW_STATES:
        raise CountryContractError(f"{prefix}.owner_review.state is unknown")
    if "owner" not in owner_review or owner_review.get("owner") not in (None, "") and not isinstance(owner_review.get("owner"), str):
        raise CountryContractError(f"{prefix}.owner_review.owner must be null or a string")
    if owner_state == "approved" and not owner_review.get("decision_id"):
        raise CountryContractError(f"{prefix}.owner_review approved state requires decision_id")
    if owner_state != "approved" and owner_review.get("decision_id") is not None:
        raise CountryContractError(f"{prefix}.owner_review decision_id is only valid after approval")

    publication = contract.get("publication")
    if not isinstance(publication, Mapping):
        raise CountryContractError(f"{prefix}.publication must be an object")
    publication_state = _require_text(publication, "state", f"{prefix}.publication")
    if publication_state not in PUBLICATION_STATES:
        raise CountryContractError(f"{prefix}.publication.state is unknown")
    if not isinstance(publication.get("approval_required"), bool) or publication.get("approval_required") is not True:
        raise CountryContractError(f"{prefix}.publication.approval_required must remain true")
    if publication_state in {"approved-for-release", "published"} and owner_state != "approved":
        raise CountryContractError(f"{prefix} cannot be release-ready without owner approval")
    if publication_state in {"blocked", "private-only"} and owner_state == "approved":
        # An approved owner can still keep a country private, but the contract
        # must say why instead of accidentally looking publishable.
        if not publication.get("reason"):
            raise CountryContractError(f"{prefix}.publication.reason is required for a private approved lane")

    readiness = contract.get("readiness")
    if not isinstance(readiness, Mapping):
        raise CountryContractError(f"{prefix}.readiness must be an object")
    try:
        validate_readiness(readiness)
    except ReadinessError as error:
        raise CountryContractError(f"{prefix}.readiness is invalid: {error}") from error
    if readiness.get("owner_review") != owner_state:
        raise CountryContractError(f"{prefix}.readiness.owner_review must match owner_review.state")
    if owner_state != "approved" and readiness.get("public_release_allowed") is not False:
        raise CountryContractError(f"{prefix} cannot allow public release before owner approval")


def validate_country_contracts(contracts: Iterable[Mapping[str, Any]], *, known_source_ids: Iterable[str] | None = None) -> None:
    """Validate a collection and reject duplicate country/source ownership."""
    seen_countries: set[str] = set()
    seen_sources: set[str] = set()
    for contract in contracts:
        validate_country_contract(contract, known_source_ids=known_source_ids)
        code = str(contract["country_code"])
        if code in seen_countries:
            raise CountryContractError(f"duplicate country contract: {code}")
        seen_countries.add(code)
        duplicates = seen_sources.intersection(contract["source_ids"])
        if duplicates:
            raise CountryContractError(f"source IDs assigned to multiple country contracts: {sorted(duplicates)}")
        seen_sources.update(contract["source_ids"])
