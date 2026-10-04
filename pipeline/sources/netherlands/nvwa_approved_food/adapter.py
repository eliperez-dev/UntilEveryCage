"""Parse NVWA's repeated approved-food SOAP rows as private observations."""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SOURCE_ID = CONFIG["source_id"]
ADAPTER_VERSION = CONFIG["adapter_version"]
SCHEMA_VERSION = CONFIG["schema_version"]
LIST_CODES = tuple(CONFIG["list_codes"])

_OBSERVATION_FIELDS = frozenset({
    "plaats", "adres", "remark", "aanvangsdatum", "specificatiecode",
    "opheffingsdatum", "transportNl", "diersoortNl", "postcode",
    "onderzoekLaboratorium", "transportEn", "bijzonderheden", "activiteit",
    "regelgeving", "categorie", "erkenningssoort", "handelsnaam",
    "erkenningsnummer", "diersoortEn", "producttype",
})


class NvwaContractError(ValueError):
    """A preserved NVWA control or SOAP artifact violates the adapter contract."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _parse_control(content: bytes) -> dict[str, str]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise NvwaContractError("invalid NVWA control XML") from error
    found = {
        element.attrib.get("code", ""): _clean(element.attrib.get("label")) or ""
        for element in root.iter()
        if _local_name(element.tag) == "list"
    }
    missing = sorted(set(LIST_CODES) - found.keys())
    if missing:
        raise NvwaContractError("current control XML no longer advertises required list codes: " + ", ".join(missing))
    return {code: found[code] for code in LIST_CODES}


def _parse_response(content: bytes, *, list_code: str) -> tuple[list[dict[str, Any]], dict[str, int | None]]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise NvwaContractError(f"invalid NVWA SOAP XML for {list_code}") from error
    if any(_local_name(element.tag) == "Fault" for element in root.iter()):
        raise NvwaContractError(f"NVWA SOAP fault for {list_code}")

    observations: list[dict[str, Any]] = []
    for element in root.iter():
        children = list(element)
        if not children:
            continue
        raw_fields = {_local_name(child.tag): child.text for child in children}
        # The recognition value identifies the source-local facility. A row is
        # one list/activity/product/species observation, even when that number
        # has already appeared in this or another list.
        if "erkenningsnummer" in raw_fields or (
            len(set(raw_fields) & _OBSERVATION_FIELDS) >= 2
            and bool(set(raw_fields) & {"handelsnaam", "adres", "plaats", "categorie", "activiteit", "producttype"})
        ):
            observations.append(raw_fields)

    pagination_values: dict[str, int | None] = {
        "cvgOffset": None, "cvgLimit": None, "cvgTotal": None, "cvgReturned": None,
    }
    for element in root.iter():
        name = _local_name(element.tag)
        if name not in pagination_values:
            continue
        try:
            pagination_values[name] = int(element.text) if element.text and element.text.strip() else None
        except ValueError as error:
            raise NvwaContractError(f"invalid NVWA pagination value for {list_code}") from error
    return observations, pagination_values


def _observation_key(list_code: str, recognition: str, fields: dict[str, Any], duplicate: int) -> str:
    canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{list_code}|{recognition}|{digest}|{duplicate}"


def _make_record(
    *, list_code: str, list_label: str, fields: dict[str, Any], source_row: int,
    artifact_sha256: str, duplicate_number: int,
) -> dict[str, Any]:
    cleaned = {name: _clean(value) for name, value in fields.items()}
    recognition = cleaned.get("erkenningsnummer")
    source_record_key = _observation_key(list_code, recognition or "missing", fields, duplicate_number)
    location = {
        key: value for key, value in (
            ("address", cleaned.get("adres")),
            ("address_lines", [cleaned.get("adres")] if cleaned.get("adres") else None),
            ("postal_code", cleaned.get("postcode")),
            ("city", cleaned.get("plaats")),
            ("country_code", "NL"),
        ) if value
    }
    activity_observation = {
        "list_code": list_code,
        "list_label": list_label,
        "category": cleaned.get("categorie"),
        "activity": cleaned.get("activiteit"),
        "product_type": cleaned.get("producttype"),
        "species_nl": cleaned.get("diersoortNl"),
        "species_en": cleaned.get("diersoortEn"),
        "regulation": cleaned.get("regelgeving"),
        "approval_type": cleaned.get("erkenningssoort"),
        "specification_code": cleaned.get("specificatiecode"),
    }
    normalized: dict[str, Any] = {
        "establishment_id": recognition,
        "recognition_number": recognition,
        "trading_name": cleaned.get("handelsnaam"),
        "country_code": "NL",
        "activity_observations": [activity_observation],
        "activities": [activity_observation["activity"]] if activity_observation["activity"] else [],
        "activity_codes": [],
        "activity_descriptions": [
            value for value in (activity_observation["category"], activity_observation["product_type"])
            if value
        ],
        "species": [value for value in (activity_observation["species_nl"], activity_observation["species_en"]) if value],
        "approval_lifecycle_values": {
            "start_date": cleaned.get("aanvangsdatum"),
            "end_date": cleaned.get("opheffingsdatum"),
            "remark": cleaned.get("remark"),
            "details": cleaned.get("bijzonderheden"),
        },
        "coordinates": None,
        "coordinate_state": "not_provided",
        "coordinate_precision": "unavailable",
        "coordinate_gate": "review_required",
        "privacy_gate": "pending",
        "source_scope_eligibility": "eligible",
        "publication_gate": "blocked",
    }
    # Addresses stay out of general normalized display fields. The shared
    # handoff attaches this private evidence for the separate geocoding queue.
    if location:
        normalized["private_location_evidence"] = location
    return {
        "source_id": SOURCE_ID,
        "source_row": source_row,
        "source_record_key": source_record_key,
        "source_list_code": list_code,
        "source_list_label": list_label,
        "source_artifact_sha256": artifact_sha256,
        "source_values": fields,
        "normalized": normalized,
    }


class NvwaApprovedFoodAdapter:
    """Parse an acquisition bundle into private source-observation rows."""

    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        bundle_path = Path(raw_path)
        bundle_bytes = bundle_path.read_bytes()
        if hashlib.sha256(bundle_bytes).hexdigest() != artifact.sha256 or len(bundle_bytes) != artifact.byte_size:
            raise NvwaContractError("acquisition bundle checksum or byte size mismatch")
        try:
            bundle = json.loads(bundle_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NvwaContractError("invalid NVWA acquisition bundle manifest") from error
        if bundle.get("bundle_version") != "nvwa-approved-food-bundle-v1" or bundle.get("source_id") != SOURCE_ID:
            raise NvwaContractError("unsupported NVWA acquisition bundle")
        control = next((item for item in bundle.get("artifacts", []) if item.get("kind") == "control"), None)
        if control is None:
            raise NvwaContractError("NVWA bundle is missing its control XML")
        artifact_root = bundle_path.parent
        control_bytes = (artifact_root / control["file"]).read_bytes()
        if hashlib.sha256(control_bytes).hexdigest() != control.get("sha256") or len(control_bytes) != control.get("byte_size"):
            raise NvwaContractError("NVWA control artifact checksum or byte size mismatch")
        labels = _parse_control(control_bytes)

        soap_artifacts = [item for item in bundle.get("artifacts", []) if item.get("kind") == "soap"]
        codes_present = {item.get("list_code") for item in soap_artifacts}
        if codes_present != set(LIST_CODES):
            raise NvwaContractError("NVWA bundle must contain all eight configured lists")
        rows_by_list: dict[str, list[dict[str, Any]]] = defaultdict(list)
        unknown_fields_by_list: dict[str, Counter[str]] = defaultdict(Counter)
        input_rows = 0
        for source_artifact in sorted(soap_artifacts, key=lambda item: (item["list_code"], item.get("offset", 0))):
            list_code = source_artifact["list_code"]
            raw = (artifact_root / source_artifact["file"]).read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != source_artifact.get("sha256") or len(raw) != source_artifact.get("byte_size"):
                raise NvwaContractError(f"NVWA SOAP artifact checksum or byte size mismatch for {list_code}")
            observations, pagination = _parse_response(raw, list_code=list_code)
            expected_rows = source_artifact.get("observation_rows")
            if expected_rows is not None and expected_rows != len(observations):
                raise NvwaContractError(f"NVWA SOAP row count changed for {list_code}")
            rows_by_list[list_code].extend(
                {"fields": fields, "artifact_sha256": digest} for fields in observations
            )
            for fields in observations:
                unknown_fields_by_list[list_code].update(set(fields) - _OBSERVATION_FIELDS)
            input_rows += len(observations)

        parsed: list[dict[str, Any]] = []
        normalized: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        observations_by_list: dict[str, int] = {}
        unique_recognition_numbers_by_list: dict[str, int] = {}
        next_source_row = 1
        for list_code in LIST_CODES:
            observations = rows_by_list[list_code]
            observations_by_list[list_code] = len(observations)
            unique_numbers = {
                value for item in observations
                if (value := _clean(item["fields"].get("erkenningsnummer")))
            }
            unique_recognition_numbers_by_list[list_code] = len(unique_numbers)
            identical_occurrences: Counter[str] = Counter()
            for item in observations:
                fields = item["fields"]
                recognition = _clean(fields.get("erkenningsnummer"))
                canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                identical_occurrences[fingerprint] += 1
                record = _make_record(
                    list_code=list_code, list_label=labels[list_code], fields=fields,
                    source_row=next_source_row, artifact_sha256=item["artifact_sha256"],
                    duplicate_number=identical_occurrences[fingerprint],
                )
                next_source_row += 1
                parsed.append(record)
                if recognition:
                    normalized.append(record)
                else:
                    quarantined.append({"reasons": ["missing_recognition_number"], "record": record})

        root = Path(run_dir)
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed)
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", normalized)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        manifest = private_manifest(
            source_id=SOURCE_ID,
            adapter_version=ADAPTER_VERSION,
            schema_version=SCHEMA_VERSION,
            artifact=artifact,
            input_rows=len(parsed),
            normalized_rows=len(normalized),
            quarantined_rows=len(quarantined),
            normalized_sha256=normalized_hash,
            parsed_sha256=parsed_hash,
            anomaly_counts={"missing_recognition_number": len(quarantined)} if quarantined else {},
        )
        manifest.update({
            "coverage": CONFIG["coverage"],
            "observation_rows_by_list": observations_by_list,
            "unique_recognition_numbers_by_list": unique_recognition_numbers_by_list,
            "count_semantics": "Counts are repeated approval observations and unique source recognition numbers within each individual list; no summed facility count is computed.",
            "unknown_source_fields_by_list": {
                code: dict(sorted(counts.items())) for code, counts in sorted(unknown_fields_by_list.items()) if counts
            },
            "schema_status": "schema-drift" if any(unknown_fields_by_list.values()) else "known-wsdl-fields",
            "source_artifacts": [
                {key: value for key, value in item.items() if key not in {"file"}}
                for item in bundle["artifacts"]
            ],
            "geocoding": "not-run; no source coordinates; private address evidence is available to the separately approved geocoding queue",
        })
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Write importer-compatible private handoff, preserving each observation."""
        seen: set[str] = set()
        for row in rows:
            key = row.get("source_record_key")
            if not isinstance(key, str) or key in seen:
                raise NvwaContractError("NVWA candidate handoff has missing or duplicate observation keys")
            seen.add(key)
            normalized = row.get("normalized") or {}
            if normalized.get("establishment_id") != normalized.get("recognition_number"):
                raise NvwaContractError("NVWA establishment identifier must remain its source recognition number")
            normalized["activities"] = [
                item["activity"] for item in normalized.get("activity_observations", []) if item.get("activity")
            ]
        return write_handoff(run_dir, rows, artifact, source_id=SOURCE_ID)
