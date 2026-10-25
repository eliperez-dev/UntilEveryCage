"""Privacy-separated adapter for the AESAN national RGSEAA XLSX."""
from __future__ import annotations

import hashlib
import io
import json
import posixpath
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_jsonl, private_manifest

CONFIG = json.loads((Path(__file__).with_name("config.json")).read_text(encoding="utf-8"))

SOURCE_ID = CONFIG["source_id"]
ADAPTER_VERSION = CONFIG["adapter_version"]
SCHEMA_VERSION = CONFIG["schema_version"]
SOURCE_URL = CONFIG["source_url"]
HEADERS = ("N_RGSEAA", "Razon_Social", "Domicilio_industrial", "Provincia", "CCAA", "Clave", "Clave_Descripcion")
ANIMAL_ORIGIN_KEYS = frozenset({"10", "12", "14", "15"})
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_ZIP_MEMBERS = 128
_MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
           "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
           "noviembre": 11, "diciembre": 12}


def _clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _column_index(reference: str) -> int:
    match = re.fullmatch(r"([A-Z]+)[0-9]+", reference)
    if not match:
        raise ValueError("malformed AESAN XLSX cell reference")
    index = 0
    for char in match.group(1):
        index = index * 26 + ord(char) - 64
    return index - 1


def _workbook_parts(archive: zipfile.ZipFile) -> tuple[str, str, str]:
    names = set(archive.namelist())
    if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
        raise ValueError("unsupported AESAN XLSX workbook")
    total_uncompressed = sum(member.file_size for member in archive.infolist())
    if len(names) > MAX_ZIP_MEMBERS or total_uncompressed > MAX_EXPANDED_BYTES:
        raise ValueError("AESAN XLSX exceeds configured archive bounds")
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    sheets = workbook.findall(".//{*}sheet")
    if len(sheets) != 1:
        raise ValueError("AESAN XLSX worksheet count changed")
    sheet_name = sheets[0].attrib.get("name", "")
    relation_id = sheets[0].attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next((item.attrib.get("Target") for item in relationships
                   if item.attrib.get("Id") == relation_id), None)
    if not target:
        raise ValueError("AESAN XLSX worksheet relationship missing")
    sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
    if not sheet_path.startswith("xl/") or ".." in sheet_path.split("/") or sheet_path not in names:
        raise ValueError("AESAN XLSX worksheet path is invalid")
    shared_path = "xl/sharedStrings.xml"
    if shared_path not in names:
        raise ValueError("AESAN XLSX shared strings are missing")
    return sheet_name, sheet_path, shared_path


def _date_from_title(title: str) -> str | None:
    match = re.search(r"actualizado\s+a\s+(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})", title, re.I)
    if not match:
        return None
    month = _MONTHS.get(match.group(2).casefold())
    return f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(1)):02d}" if month else None


def _read_xlsx(content: bytes) -> tuple[str, list[tuple[int, dict[str, str]]], str | None]:
    """Parse the pinned workbook table without coercing source text fields."""
    if not content.startswith(b"PK\x03\x04"):
        raise ValueError("AESAN artifact is not an XLSX container")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            sheet_name, sheet_path, shared_path = _workbook_parts(archive)
            shared_root = ET.fromstring(archive.read(shared_path))
            shared = ["".join(item.itertext()) for item in shared_root.findall(".//{*}si")]
            header_found = False
            title_parts: list[str] = []
            rows: list[tuple[int, dict[str, str]]] = []
            with archive.open(sheet_path) as stream:
                for _, element in ET.iterparse(stream, events=("end",)):
                    if not element.tag.endswith("}row"):
                        continue
                    row_number = int(element.attrib.get("r", "0"))
                    cells: dict[int, str] = {}
                    for cell in element.findall("{*}c"):
                        column = _column_index(cell.attrib.get("r", ""))
                        kind = cell.attrib.get("t")
                        if kind == "inlineStr":
                            value = "".join(cell.itertext())
                        else:
                            node = cell.find("{*}v")
                            value = "" if node is None else (node.text or "")
                            if kind == "s" and value:
                                value = shared[int(value)]
                        cells[column] = value
                    if not header_found:
                        line = [cells.get(index, "") for index in range(max(cells, default=-1) + 1)]
                        if tuple(line[:len(HEADERS)]) == HEADERS:
                            if any(_clean(line[index]) for index in range(len(HEADERS), len(line))):
                                raise ValueError("AESAN XLSX header has unexpected columns")
                            header_found = True
                        else:
                            title_parts.extend(value for value in cells.values() if _clean(value))
                    elif any(_clean(value) for value in cells.values()):
                        if any(index >= len(HEADERS) and _clean(value) for index, value in cells.items()):
                            raise ValueError("AESAN XLSX row contains unexpected columns")
                        values = {header: cells.get(index, "") for index, header in enumerate(HEADERS)}
                        rows.append((row_number, values))
                    element.clear()
            if not header_found:
                raise ValueError("AESAN XLSX schema drift: exact RGSEAA headers missing")
            if not rows:
                raise ValueError("AESAN XLSX contains no data rows")
    except (KeyError, IndexError, TypeError, ET.ParseError, zipfile.BadZipFile) as error:
        raise ValueError("malformed or unsupported AESAN XLSX workbook") from error
    title = " ".join(title_parts)
    if "RGSEAA" not in title.upper():
        raise ValueError("AESAN XLSX title block changed")
    return sheet_name, rows, _date_from_title(title)


class RgseaaAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        sheet_name, source_rows, source_update_date = _read_xlsx(content)
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        row_occurrences: Counter[str] = Counter()
        key_counts: Counter[str] = Counter()
        non_allowlisted_key_count = 0
        for row_number, values in source_rows:
            registration = _clean(values["N_RGSEAA"])
            key = _clean(values["Clave"])
            label = _clean(values["Clave_Descripcion"])
            if not registration:
                quarantined.append({"source_row": row_number, "reason": "missing_source_registration_number"})
                continue
            canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            row_occurrences[digest] += 1
            record_key = hashlib.sha256(f"{digest}|{row_occurrences[digest]}".encode()).hexdigest()
            normalized_key = key.lstrip("0") or "0"
            eligible = normalized_key in ANIMAL_ORIGIN_KEYS
            key_counts[key or "missing"] += 1
            non_allowlisted_key_count += bool(key) and normalized_key not in ANIMAL_ORIGIN_KEYS
            normalized = {
                "establishment_id": registration,
                "country_code": "ES",
                "nation": "Spain",
                "region": _clean(values["CCAA"]) or None,
                "province": _clean(values["Provincia"]) or None,
                "address": _clean(values["Domicilio_industrial"]) or None,
                "source_classification_code": key or None,
                "source_classification_label": label or None,
                "source_scope_eligibility": "eligible" if eligible else "out_of_scope",
                "source_scope_category": "animal_origin_food_chain" if eligible else "other_rgseaa_food_chain",
                "source_address_state": "source_industrial_address" if values["Domicilio_industrial"].strip() else "not_supplied",
                "coordinate_state": "not-supplied",
                "coordinate_precision": "unmapped-no-source-coordinates",
                "privacy_gate": "restricted-private-evidence",
                "coordinate_gate": "unmapped",
                "rights_gate": "review_required",
                "publication_gate": "blocked",
            }
            accepted.append({"source_id": SOURCE_ID, "source_row": row_number,
                             "source_row_id": record_key, "source_record_key": record_key,
                             "source_values": values, "normalized": normalized})
        fingerprint = hashlib.sha256(json.dumps({"sheet": sheet_name, "headers": HEADERS},
                                                ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return {"accepted": accepted, "quarantined": quarantined,
                "input_rows": len(source_rows), "schema_fingerprint": fingerprint,
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "sheet_name": sheet_name, "source_update_date": source_update_date,
                "key_counts": dict(sorted(key_counts.items())), "non_allowlisted_key_count": non_allowlisted_key_count,
                "candidate_rows": sum(row["normalized"]["source_scope_eligibility"] == "eligible" for row in accepted)}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw_path = Path(raw_path)
        raw = raw_path.read_bytes()
        if artifact.source_url != SOURCE_URL or artifact.sha256 != hashlib.sha256(raw).hexdigest() or artifact.byte_size != len(raw):
            raise ValueError("AESAN artifact provenance mismatch")
        parsed = self.parse_bytes(raw)
        root = Path(run_dir)
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed["accepted"])
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", parsed["accepted"])
        _, quarantine_hash, _ = atomic_jsonl(root / "quarantined" / "records.jsonl", parsed["quarantined"])
        manifest = private_manifest(
            source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION, schema_version=SCHEMA_VERSION,
            artifact=artifact, input_rows=parsed["input_rows"],
            normalized_rows=len(parsed["accepted"]), quarantined_rows=len(parsed["quarantined"]),
            normalized_sha256=normalized_hash, parsed_sha256=parsed_hash,
            anomaly_counts={"missing_source_registration_number": len(parsed["quarantined"])},
        )
        manifest.update({
            "schema_fingerprint": parsed["schema_fingerprint"],
            "source_sha256": parsed["source_sha256"],
            "sheet_name": parsed["sheet_name"],
            "source_update_date": parsed["source_update_date"],
            "source_update_date_semantics": "AESAN workbook title update date; not row-level operational effective dates",
            "source_key_counts": parsed["key_counts"],
            "non_allowlisted_key_count": parsed["non_allowlisted_key_count"],
            "candidate_rows": parsed["candidate_rows"],
            "candidate_scope": "exact AESAN RGSEAA keys 10, 12, 14, 15 per current official classification guide",
            "out_of_scope_rows": len(parsed["accepted"]) - parsed["candidate_rows"],
            "location_handling": "source industrial address retained privately as location evidence; source coordinates not supplied; no geocoding run",
            "release_state": "not-created", "publication_state": "private-candidate",
        })
        manifest["quarantined_sha256"] = quarantine_hash
        from pipeline.contracts.source_lifecycle import atomic_json
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                parsed: dict[str, Any]) -> dict[str, Any]:
        rows = [{"source_id": row["source_id"], "source_row": row["source_row"],
                 "source_record_key": row["source_record_key"], "source_values": {},
                 "normalized": {key: row["normalized"].get(key) for key in (
                     "establishment_id", "country_code", "nation", "region", "province", "address",
                     "source_classification_code", "source_classification_label", "source_scope_eligibility",
                     "source_scope_category", "source_address_state", "coordinate_state", "coordinate_precision",
                     "privacy_gate", "coordinate_gate", "rights_gate", "publication_gate")}}
                for row in parsed["accepted"]
                if row["normalized"].get("source_scope_eligibility") == "eligible"]
        return write_handoff(run_dir, rows, artifact, source_id=SOURCE_ID,
                             emit_graph_candidates=True)
