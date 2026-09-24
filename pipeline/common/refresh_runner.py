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
    ACQUISITION_CLASSIFICATIONS, AdapterCapabilities, RegisteredAdapter,
    RefreshAdapter, RefreshRequest, SOURCE_KINDS, canonical_plan, row_free_summary,
)
from pipeline.source_registry import load_registry
from .adapter_registry import load as load_capabilities
from .source_operations import load_source_schedules


class RefreshRunnerError(ValueError):
    """A refresh plan is unsafe or cannot be executed."""


def _json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _artifact_digest(path: Path) -> dict[str, Any]:
    """Return a deterministic digest for a file or a multi-file bundle."""
    if path.is_file():
        raw = path.read_bytes()
        return {"available": True, "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw)}
    if path.is_dir():
        digest = hashlib.sha256()
        size = 0
        files = [item for item in sorted(path.rglob("*")) if item.is_file()]
        for item in files:
            raw = item.read_bytes()
            relative = item.relative_to(path).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big")); digest.update(relative)
            digest.update(len(raw).to_bytes(8, "big")); digest.update(raw)
            size += len(raw)
        return {"available": bool(files), "sha256": digest.hexdigest() if files else None, "byte_size": size if files else None}
    return {"available": False, "sha256": None, "byte_size": None}


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
        registered = self.adapters.get(source_id)
        has_live_fetch_hook = bool(
            capability and capability.live_callable and registered
            and callable(getattr(registered.adapter, "acquire", None))
        )
        access_mode = str(entry.get("access_method") or (capability.acquisition if capability else "unknown"))
        cadence = schedule.cadence if schedule is not None else str(entry.get("cadence") or "unknown")
        fallback = schedule.manual_fallback if schedule is not None else (
            "operator-assisted/manual review required" if any(token in access_mode.lower() for token in ("assisted", "operator", "authorized"))
            else "no automated fallback recorded")
        return {
            "access_mode": access_mode,
            "operational_classification": capability.operational_classification if capability else "failed",
            "live_callable": bool(capability.live_callable) if capability else False,
            "terms_review_state": "documented-source-terms; project-review-required",
            "review_state": str((capability.publication if capability else "human_gate_required")),
            "cadence": cadence,
            "assisted_manual_fallback": fallback,
            "live_access": (
                "source-specific-acquisition-hook-registered" if has_live_fetch_hook else
                "not-authorized-by-runner" if str(capability.acquisition if capability else "").lower() not in {"verified", "bounded_private_fetch"} else
                "source-specific-hook-required"
            ),
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
        classification_counts: dict[str, int] = {}
        for item in results:
            classification = str(item.get("acquisition_classification") or "failed")
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
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
            "classification_counts": dict(sorted(classification_counts.items())),
            "results": results, "publication": {"release_created": False, "promoted": False, "published": False},
            "operational": {"sources": source_operations, "aggregate_only": True},
            "exit_status": "failed" if failures else "ok",
        }
        _json(run_root / "manifest.json", aggregate)
        _json(run_root / "source-health-index.json", {
            "schema_version": "source-health-index-v2",
            "run_id": plan["run_id"],
            "as_of_utc": aggregate["completed_at_utc"],
            "private_validation": True,
            "public_exposure": False,
            "sources": [
                {
                    "source_id": item["source_id"],
                    "status": item.get("acquisition_classification", "failed"),
                    "run_status": item["status"],
                    "attempts": item.get("attempts", 0) if isinstance(item.get("attempts"), int) else len(item.get("attempts", [])),
                    "previous_valid_state": item.get("operational", {}).get("previous_valid_state", {"verified": False}),
                    "public_exposure": False,
                }
                for item in results
            ],
        })
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
                      "acquisition_classification": "failed",
                      "operational_classification": "failed",
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
                # A source-owned bounded fetch is an optional capability.  It
                # is never called until the operator supplies an explicit
                # per-source authorization and terms-review reference.  The
                # path is checked before the adapter sees the request so a
                # future adapter cannot accidentally probe a source.
                acquisition_classification = "assisted"
                if request.mode == "live-acquisition":
                    acquire = getattr(registered.adapter, "acquire", None)
                    if callable(acquire):
                        if not registered.capabilities.live_callable:
                            return self._write_blocked_result(
                                source_id, request, result_path,
                                classification=registered.capabilities.operational_classification,
                                reason="source is operator-assisted; provide a preserved local artifact",
                            )
                        if not self._live_authorized(source_id, request.options):
                            return self._write_blocked_result(
                                source_id, request, result_path,
                                classification="terms-blocked",
                                reason="explicit source authorization and terms review are required before network acquisition",
                            )
                        acquired = acquire(run_dir=source_dir, options=request.options)
                        if not isinstance(acquired, Mapping):
                            raise RefreshRunnerError("acquisition hook must return a mapping")
                        acquired = dict(acquired)
                        raw_value = acquired.get("artifact_path") or acquired.get("path")
                        if not raw_value:
                            raise RefreshRunnerError("acquisition hook did not return an artifact path")
                        artifact = Path(str(raw_value))
                        request_options = {**request.options, "acquisition": acquired}
                        summary = registered.adapter.refresh(mode="local-artifact", run_dir=source_dir, artifact=artifact, options=request_options)
                        acquisition_classification = "live"
                    else:
                        # Legacy source bridges still fail closed themselves;
                        # preserving that behavior keeps custom/test adapters
                        # compatible while making production status honest.
                        summary = registered.adapter.refresh(mode=request.mode, run_dir=source_dir, artifact=artifact, options=request.options)
                        acquisition_classification = "live"
                else:
                    summary = registered.adapter.refresh(mode=request.mode, run_dir=source_dir, artifact=artifact, options=request.options)
                    acquisition_classification = "assisted"
                if not isinstance(summary, Mapping):
                    raise RefreshRunnerError("adapter refresh must return a mapping")
                declared = summary.get("acquisition_classification")
                if declared in ACQUISITION_CLASSIFICATIONS:
                    acquisition_classification = str(declared)
                schema_status = str(summary.get("schema_status") or "").lower()
                if schema_status in {"drift", "schema-drift", "changed", "blocked"} or summary.get("drift_alarms"):
                    acquisition_classification = "schema-drift"
                safe = row_free_summary(summary)
                if request.import_candidates and acquisition_classification == "schema-drift":
                    safe["candidate_import"] = {"status": "blocked", "reason": "schema-drift"}
                elif request.import_candidates:
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
                          "acquisition_classification": acquisition_classification,
                          "operational_classification": acquisition_classification,
                          "attempts": attempt + 1, "elapsed_seconds": round(time.monotonic() - started, 6),
                          "summary": safe, "publication": {"release_created": False, "promoted": False, "published": False},
                          "operational": self._operational_metadata(source_id, request, attempts=attempt + 1,
                                                                     summary=safe,
                                                                     classification=acquisition_classification)}
                _json(result_path, result)
                _json(source_dir / "source-health.json", {
                    "schema_version": "source-health-v2",
                    "source_id": source_id,
                    "status": acquisition_classification,
                    "run_status": "succeeded",
                    "artifact": result["operational"]["artifact"],
                    "retrieved_at_utc": result["operational"]["acquisition_timestamp_utc"],
                    "previous_valid_state": result["operational"]["previous_valid_state"],
                    "public_exposure": False,
                })
                return result
            except Exception as exc:  # isolate source failures by design
                reason = self._failure_reason(exc)
                attempts.append({"attempt": attempt + 1, "error_type": type(exc).__name__, "error": reason,
                                 "failure_reason": reason})
                if attempt < request.retries:
                    continue
                if "schema" in reason:
                    failed_classification = "schema-drift"
                elif request.mode == "live-acquisition" and not registered.capabilities.live_callable and "live acquisition" in reason:
                    failed_classification = registered.capabilities.operational_classification
                elif "terms" in reason or "authorization" in reason or "live acquisition" in reason:
                    failed_classification = "terms-blocked"
                else:
                    failed_classification = "failed"
                result = {"source_id": source_id, "status": "failed", "mode": request.mode,
                          "acquisition_classification": failed_classification,
                          "operational_classification": failed_classification,
                          "attempts": attempts,
                          "operational": self._operational_metadata(source_id, request, attempts=len(attempts),
                                                                     failure_reason=reason,
                                                                     classification=failed_classification)}
                _json(result_path, result)
                _json(source_dir / "source-health.json", {
                    "schema_version": "source-health-v2",
                    "source_id": source_id,
                    "status": result["acquisition_classification"],
                    "run_status": "failed",
                    "artifact": result["operational"]["artifact"],
                    "retrieved_at_utc": result["operational"]["acquisition_timestamp_utc"],
                    "previous_valid_state": result["operational"]["previous_valid_state"],
                    "failure_reason": result["operational"]["failure_reason"],
                    "public_exposure": False,
                })
                return result
        raise AssertionError("unreachable")

    @staticmethod
    def _live_authorized(source_id: str, options: Mapping[str, Any]) -> bool:
        """Return true only for an explicit, source-scoped live grant.

        A boolean global switch is deliberately not accepted.  This prevents
        an all-source plan from turning a newly registered adapter into an
        unexpected network client.
        """
        selected = options.get("authorized_live_sources", ())
        if not isinstance(selected, (list, tuple, set, frozenset)) or source_id not in selected:
            return False
        reviews = options.get("terms_review_paths")
        if isinstance(reviews, Mapping):
            review = reviews.get(source_id)
        else:
            review = None
        if review is None:
            review = options.get("terms_review_path")
        return bool(review)

    def _write_blocked_result(self, source_id: str, request: RefreshRequest,
                              result_path: Path, *, classification: str,
                              reason: str) -> dict[str, Any]:
        result = {
            "source_id": source_id, "status": "failed", "mode": request.mode,
            "acquisition_classification": classification,
            "operational_classification": classification, "attempts": [],
            "operational": self._operational_metadata(
                source_id, request, attempts=0, failure_reason=reason,
                classification=classification,
            ),
        }
        _json(result_path, result)
        source_dir = result_path.parent
        _json(source_dir / "source-health.json", {
            "schema_version": "source-health-v2", "source_id": source_id,
            "status": classification, "run_status": "failed",
            "artifact": result["operational"]["artifact"],
            "retrieved_at_utc": result["operational"]["acquisition_timestamp_utc"],
            "previous_valid_state": result["operational"]["previous_valid_state"],
            "failure_reason": reason, "public_exposure": False,
        })
        return result

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
                              failure_reason: str | None = None,
                              classification: str | None = None) -> dict[str, Any]:
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
        if artifact is not None:
            artifact_meta = _artifact_digest(artifact)
        acquired_at = summary.get("retrieved_at_utc") or summary.get("acquisition_timestamp_utc")
        previous = summary.get("previous_valid_state")
        if isinstance(previous, Mapping):
            previous_state = dict(previous)
        else:
            previous_state = self._previous_valid_state(source_id, request.options, failure_reason=failure_reason)
        return {
            **static,
            "mode": request.mode,
            "operational_classification": classification or ("failed" if failure_reason else "assisted"),
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

    @staticmethod
    def _previous_valid_state(source_id: str, options: Mapping[str, Any], *, failure_reason: str | None) -> dict[str, Any]:
        """Return aggregate-only evidence that a prior validated state remains.

        The runner does not copy the prior artifact or expose its location.
        Callers may provide an aggregate state map, or a private manifest path
        for the runner to verify locally.
        """
        states = options.get("previous_valid_states")
        candidate: Any = states.get(source_id) if isinstance(states, Mapping) else None
        paths = options.get("previous_valid_state_paths")
        path_value = paths.get(source_id) if isinstance(paths, Mapping) else None
        if path_value is None and isinstance(options.get("previous_valid_state_path"), str):
            path_value = options.get("previous_valid_state_path")
        if isinstance(candidate, Mapping):
            return {
                "state": str(candidate.get("state") or "preserved-by-private-boundary"),
                "verified": bool(candidate.get("verified", False)),
                "artifact_sha256": candidate.get("artifact_sha256") if isinstance(candidate.get("artifact_sha256"), str) else None,
            }
        if path_value:
            path = Path(str(path_value))
            if path.is_file():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    payload = {}
                if isinstance(payload, Mapping):
                    digest = payload.get("sha256") or payload.get("checksum_sha256") or payload.get("artifact_sha256")
                    return {"state": "preserved-by-private-boundary", "verified": bool(digest), "artifact_sha256": digest if isinstance(digest, str) else None}
        if failure_reason:
            return {"state": "preserved-by-private-boundary", "verified": False}
        return {"state": "not-checked", "verified": False}


def run_refresh(request: RefreshRequest, *, catalog: RefreshCatalog | None = None) -> dict[str, Any]:
    return RefreshRunner(catalog).run(request)
