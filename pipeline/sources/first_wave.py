"""Source-owned bridges for the first D2 adapter cohort.

The shared runner owns orchestration, retries, database boundaries, and
publication gates. This module only describes source-specific adapter entry
points and supplies small synthetic artifacts for deterministic contract tests.
It deliberately contains no real source rows or acquisition output.
"""
from __future__ import annotations

import hashlib
import json
import re
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
from .italy.it_1069_adapter import Italy1069Adapter
from .australia.npi import NpiFacilitiesAdapter
from .australia.sa_epa import SaEpaLicensedActivitiesAdapter


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
        live_callable = self.source_id in {"be.locations", "ca.ontario.meat-plants", "ca.cfia.federal-meat", "fr.dgal.section-i", "fr.dgal.section-ii", "it.853-2004"}
        operational = "terms-blocked" if live_callable else "assisted"
        return {
            "source_id": self.source_id,
            "fixture_ready": True,
            "local_artifact_ready": True,
            "live_acquisition": self.live_acquisition,
            "operational_classification": operational,
            "live_callable": live_callable,
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


def _italy_1069() -> SourceAdapter:
    return Italy1069Adapter()


def _australia_npi() -> SourceAdapter:
    return NpiFacilitiesAdapter()


def _australia_sa_epa() -> SourceAdapter:
    return SaEpaLicensedActivitiesAdapter()


FIRST_WAVE: tuple[SourceDescriptor, ...] = (
    SourceDescriptor("dk.smiley", "DK", "https://pub.fvst.dk/publikationer/Smileydata.xml", _denmark, (ROOT / "denmark" / "fixtures" / "synthetic.xml",), "denmark-smiley-contract-v1", "denmark-smiley-contract-v1", "verified"),
    SourceDescriptor("be.locations", "BE", BELGIUM_CONFIG["operator_url"], _belgium, (ROOT / "belgium" / "fixtures" / "synthetic_operators.csv", ROOT / "belgium" / "fixtures" / "synthetic_activity_codes.csv"), BELGIUM_CONFIG["adapter_version"], BELGIUM_CONFIG["schema_version"], "assisted_only"),
    SourceDescriptor("ca.ontario.meat-plants", "CA", "https://data.ontario.ca/dataset/a763088c-018d-48b7-bf47-3027a8c725b8/resource/ee6d559a-78de-40e6-b2ba-ad3c4a674b96/download/1._all_meat_plants.csv", OntarioMeatPlantsAdapter, (ROOT / "canada" / "fixtures" / "ontario.csv",), "ca-meat-v2-workbook", "ca-meat-tabular-workbook-v1", "verified"),
    SourceDescriptor("ca.cfia.federal-meat", "CA", "https://active.inspection.gc.ca/scripts/meavia/reglist/download.asp?lang=e", CfiaFederalMeatAdapter, (ROOT / "canada" / "fixtures" / "cfia.csv",), "ca-meat-v2-workbook", "ca-meat-tabular-workbook-v1", "assisted_only"),
    SourceDescriptor("fr.dgal.section-i", "FR", "https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_ONG_DOM.txt", _france_i, (ROOT / "france" / "fixtures" / "section_i.csv",), "fr-dgal-853-v2", "fr-dgal-853-txt-v2", "verified"),
    SourceDescriptor("fr.dgal.section-ii", "FR", "https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_COL_LAGO.txt", _france_ii, (ROOT / "france" / "fixtures" / "section_ii.csv",), "fr-dgal-853-v2", "fr-dgal-853-txt-v2", "verified"),
    SourceDescriptor("it.853-2004", "IT", "https://www.dati.salute.gov.it/", _italy, (ROOT / "italy" / "fixtures" / "synthetic_853.csv",), "it-853-candidate-v2", "it-853-csv-v2.0", "verified"),
    SourceDescriptor("it.1069-2009", "IT", "https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-i-sottoprodotti-di-origine-animale/", _italy_1069, (ROOT / "italy" / "fixtures" / "synthetic_1069.csv",), "it-1069-provisional-v1", "it-1069-synthetic-contract-v1", "assisted_only"),
    SourceDescriptor("au.npi.facilities", "AU", "https://data.gov.au/data/dataset/043f58e0-a188-4458-b61c-04e5b540aea4", _australia_npi, (ROOT / "australia" / "fixtures" / "npi_facilities.csv",), "au-npi-facilities-v1", "au-npi-csv-v1", "assisted_only"),
    SourceDescriptor("au.sa.epa.licensed-activities", "AU", "https://data.sa.gov.au/data/dataset/8fdb86ff-d3d1-4f9e-85a5-bed4080d5ee1", _australia_sa_epa, (ROOT / "australia" / "fixtures" / "sa_epa_activities.geojson",), "au-sa-epa-licensed-activities-v1", "au-sa-epa-geojson-v1", "assisted_only"),
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

    def acquire(self, *, run_dir: Path, options: Mapping[str, Any]) -> Mapping[str, Any]:
        """Invoke an existing bounded source fetch, when explicitly granted.

        The runner performs the source-scoped authorization check before this
        method is called.  This hook only wires existing acquisition modules;
        it does not create a new HTTP client or discover undocumented routes.
        """
        review_paths = options.get("terms_review_paths")
        review = review_paths.get(self.source_id) if isinstance(review_paths, Mapping) else None
        review = review or options.get("terms_review_path")
        if not review:
            raise RuntimeError("terms review is required for live acquisition")
        root = run_dir / "acquisition"
        run_id = run_dir.name
        timeout = float(options.get("timeout_seconds", 60.0))
        max_bytes = int(options.get("max_bytes", 128 * 1024 * 1024))
        if self.source_id == "be.locations":
            from .belgium.acquire import fetch_pair
            pair = fetch_pair(output_root=root, terms_review_path=Path(str(review)), run_id=run_id, timeout_seconds=timeout, max_bytes=max_bytes)
            return {"artifact_path": pair["operator"]["artifact_path"], "companion_artifact_path": pair["activity_codes"]["artifact_path"], "acquisition": pair}
        if self.source_id in {"ca.ontario.meat-plants", "ca.cfia.federal-meat"}:
            from .canada.acquire import fetch_source_artifact
            source = "cfia" if self.source_id == "ca.cfia.federal-meat" else "ontario"
            return fetch_source_artifact(source=source, output_root=root, terms_review_path=Path(str(review)), run_id=run_id, timeout_seconds=timeout, max_bytes=max_bytes)
        if self.source_id in {"fr.dgal.section-i", "fr.dgal.section-ii"}:
            from .france.acquire import fetch_section
            section = "I" if self.source_id.endswith("section-i") else "II"
            return fetch_section(section=section, output_root=root, terms_review_path=Path(str(review)), run_id=run_id, timeout_seconds=timeout, max_bytes=max_bytes)
        if self.source_id == "it.853-2004":
            from .italy.acquire import fetch
            return fetch(output_root=root, run_id=run_id, terms_review_path=Path(str(review)), timeout_seconds=timeout, max_bytes=max_bytes)
        raise RuntimeError(f"no approved live callable for {self.source_id}; use assisted local artifact")

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        if mode == "live-acquisition":
            raise RuntimeError("live acquisition is not wired into the D2 runner; use a preserved local artifact")
        raw_path = artifact if mode == "local-artifact" else self.descriptor.fixture_paths[0]
        if raw_path is None or not raw_path.is_file():
            raise FileNotFoundError(f"preserved artifact is unavailable for {self.source_id}")
        source_adapter = self.descriptor.adapter()
        if self.source_id == "au.npi.facilities":
            try:
                source_adapter.validate_schema(raw_path.read_bytes())
            except ValueError as error:
                if "schema drift" in str(error).lower():
                    return {
                        "input_rows": 0,
                        "normalized_rows": 0,
                        "quarantined_rows": 0,
                        "schema_status": "schema-drift",
                        "drift_alarms": [str(error)],
                        "candidate_handoff": False,
                        "review_required": True,
                        "public_surfaces": {"api": False, "map": False, "csv": False},
                    }
                raise
        acquisition = options.get("acquisition")
        if self.source_id == "be.locations" and isinstance(acquisition, Mapping) and acquisition.get("companion_artifact_path"):
            # The Belgian adapter joins two source artifacts.  Use the
            # acquired companion codebook instead of silently falling back to
            # the checked-in synthetic fixture.
            companion_path = Path(str(acquisition["companion_artifact_path"]))
            companion_facts = acquisition.get("acquisition", {}).get("activity_codes", {}) if isinstance(acquisition.get("acquisition"), Mapping) else {}
            companion_raw = companion_path.read_bytes()
            companion_artifact = SourceArtifact(
                source_url=str(companion_facts.get("final_url") or companion_facts.get("requested_url") or self.descriptor.source_url),
                retrieved_at_utc=str(companion_facts.get("retrieved_at_utc") or SYNTHETIC_RETRIEVED_AT),
                sha256=hashlib.sha256(companion_raw).hexdigest(), byte_size=len(companion_raw),
                code_version=self.adapter_version, config_version=self.descriptor.schema_version,
                rights_caveat="source-specific terms remain a human gate",
                privacy_caveat="private candidate staging; privacy review remains required",
                coverage="Belgian activity-code companion artifact; not a facility list",
            )
            source_adapter = BelgiumOperatorsAdapter(companion_path, companion_artifact)
        acquisition = options.get("acquisition") if isinstance(options.get("acquisition"), Mapping) else {}
        if self.source_id == "it.1069-2009" and mode == "local-artifact":
            # A local copy is not provenance by itself. Require its operator
            # sidecar before the parser can accept it; row values never enter
            # this manifest path.
            sidecar = raw_path.with_name("acquisition-metadata.json")
            if not sidecar.is_file():
                raise ValueError("preserved ABP artifact provenance sidecar is required")
            facts = json.loads(sidecar.read_text(encoding="utf-8"))
            required_facts = ("source_url", "retrieved_at_utc", "sha256", "byte_size", "terms_review_reference")
            if not isinstance(facts, Mapping) or any(not facts.get(key) for key in required_facts):
                raise ValueError("preserved ABP artifact provenance sidecar is incomplete")
            raw_bytes = raw_path.read_bytes()
            if facts["sha256"] != hashlib.sha256(raw_bytes).hexdigest() or int(facts["byte_size"]) != len(raw_bytes):
                raise ValueError("preserved ABP artifact provenance digest mismatch")
            if not isinstance(facts["terms_review_reference"], str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", facts["terms_review_reference"]):
                raise ValueError("preserved ABP terms review reference is invalid")
            acquisition = {**acquisition, **facts}
        source_artifact = self.descriptor.artifact_for(raw_path)
        acquisition_facts = acquisition
        if self.source_id == "au.sa.epa.licensed-activities" and mode == "local-artifact":
            metadata = options.get("artifact_metadata")
            if isinstance(metadata, Mapping) and "source_url" not in metadata:
                metadata = metadata.get(self.source_id)
            if not isinstance(metadata, Mapping):
                raise RuntimeError("local SA EPA artifact metadata is required; supply official URL, UTC retrieval time, hash, byte size, and edition date")
            required = ("source_url", "retrieved_at_utc", "sha256", "byte_size")
            missing = [field for field in required if metadata.get(field) in (None, "")]
            if metadata.get("publication_date") in (None, "") and metadata.get("effective_date") in (None, ""):
                missing.append("effective_date or publication_date")
            if missing:
                raise RuntimeError("incomplete local SA EPA artifact metadata: " + ", ".join(missing))
            if str(metadata["source_url"]) not in {
                "https://data.sa.gov.au/data/dataset/8fdb86ff-d3d1-4f9e-85a5-bed4080d5ee1",
                "https://data.sa.gov.au/data/dataset/8fdb86ff-d3d1-4f9e-85a5-bed4080d5ee1/resource/26e076f3-c37f-4089-8f28-3f7c9afd997e/download/topo_epa_activities_wgs84.geojson",
            }:
                raise RuntimeError("local SA EPA artifact URL does not match the recorded source")
            source_artifact = SourceArtifact(
                source_url=str(metadata["source_url"]), retrieved_at_utc=str(metadata["retrieved_at_utc"]),
                sha256=str(metadata["sha256"]), byte_size=int(metadata["byte_size"]),
                publication_date=metadata.get("publication_date"), effective_date=metadata.get("effective_date"),
                code_version=self.adapter_version, config_version=self.descriptor.schema_version,
                rights_caveat=str(metadata.get("rights_caveat") or "source terms unresolved; private staging only"),
                privacy_caveat=str(metadata.get("privacy_caveat") or "privacy review required; private staging only"),
                coverage=self.descriptor.source_id + "; no completeness claim",
            )
            acquisition_facts = {}
        if self.source_id == "be.locations" and isinstance(acquisition.get("acquisition"), Mapping):
            acquisition_facts = acquisition["acquisition"].get("operator", {})
        if acquisition_facts:
            source_artifact = SourceArtifact(
                source_url=str(acquisition_facts.get("final_url") or acquisition_facts.get("requested_url") or acquisition_facts.get("source_url") or source_artifact.source_url),
                retrieved_at_utc=str(acquisition_facts.get("retrieved_at_utc") or source_artifact.retrieved_at_utc),
                sha256=str(acquisition_facts.get("sha256") or source_artifact.sha256),
                byte_size=int(acquisition_facts.get("byte_size") or source_artifact.byte_size),
                publication_date=acquisition_facts.get("publication_date"), effective_date=acquisition_facts.get("effective_date"),
                code_version=self.adapter_version, config_version=self.descriptor.schema_version,
                rights_caveat=(f"terms pending; review reference {acquisition_facts['terms_review_reference']}"
                               if self.source_id == "it.1069-2009" and acquisition_facts.get("terms_review_reference")
                               else source_artifact.rights_caveat),
                privacy_caveat=source_artifact.privacy_caveat,
                coverage=source_artifact.coverage, redirects=tuple(acquisition_facts.get("redirects") or ()),
            )
        status = run_private_lifecycle(
            raw_path, run_dir, source_artifact, source_adapter,
            health_as_of_utc=source_artifact.retrieved_at_utc,
        )
        if self.source_id == "au.sa.epa.licensed-activities" and status.get("status") == "failed":
            raise RuntimeError("SA EPA private validation failed; previous validated state is preserved")
        if status.get("status") == "failed":
            # Do not let a lifecycle validation failure look like a successful
            # acquisition to the shared runner. Preserve only a row-free class
            # signal; exception text can contain source values or local paths.
            if status.get("error_type") == "ValueError":
                raise ValueError("schema validation failed")
            raise RuntimeError("source lifecycle validation failed")
        if self.source_id == "it.1069-2009" and mode == "local-artifact":
            # Keep the row-free acquisition facts beside the private run so
            # the required provenance and terms reference survive a replay.
            safe_facts = {key: acquisition[key] for key in (
                "source_url", "retrieved_at_utc", "sha256", "byte_size",
                "publication_date", "effective_date", "terms_review_reference",
            ) if key in acquisition}
            (run_dir / "acquisition-metadata.json").write_text(
                json.dumps(safe_facts, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        lifecycle_root = Path(status["run_dir"])
        manifest = status.get("manifest") or {}
        candidate_handoff = False
        if status.get("status") == "candidate-ready":
            normalized = lifecycle_root / "normalized" / ("licences.jsonl" if self.source_id == "au.sa.epa.licensed-activities" else "records.jsonl")
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
        readiness = descriptor.readiness()
        capabilities = AdapterCapabilities(
            source_id=descriptor.source_id,
            adapter_version=descriptor.adapter_version,
            schema_version=descriptor.schema_version,
            acquisition=descriptor.live_acquisition,
            geocoding="disabled",
            publication=descriptor.publication,
            adapter_path=f"pipeline/sources/{descriptor.country_code.lower()}",
            country_code=descriptor.country_code.lower(),
            operational_classification=readiness["operational_classification"],
            live_callable=readiness["live_callable"],
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
