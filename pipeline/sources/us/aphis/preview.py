"""Bounded private-preview projection for APHIS Class R registrants.

This module is deliberately narrower than the APHIS observation adapter.  It
accepts only a registrations handoff whose source-provided registration type
is exactly Class R - Research Facility.  It does not assert an operating
facility, merge identities, or authorize release/public display.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


_CLASS_R = re.compile(r"^class\s+r\s*-\s*research\s+facility$", re.IGNORECASE)


class AphisPreviewError(ValueError):
    """The supplied private APHIS handoff is outside this bounded lane."""


def _text(value: Any) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None


def _city_state_zip(values: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    city, state, postal = (_text(values.get(key)) for key in ("City", "State", "Zip"))
    # The current registrants export includes this combined field.  Preserve
    # it in private source_values and use it only to populate the restricted
    # location evidence when separate columns are absent.
    combined = _text(values.get("City-State-Zip"))
    if combined and (not city or not state or not postal):
        match = re.match(r"^(.*?)(?:\s*,\s*|\s+)([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)$", combined)
        if match:
            city, state, postal = city or _text(match.group(1)), state or match.group(2).upper(), postal or match.group(3)
    return city, state, postal


def project_class_r_registration(record: dict[str, Any]) -> dict[str, Any]:
    """Make one generic-private-preview-compatible record without losing evidence."""
    if record.get("source_id") != "us.aphis" or not isinstance(record.get("normalized"), dict):
        raise AphisPreviewError("aphis_preview_row_source_invalid")
    normalized = record["normalized"]
    values = record.get("source_values")
    if not isinstance(values, dict) or normalized.get("profile") != "registrations":
        raise AphisPreviewError("aphis_preview_requires_registrations")
    registration_type = _text(normalized.get("registration_or_license_type"))
    if registration_type is None or not _CLASS_R.fullmatch(registration_type):
        raise AphisPreviewError("aphis_preview_requires_explicit_class_r")
    native_ids = normalized.get("source_native_ids")
    if not isinstance(native_ids, dict):
        native_ids = {}
    identity = _text(native_ids.get("certificate_number")) or _text(native_ids.get("customer_number"))
    if identity is None:
        raise AphisPreviewError("aphis_preview_missing_source_identifier")
    city, state, postal = _city_state_zip(values)
    address_lines = [line for line in (_text(values.get("Address Line 1")), _text(values.get("Address Line 2"))) if line]
    private_location: dict[str, Any] = {"country_code": "US"}
    if address_lines:
        private_location["address_lines"] = address_lines
    if city:
        private_location["city"] = city
    if state:
        private_location["region"] = state
    if postal:
        private_location["postal_code"] = postal
    projected = dict(record)
    projected["normalized"] = {
        "establishment_id": f"aphis-registration:{identity}",
        "facility_identity_state": "source_scoped_registration_not_operating_facility_assertion",
        "country_code": "US",
        "city": city,
        "state": state,
        "postal_code": postal,
        "source_classification_code": "Class R",
        "source_classification_label": "Research Facility",
        "source_activity": registration_type,
        "aphis_registration_class": "Class R",
        "source_status": _text(normalized.get("status")),
        "status_date": _text(normalized.get("status_date")),
        "source_native_ids": native_ids,
        "address_state": "source-address-retained-private-pending-review",
        "private_location_evidence": private_location,
        "coordinates": None,
        "coordinate_state": "no_source_coordinate",
        "privacy_gate": "pending-review",
        "coordinate_gate": "review_required",
        "publication_gate": "blocked",
        "source_scope_eligibility": "eligible",
    }
    return projected


def project_class_r_registrations(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [project_class_r_registration(record) for record in records]
    if not rows:
        raise AphisPreviewError("aphis_preview_no_rows")
    return rows
