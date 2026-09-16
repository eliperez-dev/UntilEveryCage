"""Private FASFC operator adapter with deterministic LAP/PAP codebook join.

The operator feed is broader than slaughterhouses.  This adapter retains every
source activity and only derives conservative, reviewable categories.  Address,
coordinates, enterprise numbers, and other source values stay in private parsed
evidence; normalized rows deliberately carry no address or coordinate payload.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


class BelgiumSchemaError(ValueError):
    """A supplied operator or codebook artifact is not a supported CSV schema."""


_ALIASES = {
    "operator_id": ("operator_id", "operator id", "operator number", "enterprise number", "enterprise id", "nummer operator", "numero operateur"),
    "establishment_id": ("establishment_id", "establishment id", "establishment number", "establishment nr", "n establishment", "nummer vestiging", "numero etablissement", "n etablissement"),
    "name": ("name", "operator name", "establishment name", "name operator", "naam", "nom", "name establishment"),
    "address": ("address", "address line", "street", "street address", "street and number", "adres", "adresse"),
    "postcode": ("postcode", "postal code", "zip", "code postal"),
    "municipality": ("municipality", "city", "town", "gemeente", "commune", "municipality name"),
    "region": ("region", "province", "provincie", "province"),
    "latitude": ("latitude", "lat", "latitude y"),
    "longitude": ("longitude", "lon", "lng", "longitude x"),
    "activity_code": ("activity_code", "activity code", "activity codes", "lap code", "lap id", "pap code", "pap id", "code lap", "code pap", "activiteiten code", "code activite"),
    "activity_description": ("activity_description", "activity description", "activity", "description", "omschrijving activiteit", "description activite"),
    "approval_number": ("approval_number", "approval number", "approval nr", "agrément", "erkenningsnummer", "numero agrement"),
    "authorization_number": ("authorization_number", "authorization number", "authorization nr", "authorisation number", "autorisatienummer", "numero autorisation"),
    "status": ("status", "current status", "state", "statuut", "statut"),
    "effective_date": ("effective_date", "effective date", "valid from", "start date", "geldigheid vanaf", "date debut"),
}
_CODE_ALIASES = {
    "lap_code": ("lap_code", "lap code", "lap id", "pap_code", "pap code", "pap id", "activity_code", "activity code", "code lap", "code pap"),
    "place_code": ("place_code", "place code", "pl code", "location code", "code lieu", "plaats code"),
    "place_description": ("place_description", "place description", "location description", "lieu", "plaats"),
    "activity_description": ("activity_description", "activity description", "activity", "activiteit", "activite"),
    "product_description": ("product_description", "product description", "product", "produit", "productomschrijving"),
    "approval_code": ("approval_code", "approval code", "approval form", "code agrement", "erkenningscode"),
    "approval_description": ("approval_description", "approval description", "approval", "agrement", "erkenning"),
}
_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("slaughter", ("slaughter", "abattoir", "slachthuis", "killing", "abattage")),
    ("cutting", ("cutting", "butchery", "deboning", "uitsnijder", "decoupe", "découpe")),
    ("processing", ("processing", "meat product", "manufactur", "transformation", "verwerking", "preparation")),
    ("logistics_and_storage", ("cold store", "cold-storage", "storage", "warehouse", "freezer", "refrigerat", "opslag", "entreposage")),
    ("animal_by_products", ("animal by-product", "animal byproduct", "abp", "sous-produit", "dierlijke bijproduct")),
    ("export", ("export", "third country trade", "handel derde landen")),
)
_PUBLIC_CATEGORIES = {"slaughter", "cutting", "processing", "logistics_and_storage"}
_RISK = re.compile(r"\b(flat|apartment|appartement|residential|home|maison|c/o|care of|caravan|woning)\b", re.I)


def _key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _csv(content: bytes) -> tuple[list[str], list[list[str]], str, str]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        try:
            sample = text[:8192]
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = type("FallbackDialect", (), {"delimiter": ",", "quotechar": '"'})
        try:
            rows = list(csv.reader(text.splitlines(), delimiter=dialect.delimiter, quotechar=dialect.quotechar, strict=True))
        except csv.Error as exc:
            raise BelgiumSchemaError("malformed CSV") from exc
        if not rows or not rows[0]:
            raise BelgiumSchemaError("missing CSV header")
        headers = [h.strip() for h in rows[0]]
        if len(set(_key(h) for h in headers)) != len(headers):
            raise BelgiumSchemaError("duplicate normalized CSV headers")
        return headers, rows[1:], encoding, dialect.delimiter
    raise BelgiumSchemaError("unsupported CSV encoding")


def _header_map(headers: Iterable[str], aliases: dict[str, tuple[str, ...]], required: set[str]) -> dict[str, str]:
    normalized = {_key(header): header for header in headers}
    result: dict[str, str] = {}
    for field, choices in aliases.items():
        for choice in choices:
            if _key(choice) in normalized:
                result[field] = normalized[_key(choice)]
                break
    missing = sorted(required - result.keys())
    if missing:
        raise BelgiumSchemaError("missing supported columns: " + ", ".join(missing))
    return result


def _row_values(headers: list[str], values: list[str]) -> dict[str, str | None]:
    return {header: (values[index] if index < len(values) else None) for index, header in enumerate(headers)}


def _split_codes(value: str | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip() for part in re.split(r"[;,|]\s*", value or "") if part.strip()))


def _categories(values: Iterable[str | None]) -> tuple[str, ...]:
    found: list[str] = []
    for value in values:
        text = (value or "").casefold()
        for category, needles in _CATEGORY_RULES:
            if any(needle.casefold() in text for needle in needles) and category not in found:
                found.append(category)
    return tuple(found)


def _fingerprint(headers: list[str]) -> str:
    return hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class BelgiumOperatorsAdapter:
    source_id = CONFIG["source_id"]
    adapter_version = CONFIG["adapter_version"]
    schema_version = CONFIG["schema_version"]

    def __init__(self, activity_codes_path: str | Path, activity_artifact: SourceArtifact | None = None):
        self.activity_codes_path = Path(activity_codes_path)
        self.activity_artifact = activity_artifact

    def _codebook(self) -> tuple[dict[str, dict[str, str | None]], dict[str, Any]]:
        content = self.activity_codes_path.read_bytes()
        if self.activity_artifact is not None:
            digest = hashlib.sha256(content).hexdigest()
            if digest != self.activity_artifact.sha256 or len(content) != self.activity_artifact.byte_size:
                raise ValueError("activity-code artifact provenance mismatch")
        headers, rows, encoding, delimiter = _csv(content)
        fields = _header_map(headers, _CODE_ALIASES, {"lap_code"})
        codebook: dict[str, dict[str, str | None]] = {}
        ambiguous: set[str] = set()
        for values in rows:
            raw = _row_values(headers, values)
            code = _clean(raw.get(fields["lap_code"]))
            if not code:
                continue
            item = {field: _clean(raw.get(header)) for field, header in fields.items()}
            if code in codebook and codebook[code] != item:
                ambiguous.add(code)
            codebook[code] = item
        metadata = {"sha256": hashlib.sha256(content).hexdigest(), "byte_size": len(content), "schema_fingerprint": _fingerprint(headers), "column_count": len(headers), "row_count": len(rows), "encoding": encoding, "delimiter": delimiter, "ambiguous_codes": sorted(ambiguous)}
        for code in ambiguous:
            codebook.pop(code, None)
        return codebook, metadata

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        codebook, codebook_meta = self._codebook()
        headers, rows, encoding, delimiter = _csv(content)
        fields = _header_map(headers, _ALIASES, {"establishment_id", "name", "activity_code"})
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        anomalies: Counter[str] = Counter()
        seen: Counter[tuple[str | None, str | None]] = Counter()
        prepared: list[tuple[int, dict[str, str | None], tuple[str, ...]]] = []
        row_lengths: Counter[str] = Counter()
        for line, values in enumerate(rows, start=2):
            raw = _row_values(headers, values)
            row_lengths[str(len(values))] += 1
            codes = _split_codes(_clean(raw.get(fields["activity_code"])))
            prepared.append((line, raw, codes))
            for code in codes:
                seen[(_clean(raw.get(fields["establishment_id"])), code)] += 1
        for line, raw, codes in prepared:
            establishment_id = _clean(raw.get(fields["establishment_id"]))
            name = _clean(raw.get(fields["name"]))
            reasons: list[str] = []
            if len(values) != len(headers) or any(value is None for value in raw.values()):
                reasons.append("malformed_row")
            if not establishment_id:
                reasons.append("missing_establishment_id")
            if not name:
                reasons.append("missing_name")
            if not codes:
                reasons.append("missing_activity_code")
            if any(code not in codebook for code in codes):
                reasons.append("unresolved_activity_code")
            if any(seen[(establishment_id, code)] > 1 for code in codes):
                reasons.append("ambiguous_repeated_establishment_activity")
            address = _clean(raw.get(fields.get("address", ""))) if "address" in fields else None
            if address and _RISK.search(address):
                reasons.append("address_privacy_risk")
            joined = [codebook[code] for code in codes if code in codebook]
            descriptions = [_clean(raw.get(fields.get("activity_description", "")))] + [item.get("activity_description") for item in joined]
            categories = _categories(descriptions + [item.get("place_description") for item in joined] + [item.get("product_description") for item in joined])
            public_categories = tuple(category for category in categories if category in _PUBLIC_CATEGORIES)
            record = {
                "source_id": self.source_id,
                "source_row": line,
                "source_record_key": f"{establishment_id or 'unknown'}|{','.join(codes) or 'unknown'}|{line}",
                "source_values": raw,
                "normalized": {
                    "establishment_id": establishment_id,
                    "operator_id": _clean(raw.get(fields.get("operator_id", ""))) if "operator_id" in fields else None,
                    "name": name,
                    "trading_name": name,
                    "country_code": "BE",
                    "nation": "Belgium",
                    "municipality": _clean(raw.get(fields.get("municipality", ""))) if "municipality" in fields else None,
                    "city": _clean(raw.get(fields.get("municipality", ""))) if "municipality" in fields else None,
                    "postcode": _clean(raw.get(fields.get("postcode", ""))) if "postcode" in fields else None,
                    "address": None,
                    "address_state": "source-present-pending-privacy-review" if address else "unknown",
                    "coordinates": None,
                    "coordinate_state": "source-value-present-pending-review" if any(_clean(raw.get(fields.get(key, ""))) for key in ("latitude", "longitude") if key in fields) else "unknown",
                    "activity_codes": codes,
                    "activity_descriptions": tuple(dict.fromkeys(item.get("activity_description") for item in joined if item.get("activity_description"))),
                    "activity_categories": public_categories,
                    "source_activity_categories": categories,
                    "scope_flags": {"slaughterhouse": "slaughter" in categories, "cutting": "cutting" in categories, "processing": "processing" in categories, "storage": "logistics_and_storage" in categories, "animal_by_products": "animal_by_products" in categories, "export": "export" in categories},
                    "approval_number": _clean(raw.get(fields.get("approval_number", ""))) if "approval_number" in fields else None,
                    "authorization_number": _clean(raw.get(fields.get("authorization_number", ""))) if "authorization_number" in fields else None,
                    "status": _clean(raw.get(fields.get("status", ""))) if "status" in fields else None,
                    "effective_date": _clean(raw.get(fields.get("effective_date", ""))) if "effective_date" in fields else None,
                    "privacy_gate": "pending-review",
                    "coordinate_gate": "review_required",
                    "publication_gate": "blocked",
                },
            }
            if reasons:
                unique = tuple(dict.fromkeys(reasons))
                for reason in unique:
                    anomalies[reason] += 1
                quarantined.append({"reasons": unique, "record": record})
            else:
                accepted.append(record)
        return {"accepted": accepted, "quarantined": quarantined, "input_rows": len(rows), "source_sha256": hashlib.sha256(content).hexdigest(), "operator_schema_fingerprint": _fingerprint(headers), "operator_column_count": len(headers), "operator_encoding": encoding, "operator_delimiter": delimiter, "row_length_counts": dict(sorted(row_lengths.items())), "codebook": codebook_meta, "coverage_counts": dict(Counter(category for item in accepted for category in item["normalized"]["source_activity_categories"])), "anomaly_counts": dict(sorted(anomalies.items()))}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if artifact.sha256 != digest or artifact.byte_size != len(raw):
            raise ValueError("operator artifact provenance mismatch")
        result = self.parse_bytes(raw)
        root = Path(run_dir)
        parsed = result["accepted"] + [item["record"] for item in result["quarantined"]]
        _, parsed_sha, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed)
        _, normalized_sha, _ = atomic_jsonl(root / "normalized" / "records.jsonl", result["accepted"])
        atomic_jsonl(root / "quarantined" / "records.jsonl", result["quarantined"])
        manifest = private_manifest(source_id=self.source_id, adapter_version=self.adapter_version, schema_version=self.schema_version, artifact=artifact, input_rows=result["input_rows"], normalized_rows=len(result["accepted"]), quarantined_rows=len(result["quarantined"]), normalized_sha256=normalized_sha, parsed_sha256=parsed_sha, anomaly_counts=result["anomaly_counts"])
        manifest.update({"country_code": "BE", "coverage": CONFIG["coverage"], "geocoding": "disabled", "operator_schema_fingerprint": result["operator_schema_fingerprint"], "operator_column_count": result["operator_column_count"], "operator_encoding": result["operator_encoding"], "operator_delimiter": result["operator_delimiter"], "row_length_counts": result["row_length_counts"], "coverage_counts": result["coverage_counts"], "activity_codebook": result["codebook"], "codebook_source_url": self.activity_artifact.source_url if self.activity_artifact else "unrecorded-companion-artifact", "codebook_retrieved_at_utc": self.activity_artifact.retrieved_at_utc if self.activity_artifact else None, "codebook_sha256": result["codebook"]["sha256"], "codebook_byte_size": result["codebook"]["byte_size"]})
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact, parsed: dict[str, Any]) -> dict[str, Any]:
        return write_handoff(run_dir, [item["record"] if "record" in item else item for item in parsed["accepted"]], artifact, source_id=self.source_id)
