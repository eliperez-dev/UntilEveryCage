"""Private adapter for the Ministry 853/2004 CSV contract.

The source has one row per establishment/activity observation. This adapter
preserves the complete source row, keeps sensitive address/tax/coordinate
values private, and quarantines ambiguity or malformed input instead of
silently merging or repairing it.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest
from pipeline.common.graph_candidates import build_identifier_graph_candidate, write_graph_candidates
from pipeline.common.review_metrics import build_private_review_metrics


REQUIRED = tuple(
    "precedente_bollo_cee;num_identificativo_produzione_commercializzazione;ragione_sociale;indirizzo;comune;provincia;codice_regione;regione;classificazione_stabilimento;codice_impianto_attivita;descrizione_impianto_attivita;prodotti_abilitati;specifica_prodotti;paesi_export_autorizzato;longitudine;latitudine;stato_localizzazione;cod_fiscale;p_iva;codice_comune;data_inizio_attivita;data_fine_attivita;stato_attivita;data_ultimo_aggiornamento;num_identificativo_produzione_commercializzazione_2".split(";")
)
STATUS = {"AUTORIZZATA": "Autorizzata", "REVOCATA": "Revocata", "SOSPESA": "Sospesa"}
DATE_FIELDS = ("data_inizio_attivita", "data_fine_attivita", "data_ultimo_aggiornamento")
MONTHS = {
    "GEN": 1, "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAG": 5, "MAY": 5,
    "GIU": 6, "JUN": 6, "LUG": 7, "JUL": 7, "AGO": 8, "AUG": 8,
    "SET": 9, "SEP": 9, "OTT": 10, "OCT": 10, "NOV": 11, "DIC": 12, "DEC": 12,
}


def clean(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def row_id(row: dict[str | None, Any], occurrence: int) -> str:
    stable_row = {"__extra_columns" if key is None else str(key): value for key, value in row.items()}
    payload = json.dumps(stable_row, sort_keys=True, ensure_ascii=False, default=list, separators=(",", ":"))
    return hashlib.sha256(f"{payload}|{occurrence}".encode()).hexdigest()


def _normalize_date(value: str | None) -> str | None:
    """Normalize the catalog's ISO and Italian/English abbreviated dates."""
    if not value or value.strip() in {"-", "—"}:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        pass
    parts = value.strip().upper().split("-")
    if len(parts) != 3 or not parts[0].isdigit() or not parts[2].isdigit():
        return None
    month = MONTHS.get(parts[1])
    if month is None:
        return None
    try:
        return date(2000 + int(parts[2]), month, int(parts[0])).isoformat()
    except ValueError:
        return None


def _date_state(value: str | None) -> str:
    if not value or value.strip() in {"-", "—"}:
        return "unknown"
    return "known" if _normalize_date(value) else "invalid"


class Italy853Adapter:
    source_id = "it.853-2004"
    adapter_version = "it-853-candidate-v2"
    schema_version = "it-853-csv-v2.0"

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                parsed: dict[str, Any]) -> dict[str, Any]:
        """Write the generic importer handoff for accepted private rows."""
        rows = [item["record"] if "record" in item else item for item in parsed["accepted"]]
        return write_handoff(run_dir, rows, artifact, source_id=self.source_id)

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        digest = hashlib.sha256(content).hexdigest()
        try:
            text = content.decode("utf-8-sig")
            reader = csv.DictReader(text.splitlines(), delimiter=";", strict=True)
            headers = tuple(reader.fieldnames or ())
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as error:
            raise ValueError("malformed or unsupported UTF-8 CSV") from error
        if headers != REQUIRED:
            raise ValueError("schema drift")

        occurrences: Counter[tuple[str | None, str | None]] = Counter()
        category_counts: Counter[str] = Counter()
        activity_counts: Counter[str] = Counter()
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        for line, row in enumerate(rows, 2):
            if None in row:
                # An extra delimited field changes the source shape rather
                # than merely making one observation incomplete; fail closed
                # so schema drift cannot enter a candidate run.
                raise ValueError("schema drift: row has extra columns")
            rec = clean(row.get(REQUIRED[1]))
            activity = clean(row.get("codice_impianto_attivita"))
            category_counts[clean(row.get("classificazione_stabilimento")) or "unknown"] += 1
            activity_counts[activity or "unknown"] += 1
            key = (rec, activity)
            occurrences[key] += 1
            reasons: list[str] = []
            if any(value is None or isinstance(value, list) for value in row.values()):
                reasons.append("malformed_row_shape")
            if not rec:
                reasons.append("missing_recognition_number")
            if not activity:
                reasons.append("missing_activity_code")
            if occurrences[key] > 1:
                reasons.append("ambiguous_repeated_recognition_activity")
            raw_status = clean(row.get("stato_attivita"))
            if raw_status and raw_status.upper() not in STATUS:
                reasons.append("unknown_status")
            status = STATUS.get(raw_status.upper()) if raw_status else None
            for field in DATE_FIELDS:
                value = clean(row.get(field))
                if _date_state(value) == "invalid":
                    reasons.append(f"invalid_{field}")
            municipality_code = clean(row.get("codice_comune"))
            geography_precision = "municipality-code" if municipality_code and len(municipality_code) == 6 else "unknown"
            normalized_dates = {field: _normalize_date(clean(row.get(field))) for field in DATE_FIELDS}
            normalized = {
                "establishment_id": rec,
                "recognition_number": rec,
                "source_activity_code": activity,
                "facility_grouping": "provisional-recognition-number",
                "facility_identity_state": "provisional-source-recognition-number",
                "observation_identity_state": "source-row-with-occurrence",
                "name": clean(row.get("ragione_sociale")),
                "trading_name": clean(row.get("ragione_sociale")),
                "address": None,
                "municipality": clean(row.get("comune")),
                "city": clean(row.get("comune")),
                "province": clean(row.get("provincia")),
                "region": clean(row.get("regione")),
                "country_code": "IT",
                "nation": "Italy",
                "geography_precision": geography_precision,
                "geography_state": "source-municipality-code" if geography_precision != "unknown" else "unknown",
                "classification": clean(row.get("classificazione_stabilimento")),
                "classification_state": "source-category-preserved" if clean(row.get("classificazione_stabilimento")) else "unknown",
                "classification_decision": "review_required",
                "activity_state": "source-code-preserved-unmapped",
                "activity_code": activity,
                "activity_description": clean(row.get("descrizione_impianto_attivita")),
                "products": clean(row.get("prodotti_abilitati")),
                "status": status,
                "status_state": "known" if status else "unknown",
                "dates": normalized_dates,
                "date_state": {field: _date_state(clean(row.get(field))) for field in DATE_FIELDS},
                "coordinates": None,
                "coordinate_state": "source-value-present-pending-review" if clean(row.get("longitudine")) or clean(row.get("latitudine")) else "unknown",
                "coordinate_precision": "source-precision-unknown" if clean(row.get("longitudine")) or clean(row.get("latitudine")) else "unresolved",
                "privacy_gate": "pending-review",
                "coordinate_gate": "review_required",
                "publication_gate": "blocked",
            }
            record = {
                "source_id": self.source_id,
                "source_row": line,
                "source_row_id": row_id(row, occurrences[key]),
                "source_record_key": f"{rec or 'unknown'}|{activity or 'unknown'}|{occurrences[key]}",
                "source_values": {"__extra_columns" if key is None else str(key): value for key, value in row.items()},
                "normalized": normalized,
            }
            if reasons:
                quarantined.append({"reasons": tuple(dict.fromkeys(reasons)), "record": record})
            else:
                accepted.append(record)
        return {"accepted": accepted, "quarantined": quarantined, "source_sha256": digest, "input_rows": len(rows), "schema_fingerprint": hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(), "source_category_counts": dict(sorted(category_counts.items())), "source_activity_counts": dict(sorted(activity_counts.items()))}

    def parse_file(self, path: str | Path) -> dict[str, Any]:
        return self.parse_bytes(Path(path).read_bytes())

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if artifact.sha256 != digest or artifact.byte_size != len(raw):
            raise ValueError("artifact provenance mismatch")
        result = self.parse_bytes(raw)
        root = Path(run_dir)
        accepted = result["accepted"]
        quarantined = result["quarantined"]
        parsed = accepted + [item["record"] for item in quarantined]
        _, parsed_sha256, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed)
        _, normalized_sha256, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        graph_candidates = []
        for item in parsed:
            record = item.get("record") if isinstance(item, dict) and isinstance(item.get("record"), dict) else item
            if not isinstance(record, dict):
                continue
            source_key = record.get("source_record_key")
            source_values = record.get("source_values")
            if not isinstance(source_key, str) or not source_key or not isinstance(source_values, dict):
                continue
            recognition = clean(source_values.get("num_identificativo_produzione_commercializzazione"))
            piva = clean(source_values.get("p_iva"))
            fiscal = clean(source_values.get("cod_fiscale"))
            graph_candidates.append(build_identifier_graph_candidate(
                source_id=self.source_id,
                source_record_key=source_key,
                source_values=source_values,
                facility_identifier=("eu_recognition_number", recognition) if recognition else None,
                organization_identifier=(("italian_vat", piva) if piva else ("italian_fiscal_code", fiscal) if fiscal else None),
                observed_at=artifact.retrieved_at_utc,
                source_row=record.get("source_row", 1),
            ))
        graph_manifest = write_graph_candidates(root / "graph", graph_candidates)
        anomaly_counts = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(
            source_id=self.source_id,
            adapter_version=self.adapter_version,
            schema_version=self.schema_version,
            artifact=artifact,
            input_rows=result["input_rows"],
            normalized_rows=len(accepted),
            quarantined_rows=len(quarantined),
            normalized_sha256=normalized_sha256,
            parsed_sha256=parsed_sha256,
            anomaly_counts=dict(sorted(anomaly_counts.items())),
        )
        manifest.update({"coverage": "Italian Ministry 853/2004 CSV; one source row per establishment/activity; 1069/2009 excluded", "geocoding": "disabled", "schema_fingerprint": result["schema_fingerprint"], "source_category_counts": result["source_category_counts"], "source_activity_counts": result["source_activity_counts"], "review_metrics": build_private_review_metrics(accepted, quarantined), "graph_candidate_summary": {key: graph_manifest[key] for key in ("candidate_count", "facility_identifier_candidates", "organization_identifier_candidates", "operator_relationship_candidates", "review_required_count", "publication_status")}})
        atomic_json(root / "manifest.json", manifest)
        return manifest
