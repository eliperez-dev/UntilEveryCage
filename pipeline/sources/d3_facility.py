"""D3 facility-master bridges for the shared private refresh runner.

This module only adapts existing source-local parsers to the D2 control plane.
It does not acquire, geocode, approve, promote, or publish records.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceAdapter, SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.refresh import AdapterCapabilities
from pipeline.germany import bltu_adapter
from pipeline.sources.uk.fsa_approved.adapter import FsaApprovedEstablishmentsAdapter
from pipeline.sources.uk.fss_approved.adapter import FssApprovedEstablishmentsAdapter
from pipeline.sources.us.fsis.adapter import FsisMpiAdapter

ROOT = Path(__file__).resolve().parent
SYNTHETIC_RETRIEVED_AT = "2026-01-01T00:00:00Z"


class GermanyBltuAdapter:
    """Typed bridge around the existing private BLtU export parser."""

    source_id = "de.locations"
    adapter_version = bltu_adapter.ADAPTER_VERSION
    schema_version = bltu_adapter.SCHEMA_VERSION

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        root = Path(run_dir)
        config = asdict(artifact)
        config.update({"source_id": self.source_id, "source_url": artifact.source_url,
                       "retrieved_at_utc": artifact.retrieved_at_utc,
                       "checksum_sha256": artifact.sha256, "byte_size": artifact.byte_size,
                       "publication_state": "private-candidate"})
        # Reuse the tested source-local parser in a private scratch directory,
        # then normalize its source ID to the authoritative registry identity.
        scratch = root / "_bltu"
        legacy = bltu_adapter.run(Path(raw_path), scratch, config)
        normalized = []
        for line in (scratch / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            row["source_id"] = self.source_id
            row["source_record_key"] = row.get("establishment_id")
            row.setdefault("normalized", {})
            row["normalized"]["source_id"] = self.source_id
            normalized.append(row)
        parsed = [json.loads(line) for line in (scratch / "parsed" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
        quarantined = [json.loads(line) for line in (scratch / "quarantined" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
        parsed_by_id = {
            str(item.get("source_values", [])[5] if isinstance(item.get("source_values"), list)
                and len(item.get("source_values", [])) > 5 else "").strip(): item
            for item in parsed
        }
        for row in parsed + [item for item in quarantined]:
            row["source_id"] = self.source_id
        for row in normalized:
            source_row = parsed_by_id.get(str(row.get("establishment_id", "")).strip())
            # The legacy BLtU parser emits a source-local normalized shape.
            # Adapt it here to the shared candidate handoff without changing
            # that parser's independently tested output contract.
            row["source_row"] = source_row.get("source_row") if source_row else None
            row["normalized"] = {
                "establishment_id": row.get("establishment_id"),
                "trading_name": row.get("establishment_name"),
                "city": row.get("city"),
                "activity_categories": [row.get("type")] if row.get("type") else [],
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "coordinate_status": row.get("coordinate_status"),
            }
            if source_row:
                values = source_row.get("source_values", {})
                headers = source_row.get("source_headers", [])
                row["source_values"] = dict(zip(headers, values)) if isinstance(values, list) else values
        def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=list) + "\n" for row in rows), encoding="utf-8")
        write_jsonl(root / "parsed" / "records.jsonl", parsed)
        write_jsonl(root / "normalized" / "records.jsonl", normalized)
        write_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        (root / "released").mkdir(parents=True, exist_ok=True)
        manifest = {**config, "source_id": self.source_id, "adapter_version": self.adapter_version,
                    "schema_version": self.schema_version, "checksum_sha256": hashlib.sha256(Path(raw_path).read_bytes()).hexdigest(),
                    "byte_size": Path(raw_path).stat().st_size, "input_rows": len(parsed),
                    "normalized_rows": len(normalized), "quarantined_rows": len(quarantined),
                    "release_state": "not-created", "publication_state": "private-candidate",
                    "geocoding": "disabled", "profile": "bltu-general-list"}
        (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        (root / "qa.json").write_text(json.dumps({"source_id": self.source_id, "input_rows": len(parsed), "normalized_rows": len(normalized), "quarantined_rows": len(quarantined), "drift_alarms": []}, sort_keys=True) + "\n", encoding="utf-8")
        return manifest


class D3FacilityRefreshAdapter:
    """Source-neutral runner hook for D3 facility sources."""

    def __init__(self, source_id: str, adapter_factory: Callable[[], SourceAdapter],
                 fixture_path: Path, source_url: str, adapter_version: str,
                 schema_version: str, acquisition: str) -> None:
        self.source_id = source_id
        self._factory = adapter_factory
        self.fixture_path = fixture_path
        self.source_url = source_url
        self.adapter_version = adapter_version
        self.schema_version = schema_version
        self.acquisition = acquisition

    def _artifact(self, path: Path) -> SourceArtifact:
        # A directory is a multi-file FSIS bundle; its source adapter records
        # per-role hashes and the bundle digest in the private manifest.
        if path.is_dir():
            parts = [p for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in {".csv", ".txt"}]
            payload = b"".join(p.read_bytes() for p in parts)
            size = sum(p.stat().st_size for p in parts)
        else:
            payload = path.read_bytes()
            size = len(payload)
        return SourceArtifact(source_url=self.source_url, retrieved_at_utc=SYNTHETIC_RETRIEVED_AT,
                              sha256=hashlib.sha256(payload).hexdigest(), byte_size=size,
                              code_version=self.adapter_version, config_version=self.schema_version,
                              rights_caveat="source-specific terms remain a human gate",
                              privacy_caveat="private candidate staging; privacy review remains required",
                              coverage=f"{self.source_id} source scope; no completeness claim")

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        if mode == "live-acquisition":
            raise RuntimeError(f"live acquisition is not unattended for {self.source_id}; use assisted local artifact")
        raw_path = artifact if mode == "local-artifact" else self.fixture_path
        if not raw_path.exists():
            raise FileNotFoundError(f"preserved artifact is unavailable for {self.source_id}: {raw_path}")
        source_artifact = self._artifact(raw_path)
        adapter = self._factory()
        status = run_private_lifecycle(raw_path, run_dir, source_artifact, adapter,
                                       health_as_of_utc=source_artifact.retrieved_at_utc)
        lifecycle_root = Path(status["run_dir"])
        manifest = status.get("manifest") or {}
        candidate_handoff = False
        if status.get("status") == "candidate-ready":
            rows = [json.loads(line) for line in (lifecycle_root / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
            write_handoff(lifecycle_root / "candidate-handoff", rows, source_artifact, source_id=self.source_id, profile="d3-facility-master")
            candidate_handoff = True
        return {"lifecycle_status": status.get("status"), "publication_state": status.get("publication_state", "unchanged"),
                "input_rows": manifest.get("input_rows", 0), "normalized_rows": manifest.get("normalized_rows", 0),
                "quarantined_rows": manifest.get("quarantined_rows", 0), "candidate_handoff": candidate_handoff,
                "review_required": True, "release_promoted": bool(status.get("release_promoted", False)),
                "public_surfaces": {"api": False, "map": False, "csv": False},
                "live_acquisition": self.acquisition}


def D3_DESCRIPTORS() -> tuple[dict[str, Any], ...]:
    return (
        {"source_id": "us.fsis", "country_code": "us", "url": "https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory", "factory": FsisMpiAdapter, "fixture": ROOT / "us" / "fsis" / "fixtures", "adapter_version": "us-fsis-candidate-v2", "schema_version": "us-fsis-mpi-v1", "acquisition": "operator_assisted_only"},
        {"source_id": "de.locations", "country_code": "de", "url": "https://www.bvl.bund.de/bltu", "factory": GermanyBltuAdapter, "fixture": ROOT.parent / "germany" / "fixtures" / "synthetic_bltu.csv", "adapter_version": bltu_adapter.ADAPTER_VERSION, "schema_version": bltu_adapter.SCHEMA_VERSION, "acquisition": "assisted_only"},
        {"source_id": "fsa_approved_establishments", "country_code": "gb", "url": "https://data.food.gov.uk/catalog/datasets/", "factory": FsaApprovedEstablishmentsAdapter, "fixture": ROOT / "uk" / "fsa_approved" / "fixtures" / "valid.csv", "adapter_version": "fsa-uk-v2-1", "schema_version": "fsa-uk-approved-v1", "acquisition": "bounded_private_fetch"},
        {"source_id": "fss_approved_establishments", "country_code": "gb", "url": "https://www.foodstandards.gov.scot/", "factory": FssApprovedEstablishmentsAdapter, "fixture": ROOT / "uk" / "fss_approved" / "fixtures" / "valid.csv", "adapter_version": "fss-scotland-v2-1", "schema_version": "fss-scotland-approved-v1", "acquisition": "bounded_private_fetch"},
    )


def register_d3(catalog: Any) -> None:
    for item in D3_DESCRIPTORS():
        if item["source_id"] not in catalog.sources:
            continue
        catalog.register(D3FacilityRefreshAdapter(item["source_id"], item["factory"], item["fixture"], item["url"], item["adapter_version"], item["schema_version"], item["acquisition"]), AdapterCapabilities(source_id=item["source_id"], adapter_version=item["adapter_version"], schema_version=item["schema_version"], acquisition=item["acquisition"], geocoding="disabled", publication="human_gate_required", adapter_path=str(item["fixture"].parent), country_code=item["country_code"]))

