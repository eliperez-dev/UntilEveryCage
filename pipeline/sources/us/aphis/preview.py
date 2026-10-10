"""Private source-scoped APHIS registration projection.

The active register covers nine license/registration classes. These are
directory observations, not operating-site assertions: only mailing city and
state are retained as coarse private context and no coordinate is generated.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


_CLASS = re.compile(r"^class\s+([ABCFGHRTV])(?:\s*-\s*(.+))?$", re.IGNORECASE)
_KNOWN_CLASSES = {"A", "B", "C", "F", "G", "H", "R", "T", "V"}


class AphisPreviewError(ValueError):
    """The supplied private APHIS handoff is outside the registration lane."""


def _text(value: Any) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None


def _class(value: Any) -> tuple[str, str]:
    text = _text(value)
    match = _CLASS.fullmatch(text or "")
    if match is None or match.group(1).upper() not in _KNOWN_CLASSES:
        raise AphisPreviewError("aphis_preview_requires_known_native_license_class")
    code = match.group(1).upper()
    return code, text or f"Class {code}"


def project_registration(record: dict[str, Any]) -> dict[str, Any]:
    """Project one active registration without asserting a facility/site."""
    if record.get("source_id") != "us.aphis" or not isinstance(record.get("normalized"), dict):
        raise AphisPreviewError("aphis_preview_row_source_invalid")
    normalized = record["normalized"]
    if normalized.get("profile") != "registrations":
        raise AphisPreviewError("aphis_preview_requires_registrations")
    native_ids = normalized.get("source_native_ids")
    if not isinstance(native_ids, dict):
        native_ids = {}
    identity = _text(native_ids.get("aphis_license_number")) or _text(native_ids.get("certificate_number"))
    if identity is None:
        raise AphisPreviewError("aphis_preview_missing_source_identifier")
    code, label = _class(normalized.get("registration_or_license_type"))
    city = _text(normalized.get("mailing_city"))
    state = _text(normalized.get("mailing_state"))
    dba_names = normalized.get("dba_names")
    if not isinstance(dba_names, list) or any(not isinstance(item, str) or not item.strip() for item in dba_names):
        raise AphisPreviewError("aphis_preview_dba_schema_invalid")
    private_location: dict[str, Any] = {"country_code": "US"}
    if city:
        private_location["city"] = city
    if state:
        private_location["region"] = state
    projected = dict(record)
    projected["normalized"] = {
        "establishment_id": f"aphis-registration:{identity}",
        "facility_identity_state": "source_scoped_registration_not_operating_facility_assertion",
        "country_code": "US",
        "city": city,
        "state": state,
        "canonical_name": _text(normalized.get("canonical_name")),
        "dba_names": dba_names,
        "source_classification_code": f"Class {code}",
        "source_classification_label": label,
        "source_activity": label,
        "aphis_registration_class": f"Class {code}",
        "source_status": "active_list_membership",
        "source_native_ids": native_ids,
        "expiration_date": _text(normalized.get("expiration_date")),
        "address_state": "mailing_city_state_only_not_operating_site",
        "private_location_evidence": private_location,
        "coordinates": None,
        "coordinate_state": "no_source_coordinate",
        "privacy_gate": "pending-review",
        "coordinate_gate": "review_required",
        "publication_gate": "blocked",
        "source_scope_eligibility": "eligible",
    }
    return projected


def project_registrations(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [project_registration(record) for record in records]
    if not rows:
        raise AphisPreviewError("aphis_preview_no_rows")
    return rows
