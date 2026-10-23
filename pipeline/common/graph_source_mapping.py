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

# These registries describe an inspected/approved/regulated animal premises,
# not merely a postal reference. A role is emitted only when a street-level
# address is actually present in normalized or source-native evidence.
PREMISES_ADDRESS_SOURCES = frozenset({
    "au.npi.facilities", "ca.ontario.meat-plants", "dk.smiley",
    "es.cat.feed-sandach", "fsa_approved_establishments",
    "fss_approved_establishments", "nl.nvwa.approved-food", "us.fsis",
    "fr.georisques.icpe.animal", "gb.scot.marine.aquaculture", "it.853-2004",
})


def _has_address_evidence(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for key in ("address", "street", "street_address", "street_address_1", "address_lines", "indirizzo",
                "address_line_1", "address_line_2", "address1", "adresse1", "adre_a",
                "loc_add1", "Adresse", "Address1", "Address2"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return True
        if isinstance(item, (list, tuple)) and any(isinstance(part, str) and part.strip() for part in item):
            return True
    nested = value.get("private_location_evidence")
    return _has_address_evidence(nested) if isinstance(nested, dict) else False


def _has_city_reference(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if any(isinstance(value.get(key), str) and value[key].strip()
           for key in ("city", "municipality", "locality", "town")):
        return True
    nested = value.get("private_location_evidence")
    return _has_city_reference(nested) if isinstance(nested, dict) else False


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


def additional_source_identifiers(source_id: str, normalized: dict[str, Any],
                                  source_values: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Return source-documented facility-ID aliases without creating entities."""
    values = source_values if isinstance(source_values, dict) else {}
    fields = {
        "fr.georisques.icpe.animal": (("siret", "french_siret", "fr.insee.siret"),),
        "fr.dgal.section-i": (("SIRET", "french_siret", "fr.insee.siret"), ("siret", "french_siret", "fr.insee.siret")),
        "fr.dgal.section-ii": (("SIRET", "french_siret", "fr.insee.siret"), ("siret", "french_siret", "fr.insee.siret")),
    }.get(source_id, ())
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for field, identifier_type, namespace in fields:
        value = values.get(field)
        if isinstance(value, str):
            compact = "".join(character for character in value if character.isdigit())
            if len(compact) == 14 and compact == value.strip().replace(" ", ""):
                pair = (identifier_type, compact)
                if pair not in seen:
                    seen.add(pair)
                    result.append({"identifier_type": identifier_type, "value": value.strip(),
                                   "id_namespace": namespace, "identity_scope": "source_scoped"})
    return result


def organization_identifiers(source_id: str, normalized: dict[str, Any],
                             source_values: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Allowlist declared business-ID fields and exclude mixed personal IDs."""
    values = source_values if isinstance(source_values, dict) else {}
    result: list[dict[str, str]] = []

    def add(field: str, identifier_type: str, namespace: str, length: int) -> None:
        value = values.get(field)
        if isinstance(value, str):
            compact = "".join(character for character in value if character.isdigit())
            if len(compact) == length and compact == value.strip().replace(" ", ""):
                result.append({"identifier_type": identifier_type, "value": value.strip(),
                               "id_namespace": namespace, "identity_scope": "source_scoped"})

    if source_id in {"it.853-2004", "it.1069-2009"}:
        add("p_iva", "italian_vat", "it.tax-authority.vat", 11)
    elif source_id == "au.npi.facilities":
        add("abn", "australian_business_number", "au.abr.abn", 11)
        add("acn", "australian_company_number", "au.asic.acn", 9)
    elif source_id == "br.sif.registered":
        # CPF_CNPJ is mixed; only 14-digit CNPJ shape is emitted, never CPF.
        add("CPF_CNPJ", "brazil_cnpj", "br.receita.cnpj", 14)
    elif source_id == "dk.smiley":
        for field in ("CVR_nummer", "cvrnr"):
            add(field, "cvr", "dk.virk.cvr", 8)
    return result


def operator_asserted(source_id: str, source_values: dict[str, Any] | None = None) -> bool:
    """Use only the 853 register's documented VAT plus legal-name assertion."""
    values = source_values if isinstance(source_values, dict) else {}
    return bool(source_id in {"it.853-2004", "it.1069-2009"}
                and any(item["identifier_type"] == "italian_vat"
                        for item in organization_identifiers(source_id, {}, values))
                and isinstance(values.get("ragione_sociale"), str)
                and values["ragione_sociale"].strip())


def name_assertions(source_id: str, normalized: dict[str, Any], source_values: dict[str, Any] | None = None) -> list[dict[str, str]]:
    assertions: list[dict[str, str]] = []
    fields = NAME_FIELDS.get(source_id, ())
    if source_id in {"it.1069-2009", "it.853-2004"}:
        legal_name = source_values.get("ragione_sociale") if isinstance(source_values, dict) else None
        legal_name = legal_name if isinstance(legal_name, str) and legal_name.strip() else normalized.get("name")
        if isinstance(legal_name, str) and legal_name.strip():
            assertions.append({"value": legal_name.strip(), "source_field": "ragione_sociale" if isinstance(source_values, dict) and source_values.get("ragione_sociale") else "name", "role": "legal"})
        fields = tuple((field, role) for field, role in fields if field == "facility_display_name")
    if source_id == "fr.georisques.icpe.animal":
        legal_name = source_values.get("raisonSociale") if isinstance(source_values, dict) else None
        if isinstance(legal_name, str) and legal_name.strip():
            assertions.append({"value": legal_name.strip(), "source_field": "raisonSociale", "role": "legal"})
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


def location_role(source_id: str, normalized: dict[str, Any], source_values: dict[str, Any] | None = None) -> str:
    raw = normalized.get("location_role")
    address_evidence = _has_address_evidence(normalized) or _has_address_evidence(source_values)
    address_state = normalized.get("address_state")
    if source_id == "us.aphis" and (
        isinstance(address_state, str) and "mailing" in address_state.casefold()
        or normalized.get("mailing_city") or normalized.get("location_evidence_role") == "mailing_locality_only_not_operating_site"
    ):
        return "mailing"
    if isinstance(raw, str) and raw in LOCATION_ROLES:
        role = LOCATION_ROLES[raw]
        return role if role != "operating" or address_evidence else "unknown"
    if source_id == "au.npi.facilities" and raw == "source-reported-facility-location":
        return "operating" if address_evidence else "unknown"
    if source_id in PREMISES_ADDRESS_SOURCES and address_evidence:
        return "operating"
    if _has_city_reference(normalized) or _has_city_reference(source_values):
        return "city_reference"
    return "unknown"


__all__ = ["FACILITY_IDENTIFIERS", "LOCATION_ROLES", "NAME_FIELDS", "PREMISES_ADDRESS_SOURCES",
           "additional_source_identifiers", "location_role", "name_assertions",
           "operator_asserted", "organization_identifiers", "source_identifier"]
