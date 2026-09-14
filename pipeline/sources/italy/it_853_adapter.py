from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

REQUIRED = tuple(
    "precedente_bollo_cee;num_identificativo_produzione_commercializzazione;ragione_sociale;indirizzo;comune;provincia;codice_regione;regione;classificazione_stabilimento;codice_impianto_attivita;descrizione_impianto_attivita;prodotti_abilitati;specifica_prodotti;paesi_export_autorizzato;longitudine;latitudine;stato_localizzazione;cod_fiscale;p_iva;codice_comune;data_inizio_attivita;data_fine_attivita;stato_attivita;data_ultimo_aggiornamento;num_identificativo_produzione_commercializzazione_2".split(";")
)
STATUS = {"AUTORIZZATA": "Autorizzata", "REVOCATA": "Revocata", "SOSPESA": "Sospesa"}


def clean(v):
    return v.strip() if v and v.strip() else None


def row_id(row, occurrence):
    payload = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{payload}|{occurrence}".encode()).hexdigest()


# Content identity plus occurrence preserves rerun stability without line-number identity.
class Italy853Adapter:
    source_id = "it.853-2004"
    adapter_version = "it-853-candidate-v1"
    schema_version = "it-853-csv-v2.0"

    def parse_bytes(self, content):
        digest = hashlib.sha256(content).hexdigest()
        rows = list(csv.DictReader(content.decode("utf-8-sig").splitlines(), delimiter=";"))
        if not rows or tuple(rows[0]) != REQUIRED:
            raise ValueError("schema drift")
        seen = set()
        occurrences = {}
        accepted = []
        quarantined = []
        for line, row in enumerate(rows, 2):
            rec = clean(row.get(REQUIRED[1]))
            act = clean(row.get("codice_impianto_attivita"))
            key = (rec, act)
            reasons = []
            occurrences[key] = occurrences.get(key, 0) + 1
            if None in row or None in row.values() or any(isinstance(v, list) for v in row.values()):
                reasons.append("malformed_row_shape")
            if not rec:
                reasons.append("missing_recognition_number")
            if not act:
                reasons.append("missing_activity_code")
            # Repeated recognition/activity rows are quarantined instead of silently collapsed.
            if key in seen:
                reasons.append("ambiguous_repeated_recognition_activity")
            seen.add(key)
            status = clean(row.get("stato_attivita"))
            if status and status.upper() not in STATUS:
                reasons.append("unknown_status")
            status = STATUS.get(status.upper()) if status else None
            # Sensitive source_values remain private; normalized exposure is screened.
            out = {
                "source_id": self.source_id,
                "source_row": line,
                "source_row_id": row_id(row, occurrences[key]),
                "source_values": dict(row),
                "normalized": {
                    "recognition_number": rec,
                    "facility_grouping": "provisional-recognition-number",
                    "name": clean(row.get("ragione_sociale")),
                    "address": None,
                    "municipality": clean(row.get("comune")),
                    "region": clean(row.get("regione")),
                    "activity_code": act,
                    "activity_description": clean(row.get("descrizione_impianto_attivita")),
                    "products": clean(row.get("prodotti_abilitati")),
                    "status": status,
                    "coordinates": None,
                    "privacy_gate": "pending-review",
                    "publication_gate": "blocked",
                },
            }
            (quarantined if reasons else accepted).append(
                {"reasons": tuple(reasons), "record": out} if reasons else out
            )
        return {"accepted": accepted, "quarantined": quarantined, "source_sha256": digest, "input_rows": len(rows)}

    def parse_file(self, path):
        return self.parse_bytes(Path(path).read_bytes())

    def run(self, raw_path, run_dir, artifact):
        raw = Path(raw_path).read_bytes()
        result = self.parse_bytes(raw)
        if artifact.sha256 != result["source_sha256"] or artifact.byte_size != len(raw):
            raise ValueError("artifact provenance mismatch")
        root = Path(run_dir)
        (root / "normalized").mkdir(parents=True, exist_ok=True)
        (root / "quarantined").mkdir(parents=True, exist_ok=True)
        normalized = "".join(json.dumps(x, sort_keys=True, default=list) + "\n" for x in result["accepted"])
        quarantined = "".join(json.dumps(x, sort_keys=True, default=list) + "\n" for x in result["quarantined"])
        (root / "normalized" / "records.jsonl").write_text(normalized, encoding="utf-8")
        (root / "quarantined" / "records.jsonl").write_text(quarantined, encoding="utf-8")
        manifest = {
            "source_id": self.source_id, "schema_version": self.schema_version,
            "source_url": artifact.source_url, "retrieved_at_utc": artifact.retrieved_at_utc,
            "sha256": artifact.sha256, "checksum_sha256": artifact.sha256,
            "byte_size": artifact.byte_size, "code_version": artifact.code_version,
            "config_version": artifact.config_version, "publication_state": "private-candidate",
            "release_state": "not-created", "input_rows": result["input_rows"],
            "normalized_rows": len(result["accepted"]), "quarantined_rows": len(result["quarantined"]),
            "normalized_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
            "acquisition": {"source_url": artifact.source_url, "retrieved_at_utc": artifact.retrieved_at_utc, "sha256": artifact.sha256, "byte_size": artifact.byte_size},
            "handoff_contract": "candidate_handoff-v1",
        }
        (root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return manifest
