"""Private adapters for the verified Ontario and CFIA meat-plant routes."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.common.review import write_operator_review_packet
from pipeline.common.tabular import occurrence_key, read_rows, resolve_mapping, row_identity, value
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest


ALIASES = {
    "plant_number": ("plant number", "registration number", "establishment number", "establishment id", "plant id", "registration no", "plant number no. de l'usine"),
    "name": ("plant name", "operator name", "operators name", "name of operator", "establishment name", "operator", "name", "plant name nom de l'usine"),
    "doing_business_as": ("doing business as", "dba name", "also doing business as name", "trade name"),
    "address": ("address", "location address", "street address", "location", "address adresse"),
    "city": ("city", "location city", "municipality", "town", "city ville"),
    "province": ("province", "location province", "prov", "state", "province"),
    "postal_code": ("postal code", "postcode", "zip", "postal code code postal"),
    "phone": ("phone", "telephone", "telephone numbers", "contact phone", "telephone telephone"),
    "latitude": ("latitude", "lat", "y"),
    "longitude": ("longitude", "lon", "lng", "x"),
    "animal_class": ("animal class", "animal classes", "species", "species processed", "animal class catégorie d'animaux"),
    "plant_type": ("plant type", "type", "dataset", "facility type"),
    "function_codes": ("function codes", "function code", "activities", "activity codes", "activity"),
    "status": ("status", "current status", "state"),
    "effective_date": ("effective date", "date updated", "last updated", "updated"),
}


def _clean(raw: str | None) -> str | None:
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _categories(*values_: str | None) -> tuple[str, ...]:
    text = " ".join(item for item in values_ if item).lower()
    categories: list[str] = []
    if any(token in text for token in ("abattoir", "slaughter", "slaughterhouse")) or re.search(r"(?:^|[ ,;/])1[a-h]?(?:$|[ ,;/])", text): categories.append("slaughter")
    if any(token in text for token in ("cutting", "boning", "further processing")) or re.search(r"(?:^|[ ,;/])3x?(?:$|[ ,;/])", text): categories.append("cutting")
    if any(token in text for token in ("processing", "canning", "rendering")) or re.search(r"(?:^|[ ,;/])(?:6|7)(?:$|[ ,;/])", text): categories.append("processing")
    if any(token in text for token in ("storage", "cold store", "dry store")) or re.search(r"(?:^|[ ,;/])10(?:$|[ ,;/])", text): categories.append("logistics_and_storage")
    return tuple(dict.fromkeys(categories))


class CanadaMeatAdapter:
    def __init__(self, source_id: str, jurisdiction_level: str, jurisdiction: str, source_url: str, coverage: str, require_categories: bool = False) -> None:
        self.source_id, self.jurisdiction_level, self.jurisdiction, self.source_url, self.coverage = source_id, jurisdiction_level, jurisdiction, source_url, coverage
        self.require_categories = require_categories
        self.adapter_version, self.schema_version = "ca-meat-v1", "ca-meat-delimited-v1"

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        required = ("plant_number", "name")
        headers, rows, delimiter, schema_fingerprint = read_rows(content, ALIASES, required=required)
        mapping = resolve_mapping(headers, ALIASES)
        occurrences: Counter[tuple[str | None, ...]] = Counter(); accepted: list[dict[str, Any]] = []; quarantined: list[dict[str, Any]] = []
        for line, row in enumerate(rows, 2):
            plant_number, name = _clean(value(row, mapping, "plant_number")), _clean(value(row, mapping, "name"))
            key = occurrence_key(row, mapping, ("plant_number", "name", "city", "province", "function_codes", "animal_class")); occurrences[key] += 1
            plant_type, functions, animal_class = _clean(value(row, mapping, "plant_type")), _clean(value(row, mapping, "function_codes")), _clean(value(row, mapping, "animal_class"))
            categories = _categories(plant_type, functions, animal_class)
            reasons: list[str] = []
            if not plant_number: reasons.append("missing_plant_number")
            if not name: reasons.append("missing_operator_or_plant_name")
            if self.require_categories and not categories: reasons.append("unknown_function_code")
            if occurrences[key] > 1: reasons.append("duplicate_source_row")
            normalized = {
                "establishment_id": plant_number, "recognition_number": plant_number, "facility_grouping": f"provisional-{self.jurisdiction_level}-plant-number", "identity_review": "required-before-merge",
                "name": name, "trading_name": _clean(value(row, mapping, "doing_business_as")) or name, "address": None,
                "address_state": "source-value-present-pending-review" if _clean(value(row, mapping, "address")) else "unknown", "city": _clean(value(row, mapping, "city")), "postal_code": _clean(value(row, mapping, "postal_code")), "province": _clean(value(row, mapping, "province")),
                "country_code": "CA", "nation": "Canada", "jurisdiction_level": self.jurisdiction_level, "jurisdiction": self.jurisdiction,
                "source_plant_type": plant_type, "source_function_codes": functions, "animal_class": animal_class, "activity_categories": categories,
                "classification_state": "derived-from-source-label" if categories else "unclassified", "observation_state": "listed-at-retrieval", "disappearance_semantics": "not-observed; never inferred as closure",
                "coordinates": None, "coordinate_state": "source-value-present-pending-review" if _clean(value(row, mapping, "latitude")) or _clean(value(row, mapping, "longitude")) else "not-supplied-by-source", "privacy_gate": "pending-review", "coordinate_gate": "review_required", "publication_gate": "blocked",
            }
            record = {"source_id": self.source_id, "source_row": line, "source_row_id": row_identity(row, occurrences[key]), "source_record_key": f"{plant_number or 'unknown'}|{occurrences[key]}", "source_values": row, "normalized": normalized}
            if reasons: quarantined.append({"reasons": tuple(dict.fromkeys(reasons)), "record": record})
            else: accepted.append(record)
        return {"accepted": accepted, "quarantined": quarantined, "input_rows": len(rows), "delimiter": delimiter, "headers": headers, "schema_fingerprint": schema_fingerprint, "source_sha256": hashlib.sha256(content).hexdigest()}

    def parse_file(self, path: str | Path) -> dict[str, Any]: return self.parse_bytes(Path(path).read_bytes())

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if artifact.sha256 != hashlib.sha256(raw).hexdigest() or artifact.byte_size != len(raw): raise ValueError("artifact provenance mismatch")
        result = self.parse_bytes(raw); root = Path(run_dir); accepted, quarantined = result["accepted"], result["quarantined"]; parsed = accepted + [item["record"] for item in quarantined]
        _, parsed_sha256, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed); _, normalized_sha256, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted); atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        anomaly_counts = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(source_id=self.source_id, adapter_version=self.adapter_version, schema_version=self.schema_version, artifact=artifact, input_rows=result["input_rows"], normalized_rows=len(accepted), quarantined_rows=len(quarantined), normalized_sha256=normalized_sha256, parsed_sha256=parsed_sha256, anomaly_counts=dict(sorted(anomaly_counts.items())))
        manifest.update({"country_code": "CA", "jurisdiction_level": self.jurisdiction_level, "jurisdiction": self.jurisdiction, "delimiter": result["delimiter"], "schema_fingerprint": result["schema_fingerprint"], "coverage": self.coverage, "geocoding": "disabled"})
        atomic_json(root / "manifest.json", manifest)
        write_operator_review_packet(root, manifest, source_scope=self.coverage, checks=("keep federal and provincial identities separate", "review address, phone, and coordinate privacy", "review duplicate plant-number rows without silent merge", "confirm function-code or plant-type mapping", "approve any project release separately"), blockers=("no national completeness claim", "publication and privacy approval pending", "source disappearance means not observed, not closure"))
        return manifest


ONTARIO_URL = "https://data.ontario.ca/dataset/a763088c-018d-48b7-bf47-3027a8c725b8/resource/ee6d559a-78de-40e6-b2ba-ad3c4a674b96/download/1._all_meat_plants.csv"
CFIA_URL = "https://active.inspection.gc.ca/scripts/meavia/reglist/download.asp?lang=e"


class OntarioMeatPlantsAdapter(CanadaMeatAdapter):
    def __init__(self) -> None: super().__init__("ca.ontario.meat-plants", "provincial", "Ontario", ONTARIO_URL, "Government of Ontario provincially licensed meat plants; Ontario only; plant name/number, contact, coordinates, and animal-class source fields; no national completeness claim")


class CfiaFederalMeatAdapter(CanadaMeatAdapter):
    def __init__(self) -> None: super().__init__("ca.cfia.federal-meat", "federal", "Canada", CFIA_URL, "CFIA federally registered meat establishments and licensed operators; federal registry only; provincial establishments are excluded", require_categories=True)
