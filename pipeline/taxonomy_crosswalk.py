"""Versioned, source-aware projection from retained evidence to taxonomy v1.

This module deliberately consumes only already-retained normalized/source
fields. It does not fetch or infer facility identity. Source values remain
unchanged; callers persist the returned projection as derived data.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable

TAXONOMY_VERSION = "uec-taxonomy-v1"
# v7 adds the exact Géorisques ICPE animal-rubric projection without
# mutating earlier derived assignment sets.
CROSSWALK_VERSION = "uec-source-crosswalk-v7"
PRIMARY_PRECEDENCE = (
    "slaughter", "research_and_animal_use", "animal_keeping_and_production",
    "processing_and_preparation", "other_regulated_premises", "unclassified",
)
VALID_METHODS = {"direct", "derived", "candidate"}
VALID_STATUSES = {"mapped", "partial", "unmapped", "unclassified", "conflicting", "ambiguous"}

# Exact Denmark source codes and approval status come from the pinned local
# reviewed ruleset; review-required transition/status codes are not activities.
_DK_SOURCE = json.loads((Path(__file__).parent / "config" / "denmark-classification-v1.json").read_text(encoding="utf-8"))
_DK_LEAF_PRIMARY = {
    "slaughter": "slaughter", "meat_processing": "processing_and_preparation",
    "fish_processing": "processing_and_preparation", "dairy_processing": "processing_and_preparation",
    "egg_processing": "processing_and_preparation", "mixed_food_processing": "processing_and_preparation",
    "logistics_and_storage": "other_regulated_premises", "animal_products_adjacent": "other_regulated_premises",
    "general_food_business": "other_regulated_premises", "butcher_retail": "other_regulated_premises",
    "fish_retail": "other_regulated_premises", "retail_and_prepared_food": "other_regulated_premises",
    "commercial_food_business": "other_regulated_premises", "catering_and_institutional_kitchens": "other_regulated_premises",
    "food_contact_and_packaging": "other_regulated_premises",
}
_DK = {code: (rule["classification"], "direct")
       for rule in _DK_SOURCE["rules"] if rule.get("review_status") == "approved"
       and rule.get("classification") in _DK_LEAF_PRIMARY for code in rule["codes"]}
_NATIVE_V3 = json.loads((Path(__file__).parent / "config" / "source-taxonomy-v3.json").read_text(encoding="utf-8"))
_DE_SOURCE = json.loads((Path(__file__).parent / "config" / "germany-bltu-classification-v1.json").read_text(encoding="utf-8"))
_DE = {code: (rule["leaf_activity"], rule["primary_key"])
       for code, rule in _DE_SOURCE["rules"].items()}


def _crosswalk_version(source_id: str) -> str:
    return {
        "eu.eea.intensive-livestock": "eea-livestock-source-crosswalk-v2",
        "no.fiskeridir.aquaculture": "no-aquaculture-source-crosswalk-v2",
        "de.locations": "de-bltu-source-crosswalk-v1",
        "mx.locations": "mx-denue-source-crosswalk-v1",
        "nz.locations": "nz-mpi-rmp-source-crosswalk-v1",
    }.get(source_id, CROSSWALK_VERSION)
_LEAF_TO_PRIMARY = {
    "slaughter": "slaughter", "meat_processing": "processing_and_preparation",
    "fish_processing": "processing_and_preparation", "dairy_processing": "processing_and_preparation",
    "egg_processing": "processing_and_preparation", "cutting": "processing_and_preparation",
    "processing": "processing_and_preparation", "animal_keeping": "animal_keeping_and_production",
    "animal_production": "animal_keeping_and_production", "research": "research_and_animal_use",
    "animal_by_products": "other_regulated_premises", "logistics_and_storage": "other_regulated_premises",
    "butcher_retail": "other_regulated_premises",
    "export": "other_regulated_premises", "general_food_business": "other_regulated_premises",
    **_DK_LEAF_PRIMARY,
}
_OLD_CATEGORY = {
    "slaughter": "slaughter", "meat_processing": "processing_and_preparation",
    "fish_processing": "processing_and_preparation", "dairy_processing": "processing_and_preparation",
    "egg_processing": "processing_and_preparation", "cutting": "processing_and_preparation",
    "processing": "processing_and_preparation", "butcher_retail": "other_regulated_premises",
    "fish_retail": "other_regulated_premises", "logistics_and_storage": "other_regulated_premises",
    "animal_products_adjacent": "other_regulated_premises", "animal_by_products": "other_regulated_premises",
    "research": "research_and_animal_use", "animal_keeping": "animal_keeping_and_production",
}


def _values(obj: dict[str, Any], names: Iterable[str]) -> list[str]:
    result: list[str] = []
    for name in names:
        value = obj.get(name)
        values = value if isinstance(value, (list, tuple, set)) else [value]
        for item in values:
            if isinstance(item, (str, int, float)) and str(item).strip():
                text = str(item).strip()
                if text not in result:
                    result.append(text)
    return result


def _primary_for_leaf(leaf: str) -> str | None:
    return _LEAF_TO_PRIMARY.get(leaf)


def _first_evidence(normalized: dict[str, Any], original: dict[str, Any], names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for field in names:
        values = _values(normalized, (field,))
        if values:
            # Sort multi-value evidence only in this projection; the original
            # normalized/source_values fields retain their supplied ordering.
            return f"normalized.{field}", "; ".join(sorted(values))
    source_values = original.get("source_values") if isinstance(original.get("source_values"), dict) else {}
    for field in names:
        values = _values(source_values, (field,))
        if values:
            return f"source_values.{field}", "; ".join(sorted(values))
    return None, None


def _decision(source: str, normalized: dict[str, Any], original: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    codes = _values(normalized, ("activity_codes", "source_function_codes", "source_classification_codes", "source_classification_code", "activity_code", "source_category", "sector", "sector_code", "native_code", "primary_anzsic_class_code"))
    labels = _values(normalized, ("activity_descriptions", "activity_description", "activity_label", "source_activity", "source_classification_label", "activities", "processing_activities", "primary_anzsic_class_name"))
    # Some adapters intentionally retain exact evidence only in source_values.
    source_values = original.get("source_values") if isinstance(original.get("source_values"), dict) else {}
    if not codes:
        codes = _values(source_values, ("activity_code", "activity_codes", "lap_code", "pap_code", "source_function_code", "source_classification_code"))
    if not labels:
        labels = _values(source_values, ("activity_description", "activity", "activities", "category", "associated activities"))
    if source in {"fsa_approved_establishments", "fss_approved_establishments"} and not codes:
        codes = [value for value in _values(normalized, ("activities",))
                 if value.casefold() in {"sh", "cp", "mp", "cs"}]
        if not codes:
            codes = [value for value in _values(source_values, ("activities",))
                     if value.casefold() in {"sh", "cp", "mp", "cs"}]
    assignments: list[dict[str, str]] = []

    if source == "dk.smiley":
        for code in codes:
            if code in _DK:
                leaf, method = _DK[code]
                assignments.append({"leaf_activity": leaf, "primary": _primary_for_leaf(leaf) or "unclassified", "method": method})
    elif source == "de.locations":
        unknown = False
        seen_codes: set[str] = set()
        for code in codes:
            rule = _DE.get(code.upper())
            if rule:
                normalized_code = code.upper()
                if normalized_code not in seen_codes:
                    assignments.append({"leaf_activity": rule[0], "primary": rule[1], "method": "direct",
                                        "source_code_reference": "normalized.activity_codes",
                                        "source_code": normalized_code,
                                        "source_label_reference": "crosswalk.annex_v_activity_code",
                                        "source_label": _DE_SOURCE["rules"][normalized_code]["source_label"]})
                    seen_codes.add(normalized_code)
            else:
                unknown = True
        return assignments, ("partial" if assignments and unknown else
                             "mapped" if assignments else "unmapped" if codes else "unclassified")
    elif source == "eu.eea.intensive-livestock":
        if normalized.get("source_activity") == "Livestock" and normalized.get("source_reporting_year") == 2024:
            assignments.append({"leaf_activity": "animal_production",
                                "primary": "animal_keeping_and_production", "method": "direct",
                                "source_code_reference": "normalized.source_activity",
                                "source_code": "Livestock", "source_label_reference": "normalized.source_activity",
                                "source_label": "Livestock"})
    elif source == "no.fiskeridir.aquaculture":
        # A non-empty species scope plus the adapter's animal-only category
        # confirms aquaculture production. Use the existing animal-production
        # leaf, not a new display category or a status-derived inference.
        categories = _values(normalized, ("activity_categories",))
        species_scope = _values(normalized, ("source_species_scope",))
        if "animal-aquaculture" in categories and species_scope:
            assignments.append({"leaf_activity": "animal_production",
                                "primary": "animal_keeping_and_production", "method": "derived"})
    elif source == "gb.scot.marine.aquaculture":
        # The source adapter retains only finfish/shellfish production sites;
        # fisheries are excluded upstream. This maps activity, not status.
        categories = _values(normalized, ("activity_categories",))
        if any(category in {"animal-aquaculture-finfish", "animal-aquaculture-shellfish"}
               for category in categories):
            assignments.append({"leaf_activity": "animal_production",
                                "primary": "animal_keeping_and_production", "method": "derived"})
    elif source == "us.epa.echo-animal-production":
        # Native industry classifications scope the records; CWA association
        # alone does not establish CAFO status or current operation.
        basis = normalized.get("industry_classification_basis")
        naics = _values(basis, ("naics_codes",)) if isinstance(basis, dict) else []
        sics = _values(basis, ("sic_codes",)) if isinstance(basis, dict) else []
        matched_naics = [code for code in naics if len(code) == 6 and code.startswith("112") and code.isdigit()]
        from pipeline.sources.us.epa_echo.acquire import SIC_CODES
        matched_sics = [code for code in sics if code in SIC_CODES]
        if matched_naics or matched_sics:
            assignments.append({"leaf_activity": "animal_production",
                                "primary": "animal_keeping_and_production", "method": "direct"})
    elif source == "mx.locations":
        # DENUE's native SCIAN class is the direct classification basis.
        # Names and free text never create an activity assignment.
        code = normalized.get("activity_class_id")
        code_reference = "normalized.activity_class_id"
        if code is None:
            code = source_values.get("CLASE_ACTIVIDAD_ID")
            code_reference = "source_values.CLASE_ACTIVIDAD_ID"
        mx_rules = {
            "311611": ("slaughter", "slaughter"),
            "311612": ("processing", "processing_and_preparation"),
            "311613": ("processing", "processing_and_preparation"),
            "311614": ("processing", "processing_and_preparation"),
        }
        matched_codes = _values({"activity_class_id": code}, ("activity_class_id",))
        unknown_codes = []
        for value in sorted(set(matched_codes)):
            rule = mx_rules.get(value)
            if rule:
                assignments.append({"leaf_activity": rule[0], "primary": rule[1], "method": "direct",
                                    "source_code_reference": code_reference, "source_code": value})
            else:
                unknown_codes.append(value)
        if matched_codes:
            return assignments, ("partial" if assignments and unknown_codes else "mapped" if assignments else "unmapped")
    elif source == "nz.locations":
        # MPI labels classify only activities explicitly stated by the export.
        # RMPs can cover multiple locations and are not one-to-one facilities.
        import re
        nz_fields = (
            ("normalized.programme_type", normalized.get("programme_type") or source_values.get("Programme Type")),
            ("normalized.primary_activity", normalized.get("primary_activity") or source_values.get("Primary")),
            ("normalized.secondary_activity", normalized.get("secondary_activity") or source_values.get("Secondary Process")),
            ("normalized.product_material", normalized.get("product_material") or source_values.get("Product/Material")),
        )
        nz_rules = (
            (re.compile(r"\b(?:micro\s*)?abattoirs?\b|\bslaughter(?:ing|houses?)?\b", re.I),
             "slaughter", "slaughter"),
            (re.compile(r"\bchicken\s+producers?\b|\bfarm\s+dair(?:y|ies)\b|\begg\s+production\b", re.I),
             "animal_production", "animal_keeping_and_production"),
            (re.compile(r"(?=.*\b(?:bee|honey|meat|dairy|fish|seafood)\b)(?=.*\bprocessing\b)", re.I),
             "processing", "processing_and_preparation"),
            (re.compile(r"\b(?:storage|stores?|transport|transportation)\b", re.I),
             "logistics_and_storage", "other_regulated_premises"),
            (re.compile(r"\bdual\s+operator\s+butchers?\b", re.I),
             "butcher_retail", "other_regulated_premises"),
        )
        evidence: dict[tuple[str, str, str], list[tuple[str, str]]] = {}
        material_pattern = re.compile(r"\b(?:bee|honey|meat|dairy|fish|seafood)\b", re.I)
        processing_word = re.compile(r"\bprocessing\b", re.I)
        material_evidence: list[tuple[str, str]] = []
        process_evidence: list[tuple[str, str]] = []
        for field, raw_value in nz_fields:
            values = raw_value if isinstance(raw_value, (list, tuple, set)) else [raw_value]
            for raw in values:
                value = str(raw).strip() if raw is not None else ""
                if not value:
                    continue
                if material_pattern.search(value):
                    material_evidence.append((field, value))
                if processing_word.search(value):
                    process_evidence.append((field, value))
                for pattern, leaf, primary in nz_rules:
                    if pattern.search(value):
                        key = (leaf, primary, "derived")
                        pair = (field, value)
                        evidence.setdefault(key, [])
                        if pair not in evidence[key]:
                            evidence[key].append(pair)
        if material_evidence and process_evidence:
            key = ("processing", "processing_and_preparation", "derived")
            evidence.setdefault(key, [])
            for pair in material_evidence + process_evidence:
                if pair not in evidence[key]:
                    evidence[key].append(pair)
        for (leaf, primary, method), matches in sorted(evidence.items()):
            assignments.append({
                "leaf_activity": leaf, "primary": primary, "method": method,
                "source_label_reference": "; ".join(field for field, _ in matches),
                "source_label": "; ".join(value for _, value in matches),
            })
        has_labels = any(str(value or "").strip() for _, value in nz_fields)
        return assignments, ("mapped" if assignments else "unmapped" if has_labels else "unclassified")
    elif source == "be.locations":
        # Adapter output is produced only after the reviewed PAP signature
        # matched the exact place/activity/product tuple in the pinned codebook.
        # The normalized candidate handoff retains the exact-allowlisted
        # categories as activity_categories; source_activity_categories is
        # present only in the richer source artifact. Both carry the same
        # exact codebook-derived evidence for this adapter.
        categories = _values(normalized, ("source_activity_categories", "activity_categories"))
        recognized = 0
        for category in categories:
            leaf = {"slaughter": "slaughter", "cutting": "cutting", "processing": "processing",
                    "animal_by_products": "animal_by_products", "logistics_and_storage": "logistics_and_storage"}.get(category)
            if leaf:
                assignments.append({"leaf_activity": leaf, "primary": _primary_for_leaf(leaf) or "unclassified", "method": "direct"})
                recognized += 1
        if assignments and recognized < len(categories):
            return assignments, "partial"
    elif source == "us.fsis":
        # Structured FSIS activity columns are source fields, not inspection
        # system attributes. The user-approved roster projection is exhaustive:
        # any affirmative slaughter value takes precedence; every other roster
        # row is a processing candidate. Native flags remain source evidence.
        def affirmative(values: Any) -> bool:
            return isinstance(values, dict) and any(str(value).strip().casefold() in {"yes", "y", "true", "1"}
                                                    for value in values.values())
        if affirmative(normalized.get("species_slaughtered")):
            assignments.append({"leaf_activity": "slaughter", "primary": "slaughter", "method": "direct"})
        elif normalized.get("establishment_id") or normalized.get("establishment_number"):
            assignments.append({"leaf_activity": "processing", "primary": "processing_and_preparation", "method": "direct"})
    elif source == "us.aphis":
        # Exact APHIS classes are source classifications, not inferences from
        # names, mailing locations, or associated evidence rows.
        aphis_classes = {
            "Class A": ("animal_keeping", "animal_keeping_and_production"),
            "Class R": ("research", "research_and_animal_use"),
            "Class F": ("research", "research_and_animal_use"),
            "Class G": ("research", "research_and_animal_use"),
            "Class V": ("research", "research_and_animal_use"),
            "Class B": ("general_food_business", "other_regulated_premises"),
            "Class C": ("general_food_business", "other_regulated_premises"),
            "Class H": ("general_food_business", "other_regulated_premises"),
            "Class T": ("general_food_business", "other_regulated_premises"),
        }
        mapped = aphis_classes.get(normalized.get("aphis_registration_class"))
        if mapped:
            assignments.append({"leaf_activity": mapped[0], "primary": mapped[1], "method": "direct"})
    elif source == "fr.georisques.icpe.animal":
        rubric_rules = {
            **{code: ("animal_keeping", "animal_keeping_and_production") for code in
               ("2101", "2102", "2110", "2111", "2112", "2113", "2120", "2130", "2140", "2150", "3660")},
            "2210": ("slaughter", "slaughter"), "3641": ("slaughter", "slaughter"),
            "2221": ("processing", "processing_and_preparation"),
            "2230": ("processing", "processing_and_preparation"),
        }
        for code in codes:
            rule = rubric_rules.get(code)
            if rule:
                assignments.append({"leaf_activity": rule[0], "primary": rule[1], "method": "direct"})
        return assignments, ("mapped" if assignments else "unmapped" if codes else "unclassified")
    elif source in {"it.853-2004", "es.cat.feed-sandach"}:
        rules = _NATIVE_V3[source]
        unknown = False
        for code in codes:
            rule = rules.get(code.upper())
            if rule:
                assignments.append({"leaf_activity": rule[0], "primary": rule[1], "method": "direct"})
            else:
                unknown = True
        return assignments, ("partial" if assignments and unknown else "mapped" if assignments else "unmapped" if codes else "unclassified")
    elif source == "it.1069-2009":
        return [], "unmapped" if codes else "unclassified"
    elif source.startswith("au."):
        rules = _NATIVE_V3.get(source, {})
        for code in codes:
            rule = rules.get(code)
            if rule:
                assignments.append({"leaf_activity": rule[0], "primary": rule[1], "method": "derived"})
        return assignments, ("mapped" if assignments else "unmapped" if codes or labels else "unclassified")
    elif source in {"fr.dgal.section-i", "fr.dgal.section-ii"}:
        text = " ".join(codes + labels).upper()
        import re
        # Exact SH and CP tokens are source codes; text rules remain derived.
        if re.search(r"(?<![A-Z0-9])SH(?![A-Z0-9])", text):
            assignments.append({"leaf_activity": "slaughter", "primary": "slaughter", "method": "direct"})
        if re.search(r"(?<![A-Z0-9])CP(?![A-Z0-9])", text):
            assignments.append({"leaf_activity": "cutting", "primary": "processing_and_preparation", "method": "direct"})
        for pattern, leaf, primary in ((r"\b(?:ABAT|ABATTAGE|SLAUGHT)\w*\b", "slaughter", "slaughter"),
                                       (r"\b(?:CUT|DECOUPE|DÉCOUPE)\w*\b", "cutting", "processing_and_preparation"),
                                       (r"\b(?:TRANSFORM|PROCESS|PREPAR|PRÉPAR)\w*\b", "processing", "processing_and_preparation")):
            if re.search(pattern, text) and not any(a["leaf_activity"] == leaf for a in assignments):
                assignments.append({"leaf_activity": leaf, "primary": primary, "method": "derived"})
    elif source.startswith("uk.") or source in {"fsa_approved_establishments", "fss_approved_establishments"}:
        # Existing controlled UK activity labels are heuristics. Require whole
        # words to avoid accidental substring matches such as "fresh" -> fish.
        import re
        rules = ((r"\bslaughter(?:house)?\b", "slaughter", "slaughter"),
                 (r"\b(?:cutting|boning)\b", "cutting", "processing_and_preparation"),
                 (r"\b(?:processing|preparation|packing)\b", "processing", "processing_and_preparation"))
        fsa_monthly_labels = {
            "packing centre (egg)": ("processing", "processing_and_preparation"),
            "liquid egg plant": ("processing", "processing_and_preparation"),
            "re-wrappingand repackaging establishment": ("processing", "processing_and_preparation"),
            "factory vessel (fish)": ("processing", "processing_and_preparation"),
            "fresh fishery products plant": ("processing", "processing_and_preparation"),
            "mince meat establishment": ("processing", "processing_and_preparation"),
            "game handling establishment": ("processing", "processing_and_preparation"),
            "mechanically separated meat establishment": ("processing", "processing_and_preparation"),
            "dispatch centre (lbm)": ("logistics_and_storage", "other_regulated_premises"),
            "purification centre (lbm)": ("logistics_and_storage", "other_regulated_premises"),
            "auction hall (fish)": ("logistics_and_storage", "other_regulated_premises"),
            "wholesale market (fish)": ("logistics_and_storage", "other_regulated_premises"),
            "collection centre (dairy)": ("logistics_and_storage", "other_regulated_premises"),
        }
        uk_exact_labels = {
            "sh": ("slaughter", "slaughter"),
            "cp": ("cutting", "processing_and_preparation"),
            "mp": ("processing", "processing_and_preparation"),
            "cs": ("logistics_and_storage", "other_regulated_premises"),
        }
        unresolved_labels = 0
        for label in labels:
            matched = False
            normalized_label = re.sub(r"\s+", " ", label).strip().casefold()
            monthly = fsa_monthly_labels.get(normalized_label) if source == "fsa_approved_establishments" else None
            exact_code = uk_exact_labels.get(normalized_label)
            if monthly or exact_code:
                leaf, primary = monthly or exact_code
                assignments.append({"leaf_activity": leaf, "primary": primary, "method": "derived"})
                matched = True
            for pattern, leaf, primary in rules:
                if not monthly and re.search(pattern, label, re.I):
                    assignments.append({"leaf_activity": leaf, "primary": primary, "method": "derived"})
                    matched = True
            if not matched:
                unresolved_labels += 1
        if assignments and unresolved_labels:
            return assignments, "partial"
    elif source in {"ca.cfia.federal-meat", "ca.ontario.meat-plants", "ca.cfia"}:
        # CFIA adapter has a pinned numbered function-key mapping. Honor only
        # explicit slot/value signatures emitted in source_function_codes;
        # ordinary category labels remain derived.
        import re
        encoded = " ".join(codes)
        function_targets = {
            "codes1": (set("abcdefghij"), "slaughter", "slaughter"),
            "codes2": (set("fxg"), "processing", "processing_and_preparation"),
            "codes3": (set("fxg"), "cutting", "processing_and_preparation"),
            "code4": ({"y"}, "processing", "processing_and_preparation"),
            "code5": ({"y"}, "processing", "processing_and_preparation"),
            "codes6": (set("fxg"), "processing", "processing_and_preparation"),
            "code7": ({"y"}, "logistics_and_storage", "other_regulated_premises"),
            "code8": ({"y"}, "processing", "processing_and_preparation"),
            "codes10": (set("ab"), "logistics_and_storage", "other_regulated_premises"),
        }
        direct_seen = False
        for match in re.finditer(r"\b(codes?[_ ]?(?:1|2|3|6|9|10)|code[_ ]?(?:4|5|7|8))\s*[=:]\s*([a-z]+)\b", encoded, re.I):
            slot = re.sub(r"[^a-z0-9]", "", match.group(1).casefold())
            value = match.group(2).casefold()
            expected = function_targets.get(slot)
            if expected and value in expected[0]:
                leaf, primary = expected[1], expected[2]
                assignments.append({"leaf_activity": leaf, "primary": primary, "method": "direct"})
                direct_seen = True
        categories = _values(normalized, ("activity_categories",))
        if not direct_seen:
            for category in categories:
                primary = _OLD_CATEGORY.get(category)
                if primary:
                    leaf = category if category in _LEAF_TO_PRIMARY else "processing"
                    assignments.append({"leaf_activity": leaf, "primary": primary, "method": "derived"})
        if not assignments and not direct_seen:
            text = " ".join(labels).casefold()
            if re.search(r"\b(?:slaughter|abattoir|slaughterhouse)\b", text):
                assignments.append({"leaf_activity": "slaughter", "primary": "slaughter", "method": "derived"})
            if re.search(r"\b(?:processing|cutting|packing)\b", text):
                assignments.append({"leaf_activity": "processing", "primary": "processing_and_preparation", "method": "derived"})
    else:
        # A controlled adapter's existing categories can be preserved as
        # source labels but are not elevated to confirmed classification.
        categories = _values(normalized, ("activity_categories",))
        if categories:
            return [], "unclassified"

    # Classify event-only datasets as non-activities even if labels contain
    # terms such as inspection, recall, enforcement, or investigation.
    import re
    event_words = ("inspection", "enforcement", "recall", "investigation")
    event_only = (source.endswith((".inspections", ".recalls", ".enforcement", ".investigations"))
                  or any(re.search(rf"\b{word}\b", label, re.I) for word in event_words for label in labels))
    if event_only:
        assignments = []
        return assignments, "unclassified"
    identities = {(item["leaf_activity"], item["primary"], item["method"]) for item in assignments}
    assignments = [{"leaf_activity": leaf, "primary": primary, "method": method}
                   for leaf, primary, method in sorted(identities)]
    if not assignments:
        return [], "unmapped" if codes or labels else "unclassified"
    methods = {item["method"] for item in assignments}
    if len({item["primary"] for item in assignments}) > 1 and len(methods) > 1:
        return assignments, "conflicting"
    return assignments, "mapped" if not (codes and source == "dk.smiley" and any(c not in _DK for c in codes)) else "partial"


def project_observation(record: dict[str, Any]) -> dict[str, Any]:
    """Return stable derived fields without changing source evidence."""
    source = str(record.get("source_id") or "")
    normalized = record.get("normalized") if isinstance(record.get("normalized"), dict) else {}
    source_values = record.get("source_values") if isinstance(record.get("source_values"), dict) else {}
    assignments, status = _decision(source, normalized, record)
    primaries = sorted({a["primary"] for a in assignments if a["primary"] != "unclassified"},
                       key=lambda value: (PRIMARY_PRECEDENCE.index(value), value))
    methods = {a["method"] for a in assignments}
    if len(methods) > 1 and status == "mapped":
        status = "partial"
    if not assignments and status not in VALID_STATUSES:
        status = "unclassified"
    display = next((value for value in PRIMARY_PRECEDENCE if value in primaries), "unclassified")
    code_reference, source_code = _first_evidence(normalized, record,
        ("activity_codes", "source_function_codes", "source_classification_codes", "source_classification_code", "activity_code", "source_category", "primary_anzsic_class_code"))
    if source == "us.epa.echo-animal-production" and source_code is None:
        basis = normalized.get("industry_classification_basis")
        if isinstance(basis, dict):
            native_codes = _values(basis, ("naics_codes", "sic_codes"))
            if native_codes:
                code_reference = "normalized.industry_classification_basis"
                source_code = "; ".join(sorted(native_codes))
    if source in {"fsa_approved_establishments", "fss_approved_establishments"} and source_code is None:
        uk_codes = [value for value in _values(normalized, ("activities",))
                    if value.casefold() in {"sh", "cp", "mp", "cs"}]
        if not uk_codes:
            uk_codes = [value for value in _values(source_values, ("activities",))
                        if value.casefold() in {"sh", "cp", "mp", "cs"}]
        if uk_codes:
            code_reference = "normalized.activities" if _values(normalized, ("activities",)) else "source_values.activities"
            source_code = "; ".join(sorted(uk_codes))
    label_reference, source_label = _first_evidence(normalized, record,
        ("activity_descriptions", "activity_description", "activity_label", "source_activity", "source_classification_label", "activities", "primary_anzsic_class_name"))
    # Keep explicit rule evidence references with every assignment. Adapter
    # outputs can carry multiple source codes; the assignment stores the exact
    # source field path and its original scalar, while source_values remains
    # untouched on the observation.
    enriched = []
    for assignment in assignments:
        item = dict(assignment)
        item.setdefault("source_code_reference", code_reference)
        item.setdefault("source_code", source_code)
        item.setdefault("source_label_reference", label_reference)
        item.setdefault("source_label", source_label)
        enriched.append(item)
    crosswalk_version = _crosswalk_version(source)
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "crosswalk_version": crosswalk_version,
        "ruleset_version": crosswalk_version,
        "taxonomy_assignments": enriched,
        "taxonomy_primaries": primaries,
        "taxonomy_mapping_method": next(iter(methods)) if len(methods) == 1 else (
            "direct" if source in {"dk.smiley", "be.locations", "de.locations", "us.fsis", "us.epa.echo-animal-production", "fr.georisques.icpe.animal", "mx.locations"} or source.startswith(("it.", "es.")) else
            "candidate" if source.startswith("au.") else "derived"),
        "taxonomy_mapping_status": status,
        "taxonomy_display_category": display,
    }


def crosswalk_document(source_id: str) -> dict[str, Any]:
    """Small persistence-ready description of the source rule authority."""
    rules: list[dict[str, Any]] = []
    if source_id == "dk.smiley":
        for code, (leaf, method) in sorted(_DK.items()):
            rules.append({"source_code": code, "leaf_key": leaf, "primary_key": _primary_for_leaf(leaf), "mapping_method": method})
    elif source_id == "de.locations":
        for code, rule in sorted(_DE_SOURCE["rules"].items()):
            rules.append({"source_code": code, "source_label": rule["source_label"],
                          "source_field": "EU Commission Technical Specifications Annex V",
                          "leaf_key": rule["leaf_activity"],
                          "primary_key": rule["primary_key"], "mapping_method": "direct"})
    elif source_id == "be.locations":
        rules = [{"source_field": "activity_codes", "signature": "exact LAP/PAP place+activity+product codebook tuple",
                  "leaf_key": "source_activity_category", "mapping_method": "direct"}]
    elif source_id == "eu.eea.intensive-livestock":
        rules = [{"source_field": "normalized.source_activity", "source_label": "Livestock",
                  "reporting_year": 2024, "leaf_key": "animal_production",
                  "primary_key": "animal_keeping_and_production", "mapping_method": "direct"}]
    elif source_id == "no.fiskeridir.aquaculture":
        rules = [{"source_field": "normalized.activity_categories", "source_label": "animal-aquaculture",
                  "requires_nonempty_field": "normalized.source_species_scope", "leaf_key": "animal_production",
                  "primary_key": "animal_keeping_and_production", "mapping_method": "derived"}]
    elif source_id == "us.fsis":
        rules = [{"source_field": "species_slaughtered", "leaf_key": "slaughter", "primary_key": "slaughter", "mapping_method": "direct"},
                 {"source_field": "processing_activities", "leaf_key": "processing", "primary_key": "processing_and_preparation", "mapping_method": "direct"}]
    elif source_id == "us.aphis":
        rules = [
            {"source_field": "aphis_registration_class", "source_label": "Class A", "leaf_key": "animal_keeping", "primary_key": "animal_keeping_and_production", "mapping_method": "direct"},
            *[{"source_field": "aphis_registration_class", "source_label": f"Class {code}", "leaf_key": "research", "primary_key": "research_and_animal_use", "mapping_method": "direct"} for code in ("R", "F", "G", "V")],
            *[{"source_field": "aphis_registration_class", "source_label": f"Class {code}", "leaf_key": "general_food_business", "primary_key": "other_regulated_premises", "mapping_method": "direct"} for code in ("B", "C", "H", "T")],
        ]
    elif source_id == "gb.scot.marine.aquaculture":
        rules = [{"source_field": "activity_categories", "source_label": label,
                  "leaf_key": "animal_production", "primary_key": "animal_keeping_and_production",
                  "mapping_method": "derived"}
                 for label in ("animal-aquaculture-finfish", "animal-aquaculture-shellfish")]
    elif source_id == "us.epa.echo-animal-production":
        rules = [{"source_field": "industry_classification_basis.naics_codes", "source_code_prefix": "112",
                  "leaf_key": "animal_production", "primary_key": "animal_keeping_and_production", "mapping_method": "direct"},
                 {"source_field": "industry_classification_basis.sic_codes", "source_code_set": "EPA selected livestock/poultry SIC codes",
                  "leaf_key": "animal_production", "primary_key": "animal_keeping_and_production", "mapping_method": "direct"}]
    elif source_id == "mx.locations":
        rules = [
            {"source_field": "normalized.activity_class_id", "source_code": "311611", "leaf_key": "slaughter", "primary_key": "slaughter", "mapping_method": "direct"},
            *[{"source_field": "normalized.activity_class_id", "source_code": code, "leaf_key": "processing", "primary_key": "processing_and_preparation", "mapping_method": "direct"}
              for code in ("311612", "311613", "311614")],
        ]
    elif source_id == "nz.locations":
        rules = [
            {"source_field": "Programme Type / Primary / Secondary Process / Product/Material", "source_label": "whole-word micro abattoir or slaughter", "leaf_key": "slaughter", "primary_key": "slaughter", "mapping_method": "derived"},
            {"source_field": "Programme Type / Primary / Secondary Process / Product/Material", "source_label": "whole-word chicken producers, farm dairies, or egg production", "leaf_key": "animal_production", "primary_key": "animal_keeping_and_production", "mapping_method": "derived"},
            {"source_field": "Product/Material / Programme Type plus Primary / Secondary Process", "source_label": "whole-word bee, honey, meat, dairy, fish, or seafood material and whole-word processing", "leaf_key": "processing", "primary_key": "processing_and_preparation", "mapping_method": "derived"},
            {"source_field": "Programme Type / Primary / Secondary Process / Product/Material", "source_label": "whole-word storage, store, or transport", "leaf_key": "logistics_and_storage", "primary_key": "other_regulated_premises", "mapping_method": "derived"},
            {"source_field": "Programme Type / Primary / Secondary Process / Product/Material", "source_label": "whole-word dual operator butcher", "leaf_key": "butcher_retail", "primary_key": "other_regulated_premises", "mapping_method": "derived"},
        ]
    elif source_id == "fr.georisques.icpe.animal":
        rules = [
            *[{"source_code": code, "leaf_key": "animal_keeping", "primary_key": "animal_keeping_and_production", "mapping_method": "direct"}
              for code in ("2101", "2102", "2110", "2111", "2112", "2113", "2120", "2130", "2140", "2150", "3660")],
            *[{"source_code": code, "leaf_key": "slaughter", "primary_key": "slaughter", "mapping_method": "direct"} for code in ("2210", "3641")],
            *[{"source_code": code, "leaf_key": "processing", "primary_key": "processing_and_preparation", "mapping_method": "direct"} for code in ("2221", "2230")],
        ]
    elif source_id in {"fr.dgal.section-i", "fr.dgal.section-ii"}:
        rules = [{"source_code": "SH", "leaf_key": "slaughter", "primary_key": "slaughter", "mapping_method": "direct"},
                 {"source_code": "CP", "leaf_key": "cutting", "primary_key": "processing_and_preparation", "mapping_method": "direct"},
                 {"source_field": "source_activity", "leaf_key": "label-derived activity", "mapping_method": "derived"}]
    elif source_id in {"fsa_approved_establishments", "fss_approved_establishments"}:
        rules = [
            {"source_field": "activities", "source_label": "SH", "leaf_key": "slaughter", "primary_key": "slaughter", "mapping_method": "derived"},
            {"source_field": "activities", "source_label": "CP", "leaf_key": "cutting", "primary_key": "processing_and_preparation", "mapping_method": "derived"},
            {"source_field": "activities", "source_label": "MP", "leaf_key": "processing", "primary_key": "processing_and_preparation", "mapping_method": "derived"},
            {"source_field": "activities", "source_label": "CS", "leaf_key": "logistics_and_storage", "primary_key": "other_regulated_premises", "mapping_method": "derived"},
            {"source_field": "activities", "source_label": "whole-word slaughter or slaughterhouse", "leaf_key": "slaughter", "primary_key": "slaughter", "mapping_method": "derived"},
            {"source_field": "activities", "source_label": "whole-word cutting or boning", "leaf_key": "cutting", "primary_key": "processing_and_preparation", "mapping_method": "derived"},
            {"source_field": "activities", "source_label": "whole-word processing, preparation, or packing", "leaf_key": "processing", "primary_key": "processing_and_preparation", "mapping_method": "derived"},
        ]
    elif source_id.startswith("ca."):
        rules = [{"source_field": "source_function_codes", "leaf_key": "CFIA numbered function signature when present", "mapping_method": "direct"},
                 {"source_field": "activity_categories", "leaf_key": "source activity category", "mapping_method": "derived"}]
    elif source_id.startswith(("it.", "es.")):
        rules = [{"source_field": "source values", "primary_key": "unclassified", "mapping_method": "direct",
                  "mapping_status": "unclassified"}]
    elif source_id.startswith("au."):
        rules = [{"source_field": "source-native activity", "primary_key": "unclassified", "mapping_method": "candidate"}]
    else:
        rules = [{"source_field": "unsupported", "primary_key": "unclassified", "mapping_method": "candidate"}]
    normalized_rules: list[dict[str, Any]] = []
    for rule in rules:
        method = rule.get("mapping_method", "candidate")
        codes = [rule["source_code"]] if rule.get("source_code") else []
        labels = [rule["source_label"]] if rule.get("source_label") else []
        fields = [rule["source_field"]] if rule.get("source_field") else []
        if not (codes or labels or fields):
            fields = ["source values"]
        primary = rule.get("primary_key")
        leaf = rule.get("leaf_key")
        if primary is None and leaf in _LEAF_TO_PRIMARY:
            primary = _LEAF_TO_PRIMARY[leaf]
        if method == "candidate":
            primary, status, leaf = "unclassified", "ambiguous", None
        elif primary in (None, "unclassified"):
            primary, status, leaf = "unclassified", "unclassified", None
        else:
            status = rule.get("mapping_status", "mapped")
        normalized_rules.append({
            "source_codes": codes,
            "source_labels": labels,
            "source_fields": fields,
            "primary_keys": [primary],
            "leaf_key": leaf,
            "method": method,
            "status": status,
            "source_code_reference": rule.get("signature"),
            "source_label_reference": rule.get("source_field"),
        })
    crosswalk_version = _crosswalk_version(source_id)
    return {"source_id": source_id, "taxonomy_version": TAXONOMY_VERSION,
            "crosswalk_version": crosswalk_version, "ruleset_version": crosswalk_version, "rules": normalized_rules}


def persistence_assignments(projected: dict[str, Any]) -> list[dict[str, Any]]:
    """Adapt the lane projection to Lane 1's append-only assignment row shape.

    This is a serialization boundary only: it does not write or duplicate the
    database migration. Integration can pass these rows to the shared
    ``pipeline.taxonomy`` canonicalization and assignment-set writer.
    """
    rows = []
    source_assignments = list(projected.get("taxonomy_assignments", ()))
    if not source_assignments:
        status = projected.get("taxonomy_mapping_status", "unclassified")
        method = projected.get("taxonomy_mapping_method", "derived")
        if method == "candidate" and status != "ambiguous":
            method = "derived"
        source_assignments = [{"primary": "unclassified", "leaf_activity": None, "method": method}]
    status = projected.get("taxonomy_mapping_status", "unclassified")
    for ordinal, item in enumerate(source_assignments, 1):
        primary = item["primary"]
        leaf = item.get("leaf_activity")
        method = item.get("method", projected.get("taxonomy_mapping_method", "derived"))
        if status in {"unmapped", "unclassified", "conflicting", "ambiguous"}:
            primary, leaf = "unclassified", None
        if method == "candidate" and (primary != "unclassified" or status != "ambiguous"):
            method = "derived"
        rows.append({
            "assignment_ordinal": ordinal,
            "primary_key": primary,
            "leaf_key": leaf,
            "leaf_label": leaf,
            "source_code_reference": item.get("source_code_reference"),
            "source_label_reference": item.get("source_label_reference"),
            "source_code": item.get("source_code"),
            "source_label": item.get("source_label"),
            "mapping_method": method,
            "mapping_status": status,
        })
    return rows


def reproject(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Project records deterministically and return privacy-safe aggregates."""
    output = []
    counts: dict[str, Counter[str]] = {key: Counter() for key in ("source", "primary", "method", "status", "display_change")}
    for record in records:
        derived = project_observation(record)
        updated = dict(record)
        # Derived namespace only. Preserve all source/evidence/normalized data.
        updated["taxonomy"] = derived
        output.append(updated)
        source = str(record.get("source_id") or "unknown")
        counts["source"][source] += 1
        counts["status"][derived["taxonomy_mapping_status"]] += 1
        counts["method"][derived["taxonomy_mapping_method"]] += 1
        for primary in derived["taxonomy_primaries"] or ["unclassified"]:
            counts["primary"][primary] += 1
        prior = record.get("taxonomy", {}).get("taxonomy_display_category") if isinstance(record.get("taxonomy"), dict) else None
        display_state = "new" if prior is None else "unchanged" if prior == derived["taxonomy_display_category"] else "changed"
        counts["display_change"][display_state] += 1
    # Sorting by stable source key ensures row order cannot affect projection
    # or aggregate counts; output itself retains the input order.
    report = {name: dict(sorted(counter.items())) for name, counter in counts.items()}
    report["records"] = len(output)
    report["taxonomy_version"] = TAXONOMY_VERSION
    return output, report
