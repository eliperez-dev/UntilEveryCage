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


REQUIRED = tuple(
    "precedente_bollo_cee;num_identificativo_produzione_commercializzazione;ragione_sociale;indirizzo;comune;provincia;codice_regione;regione;classificazione_stabilimento;codice_impianto_attivita;descrizione_impianto_attivita;prodotti_abilitati;specifica_prodotti;paesi_export_autorizzato;longitudine;latitudine;stato_localizzazione;cod_fiscale;p_iva;codice_comune;data_inizio_attivita;data_fine_attivita;stato_attivita;data_ultimo_aggiornamento;num_identificativo_produzione_commercializzazione_2".split(";")
)
STATUS = {"AUTORIZZATA": "Autorizzata", "REVOCATA": "Revocata", "SOSPESA": "Sospesa"}
DATE_FIELDS = ("data_inizio_attivita", "data_fine_attivita", "data_ultimo_aggiornamento")


def clean(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def row_id(row: dict[str | None, Any], occurrence: int) -> str:
    stable_row = {"__extra_columns" if key is None else str(key): value for key, value in row.items()}
    payload = json.dumps(stable_row, sort_keys=True, ensure_ascii=False, default=list, separators=(",", ":"))
    return hashlib.sha256(f"{payload}|{occurrence}".encode()).hexdigest()


def _date_state(value: str | None) -> str:
    if not value:
        return "unknown"
    try:
        date.fromisoformat(value)
    except ValueError:
        return "invalid"
    return "known"


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
            normalized = {
                "establishment_id": rec,
                "recognition_number": rec,
                "source_activity_code": activity,
                "facility_grouping": "provisional-recognition-number",
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
                "activity_code": activity,
                "activity_description": clean(row.get("descrizione_impianto_attivita")),
                "products": clean(row.get("prodotti_abilitati")),
                "status": status,
                "status_state": "known" if status else "unknown",
                "dates": {field: clean(row.get(field)) for field in DATE_FIELDS},
                "date_state": {field: _date_state(clean(row.get(field))) for field in DATE_FIELDS},
                "coordinates": None,
                "coordinate_state": "source-value-present-pending-review" if clean(row.get("longitudine")) or clean(row.get("latitudine")) else "unknown",
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
        return {"accepted": accepted, "quarantined": quarantined, "source_sha256": digest, "input_rows": len(rows)}

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
        manifest["coverage"] = "Italian Ministry 853/2004 CSV; one source row per establishment/activity; 1069/2009 excluded"
        manifest["geocoding"] = "disabled"
        atomic_json(root / "manifest.json", manifest)
        return manifest
