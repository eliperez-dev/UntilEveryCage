"""Source-owned bridges for the first D2 adapter cohort.

The shared runner owns orchestration, retries, database boundaries, and
publication gates. This module only describes source-specific adapter entry
points and supplies small synthetic artifacts for deterministic contract tests.
It deliberately contains no real source rows or acquisition output.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceAdapter, SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.refresh import AdapterCapabilities

from .belgium.adapter import BelgiumOperatorsAdapter, CONFIG as BELGIUM_CONFIG
from .canada.adapter import CfiaFederalMeatAdapter, OntarioMeatPlantsAdapter
from .denmark.adapter import DenmarkSmileyAdapter
from .france.adapter import FranceDgalSectionIAdapter, FranceDgalSectionIIAdapter
from .italy.it_853_adapter import Italy853Adapter


ROOT = Path(__file__).resolve().parent
SYNTHETIC_RETRIEVED_AT = "2026-01-01T00:00:00Z"


@dataclass(frozen=True)
class SourceDescriptor:
    """Source-neutral metadata and factory for one first-wave adapter."""

    source_id: str
    country_code: str
    source_url: str
    adapter_factory: Callable[[], SourceAdapter]
    fixture_paths: tuple[Path, ...]
    adapter_version: str
    schema_version: str
    live_acquisition: str
    publication: str = "human_gate_required"

    def adapter(self) -> SourceAdapter:
        return self.adapter_factory()

    def artifact_for(self, raw_path: Path, *, retrieved_at_utc: str = SYNTHETIC_RETRIEVED_AT) -> SourceArtifact:
        raw = raw_path.read_bytes()
        return SourceArtifact(
            source_url=self.source_url,
            retrieved_at_utc=retrieved_at_utc,
            sha256=hashlib.sha256(raw).hexdigest(),
            byte_size=len(raw),
            code_version=self.adapter_version,
            config_version=self.schema_version,
            rights_caveat="source-specific terms remain a human gate",
            privacy_caveat="private candidate staging; privacy review remains required",
            coverage=f"{self.source_id} source scope; no completeness claim",
        )

    def readiness(self) -> dict[str, Any]:
        """Return capability facts without conflating acquisition and approval."""
        return {
            "source_id": self.source_id,
            "fixture_ready": True,
            "local_artifact_ready": True,
            "live_acquisition": self.live_acquisition,
            "private_pipeline": "fixture_contract_ready",
            "publication": self.publication,
            "geocoding": "disabled",
            "review_required": True,
        }


def _belgium() -> SourceAdapter:
    return BelgiumOperatorsAdapter(ROOT / "belgium" / "fixtures" / "synthetic_activity_codes.csv")


def _denmark() -> SourceAdapter:
    return DenmarkSmileyAdapter()


def _france_i() -> SourceAdapter:
    return FranceDgalSectionIAdapter()


def _france_ii() -> SourceAdapter:
    return FranceDgalSectionIIAdapter()


def _italy() -> SourceAdapter:
    return Italy853Adapter()


FIRST_WAVE: tuple[SourceDescriptor, ...] = (
    SourceDescriptor("dk.smiley", "DK", "https://pub.fvst.dk/publikationer/Smileydata.xml", _denmark, (ROOT / "denmark" / "fixtures" / "synthetic.xml",), "denmark-smiley-contract-v1", "denmark-smiley-contract-v1", "verified"),
    SourceDescriptor("be.locations", "BE", BELGIUM_CONFIG["operator_url"], _belgium, (ROOT / "belgium" / "fixtures" / "synthetic_operators.csv", ROOT / "belgium" / "fixtures" / "synthetic_activity_codes.csv"), BELGIUM_CONFIG["adapter_version"], BELGIUM_CONFIG["schema_version"], "assisted_only"),
    SourceDescriptor("ca.ontario.meat-plants", "CA", "https://data.ontario.ca/dataset/a763088c-018d-48b7-bf47-3027a8c725b8/resource/ee6d559a-78de-40e6-b2ba-ad3c4a674b96/download/1._all_meat_plants.csv", OntarioMeatPlantsAdapter, (ROOT / "canada" / "fixtures" / "ontario.csv",), "ca-meat-v2-workbook", "ca-meat-tabular-workbook-v1", "verified"),
    SourceDescriptor("ca.cfia.federal-meat", "CA", "https://active.inspection.gc.ca/scripts/meavia/reglist/download.asp?lang=e", CfiaFederalMeatAdapter, (ROOT / "canada" / "fixtures" / "cfia.csv",), "ca-meat-v2-workbook", "ca-meat-tabular-workbook-v1", "assisted_only"),
    SourceDescriptor("fr.dgal.section-i", "FR", "https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_ONG_DOM.txt", _france_i, (ROOT / "france" / "fixtures" / "section_i.csv",), "fr-dgal-853-v2", "fr-dgal-853-txt-v2", "verified"),
    SourceDescriptor("fr.dgal.section-ii", "FR", "https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_COL_LAGO.txt", _france_ii, (ROOT / "france" / "fixtures" / "section_ii.csv",), "fr-dgal-853-v2", "fr-dgal-853-txt-v2", "verified"),
    SourceDescriptor("it.853-2004", "IT", "https://www.dati.salute.gov.it/", _italy, (ROOT / "italy" / "fixtures" / "synthetic_853.csv",), "it-853-candidate-v2", "it-853-csv-v2.0", "verified"),
)

BY_SOURCE_ID = {descriptor.source_id: descriptor for descriptor in FIRST_WAVE}


class FirstWaveRefreshAdapter:
    """Adapt one source-owned lifecycle adapter to the shared D2 runner.

    Acquisition is intentionally not hidden here: fixture mode uses the
    checked-in synthetic artifact, local-artifact mode uses the caller's
    preserved path, and live-acquisition fails closed until a source-specific
    fetch contract is approved.
    """

    def __init__(self, descriptor: SourceDescriptor) -> None:
        self.descriptor = descriptor
        self.source_id = descriptor.source_id
        self.adapter_version = descriptor.adapter_version

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        if mode == "live-acquisition":
            raise RuntimeError("live acquisition is not wired into the D2 runner; use a preserved local artifact")
        raw_path = artifact if mode == "local-artifact" else self.descriptor.fixture_paths[0]
        if raw_path is None or not raw_path.is_file():
            raise FileNotFoundError(f"preserved artifact is unavailable for {self.source_id}")
        source_adapter = self.descriptor.adapter()
        source_artifact = self.descriptor.artifact_for(raw_path)
        status = run_private_lifecycle(
            raw_path, run_dir, source_artifact, source_adapter,
            health_as_of_utc=source_artifact.retrieved_at_utc,
        )
        lifecycle_root = Path(status["run_dir"])
        manifest = status.get("manifest") or {}
        candidate_handoff = False
        if status.get("status") == "candidate-ready":
            normalized = lifecycle_root / "normalized" / "records.jsonl"
            if isinstance(source_adapter, DenmarkSmileyAdapter):
                rows = [json.loads(line) for line in normalized.read_text(encoding="utf-8").splitlines() if line]
                source_adapter.write_candidate_handoff(lifecycle_root / "candidate-handoff", source_artifact, rows)
            else:
                rows = [json.loads(line) for line in normalized.read_text(encoding="utf-8").splitlines() if line]
                write_handoff(lifecycle_root / "candidate-handoff", rows, source_artifact, source_id=self.source_id)
            candidate_handoff = True
        return {
            "lifecycle_status": status.get("status"),
            "publication_state": status.get("publication_state", "unchanged"),
            "input_rows": manifest.get("input_rows", 0),
            "normalized_rows": manifest.get("normalized_rows", 0),
            "quarantined_rows": manifest.get("quarantined_rows", 0),
            "candidate_handoff": candidate_handoff,
            "review_required": True,
            "release_promoted": bool(status.get("release_promoted", False)),
            "public_surfaces": {"api": False, "map": False, "csv": False},
        }


def register_first_wave(catalog: Any) -> None:
    """Register the D2 facility adapters and D3 evidence adapters."""
    for descriptor in FIRST_WAVE:
        capabilities = AdapterCapabilities(
            source_id=descriptor.source_id,
            adapter_version=descriptor.adapter_version,
            schema_version=descriptor.schema_version,
            acquisition=descriptor.live_acquisition,
            geocoding="disabled",
            publication=descriptor.publication,
            adapter_path=f"pipeline/sources/{descriptor.country_code.lower()}",
            country_code=descriptor.country_code.lower(),
        )
        catalog.register(FirstWaveRefreshAdapter(descriptor), capabilities)
    # D3 extends the same control plane with facility-master adapters.  Keep
    # this registration beside the D2 bridge so one runner can select either
    # cohort while source-local contracts remain isolated.
    from .d3_facility import register_d3
    register_d3(catalog)
    from pipeline.sources.us.evidence import register_evidence_sources
    register_evidence_sources(catalog)


def descriptor_for(source_id: str) -> SourceDescriptor:
    try:
        return BY_SOURCE_ID[source_id]
    except KeyError as error:
        raise KeyError(f"source is not in the D2 first-wave cohort: {source_id}") from error


def run_fixture(source_id: str, run_dir: str | Path, *, retrieved_at_utc: str = SYNTHETIC_RETRIEVED_AT) -> dict[str, Any]:
    """Run one synthetic artifact through the private lifecycle.

    The returned value is aggregate-only. Source rows remain in the caller's
    private run directory and are never returned in the report.
    """
    descriptor = descriptor_for(source_id)
    raw_path = descriptor.fixture_paths[0]
    artifact = descriptor.artifact_for(raw_path, retrieved_at_utc=retrieved_at_utc)
    source_adapter = descriptor.adapter()
    status = run_private_lifecycle(raw_path, run_dir, artifact, source_adapter, health_as_of_utc=retrieved_at_utc)
    if status.get("status") == "candidate-ready":
        lifecycle_root = Path(status["run_dir"])
        if isinstance(source_adapter, DenmarkSmileyAdapter):
            rows = [json.loads(line) for line in (lifecycle_root / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
            source_adapter.write_candidate_handoff(lifecycle_root / "candidate-handoff", artifact, rows)
        else:
            rows = [json.loads(line) for line in (lifecycle_root / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
            write_handoff(lifecycle_root / "candidate-handoff", rows, artifact, source_id=source_id)
    manifest = status.get("manifest") or {}
    return {
        "source_id": source_id,
        "status": status.get("status"),
        "publication_state": status.get("publication_state", "unchanged"),
        "release_promoted": bool(status.get("release_promoted", False)),
        "input_rows": manifest.get("input_rows"),
        "normalized_rows": manifest.get("normalized_rows"),
        "quarantined_rows": manifest.get("quarantined_rows"),
        "candidate_handoff": status.get("status") == "candidate-ready",
        "health_written": (Path(status["run_dir"]) / "source-health.json").is_file() if status.get("run_dir") else False,
    }


def readiness_report() -> list[dict[str, Any]]:
    return [descriptor.readiness() for descriptor in FIRST_WAVE]


__all__ = ["BY_SOURCE_ID", "FIRST_WAVE", "FirstWaveRefreshAdapter", "SourceDescriptor", "descriptor_for", "readiness_report", "register_first_wave", "run_fixture"]
