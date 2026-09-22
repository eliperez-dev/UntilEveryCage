"""Shared-runner evidence-event adapters for APHIS observations.

APHIS registrations and inspection exports are evidence events, not facility
master rows.  This bridge reuses the existing APHIS parser and private
lifecycle handoff while making the source kind explicit to the D3 runner.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from pipeline.common.evidence_sink import import_private_evidence
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

from .aphis.adapter import AphisPublicSearchAdapter, CONFIG
from .aphis.handoff import write_private_handoff


ROOT = Path(__file__).resolve().parent
SOURCES: dict[str, dict[str, Any]] = {
    "us.aphis": {
        "profile": "registrations",
        "fixture": ROOT / "aphis" / "fixtures" / "registrations.csv",
        "source_url": CONFIG["public_search_url"],
        "adapter_version": CONFIG["adapter_version"] + "-evidence",
    },
    "us.inspections": {
        "profile": "inspections",
        "fixture": ROOT / "aphis" / "fixtures" / "inspections.csv",
        "source_url": CONFIG["inspection_reports_url"],
        "adapter_version": CONFIG["adapter_version"] + "-inspection-evidence",
    },
}


class EvidenceEventAdapter:
    source_kind = "evidence_event"
    schema_version = "us-evidence-event-v1"

    def __init__(self, source_id: str) -> None:
        if source_id not in SOURCES:
            raise ValueError(f"unsupported evidence source: {source_id}")
        self.source_id = source_id
        self.config = SOURCES[source_id]
        self.adapter_version = self.config["adapter_version"]

    def _artifact(self, path: Path, options: Mapping[str, Any]) -> SourceArtifact:
        raw = path.read_bytes()
        acquisition = options.get("acquisition") if isinstance(options.get("acquisition"), Mapping) else {}
        return SourceArtifact(
            source_url=str(acquisition.get("final_url") or options.get("source_url") or self.config["source_url"]),
            retrieved_at_utc=str(acquisition.get("retrieved_at_utc") or options.get("retrieved_at_utc") or "2026-01-01T00:00:00Z"),
            sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw),
            effective_date=options.get("effective_date"),
            code_version=self.adapter_version, config_version=self.schema_version,
            rights_caveat="APHIS evidence terms and attribution require review before publication",
            privacy_caveat="Evidence rows remain private pending privacy and factual review",
            coverage=f"{self.source_id} profile observations only; no facility completeness claim",
        )

    def acquire(self, *, run_dir: Path, options: Mapping[str, Any]) -> Mapping[str, Any]:
        """Use the existing bounded APHIS documented-download callable."""
        review_paths = options.get("terms_review_paths")
        review = review_paths.get(self.source_id) if isinstance(review_paths, Mapping) else None
        review = review or options.get("terms_review_path")
        if not review:
            raise RuntimeError("terms review is required for live acquisition")
        from .aphis.acquire import fetch_profile
        profile = self.config["profile"]
        metadata = fetch_profile(
            profile=profile, output_root=run_dir / "acquisition",
            terms_review_path=Path(str(review)), run_id=run_dir.name,
            timeout_seconds=float(options.get("timeout_seconds", 60.0)),
            max_bytes=int(options.get("max_bytes", 128 * 1024 * 1024)),
        )
        return metadata

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        if mode == "live-acquisition":
            raise RuntimeError("APHIS evidence live acquisition remains operator-assisted; use preserved local artifact")
        path = artifact if mode == "local-artifact" else Path(self.config["fixture"])
        if not path.is_file():
            raise FileNotFoundError(f"evidence artifact is unavailable for {self.source_id}")
        source_artifact = self._artifact(path, options)
        delegate = AphisPublicSearchAdapter()
        parsed_result = delegate.parse_bytes(path.read_bytes())
        if parsed_result["profile"] != self.config["profile"]:
            raise ValueError(f"APHIS artifact profile {parsed_result['profile']} does not match {self.config['profile']}")

        accepted = [self._reidentify(record) for record in parsed_result["accepted"]]
        quarantined = [self._reidentify(item["record"]) | {"reasons": item["reasons"]}
                       for item in parsed_result["quarantined"]]
        parsed = accepted + [item["record"] for item in quarantined]
        parsed_path, parsed_sha, _ = atomic_jsonl(run_dir / "parsed" / "records.jsonl", parsed)
        normalized_path, normalized_sha, _ = atomic_jsonl(run_dir / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(run_dir / "quarantined" / "records.jsonl", quarantined)
        anomaly_counts = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(
            source_id=self.source_id, adapter_version=self.adapter_version,
            schema_version=self.schema_version, artifact=source_artifact,
            input_rows=len(parsed), normalized_rows=len(accepted), quarantined_rows=len(quarantined),
            normalized_sha256=normalized_sha, parsed_sha256=parsed_sha,
            anomaly_counts=dict(sorted(anomaly_counts.items())),
        )
        manifest.update({
            "source_kind": self.source_kind, "source_profile": self.config["profile"],
            "evidence_type_counts": dict(sorted(Counter(r["normalized"].get("event_type") for r in accepted).items())),
            "event_date_states": dict(sorted(Counter("known" if r["normalized"].get("event_date") else "unknown" for r in accepted).items())),
            "linkage_candidate_count": sum(len(r["normalized"].get("linkage_candidates", [])) for r in accepted),
            "facility_identity_state": "not_asserted",
            "graph_migration": False, "publication_gate": "blocked", "test_only": True,
            "coverage": f"{self.source_id} source-native evidence events only; no facility merge or completeness claim",
        })
        atomic_json(run_dir / "manifest.json", manifest)
        handoff = write_private_handoff(
            run_dir / "evidence-handoff", accepted, source_artifact,
            profile=self.config["profile"], source_sha256=source_artifact.sha256,
            source_id=self.source_id, entity_scope="evidence_event", graph_candidate_emission=True,
        )
        return {
            "source_kind": self.source_kind,
            "source_profile": self.config["profile"],
            "input_rows": len(parsed), "normalized_rows": len(accepted),
            "quarantined_rows": len(quarantined),
            "evidence_event_rows": len(accepted),
            "evidence_type_counts": manifest["evidence_type_counts"],
            "event_date_states": manifest["event_date_states"],
            "linkage_candidate_count": manifest["linkage_candidate_count"],
            "facility_identity_state": "not_asserted",
            "candidate_handoff": True,
            "handoff_sha256": handoff["normalized_sha256"],
            "review_required": True, "graph_migration": False,
            "public_surfaces": {"api": False, "map": False, "csv": False},
        }

    def _reidentify(self, record: dict[str, Any]) -> dict[str, Any]:
        # The parser is source-owned and emits us.aphis.  The runner contract
        # keeps us.inspections distinct without inventing a cross-source ID.
        if self.source_id == "us.aphis":
            return record
        value = json.loads(json.dumps(record))
        value["source_id"] = self.source_id
        value["normalized"]["source_id"] = self.source_id
        return value


def register_evidence_sources(catalog: Any) -> None:
    from pipeline.contracts.refresh import AdapterCapabilities

    for source_id, config in SOURCES.items():
        catalog.register(
            EvidenceEventAdapter(source_id),
            AdapterCapabilities(
                source_id=source_id, adapter_version=config["adapter_version"],
                schema_version=EvidenceEventAdapter.schema_version,
                acquisition="assisted_only", geocoding="disabled",
                publication="human_gate_required", adapter_path="pipeline/sources/us/evidence.py",
                country_code="us", source_kind="evidence_event",
                operational_classification="assisted", live_callable=False,
            ),
        )


__all__ = ["EvidenceEventAdapter", "SOURCES", "register_evidence_sources", "import_private_evidence"]
