"""Privacy-minimizing adapter for Catalonia's official feed/SANDACH register."""
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

SOURCE_ID = "es.cat.feed-sandach"
ADAPTER_VERSION = "es-cat-feed-sandach-v1"
SCHEMA_VERSION = "es-cat-socrata-m48e-zdz9-v1"
HEADERS = ("nom_establiment", "adre_a", "municipi", "codi_postal", "codi_municipi_idescat", "comarca", "codi_comarca", "prov_ncia", "n_m_registre", "nom_activitat", "alimentaci_animal_aa_sandach", "data_alta_de_l_activitat", "empresa")
EXPORT_HEADERS = ("Nom establiment", "Adreça", "Municipi", "Codi postal", "Codi municipi (idescat)", "Comarca", "Codi Comarca", "Província", "Núm Registre", "Nom Activitat", "Alimentació Animal (AA) - SANDACH (S)", "Data alta de l'Activitat", "Empresa")


def _clean(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


class CataloniaFeedSandachAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        try:
            reader = csv.DictReader(content.decode("utf-8-sig", errors="strict").splitlines(), strict=True)
            headers = tuple(" ".join((value or "").split()) for value in (reader.fieldnames or ()))
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as error:
            raise ValueError("malformed or unsupported UTF-8 Catalonia CSV") from error
        if headers != EXPORT_HEADERS:
            raise ValueError("schema drift")
        rename = dict(zip(EXPORT_HEADERS, HEADERS))
        accepted, quarantined = [], []
        seen: Counter[str] = Counter()
        sector_counts: Counter[str] = Counter()
        for line, row in enumerate(rows, 2):
            if None in row or any(not isinstance(value, str) for value in row.values()):
                raise ValueError("schema drift: unexpected field count")
            row = {rename[key]: value for key, value in row.items()}
            registration = _clean(row.get("n_m_registre"))
            municipality_code = _clean(row.get("codi_municipi_idescat"))
            municipality = _clean(row.get("municipi"))
            activity = _clean(row.get("nom_activitat"))
            sector = _clean(row.get("alimentaci_animal_aa_sandach"))
            # The official register number is the source identity.  Do not
            # derive identity from names or addresses (which can be personal data).
            if not registration or not municipality_code or not activity or not sector:
                quarantined.append({"source_row": line, "reason": "missing_required_identity_or_scope_field"})
                continue
            seen[registration] += 1
            key = hashlib.sha256(f"{registration}|{seen[registration]}".encode()).hexdigest()
            sector_counts[sector] += 1
            normalized = {
                "establishment_id": registration,
                "source_record_key": key,
                "country_code": "ES", "nation": "Spain", "autonomous_community": "Catalonia",
                "jurisdiction_level": "autonomous-community", "source_scope": "Catalonia feed and SANDACH register only",
                "municipality": municipality, "city": municipality,
                "municipality_code": municipality_code, "postal_code": _clean(row.get("codi_postal")),
                "comarca": _clean(row.get("comarca")), "comarca_code": _clean(row.get("codi_comarca")),
                "province": _clean(row.get("prov_ncia")), "activity": activity, "sector": sector,
                "registered_at": _clean(row.get("data_alta_de_l_activitat")),
                "coordinate_state": "not-supplied",
                "coordinate_precision": "unmapped-no-source-coordinates",
                "privacy_gate": "minimized-private-preview", "coordinate_gate": "unmapped",
                "rights_gate": "review_required", "publication_gate": "blocked",
            }
            # Name, company, and street address are deliberately never copied
            # into parsed normalized rows or candidate handoff.
            accepted.append({"source_id": SOURCE_ID, "source_row": line, "source_row_id": key,
                             "source_record_key": key, "source_values": {}, "normalized": normalized})
        fingerprint = hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return {"accepted": accepted, "quarantined": quarantined, "input_rows": len(rows),
                "schema_fingerprint": fingerprint, "source_sha256": hashlib.sha256(content).hexdigest(),
                "sector_counts": dict(sorted(sector_counts.items()))}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if artifact.sha256 != hashlib.sha256(raw).hexdigest() or artifact.byte_size != len(raw):
            raise ValueError("artifact provenance mismatch")
        parsed = self.parse_bytes(raw)
        root = Path(run_dir)
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed["accepted"])
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", parsed["accepted"])
        atomic_jsonl(root / "quarantined" / "records.jsonl", parsed["quarantined"])
        manifest = private_manifest(source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION,
                                    schema_version=SCHEMA_VERSION, artifact=artifact,
                                    input_rows=parsed["input_rows"], normalized_rows=len(parsed["accepted"]),
                                    quarantined_rows=len(parsed["quarantined"]), normalized_sha256=normalized_hash,
                                    parsed_sha256=parsed_hash, anomaly_counts={"missing_required_identity_or_scope_field": len(parsed["quarantined"])})
        manifest.update({"schema_fingerprint": parsed["schema_fingerprint"], "source_sha256": parsed["source_sha256"],
                         "coverage": "Catalonia autonomous community only; feed and specified SANDACH register scope; not Spain-wide",
                         "sector_counts": parsed["sector_counts"], "out_of_scope_rows": 0,
                         "location_handling": "none supplied; no geocoding or invented facility points"})
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                parsed: dict[str, Any]) -> dict[str, Any]:
        return write_handoff(run_dir, parsed["accepted"], artifact, source_id=SOURCE_ID,
                             emit_graph_candidates=False)
