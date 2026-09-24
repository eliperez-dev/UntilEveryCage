"""Private source adapter for Italian Regulation (EC) 1069/2009 ABP plants."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

SOURCE_ID = "it.1069-2009"
SCHEMA_VERSION = "it-1069-csv-current-2026-09"
ADAPTER_VERSION = "it-1069-candidate-v2"
HEADERS = (
    "precedente_bollo_cee", "num_identificativo_produzione_commercializzazione", "ragione_sociale",
    "indirizzo", "comune", "provincia", "codice_regione", "regione",
    "classificazione_stabilimento", "codice_impianto_attivita", "descrizione_impianto_attivita",
    "prodotti_abilitati", "specifica_prodotti_abilitati", "paesi_export_autorizzato", "longitudine", "latitudine",
    "stato_localizzazione", "cod_fiscale", "p_iva", "codice_comune", "data_inizio_attivita",
    "data_fine_attivita", "stato_attivita", "data_ultimo_aggiornamento",
)
STATUSES = {"AUTORIZZATA": "Autorizzata", "REVOCATA": "Revocata", "SOSPESA": "Sospesa"}


def _clean(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() and value.strip() not in {"-", "—"} else None


def _row_hash(row: dict[str | None, Any], occurrence: int) -> str:
    stable = {"__extra_columns" if key is None else str(key): value for key, value in row.items()}
    data = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{data}|{occurrence}".encode("utf-8")).hexdigest()


class Italy1069Adapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                parsed: dict[str, Any]) -> dict[str, Any]:
        return write_handoff(run_dir, parsed["accepted"], artifact, source_id=self.source_id)

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        try:
            reader = csv.DictReader(content.decode("utf-8-sig", errors="strict").splitlines(), delimiter=";", strict=True)
            headers = tuple(reader.fieldnames or ())
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as error:
            raise ValueError("malformed or unsupported UTF-8 1069 CSV") from error
        if headers != HEADERS:
            raise ValueError("schema drift")
        occurrences: Counter[str] = Counter()
        coordinate_rejections: Counter[str] = Counter()
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        for line, row in enumerate(rows, 2):
            if None in row or any(not isinstance(value, str) for value in row.values()):
                raise ValueError("schema drift: row has an unexpected field count")
            recognition = _clean(row.get("num_identificativo_produzione_commercializzazione"))
            activity = _clean(row.get("codice_impianto_attivita"))
            category = _clean(row.get("classificazione_stabilimento"))
            natural_key = "|".join((recognition or "", activity or "", category or ""))
            occurrences[natural_key] += 1
            reasons: list[str] = []
            coordinate_reasons: list[str] = []
            if not recognition:
                reasons.append("missing_1069_recognition_number")
            raw_status = _clean(row.get("stato_attivita"))
            if raw_status and raw_status.upper() not in STATUSES:
                reasons.append("unknown_activity_status")
            status = STATUSES.get(raw_status.upper()) if raw_status else None
            lat_raw, lon_raw = _clean(row.get("latitudine")), _clean(row.get("longitudine"))
            coordinates = None
            if bool(lat_raw) != bool(lon_raw):
                coordinate_reasons.append("incomplete_coordinate_pair")
            elif lat_raw and lon_raw:
                try:
                    lat, lon = float(lat_raw), float(lon_raw)
                except ValueError:
                    coordinate_reasons.append("invalid_source_coordinates")
                else:
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        coordinate_reasons.append("source_coordinates_out_of_range")
                    elif lat == 0 and lon == 0:
                        coordinate_reasons.append("zero_zero_source_coordinates")
                    else:
                        coordinates = {"latitude": lat, "longitude": lon, "precision": "source-precision-unknown"}
            coordinate_rejections.update(coordinate_reasons)
            name = _clean(row.get("ragione_sociale"))
            municipality = _clean(row.get("comune"))
            status_date = _clean(row.get("data_ultimo_aggiornamento"))
            normalized = {
                "establishment_id": recognition, "recognition_number": recognition,
                "facility_grouping": "provisional-1069-recognition-number",
                "facility_identity_state": "source-scoped-provisional; no cross-regulation merge",
                "observation_identity_state": "source-row-hash-with-occurrence",
                "name": name, "trading_name": name, "address": None,
                "location_role": "recognized-1069-establishment-location",
                "location_semantics": "source-recognized-ABP-establishment-address; not-operating-proof",
                "source_location_state": "source-address-private-pending-review" if _clean(row.get("indirizzo")) else "unknown",
                "municipality": municipality, "city": municipality,
                "municipality_code": _clean(row.get("codice_comune")),
                "province": _clean(row.get("provincia")), "region": _clean(row.get("regione")),
                "region_code": _clean(row.get("codice_regione")), "country_code": "IT", "nation": "Italy",
                "regulation": "EC 1069/2009", "classification": _clean(row.get("classificazione_stabilimento")),
                "activity_code": activity, "activity_description": _clean(row.get("descrizione_impianto_attivita")),
                "products": _clean(row.get("prodotti_abilitati")),
                "product_specification": _clean(row.get("specifica_prodotti_abilitati")),
                "authorized_export_countries": _clean(row.get("paesi_export_autorizzato")),
                "previous_approval_number": _clean(row.get("precedente_bollo_cee")),
                "linked_853_recognition_number": None,
                "linked_853_recognition_number_state": "not-supplied-by-current-1069-artifact",
                "status": status, "status_state": "known" if status else "unknown",
                "source_updated_at": status_date, "source_updated_at_state": "source-value" if status_date else "unknown",
                "coordinates": coordinates,
                "coordinate_state": ("source-value-present-pending-review" if coordinates else
                                      "source-coordinate-claim-rejected" if coordinate_reasons else "unknown"),
                "coordinate_precision": "source-precision-unknown" if coordinates else "unresolved",
                "coordinate_provenance_state": "catalog-notes-some-OSM-contributor-coordinates; row-level-origin-unspecified" if coordinates else "not-supplied",
                "privacy_gate": "pending-review", "coordinate_gate": "review_required",
                "rights_gate": "review_required", "publication_gate": "blocked",
            }
            record = {
                "source_id": self.source_id, "source_row": line, "source_row_id": _row_hash(row, occurrences[natural_key]),
                "source_record_key": f"{_row_hash(row, occurrences[natural_key])}",
                "source_values": {str(key): value for key, value in row.items()}, "normalized": normalized,
            }
            if reasons:
                quarantined.append({"reasons": tuple(dict.fromkeys(reasons)), "record": record})
            else:
                accepted.append(record)
        fingerprint = hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return {"accepted": accepted, "quarantined": quarantined, "input_rows": len(rows),
                "coordinate_rejections": dict(sorted(coordinate_rejections.items())),
                "schema_fingerprint": fingerprint, "source_sha256": hashlib.sha256(content).hexdigest(),
                "recognized_1069_rows": sum(bool(_clean(row.get("num_identificativo_produzione_commercializzazione"))) for row in rows)}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if artifact.sha256 != digest or artifact.byte_size != len(raw):
            raise ValueError("artifact provenance mismatch")
        parsed = self.parse_bytes(raw)
        root = Path(run_dir)
        accepted, quarantined = parsed["accepted"], parsed["quarantined"]
        all_records = accepted + [item["record"] for item in quarantined]
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", all_records)
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        reasons = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(source_id=self.source_id, adapter_version=self.adapter_version,
                                    schema_version=self.schema_version, artifact=artifact,
                                    input_rows=parsed["input_rows"], normalized_rows=len(accepted),
                                    quarantined_rows=len(quarantined), normalized_sha256=normalized_hash,
                                    parsed_sha256=parsed_hash, anomaly_counts=dict(sorted(reasons.items())))
        manifest.update({"schema_fingerprint": parsed["schema_fingerprint"],
                         "coverage": "Italy Ministry 1069/2009 animal-by-product establishments; source rows only; not unioned with 853/2004",
                         "geocoding": "disabled", "coordinate_provenance_caveat": "catalog notes some OSM contributor coordinates; row-level provenance is unspecified",
                         "out_of_scope_rows": 0,
                         "coordinate_rejections": parsed["coordinate_rejections"]})
        atomic_json(root / "manifest.json", manifest)
        return manifest
