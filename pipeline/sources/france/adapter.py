"""Private, provenance-preserving adapters for France's DGAL 853/2004 lists."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.common.review import write_operator_review_packet
from pipeline.common.tabular import TabularSchemaError, occurrence_key, read_rows, resolve_mapping, row_identity, value
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest


ALIASES = {
    "department_number": ("department number", "department", "n departement", "numero departement", "code departement", "numero de département"),
    "approval_number": ("approval number", "approval no", "n dagrement", "numero dagrement", "num dagrement", "agrément", "agrement", "numéro agrément/approval number"),
    "siret": ("siret", "siret number"),
    "legal_name": ("legal name", "company name", "raison sociale", "nom de letablissement", "nom de l'etablissement", "establishment name", "raison sociale - enseigne commerciale/name"),
    "address": ("address", "adresse", "location address"),
    "postal_code": ("postal code", "code postal", "postcode", "code postal/postal code"),
    "commune": ("commune", "municipality", "city", "town", "commune/town"),
    "category": ("category", "categorie", "catégorie", "establishment category", "catégorie/category"),
    "associated_activities": ("associated activities", "activites associees", "activités associées", "activities", "activity", "activités associées/associated activities"),
    "species": ("species", "especes", "espèces", "animal species", "espèce/specy"),
}
REQUIRED = ("approval_number", "legal_name", "commune", "category")


def _clean(raw: str | None) -> str | None:
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _categories(category: str | None, activities: str | None) -> tuple[tuple[str, ...], bool]:
    text = " ".join(item for item in (category, activities) if item).upper()
    categories: list[str] = []
    if any(token in text for token in ("SH", "ABAT", "SLAUGHT", "ABATTAGE")):
        categories.append("slaughter")
    if any(token in text for token in ("CP", "CUT", "DECOUPE", "DÉCOUPE")):
        categories.append("cutting")
    if any(token in text for token in ("TRANSFORM", "PROCESS", "PREPAR", "PRÉPAR")):
        categories.append("processing")
    if any(token in text for token in ("ENTREP", "STOCK", "STORAGE")):
        categories.append("logistics_and_storage")
    return tuple(dict.fromkeys(categories)), bool(categories)


class FranceDgalAdapter:
    """One adapter instance represents exactly one DGAL section/source."""

    def __init__(self, source_id: str, section: str, source_url: str) -> None:
        if section not in {"I", "II"}:
            raise ValueError("DGAL section must be I or II")
        self.source_id, self.section, self.source_url = source_id, section, source_url
        self.adapter_version = "fr-dgal-853-v1"
        self.schema_version = "fr-dgal-853-txt-v1"

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        headers, rows, delimiter, schema_fingerprint = read_rows(content, ALIASES, required=REQUIRED)
        mapping = resolve_mapping(headers, ALIASES)
        occurrences: Counter[tuple[str | None, ...]] = Counter()
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        for line, row in enumerate(rows, 2):
            approval, category = _clean(value(row, mapping, "approval_number")), _clean(value(row, mapping, "category"))
            activities = _clean(value(row, mapping, "associated_activities"))
            key = occurrence_key(row, mapping, ("approval_number", "category", "associated_activities", "species"))
            occurrences[key] += 1
            reasons: list[str] = []
            if not approval: reasons.append("missing_approval_number")
            if not _clean(value(row, mapping, "legal_name")): reasons.append("missing_establishment_name")
            if not _clean(value(row, mapping, "commune")): reasons.append("missing_commune")
            if not category: reasons.append("missing_category")
            categories, recognized = _categories(category, activities)
            if not recognized: reasons.append("unknown_category_code")
            if occurrences[key] > 1: reasons.append("duplicate_source_row")
            record = {
                "source_id": self.source_id, "source_row": line,
                "source_row_id": row_identity(row, occurrences[key]),
                "source_record_key": f"{approval or 'unknown'}|{category or 'unknown'}|{activities or 'unknown'}|{occurrences[key]}",
                "source_values": row,
                "normalized": {
                    "establishment_id": approval, "recognition_number": approval,
                    "facility_grouping": "provisional-dgal-approval-number", "identity_review": "required-before-merge",
                    "name": _clean(value(row, mapping, "legal_name")), "trading_name": _clean(value(row, mapping, "legal_name")),
                    "address": None, "address_state": "source-value-present-pending-review" if _clean(value(row, mapping, "address")) else "unknown",
                    "postal_code": _clean(value(row, mapping, "postal_code")), "municipality": _clean(value(row, mapping, "commune")),
                    "city": _clean(value(row, mapping, "commune")), "department_number": _clean(value(row, mapping, "department_number")),
                    "country_code": "FR", "nation": "France", "jurisdiction_level": "national", "source_section": self.section,
                    "source_category": category, "source_activity": activities, "species": _clean(value(row, mapping, "species")),
                    "activity_categories": categories, "classification_state": "derived-from-source-label" if recognized else "unclassified",
                    "observation_state": "listed-at-retrieval", "disappearance_semantics": "not-observed; never inferred as closure",
                    "coordinates": None, "coordinate_state": "not-supplied-by-source", "privacy_gate": "pending-review",
                    "coordinate_gate": "review_required", "publication_gate": "blocked",
                },
            }
            if reasons: quarantined.append({"reasons": tuple(dict.fromkeys(reasons)), "record": record})
            else: accepted.append(record)
        return {"accepted": accepted, "quarantined": quarantined, "input_rows": len(rows), "delimiter": delimiter, "headers": headers, "schema_fingerprint": schema_fingerprint, "source_sha256": hashlib.sha256(content).hexdigest()}

    def parse_file(self, path: str | Path) -> dict[str, Any]:
        return self.parse_bytes(Path(path).read_bytes())

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if artifact.sha256 != hashlib.sha256(raw).hexdigest() or artifact.byte_size != len(raw): raise ValueError("artifact provenance mismatch")
        result = self.parse_bytes(raw); root = Path(run_dir); accepted, quarantined = result["accepted"], result["quarantined"]
        parsed = accepted + [item["record"] for item in quarantined]
        _, parsed_sha256, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed)
        _, normalized_sha256, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        anomaly_counts = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(source_id=self.source_id, adapter_version=self.adapter_version, schema_version=self.schema_version, artifact=artifact, input_rows=result["input_rows"], normalized_rows=len(accepted), quarantined_rows=len(quarantined), normalized_sha256=normalized_sha256, parsed_sha256=parsed_sha256, anomaly_counts=dict(sorted(anomaly_counts.items())))
        manifest.update({"country_code": "FR", "section": self.section, "delimiter": result["delimiter"], "schema_fingerprint": result["schema_fingerprint"], "coverage": f"France DGAL Regulation (EC) 853/2004 Section {self.section}; source rows only; no completeness claim", "geocoding": "disabled"})
        atomic_json(root / "manifest.json", manifest)
        write_operator_review_packet(root, manifest, source_scope=manifest["coverage"], checks=("confirm DGAL file terms and attribution", "review residential or mixed-use addresses", "review duplicate approval/activity identities", "confirm category codebook and current-list semantics", "approve any project release separately"), blockers=("publication approval not granted", "privacy and coordinate review pending", "source disappearance means not observed, not closure"))
        return manifest


SECTION_I_URL = "https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_ONG_DOM.txt"
SECTION_II_URL = "https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_COL_LAGO.txt"


class FranceDgalSectionIAdapter(FranceDgalAdapter):
    def __init__(self) -> None: super().__init__("fr.dgal.section-i", "I", SECTION_I_URL)


class FranceDgalSectionIIAdapter(FranceDgalAdapter):
    def __init__(self) -> None: super().__init__("fr.dgal.section-ii", "II", SECTION_II_URL)
