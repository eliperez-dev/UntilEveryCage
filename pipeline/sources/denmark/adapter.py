"""Contract adapter for the Denmark Find Smiley XML source.

Parsing is private staging only.  This adapter never creates a release or
publishes coordinates; records with no stable source key are quarantined.
"""
from __future__ import annotations
import hashlib, json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest
from pipeline.common.graph_candidates import build_identifier_graph_candidate, write_graph_candidates
from pipeline.common.review_metrics import build_private_review_metrics

SOURCE_ID = "dk.smiley"
ADAPTER_VERSION = "denmark-smiley-contract-v1"

def check_refresh(previous: dict[str, Any], current: dict[str, Any], *, max_count_delta: float = 0.25) -> None:
    """Fail closed on source/schema changes or implausible row-count shifts."""
    if previous.get("source_id") != current.get("source_id") or previous.get("schema_version") != current.get("schema_version"):
        raise ValueError("Denmark refresh schema or source identity changed")
    old, new = int(previous.get("normalized_rows", 0)), int(current.get("normalized_rows", 0))
    if old and abs(new - old) / old > max_count_delta:
        raise ValueError("Denmark refresh normalized row count drift exceeds threshold")

class DenmarkSmileyAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Map Denmark's stable source key into the generic candidate identity.

        This is an explicit source mapping: it does not fuzzy-match or infer a
        facility, and it preserves every original field in private source_values.
        """
        handoff_rows = []
        seen: set[str] = set()
        for row in rows:
            fields = row.get("source_fields", {})
            key = row.get("source_record_key")
            if not key or key in seen:
                raise ValueError("Denmark candidate contains missing or duplicate source identity")
            seen.add(key)
            classification = row.get("classification", {})
            handoff_rows.append({"source_id": SOURCE_ID, "source_row": row.get("source_row", 0),
                                 "source_record_key": key,
                                 "source_values": fields, "normalized": {
                                     "establishment_id": key, "trading_name": fields.get("Virksomhed"),
                                     "city": fields.get("By"), "postal_code": fields.get("Postnummer"),
                                     "country_code": "DK", "coordinate_precision": "city_postal",
                                     "coordinates": None,
                                     "activities": [fields.get("FVST_branchenummer")] if fields.get("FVST_branchenummer") else [],
                                     "activity_code": fields.get("FVST_branchenummer"),
                                     "classification_category": classification.get("category"),
                                     "classification_review_status": classification.get("review_status"),
                                     "in_default_map_scope": classification.get("default_visible", False),
                                     "classification_optional_filter": classification.get("optional_filter"),
                                     "privacy_gate": "pending", "coordinate_gate": "review_required",
                                     "publication_gate": "blocked"}})
        return write_handoff(run_dir, handoff_rows, artifact, source_id=SOURCE_ID)

    def run_registered(self, raw_path: str | Path, run_dir: str | Path, config: dict[str, Any]) -> dict[str, Any]:
        """Bridge the shared registered-input runner using recorded evidence."""
        required = ("source_url", "retrieved_at_utc", "checksum_sha256", "byte_size")
        missing = [key for key in required if not config.get(key)]
        if missing:
            raise ValueError("missing acquisition provenance: " + ", ".join(missing))
        raw = Path(raw_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != config["checksum_sha256"] or len(raw) != config["byte_size"]:
            raise ValueError("registered acquisition integrity mismatch")
        artifact = SourceArtifact(
            source_url=str(config["source_url"]), retrieved_at_utc=str(config["retrieved_at_utc"]),
            sha256=digest, byte_size=len(raw), publication_date=config.get("publication_date"),
            effective_date=config.get("effective_date"), code_version=str(config.get("code_version", ADAPTER_VERSION)),
            config_version=str(config.get("config_version", "unknown")), rights_caveat=config.get("rights_caveat"),
            privacy_caveat=config.get("privacy_caveat"), coverage=config.get("coverage"))
        return self.run(raw_path, run_dir, artifact)

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        """Parse one preserved artifact into private, human-gated candidate data."""
        raw = Path(raw_path).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != artifact.sha256 or len(raw) != artifact.byte_size:
            raise ValueError("acquisition metadata does not match raw artifact")
        rows: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        try:
            root = ET.fromstring(raw)
            for number, element in enumerate(root.iter(), 1):
                if element.tag.lower() != "row":
                    continue
                fields = {child.tag: (child.text or "").strip() or None for child in element}
                key = fields.get("ID_nummer") or fields.get("navnelbnr")
                record = {"source_id": SOURCE_ID, "source_row": number, "source_record_key": key,
                          "source_artifact_sha256": actual, "source_fields": fields,
                          "normalized": {"name": fields.get("Virksomhed"),
                                         "address": fields.get("Adresse"),
                                         "postcode": fields.get("Postnummer"),
                                         "city": fields.get("By"), "country_code": "DK",
                                         "coordinates": None}}
                # Without a stable source identity, normalization must not invent one.
                (quarantined if not key else rows).append({"reasons": ["missing_source_key"], "record": record} if not key else record)
        except ET.ParseError as exc:
            raise ValueError("invalid Denmark XML") from exc
        root = Path(run_dir)
        parsed_rows = rows + [item["record"] for item in quarantined]
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed_rows)
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", rows)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        graph_candidates = []
        for record in parsed_rows:
            fields = record.get("source_fields", {})
            key = record.get("source_record_key")
            if not isinstance(key, str) or not key:
                continue
            cvr = fields.get("CVR_nummer") or fields.get("cvrnr")
            cvr_text = str(cvr).strip() if cvr is not None else ""
            # CVR is a source-native eight-digit organization identifier.  Do
            # not turn labels, partial values, or punctuation-bearing values
            # into an organization node; the facility identity remains valid
            # even when the organization signal is unavailable.
            valid_cvr = cvr_text if re.fullmatch(r"\d{8}", cvr_text) else None
            graph_candidates.append(build_identifier_graph_candidate(
                source_id=SOURCE_ID,
                source_record_key=key,
                source_values=fields,
                facility_identifier=("findsmiley_id", key),
                organization_identifier=("cvr", valid_cvr) if valid_cvr else None,
                observed_at=artifact.retrieved_at_utc,
                source_row=record.get("source_row", 1),
                artifact_sha256=artifact.sha256,
                signal_bundle=[
                    {"kind": "source_identifier_cooccurrence", "identifier_types": ["findsmiley_id"], "connection_type": "exact"},
                    *([{"kind": "source_identifier_cooccurrence", "identifier_types": ["cvr"], "connection_type": "exact"}] if valid_cvr else []),
                ],
            ))
        graph_manifest = write_graph_candidates(root / "graph", graph_candidates)
        # This state is deliberately private: validation cannot authorize release.
        manifest = private_manifest(
            source_id=SOURCE_ID,
            adapter_version=ADAPTER_VERSION,
            schema_version=ADAPTER_VERSION,
            artifact=artifact,
            input_rows=len(parsed_rows),
            normalized_rows=len(rows),
            quarantined_rows=len(quarantined),
            normalized_sha256=normalized_hash,
            parsed_sha256=parsed_hash,
            anomaly_counts={"missing_source_key": len(quarantined)} if quarantined else {},
        )
        atomic_json(root / "manifest.json", manifest)
        manifest["review_metrics"] = build_private_review_metrics(rows, quarantined)
        manifest["graph_candidate_summary"] = {key: graph_manifest[key] for key in (
            "candidate_count", "facility_identifier_candidates", "organization_identifier_candidates",
            "operator_relationship_candidates", "review_required_count", "publication_status",
        )}
        atomic_json(root / "manifest.json", manifest)
        return manifest
