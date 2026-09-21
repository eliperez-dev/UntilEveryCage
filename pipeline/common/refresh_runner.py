"""Deterministic, sequential, source-neutral private refresh runner.

This is a control plane only.  It never contains source SQL, never publishes,
and never geocodes.  Source packages register a small adapter hook when they
are ready; an unregistered or reference-only source is reported explicitly.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from pipeline.contracts.refresh import (
    AdapterCapabilities, RegisteredAdapter, RefreshAdapter, RefreshRequest,
    SOURCE_KINDS, canonical_plan, row_free_summary,
)
from pipeline.source_registry import load_registry
from .adapter_registry import load as load_capabilities
from .source_operations import load_source_schedules


class RefreshRunnerError(ValueError):
    """A refresh plan is unsafe or cannot be executed."""


def _json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


class RefreshCatalog:
    """Bridge the authoritative source registry and capability registry."""

    def __init__(self, *, source_registry: Path | None = None, capability_registry: Path | None = None) -> None:
        root = Path(__file__).parents[1]
        self.source_payload = load_registry(source_registry or root / "source_registry.json")
        capability_payload = load_capabilities(capability_registry or root / "adapter-capabilities.json")
        self.sources = {item["source_id"]: item for item in self.source_payload["sources"]}
        self.capabilities = {item["source_id"]: AdapterCapabilities.from_mapping(item) for item in capability_payload["adapters"]}
        # The source registry is authoritative.  Older capability entries may
        # legitimately lag a registry rename (notably the UK aliases); retain
        # them as diagnostics but never allow them to select or execute a
        # source absent from the authoritative source list.
        self.orphan_capabilities = tuple(sorted(set(self.capabilities) - set(self.sources)))
        self.capabilities = {source_id: value for source_id, value in self.capabilities.items() if source_id in self.sources}
        self.adapters: dict[str, RegisteredAdapter] = {}
        try:
            self.schedules = load_source_schedules()
        except Exception:
            # A schedule file is useful operational evidence, but must not
            # prevent fixture-only contract tests from constructing a catalog.
            self.schedules = {}
        # Source-local code owns parsing/normalization; this is the single
        # production registration seam used by the D2 runner and CLI.
        from pipeline.sources.first_wave import register_first_wave
        register_first_wave(self)

    def register(self, adapter: RefreshAdapter, capabilities: AdapterCapabilities | None = None) -> None:
        source_id = str(adapter.source_id)
        if source_id not in self.sources:
            raise RefreshRunnerError(f"adapter source is not in authoritative registry: {source_id}")
        caps = capabilities or self.capabilities.get(source_id)
        if caps is None:
            raise RefreshRunnerError(f"adapter has no capability entry: {source_id}")
        if caps.source_id != source_id:
            raise RefreshRunnerError("adapter and capability source IDs differ")
        adapter_kind = getattr(adapter, "source_kind", "facility_master")
        if adapter_kind not in SOURCE_KINDS:
            raise RefreshRunnerError(f"adapter source_kind is unsupported: {source_id}")
        if adapter_kind != caps.source_kind:
            raise RefreshRunnerError(
                f"adapter and capability source kinds differ for {source_id}: "
                f"{adapter_kind} != {caps.source_kind}"
            )
        self.capabilities[source_id] = caps
        self.adapters[source_id] = RegisteredAdapter(caps, adapter)

    def operation_metadata(self, source_id: str) -> dict[str, Any]:
        """Return static, row-free operational facts for a source."""
        entry = self.sources[source_id]
        capability = self.capabilities.get(source_id)
        schedule = getattr(self, "schedules", {}).get(source_id)
        access_mode = str(entry.get("access_method") or (capability.acquisition if capability else "unknown"))
        cadence = schedule.cadence if schedule is not None else str(entry.get("cadence") or "unknown")
        fallback = schedule.manual_fallback if schedule is not None else (
            "operator-assisted/manual review required" if any(token in access_mode.lower() for token in ("assisted", "operator", "authorized"))
            else "no automated fallback recorded")
        return {
            "access_mode": access_mode,
            "terms_review_state": "documented-source-terms; project-review-required",
            "review_state": str((capability.publication if capability else "human_gate_required")),
            "cadence": cadence,
            "assisted_manual_fallback": fallback,
            "live_access": "not-authorized-by-runner" if str(capability.acquisition if capability else "").lower() not in {"verified", "bounded_private_fetch"} else "source-specific-hook-required",
        }

    def select(self, request: RefreshRequest) -> tuple[str, ...]:
        if request.all_eligible:
            requested_group = request.options.get("eligible_source_ids")
            if requested_group is not None:
                if not isinstance(requested_group, (list, tuple)):
                    raise RefreshRunnerError("options.eligible_source_ids must be a list")
                selected = list(requested_group)
            else:
                # Keep implemented/partial registry entries in the plan even
                # when a hook is not registered.  Unsupported sources must be
                # visible and fail the operator run rather than disappearing.
                selected = [source_id for source_id, item in self.sources.items()
                            if item.get("adapter_status") in {"implemented", "implemented_partial"}]
        else:
            selected = list(request.source_ids)
        if len(set(selected)) != len(selected):
            raise RefreshRunnerError("source selection contains duplicates")
        unknown = [source for source in selected if source not in self.sources]
        if unknown:
            raise RefreshRunnerError("source not in authoritative registry: " + ", ".join(unknown))
        return tuple(selected)


def _loopback_database(database_url: str) -> bool:
    parsed = urlparse(database_url)
    return parsed.scheme in {"postgres", "postgresql"} and parsed.hostname in {"localhost", "127.0.0.1", "::1"}


class RefreshRunner:
    def __init__(self, catalog: RefreshCatalog | None = None,
                 candidate_importer: Callable[[Path, str], Mapping[str, Any]] | None = None,
                 evidence_importer: Callable[[Path, str], Mapping[str, Any]] | None = None) -> None:
        self.catalog = catalog or RefreshCatalog()
        self.candidate_importer = candidate_importer
        self.evidence_importer = evidence_importer

    def run(self, request: RefreshRequest) -> dict[str, Any]:
        selected = self.catalog.select(request)
        source_operations = {source_id: self.catalog.operation_metadata(source_id) for source_id in selected}
        plan = canonical_plan(request, selected, self.catalog.capabilities, source_operations)
        run_root = Path(request.output_root) / plan["run_id"]
        run_root.mkdir(parents=True, exist_ok=True)
        _json(run_root / "plan.json", plan)
        if request.import_candidates and not _loopback_database(str(request.database_url)):
            raise RefreshRunnerError("candidate import is fail-closed: database must be a loopback PostgreSQL URL")
        results: list[dict[str, Any]] = []
        for source_id in selected:
            results.append(self._run_source(source_id, request, plan, run_root))
        failures = [item for item in results if item["status"] in {"failed", "unsupported"}]
        aggregate = {
            "contract_version": "private-refresh-result-v1", "run_id": plan["run_id"],
            "plan_hash": plan["plan_hash"], "mode": request.mode,
            "selected_sources": list(selected),
            "completed_at_utc": str(request.options.get("as_of_utc") or datetime.now(timezone.utc).isoformat()),
            "counts": {"selected": len(results), "succeeded": sum(r["status"] == "succeeded" for r in results),
                       "resumed": sum(r["status"] == "resumed" for r in results),
                       "skipped": sum(r["status"] == "skipped" for r in results),
                       "unsupported": sum(r["status"] == "unsupported" for r in results),
                       "failed": sum(r["status"] == "failed" for r in results)},
            "results": results, "publication": {"release_created": False, "promoted": False, "published": False},
            "operational": {"sources": source_operations, "aggregate_only": True},
            "exit_status": "failed" if failures else "ok",
        }
        _json(run_root / "manifest.json", aggregate)
        return aggregate

    def _run_source(self, source_id: str, request: RefreshRequest, plan: Mapping[str, Any], run_root: Path) -> dict[str, Any]:
        source_dir = run_root / "sources" / source_id.replace("/", "_")
        source_dir.mkdir(parents=True, exist_ok=True)
        result_path = source_dir / "manifest.json"
        if request.resume and result_path.exists():
            prior = json.loads(result_path.read_text(encoding="utf-8"))
            if prior.get("status") in {"succeeded", "skipped", "unsupported"}:
                return {**prior, "status": "resumed"}
        entry = self.catalog.sources[source_id]
        registered = self.catalog.adapters.get(source_id)
        if registered is None:
            result = {"source_id": source_id, "status": "unsupported",
                      "reason": "no registered adapter hook; source remains unexecuted",
                      "adapter_status": entry.get("adapter_status"), "mode": request.mode,
                      "operational": self._operational_metadata(source_id, request, attempts=0,
                                                                 failure_reason="adapter_unregistered")}
            _json(result_path, result)
            return result
        artifact = Path(request.artifact_paths[source_id]) if source_id in request.artifact_paths else None
        if request.mode == "local-artifact" and artifact is None:
            result = {"source_id": source_id, "status": "failed", "error": "artifact path required for this mode", "mode": request.mode,
                      "operational": self._operational_metadata(source_id, request, attempts=0,
                                                                 failure_reason="preserved_artifact_required")}
            _json(result_path, result)
            return result
        attempts: list[dict[str, Any]] = []
        for attempt in range(request.retries + 1):
            started = time.monotonic()
            try:
                summary = registered.adapter.refresh(mode=request.mode, run_dir=source_dir, artifact=artifact, options=request.options)
                safe = row_free_summary(summary)
                if request.import_candidates:
                    if registered.capabilities.source_kind == "evidence_event":
                        if self.evidence_importer is None:
                            raise RefreshRunnerError("evidence import requested but no private evidence sink was provided")
                        imported = self.evidence_importer(source_dir / "evidence-handoff", str(request.database_url))
                    else:
                        if self.candidate_importer is None:
                            raise RefreshRunnerError("candidate import requested but no generic importer was provided")
                        imported = self.candidate_importer(source_dir, str(request.database_url))
                    safe["candidate_import"] = row_free_summary(imported)
                result = {"source_id": source_id, "source_kind": registered.capabilities.source_kind,
                          "status": "succeeded", "mode": request.mode,
                          "attempts": attempt + 1, "elapsed_seconds": round(time.monotonic() - started, 6),
                          "summary": safe, "publication": {"release_created": False, "promoted": False, "published": False},
                          "operational": self._operational_metadata(source_id, request, attempts=attempt + 1,
                                                                     summary=safe)}
                _json(result_path, result)
                return result
            except Exception as exc:  # isolate source failures by design
                reason = self._failure_reason(exc)
                attempts.append({"attempt": attempt + 1, "error_type": type(exc).__name__, "error": reason,
                                 "failure_reason": reason})
                if attempt < request.retries:
                    continue
                result = {"source_id": source_id, "status": "failed", "mode": request.mode,
                          "attempts": attempts,
                          "operational": self._operational_metadata(source_id, request, attempts=len(attempts),
                                                                     failure_reason=reason)}
                _json(result_path, result)
                return result
        raise AssertionError("unreachable")

    @staticmethod
    def _failure_reason(error: BaseException) -> str:
        """Classify failures without copying exception paths or source data."""
        message = str(error).lower()
        if "injected_fixture_failure" in message:
            return "injected_fixture_failure"
        if "row-bearing" in message:
            return "row-bearing summary rejected"
        if "live acquisition" in message or "network acquisition" in message:
            return "live acquisition unsupported by registered adapter"
        if "artifact" in message and ("exist" in message or "required" in message):
            return "preserved artifact unavailable"
        if "terms" in message or "authorization" in message:
            return "terms or authorization gate blocked acquisition"
        return "adapter execution failed"

    def _operational_metadata(self, source_id: str, request: RefreshRequest, *, attempts: int,
                              summary: Mapping[str, Any] | None = None,
                              failure_reason: str | None = None) -> dict[str, Any]:
        entry = self.catalog.sources[source_id]
        capability = self.catalog.capabilities.get(source_id)
        static = self.catalog.operation_metadata(source_id)
        summary = summary or {}
        artifact = Path(request.artifact_paths[source_id]) if source_id in request.artifact_paths else None
        if artifact is None:
            registered = self.catalog.adapters.get(source_id)
            descriptor = getattr(registered.adapter, "descriptor", None) if registered else None
            fixtures = getattr(descriptor, "fixture_paths", ()) if descriptor else ()
            if request.mode == "fixture" and fixtures:
                artifact = Path(fixtures[0])
        artifact_meta: dict[str, Any] = {"available": False, "sha256": None, "byte_size": None}
        if artifact is not None and artifact.is_file():
            raw = artifact.read_bytes()
            artifact_meta = {"available": True, "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw)}
        acquired_at = summary.get("retrieved_at_utc") or summary.get("acquisition_timestamp_utc")
        previous = summary.get("previous_valid_state")
        if isinstance(previous, Mapping):
            previous_state = dict(previous)
        elif failure_reason:
            previous_state = {"state": "preserved-by-private-boundary", "verified": False}
        else:
            previous_state = {"state": "not-checked", "verified": False}
        return {
            **static,
            "mode": request.mode,
            "acquisition_timestamp_utc": acquired_at,
            "acquisition_timestamp_state": "recorded" if acquired_at else "not-recorded",
            "artifact": artifact_meta,
            "freshness": {"cadence": static["cadence"], "state": "not-assessed"},
            "retry_outcome": {"configured_retries": request.retries, "attempts": attempts,
                              "exhausted": bool(failure_reason and attempts >= request.retries + 1)},
            "previous_valid_state": previous_state,
            "failure_reason": failure_reason,
            "adapter_version": capability.adapter_version if capability else None,
            "adapter_status": entry.get("adapter_status"),
        }


def run_refresh(request: RefreshRequest, *, catalog: RefreshCatalog | None = None) -> dict[str, Any]:
    return RefreshRunner(catalog).run(request)
