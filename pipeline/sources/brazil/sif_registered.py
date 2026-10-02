"""MAPA SIF registered establishments, preserving source rows and lifecycle evidence."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import fetch_source
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

SOURCE_ID = "br.sif.registered"
SOURCE_URL = "https://dados.agricultura.gov.br/dataset/062166e3-b515-4274-8e7d-68aadd64b820/resource/97277e92-264a-4dc0-9aea-f87b8ea93798/download/sigsifestabelecimentosregistradosnosif.csv"
ADAPTER_VERSION = "br-mapa-sif-registered-v2-private-location-evidence"
SCHEMA_VERSION = "br-mapa-sif-registered-csv-v1"
HEADERS = (
    "CPF_CNPJ", "RAZAO_SOCIAL", "NOME_FANTASIA", "NR_SIF", "DATA_RESERVA",
    "DT_REGISTRO", "NUMERO_PROCESSO", "SITUACAO", "LOGRADOURO", "BAIRRO",
    "CEP", "MUNICIPIO", "UF", "TELEFONE", "EMAIL", "AREA_CATEGORIA",
    "CATEGORIA_CLASSE", "DATA_OCORRENCIA", "DESCRICAO_OCORRENCIA",
)


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    return result if result and result not in {"-", "—"} else None


def _digest_row(row: dict[str, str], occurrence: int) -> str:
    stable = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{stable}|{occurrence}".encode("utf-8")).hexdigest()


class SifRegisteredAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION

    @staticmethod
    def minimize_for_handoff(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove row payloads before writing any API/import candidate handoff."""
        return [{
            "source_id": row["source_id"],
            "source_row": row["source_row"],
            "source_row_id": row.get("source_row_id"),
            "source_record_key": row["source_record_key"],
            "source_values": {},
            "normalized": row["normalized"],
        } for row in rows]

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        try:
            text = content.decode("utf-8-sig", errors="strict")
            reader = csv.DictReader(text.splitlines(), delimiter=";", strict=True)
            headers = tuple(reader.fieldnames or ())
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as error:
            raise ValueError("malformed or unsupported MAPA SIF CSV") from error
        if headers != HEADERS:
            raise ValueError("schema drift: unexpected MAPA SIF registered columns")

        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        duplicate_rows: Counter[str] = Counter()
        observations_by_sif: Counter[str] = Counter()
        municipality_counts: Counter[str] = Counter()
        for line, source_row in enumerate(rows, start=2):
            if None in source_row or any(not isinstance(value, str) for value in source_row.values()):
                raise ValueError("schema drift: MAPA SIF row has an unexpected field count")
            row = {str(key): value for key, value in source_row.items()}
            sif = _text(row.get("NR_SIF"))
            duplicate_key = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                                         separators=(",", ":")).encode("utf-8")).hexdigest()
            duplicate_rows[duplicate_key] += 1
            record_hash = _digest_row(row, duplicate_rows[duplicate_key])
            reasons: list[str] = []
            if not sif:
                reasons.append("missing_sif_number")
            state = _text(row.get("UF"))
            municipality = _text(row.get("MUNICIPIO"))
            if municipality:
                municipality_counts[municipality] += 1
            if sif:
                observations_by_sif[sif] += 1
            status = _text(row.get("SITUACAO"))
            area = _text(row.get("AREA_CATEGORIA"))
            category_class = _text(row.get("CATEGORIA_CLASSE"))
            record = {
                "source_id": SOURCE_ID,
                "source_row": line,
                "source_row_id": record_hash,
                "source_record_key": record_hash,
                # Full source values stay in restricted parsed evidence only.
                "source_values": row,
                "normalized": {
                    "establishment_id": sif,
                    "recognition_number": sif,
                    "facility_grouping": "provisional-map-sif-number",
                    "facility_identity_state": "source-scoped; no cross-source reconciliation",
                    "observation_identity_state": "source-row-content-hash-with-occurrence",
                    "country_code": "BR",
                    "nation": "Brazil",
                    "municipality": municipality,
                    "city": municipality,
                    "state": state,
                    "address": _text(row.get("LOGRADOURO")),
                    "postal_code": _text(row.get("CEP")),
                    "source_classification_code": area,
                    "source_classification_label": category_class,
                    "source_activity": "; ".join(x for x in (area, category_class) if x) or None,
                    # Source status and dates remain source statements. No active/closed
                    # interpretation is made without an authoritative codebook.
                    "source_status": status,
                    "status_state": "source-value-uninterpreted" if status else "unknown",
                    "source_registration_date": _text(row.get("DT_REGISTRO")),
                    "source_reservation_date": _text(row.get("DATA_RESERVA")),
                    "source_occurrence_date": _text(row.get("DATA_OCORRENCIA")),
                    "occurrence_state": "present-in-restricted-evidence" if _text(row.get("DESCRICAO_OCORRENCIA")) else "not-supplied",
                    # Address and postal evidence are retained in private
                    # location staging; names, CNPJ, contacts, and occurrence
                    # text remain out of the candidate location projection.
                    "coordinates": None,
                    "coordinate_state": "not-supplied-by-source",
                    "coordinate_precision": "unresolved",
                    "privacy_gate": "pending-review",
                    "coordinate_gate": "review_required",
                    "rights_gate": "review_required",
                    "publication_gate": "blocked",
                },
            }
            if reasons:
                quarantined.append({"reasons": reasons, "record": record})
            else:
                accepted.append(record)

        schema_fingerprint = hashlib.sha256(json.dumps(headers, ensure_ascii=False,
                                                         separators=(",", ":")).encode("utf-8")).hexdigest()
        return {
            "accepted": accepted,
            "quarantined": quarantined,
            "input_rows": len(rows),
            "schema_fingerprint": schema_fingerprint,
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "observation_rows_by_sif": dict(sorted(observations_by_sif.items())),
            "municipality_count": len(municipality_counts),
            "repeated_sif_row_count": sum(count for count in observations_by_sif.values() if count > 1),
        }

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact.sha256 or len(raw) != artifact.byte_size:
            raise ValueError("source artifact provenance mismatch")
        parsed = self.parse_bytes(raw)
        root = Path(run_dir)
        accepted = parsed["accepted"]
        quarantined = parsed["quarantined"]
        all_records = accepted + [item["record"] for item in quarantined]
        _, parsed_sha, _ = atomic_jsonl(root / "parsed" / "records.jsonl", all_records)
        _, normalized_sha, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        reasons = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(
            source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION, schema_version=SCHEMA_VERSION,
            artifact=artifact, input_rows=parsed["input_rows"], normalized_rows=len(accepted),
            quarantined_rows=len(quarantined), normalized_sha256=normalized_sha,
            parsed_sha256=parsed_sha, anomaly_counts=dict(sorted(reasons.items())),
        )
        manifest.update({
            "schema_fingerprint": parsed["schema_fingerprint"],
            "coverage": "MAPA SIF registered establishment rows; repeated SIF rows are preserved as distinct observations",
            "distinct_source_sif_candidates": len(parsed["observation_rows_by_sif"]),
            "repeated_sif_row_count": parsed["repeated_sif_row_count"],
            "municipality_name_count": parsed["municipality_count"],
            "geocoding": "disabled; city names are not converted to points",
            "release_state": "not-created",
            "publication_state": "private-candidate",
        })
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, handoff_dir: str | Path, artifact: SourceArtifact,
                                parsed: dict[str, Any]) -> dict[str, Any]:
        # The shared bridge calls this after reading normalized records; caller
        # provides minimized preview rows with source_values removed.
        return write_handoff(handoff_dir, parsed["accepted"], artifact, source_id=SOURCE_ID)


def fetch(*, output_root: str | Path, run_id: str, terms_review_path: str | Path,
          timeout_seconds: float = 180.0, max_bytes: int = 64 * 1024 * 1024) -> dict[str, Any]:
    return fetch_source(
        source_id=SOURCE_ID, url=SOURCE_URL, output_root=output_root,
        artifact_name="registered-establishments.csv", terms_review_path=terms_review_path,
        run_id=run_id, timeout_seconds=timeout_seconds, max_bytes=max_bytes,
        allowed_content_types=("text/csv", "application/csv", "application/octet-stream", "text/plain"),
        code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
        coverage="MAPA/DIPOA SIF registered-establishment CSV; repeated rows retained as observations",
        rights_caveat="MAPA catalog displays CC BY; local private acquisition authorized for this run; publication and dataset-specific reuse remain separately blocked",
        privacy_caveat="restricted private evidence; names, CNPJ, addresses, contacts, and occurrence text excluded from candidate handoff",
        artifact_validator=lambda path, _headers: SifRegisteredAdapter().parse_bytes(path.read_bytes()),
    )
