"""Source-qualified mapping of retained facility fields into graph semantics.

The mapping is intentionally allowlisted: generic ``name`` and address fields
are not silently promoted to organization/operator or operating-site claims.
"""
from __future__ import annotations

from typing import Any


# Native keys and their namespaces are kept per source.  Similar-looking IDs
# from different authorities must never become equal merely because their
# text happens to match.
FACILITY_IDENTIFIERS: dict[str, tuple[str, str]] = {
    "au.npi.facilities": ("npi_facility_id", "au.npi.facilities"),
    "au.sa.epa.licensed-activities": ("sa_epa_licence_number", "au.sa.epa.licensed-activities"),
    "be.locations": ("fasfc_establishment_id", "be.locations"),
    "br.sif.registered": ("sif_establishment_id", "br.sif.registered"),
    "ca.ontario.meat-plants": ("ontario_plant_number", "ca.ontario.meat-plants"),
    "dk.smiley": ("find_smiley_establishment_id", "dk.smiley"),
    "es.cat.feed-sandach": ("catalonia_sandach_registration", "es.cat.feed-sandach"),
    "fsa_approved_establishments": ("fsa_establishment_id", "fsa_approved_establishments"),
    "fss_approved_establishments": ("fss_establishment_id", "fss_approved_establishments"),
    "it.1069-2009": ("it_1069_recognition_number", "it.1069-2009"),
    "it.853-2004": ("it_853_recognition_number", "it.853-2004"),
    "nl.nvwa.approved-food": ("nvwa_approval_number", "nl.nvwa.approved-food"),
    "us.aphis": ("aphis_establishment_id", "us.aphis"),
    "us.fsis": ("fsis_establishment_number", "us.fsis"),
    "fr.dgal.section-i": ("dgal_section_i_approval", "fr.dgal.section-i"),
    "fr.dgal.section-ii": ("dgal_section_ii_approval", "fr.dgal.section-ii"),
    "fr.georisques.icpe.animal": ("georisques_aiot", "fr.georisques.icpe.animal"),
    "gb.scot.marine.aquaculture": ("scottish_aquaculture_site_id", "gb.scot.marine.aquaculture"),
}

# Only fields whose source adapters or retained projection explicitly
# distinguish their facility/business role are eligible. Deliberately omit
# generic ``name`` and ambiguous person, account, contact, or government-link
# fields.
NAME_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "au.npi.facilities": (("registered_business_name", "legal"), ("facility_name", "business"), ("facility_display_name", "business")),
    "ca.ontario.meat-plants": (("operator_name", "operator"), ("trading_name", "trading"), ("facility_display_name", "business")),
    "dk.smiley": (("trading_name", "trading"), ("facility_display_name", "business")),
    "fsa_approved_establishments": (("trading_name", "trading"), ("facility_display_name", "business")),
    "fss_approved_establishments": (("trading_name", "trading"), ("facility_display_name", "business")),
    "nl.nvwa.approved-food": (("trading_name", "trading"), ("facility_display_name", "business")),
    "us.aphis": (("canonical_name", "business"), ("facility_display_name", "business")),
    "it.1069-2009": (("name", "business"), ("trading_name", "trading"), ("facility_display_name", "business")),
    "it.853-2004": (("name", "business"), ("trading_name", "trading"), ("facility_display_name", "business")),
    "us.fsis": (("canonical_name", "business"),),
    "fr.dgal.section-i": (("name", "business"), ("trading_name", "trading"), ("facility_display_name", "business")),
    "fr.dgal.section-ii": (("name", "business"), ("trading_name", "trading"), ("facility_display_name", "business")),
    "fr.georisques.icpe.animal": (("trading_name", "business"), ("facility_name", "business")),
    "gb.scot.marine.aquaculture": (("facility_name", "business"),),
}

LOCATION_ROLES: dict[str, str] = {
    "source-reported-facility-location": "operating",
    "mailing": "mailing",
    "registered": "registered",
    "city_reference": "city_reference",
}


def _values(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (tuple, list)):
        items = list(value)
    else:
        return []
    result: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip() and item.strip() not in result:
            result.append(item.strip())
    return result


def source_identifier(source_id: str, normalized: dict[str, Any]) -> dict[str, str] | None:
    """Return one typed, authority-namespaced facility identifier if present."""
    identifier_type, namespace = FACILITY_IDENTIFIERS.get(
        source_id, ("source_establishment_id", source_id)
    )
    candidates: list[Any] = []
    configured = {
        "au.npi.facilities": ("facility_id", "establishment_id"),
        "au.sa.epa.licensed-activities": ("establishment_id",),
        "it.1069-2009": ("recognition_number", "establishment_id"),
        "it.853-2004": ("recognition_number", "establishment_id"),
        "be.locations": ("establishment_id",),
        "ca.ontario.meat-plants": ("establishment_id", "recognition_number"),
        "us.aphis": ("establishment_id",),
        "us.fsis": ("establishment_id", "establishment_number"),
        "nl.nvwa.approved-food": ("approval_number", "establishment_id"),
        "fr.dgal.section-i": ("recognition_number", "establishment_id"),
        "fr.dgal.section-ii": ("recognition_number", "establishment_id"),
        "fr.georisques.icpe.animal": ("establishment_id",),
        "gb.scot.marine.aquaculture": ("establishment_id", "site_id"),
    }.get(source_id, ("establishment_id", "approval_number"))
    for field in configured:
        value = normalized.get(field)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    # Event rows deliberately have no establishment_id in the APHIS adapter.
    # Their identifiers are linked by the evidence lane, never retyped here.
    if source_id == "us.aphis" and normalized.get("event_type"):
        return None
    if source_id == "us.aphis" and isinstance(normalized.get("source_native_ids"), dict):
        native_ids = normalized["source_native_ids"]
        certificate = native_ids.get("certificate_number")
        if isinstance(certificate, str) and certificate.strip():
            candidates.insert(0, certificate.strip())
    if not candidates:
        return None
    return {"identifier_type": identifier_type, "id_namespace": namespace,
            "value": candidates[0], "identity_scope": "source_scoped"}


def name_assertions(source_id: str, normalized: dict[str, Any]) -> list[dict[str, str]]:
    assertions: list[dict[str, str]] = []
    fields = NAME_FIELDS.get(source_id, ())
    for field, role in fields:
        for value in _values(normalized.get(field)):
            assertions.append({"value": value, "source_field": field, "role": role})
    # Existing FSIS alias semantics remain backward compatible while new
    # records use the common typed assertion form.
    if source_id == "us.fsis":
        for field in ("dba_names", "alternate_names"):
            for value in _values(normalized.get(field)):
                assertions.append({"value": value, "source_field": field, "role": "dba"})
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for item in assertions:
        key = (item["value"].casefold(), item["role"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def location_role(source_id: str, normalized: dict[str, Any]) -> str:
    raw = normalized.get("location_role")
    if isinstance(raw, str) and raw in LOCATION_ROLES:
        return LOCATION_ROLES[raw]
    if source_id == "au.npi.facilities" and normalized.get("location_role") == "source-reported-facility-location":
        return "operating"
    return "unknown"


__all__ = ["FACILITY_IDENTIFIERS", "LOCATION_ROLES", "NAME_FIELDS", "location_role", "name_assertions", "source_identifier"]
