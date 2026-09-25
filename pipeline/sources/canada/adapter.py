"""Private adapters for the verified Ontario and CFIA meat-plant routes."""

from __future__ import annotations

import hashlib
import json
import re
import html
import io
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.common.review import write_operator_review_packet
from pipeline.common.tabular import TabularSchemaError, canonical_header, occurrence_key, read_rows, resolve_mapping, row_identity, value
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.graph_candidate_handoff import write_graph_candidate
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest


ALIASES = {
    "plant_number": ("plant number", "registration number", "establishment number", "establishment id", "plant id", "registration no", "plant number no. de l'usine", "est_num"),
    "name": ("plant name", "operator name", "operators name", "name of operator", "establishment name", "operator", "name", "plant name nom de l'usine"),
    "operator_name": ("operator name", "operators name", "name of operator"),
    "doing_business_as": ("doing business as", "dba name", "also doing business as name", "trade name"),
    "address": ("address", "location address", "street address", "location", "address adresse", "loc_add1", "loc_add2", "loc_add3"),
    "city": ("city", "location city", "municipality", "town", "city ville", "loc_city"),
    "province": ("province", "location province", "prov", "state", "province", "loc_prov"),
    "postal_code": ("postal code", "postcode", "zip", "postal code code postal", "loc_pc"),
    "phone": ("phone", "telephone", "telephone numbers", "contact phone", "telephone telephone", "tele_1"),
    "latitude": ("latitude", "lat", "y"),
    "longitude": ("longitude", "lon", "lng", "x"),
    "animal_class": ("animal class", "animal classes", "species", "species processed", "animal class catégorie d'animaux"),
    "plant_type": ("plant type", "type", "dataset", "facility type"),
    "function_codes": ("function codes", "function code", "activities", "activity codes", "activity", "codes_1", "codes_2", "codes_3", "code_4", "code_5", "codes_6", "code_7", "code_8", "codes_9", "codes_10"),
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


def _joined_source_codes(row: dict[str, str]) -> str | None:
    values = [str(raw).strip() for header, raw in row.items()
              if canonical_header(header).startswith(("codes", "code")) and str(raw).strip()]
    return "; ".join(values) or None


def _cfia_activity(row: dict[str, str]) -> tuple[tuple[str, ...], bool, bool]:
    """Map CFIA's numbered workbook columns using its published key.

    The column number is the function number; the cell contains its species or
    subtype suffix (for example ``CODES_3=fx`` means boning/cutting for poultry
    and red meat). Export markets and detained/imported-product inspection are
    not operation categories. They are recognized and retained in source
    values, but do not independently establish a meat-production facility.
    """
    columns = {re.sub(r"[^a-z0-9]", "", str(header).lower()): str(raw).strip()
               for header, raw in row.items()}
    slot_names = ("codes1", "codes2", "codes3", "code4", "code5", "codes6",
                  "code7", "code8", "codes9", "codes10")
    if not any(name in columns for name in slot_names) and "trichina" not in columns:
        return (), False, False

    valid = True
    categories: list[str] = []
    activity_seen = False
    expected = {
        "codes1": (set("abcdefghij"), "slaughter"),
        "codes2": (set("fxg"), "processing"),
        "codes3": (set("fxg"), "cutting"),
        "code4": ({"y"}, "processing"),
        "code5": ({"y"}, "processing"),
        "codes6": (set("fxg"), "processing"),
        "code7": ({"y"}, "logistics_and_storage"),
        "code8": ({"y"}, "processing"),
        "codes10": (set("ab"), "logistics_and_storage"),
    }
    for name, (allowed, category) in expected.items():
        raw = columns.get(name, "")
        if not raw:
            continue
        compact = re.sub(r"[\s,;/]+", "", raw.lower())
        if not compact or any(char not in allowed for char in compact):
            valid = False
            continue
        activity_seen = True
        if category not in categories:
            categories.append(category)

    # Function 9 is an inspection/import category, not a processing operation.
    raw_nine = columns.get("codes9", "")
    if raw_nine:
        compact = re.sub(r"[\s,;/]+", "", raw_nine.upper())
        if not compact or not re.fullmatch(r"(?:US|[ABC])+", compact):
            valid = False

    # Function 12 marks a trichina-treatment facility.
    trichina = columns.get("trichina", "")
    if trichina:
        if trichina.strip().lower() != "y":
            valid = False
        else:
            activity_seen = True
            if "processing" not in categories:
                categories.append("processing")
    return tuple(categories), not valid, activity_seen


def _fingerprint(headers: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(tuple(re.sub(r"\s+", " ", h).strip().lower() for h in headers), separators=(",", ":")).encode()).hexdigest()


def _validate_sheet(headers: tuple[str, ...], rows: list[dict[str, str]], aliases: dict[str, tuple[str, ...]], required: tuple[str, ...]) -> None:
    if not headers or len(set(headers)) != len(headers):
        raise TabularSchemaError("missing or duplicate workbook header columns")
    missing = sorted(set(required) - resolve_mapping(headers, aliases).keys())
    if missing:
        raise TabularSchemaError("schema drift; missing columns: " + ", ".join(missing))
    if any(len(row) != len(headers) for row in rows):
        raise TabularSchemaError("schema drift; row has an inconsistent column count")


def _read_xls(content: bytes, aliases: dict[str, tuple[str, ...]], *, required: tuple[str, ...]):
    """Read a legacy BIFF workbook while keeping source cells as text.

    CFIA's current download is an ``.xls`` compound-document workbook rather
    than an OOXML ``.xlsx`` file.  It must be parsed explicitly; treating the
    bytes as delimited text would silently corrupt the source evidence.
    """
    try:
        import xlrd
    except ImportError as error:  # pragma: no cover - exercised in env checks
        raise TabularSchemaError("legacy XLS requires pinned xlrd dependency") from error
    try:
        # xlrd's OLE2 consistency diagnostics default to stdout and would
        # corrupt the shared runner's row-free JSON contract. Keep them on
        # stderr while preserving the established parser/quarantine behavior.
        book = xlrd.open_workbook(file_contents=content, on_demand=True, logfile=sys.stderr)
        sheet = next((candidate for candidate in book.sheets() if candidate.nrows and candidate.ncols), None)
        if sheet is None:
            raise TabularSchemaError("workbook has no populated worksheets")

        def cell_text(cell) -> str:
            if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                return ""
            value = cell.value
            if cell.ctype == xlrd.XL_CELL_NUMBER and float(value).is_integer():
                return str(int(value))
            return str(value)

        headers = tuple(cell_text(sheet.cell(0, column)) for column in range(sheet.ncols))
        rows: list[dict[str, str]] = []
        for row_index in range(1, sheet.nrows):
            values = [cell_text(sheet.cell(row_index, column)) for column in range(sheet.ncols)]
            if any(value.strip() for value in values):
                rows.append(dict(zip(headers, values)))
    except (ImportError, IndexError, ValueError, xlrd.biffh.XLRDError) as error:
        raise TabularSchemaError("malformed or unsupported legacy XLS workbook") from error
    _validate_sheet(headers, rows, aliases, required)
    return headers, rows, "xls", _fingerprint(headers)


def _read_xlsx(content: bytes, aliases: dict[str, tuple[str, ...]], *, required: tuple[str, ...]):
    """Read the first non-empty XLSX sheet without type inference or external deps."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(node.itertext()) for node in root.findall(".//{*}si")]
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            relmap = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
            sheet = next((s for s in workbook.findall(".//{*}sheet")), None)
            if sheet is None: raise TabularSchemaError("workbook has no worksheets")
            target = relmap[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            path = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
            root = ET.fromstring(archive.read(path))
            matrix = []
            for row in root.findall(".//{*}sheetData/{*}row"):
                cells = {}
                for cell in row.findall("{*}c"):
                    ref = cell.attrib.get("r", "A1"); col = 0
                    for char in re.match(r"[A-Z]+", ref).group(): col = col * 26 + ord(char) - 64
                    col -= 1; node = cell.find("{*}v"); raw = "" if node is None else node.text or ""
                    if cell.attrib.get("t") == "s" and raw: raw = shared[int(raw)]
                    elif cell.attrib.get("t") == "inlineStr": raw = "".join(cell.itertext())
                    cells[col] = raw
                if cells: matrix.append([cells.get(i, "") for i in range(max(cells) + 1)])
    except (KeyError, IndexError, ET.ParseError, zipfile.BadZipFile) as error:
        raise TabularSchemaError("malformed or unsupported XLSX workbook") from error
    if not matrix:
        raise TabularSchemaError("workbook has no populated rows")
    headers = tuple(matrix[0]); rows = [dict(zip(headers, row)) for row in matrix[1:]]
    _validate_sheet(headers, rows, aliases, required)
    return headers, rows, "xlsx", _fingerprint(headers)


def _read_html_table(content: bytes, aliases: dict[str, tuple[str, ...]], *, required: tuple[str, ...]):
    text = html.unescape(content.decode("utf-8", errors="replace")); tables = re.findall(r"<table\b.*?</table>", text, flags=re.I | re.S)
    for table in tables:
        lines = [[re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)] for row in re.findall(r"<tr\b.*?</tr>", table, flags=re.I | re.S)]
        if not lines: continue
        headers = tuple(lines[0]); rows = [dict(zip(headers, row)) for row in lines[1:] if row]
        try: _validate_sheet(headers, rows, aliases, required)
        except TabularSchemaError: continue
        return headers, rows, "html-table-xls", _fingerprint(headers)
    raise TabularSchemaError("no supported table found in XLS capture")


class CanadaMeatAdapter:
    def __init__(self, source_id: str, jurisdiction_level: str, jurisdiction: str, source_url: str, coverage: str, require_categories: bool = False) -> None:
        self.source_id, self.jurisdiction_level, self.jurisdiction, self.source_url, self.coverage = source_id, jurisdiction_level, jurisdiction, source_url, coverage
        self.require_categories = require_categories
        self.adapter_version, self.schema_version = "ca-meat-v3-cfia-column-crosswalk", "ca-meat-tabular-workbook-v2"

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        required = ("plant_number", "name")
        if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            headers, rows, delimiter, schema_fingerprint = _read_xls(content, ALIASES, required=required)
        elif content[:2] == b"PK":
            headers, rows, delimiter, schema_fingerprint = _read_xlsx(content, ALIASES, required=required)
        elif content.lstrip().lower().startswith((b"<html", b"<!doctype html", b"<?xml")):
            headers, rows, delimiter, schema_fingerprint = _read_html_table(content, ALIASES, required=required)
        else:
            headers, rows, delimiter, schema_fingerprint = read_rows(content, ALIASES, required=required)
        mapping = resolve_mapping(headers, ALIASES)
        occurrences: Counter[tuple[str | None, ...]] = Counter(); accepted: list[dict[str, Any]] = []; quarantined: list[dict[str, Any]] = []
        for line, row in enumerate(rows, 2):
            plant_number, name = _clean(value(row, mapping, "plant_number")), _clean(value(row, mapping, "name"))
            key = occurrence_key(row, mapping, ("plant_number", "name", "city", "province", "function_codes", "animal_class")); occurrences[key] += 1
            plant_type, functions, animal_class = _clean(value(row, mapping, "plant_type")), _clean(_joined_source_codes(row) or value(row, mapping, "function_codes")), _clean(value(row, mapping, "animal_class"))
            cfia_categories, cfia_unknown, cfia_activity_seen = _cfia_activity(row) if self.require_categories else ((), False, False)
            categories = cfia_categories or _categories(plant_type, functions, animal_class)
            reasons: list[str] = []
            if not plant_number: reasons.append("missing_plant_number")
            if not name: reasons.append("missing_operator_or_plant_name")
            if self.require_categories and cfia_unknown: reasons.append("unknown_function_code")
            if self.require_categories and not categories and not cfia_unknown:
                reasons.append("unsupported_or_missing_facility_activity" if cfia_activity_seen or _joined_source_codes(row) else "unknown_function_code")
            if occurrences[key] > 1: reasons.append("duplicate_source_row")
            normalized = {
                "establishment_id": plant_number, "recognition_number": plant_number, "facility_grouping": f"provisional-{self.jurisdiction_level}-plant-number", "identity_review": "required-before-merge",
                "name": name, "operator_name": _clean(value(row, mapping, "operator_name")), "trading_name": _clean(value(row, mapping, "doing_business_as")) or name, "address": None,
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

    def _graph_candidate(self, record: dict[str, Any], artifact: SourceArtifact) -> dict[str, Any]:
        """Build a source-scoped graph candidate from one accepted source row.

        A facility node is always justified by the source establishment number.
        Operator and regulator edges are emitted only for the federal adapter:
        its workbook has an explicit operator column and its registry scope is
        federal. Ontario's plant-name field is deliberately not treated as an
        operator identity.
        """
        normalized = record["normalized"]
        facility_ref = f"facility:{record['source_record_key']}"
        support = [{"source_record_key": record["source_record_key"]}, {"artifact_sha256": artifact.sha256}]
        candidate: dict[str, Any] = {
            "contract_version": "graph-candidate-handoff-v1",
            "source_id": self.source_id,
            "source_row": record["source_row"],
            "source_record_key": record["source_record_key"],
            "source_values": record["source_values"],
            "publication": {"storage_state": "private", "privacy_status": "pending", "review_state": "review_required", "publication_status": "not_eligible", "release_id": None},
            "facilities": [{"local_ref": facility_ref, "source_identifier": {"identifier_type": "establishment-number", "value": str(normalized["establishment_id"])}}],
            "organizations": [],
            "relationships": [],
            "claims": [{"claim_domain": "operation", "claim_kind": "listed-meat-establishment", "facility_ref": facility_ref, "value_state": "known", "observed_at": artifact.retrieved_at_utc, "review_state": "review_required", "support": support}],
            "crosswalks": [],
        }
        if self.jurisdiction_level == "federal" and normalized.get("operator_name"):
            operator_ref = f"organization:operator:{record['source_record_key']}"
            regulator_ref = "organization:regulator:cfia"
            candidate["organizations"] = [
                {"local_ref": operator_ref, "source_identifier": {"identifier_type": "operator-name", "value": normalized["operator_name"]}},
                {"local_ref": regulator_ref, "source_identifier": {"identifier_type": "authority-source", "value": "CFIA"}},
            ]
            candidate["relationships"] = [
                {"relationship_type": "operator", "from_organization_ref": operator_ref, "target_facility_ref": facility_ref, "assertion_status": "asserted", "observed_at": artifact.retrieved_at_utc, "review_state": "review_required", "support": support, "assertion_basis": "explicit CFIA operator field"},
                {"relationship_type": "regulator", "from_organization_ref": regulator_ref, "target_facility_ref": facility_ref, "assertion_status": "asserted", "observed_at": artifact.retrieved_at_utc, "review_state": "review_required", "support": support, "assertion_basis": "CFIA federal registry scope"},
            ]
        return candidate

    def _write_graph_candidates(self, root: Path, records: list[dict[str, Any]], artifact: SourceArtifact) -> dict[str, Any]:
        """Persist identity-safe graph candidates and a row-free manifest.

        A row quarantined only for an unmapped activity code can still support
        a private facility/operator/regulator review edge. Rows with missing
        identity fields or duplicate source keys are excluded from graph
        staging because their identity is not sufficiently supported.
        """
        graph_root = root / "graph-candidates"
        relationship_counts: Counter[str] = Counter()
        for record in records:
            candidate = self._graph_candidate(record, artifact)
            candidate_dir = graph_root / hashlib.sha256(record["source_record_key"].encode("utf-8")).hexdigest()[:24]
            write_graph_candidate(candidate_dir, candidate)
            relationship_counts.update(item["relationship_type"] for item in candidate["relationships"])
        summary = {
            "contract_version": "graph-candidate-handoff-v1",
            "source_id": self.source_id,
            "candidate_count": len(records),
            "relationship_counts": dict(sorted(relationship_counts.items())),
            "storage_state": "private",
            "review_state": "review_required",
            "publication_status": "not_eligible",
            "universal_identity_assertions": 0,
            "row_payloads_included": False,
        }
        atomic_json(graph_root / "manifest.json", summary)
        return summary

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if artifact.sha256 != hashlib.sha256(raw).hexdigest() or artifact.byte_size != len(raw): raise ValueError("artifact provenance mismatch")
        result = self.parse_bytes(raw); root = Path(run_dir); accepted, quarantined = result["accepted"], result["quarantined"]; parsed = accepted + [item["record"] for item in quarantined]
        _, parsed_sha256, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed); _, normalized_sha256, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted); atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        anomaly_counts = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(source_id=self.source_id, adapter_version=self.adapter_version, schema_version=self.schema_version, artifact=artifact, input_rows=result["input_rows"], normalized_rows=len(accepted), quarantined_rows=len(quarantined), normalized_sha256=normalized_sha256, parsed_sha256=parsed_sha256, anomaly_counts=dict(sorted(anomaly_counts.items())))
        manifest.update({"country_code": "CA", "jurisdiction_level": self.jurisdiction_level, "jurisdiction": self.jurisdiction, "delimiter": result["delimiter"], "schema_fingerprint": result["schema_fingerprint"], "coverage": self.coverage, "geocoding": "disabled"})
        graph_records = accepted + [item["record"] for item in quarantined if set(item["reasons"]).issubset({"unknown_function_code"})]
        manifest["graph_candidates"] = self._write_graph_candidates(root, graph_records, artifact)
        manifest["graph_candidates"]["quarantined_identity_safe_rows"] = len(graph_records) - len(accepted)
        atomic_json(root / "manifest.json", manifest)
        write_operator_review_packet(root, manifest, source_scope=self.coverage, checks=("keep federal and provincial identities separate", "review address, phone, and coordinate privacy", "review duplicate plant-number rows without silent merge", "confirm function-code or plant-type mapping", "approve any project release separately"), blockers=("no national completeness claim", "publication and privacy approval pending", "source disappearance means not observed, not closure"))
        return manifest


ONTARIO_URL = "https://data.ontario.ca/dataset/a763088c-018d-48b7-bf47-3027a8c725b8/resource/ee6d559a-78de-40e6-b2ba-ad3c4a674b96/download/1._all_meat_plants.csv"
CFIA_URL = "https://active.inspection.gc.ca/scripts/meavia/reglist/download.asp?lang=e"


class OntarioMeatPlantsAdapter(CanadaMeatAdapter):
    def __init__(self) -> None: super().__init__("ca.ontario.meat-plants", "provincial", "Ontario", ONTARIO_URL, "Government of Ontario provincially licensed meat plants; Ontario only; plant name/number, contact, coordinates, and animal-class source fields; no national completeness claim")


class CfiaFederalMeatAdapter(CanadaMeatAdapter):
    def __init__(self) -> None: super().__init__("ca.cfia.federal-meat", "federal", "Canada", CFIA_URL, "CFIA federally registered meat establishments and licensed operators; federal registry only; provincial establishments are excluded", require_categories=True)
