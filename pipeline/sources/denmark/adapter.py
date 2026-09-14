"""Contract adapter for the Denmark Find Smiley XML source.

Parsing is private staging only.  This adapter never creates a release or
publishes coordinates; records with no stable source key are quarantined.
"""
from __future__ import annotations
import hashlib, json, os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from pipeline.contracts.adapter_contract import SourceArtifact

SOURCE_ID = "dk.smiley"
ADAPTER_VERSION = "denmark-smiley-contract-v1"

def _atomic(path: Path, payload: bytes) -> None:
    """Publish one complete staging file, never a partially written artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)

def _jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    """Serialize with stable ordering so reruns can be compared byte-for-byte."""
    payload = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, default=list) + "\n").encode() for row in rows)
    _atomic(path, payload)
    return hashlib.sha256(payload).hexdigest()

class DenmarkSmileyAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION

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
                record = {"source_id": SOURCE_ID, "source_record_key": key,
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
        parsed_hash = _jsonl(root / "parsed" / "records.jsonl", rows + [item["record"] for item in quarantined])
        normalized_hash = _jsonl(root / "normalized" / "records.jsonl", rows)
        _jsonl(root / "quarantined" / "records.jsonl", quarantined)
        # This state is deliberately private: validation cannot authorize release.
        manifest = {"source_id": SOURCE_ID, "adapter_version": ADAPTER_VERSION,
                    "schema_version": ADAPTER_VERSION, "checksum_sha256": actual,
                    "byte_size": len(raw), "input_rows": len(rows) + len(quarantined),
                    "normalized_rows": len(rows), "quarantined_rows": len(quarantined),
                    "parsed_sha256": parsed_hash, "normalized_sha256": normalized_hash,
                    "release_state": "not-created", "publication_state": "private-candidate",
                    "acquisition": artifact.__dict__}
        _atomic(root / "manifest.json", (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
        return manifest
