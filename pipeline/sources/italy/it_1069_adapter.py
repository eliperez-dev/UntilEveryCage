"""Provisional, synthetic-contract adapter for Italy's separate ABP source.

The upstream 1069/2009 export schema has not been verified. This adapter only
accepts the explicitly synthetic contract below; it makes no upstream schema
claim and does not infer facility identity or 853/2004 relationships.
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
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

FIELDS = ("source_observation_id", "abp_category_code", "source_activity_code", "source_status", "effective_date", "linked_853_recognition_number")
STATUS = {"active": "active", "inactive": "inactive", "suspended": "suspended", "unknown": "unknown"}


class Italy1069Adapter:
    source_id = "it.1069-2009"
    adapter_version = "it-1069-provisional-v1"
    schema_version = "it-1069-synthetic-contract-v1"

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        try:
            reader = csv.DictReader(content.decode("utf-8-sig").splitlines(), strict=True)
            headers = tuple(reader.fieldnames or ())
            if headers != FIELDS:
                raise ValueError("schema drift: artifact does not match the explicitly synthetic ABP contract")
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as exc:
            raise ValueError("malformed synthetic-contract artifact") from exc
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        occurrences: Counter[str] = Counter()
        for line, row in enumerate(rows, start=2):
            sid = (row.get("source_observation_id") or "").strip()
            category = (row.get("abp_category_code") or "").strip()
            activity = (row.get("source_activity_code") or "").strip()
            status_raw = (row.get("source_status") or "").strip().lower()
            occurrences[sid] += 1
            reasons = []
            if None in row or any(not isinstance(v, str) for v in row.values()): reasons.append("malformed_row_shape")
            if not sid: reasons.append("missing_source_observation_id")
            if not category: reasons.append("missing_abp_category_code")
            if not activity: reasons.append("missing_source_activity_code")
            if occurrences[sid] > 1: reasons.append("repeated_source_observation_id")
            if status_raw not in STATUS: reasons.append("unknown_source_status")
            raw_date = (row.get("effective_date") or "").strip()
            normalized_date = None
            if raw_date:
                try: normalized_date = date.fromisoformat(raw_date).isoformat()
                except ValueError: reasons.append("invalid_effective_date")
            values = {key: (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
            payload = json.dumps({"line": line, "values": values}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            observation = {
                "source_id": self.source_id, "source_row": line,
                "source_row_id": hashlib.sha256(payload.encode()).hexdigest(),
                "source_record_key": f"{sid or 'unknown'}|{occurrences[sid]}",
                "source_values": values,
                "normalized": {
                    "observation_identity_state": "source-observation-id-only",
                    # The shared candidate contract keys source observations
                    # by the supplied ID. This is source-ID identity only,
                    # not a reviewed or cross-source facility assertion.
                    "establishment_id": sid or None,
                    "facility_identity_state": "source-id-only-unreviewed",
                    "source_observation_id": sid or None,
                    "abp_category_code": category or None,
                    "abp_category_state": "source-code-preserved-unmapped" if category else "unknown",
                    "source_activity_code": activity or None,
                    "activity_state": "source-code-preserved-unmapped" if activity else "unknown",
                    "source_status": STATUS.get(status_raw),
                    "status_state": "source-value-preserved-uninterpreted",
                    "effective_date": normalized_date,
                    "effective_date_state": "known" if normalized_date else ("invalid" if "invalid_effective_date" in reasons else "unknown"),
                    "linked_853_recognition_number": None,
                    "cross_source_link_state": "unreviewed-link-value-retained-only" if values.get("linked_853_recognition_number") else "not-supplied",
                    "country_code": "IT", "geocoding": "disabled", "privacy_gate": "pending-review",
                    "rights_gate": "review_required", "publication_gate": "blocked",
                },
            }
            (quarantined if reasons else accepted).append({"reasons": tuple(dict.fromkeys(reasons)), "record": observation} if reasons else observation)
        return {"accepted": accepted, "quarantined": quarantined, "input_rows": len(rows),
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "category_counts": dict(sorted(Counter(x["normalized"]["abp_category_code"] for x in accepted).items())),
                "activity_counts": dict(sorted(Counter(x["normalized"]["source_activity_code"] for x in accepted).items()))}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact.sha256 or len(raw) != artifact.byte_size:
            raise ValueError("artifact provenance mismatch")
        result = self.parse_bytes(raw)
        accepted, quarantined = result["accepted"], result["quarantined"]
        parsed = accepted + [item["record"] for item in quarantined]
        root = Path(run_dir)
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed)
        _, norm_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        counts = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(source_id=self.source_id, adapter_version=self.adapter_version,
            schema_version=self.schema_version, artifact=artifact, input_rows=len(parsed),
            normalized_rows=len(accepted), quarantined_rows=len(quarantined), normalized_sha256=norm_hash,
            parsed_sha256=parsed_hash, anomaly_counts=dict(sorted(counts.items())))
        manifest.update({"coverage": "synthetic fixture/local artifact under provisional schema; upstream schema not verified",
                         "source_category_counts": result["category_counts"], "source_activity_counts": result["activity_counts"],
                         "geocoding": "disabled", "identity_policy": "source observation IDs only; no facility identity or 853 link inference"})
        atomic_json(root / "manifest.json", manifest)
        return manifest
