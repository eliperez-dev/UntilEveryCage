"""Deterministic, sequential, source-neutral private refresh runner.

This is a control plane only.  It never contains source SQL, never publishes,
and never geocodes.  Source packages register a small adapter hook when they
are ready; an unregistered or reference-only source is reported explicitly.
"""
from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from pipeline.contracts.refresh import (
    AdapterCapabilities, RegisteredAdapter, RefreshAdapter, RefreshRequest,
    canonical_plan, row_free_summary,
)
from pipeline.source_registry import load_registry
from .adapter_registry import load as load_capabilities


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
        self.adapters[source_id] = RegisteredAdapter(caps, adapter)

    def select(self, request: RefreshRequest) -> tuple[str, ...]:
        if request.all_eligible:
            # Eligible means an explicitly implemented/partial adapter status;
            # missing hooks are retained in the plan and reported as skips.
            selected = [source_id for source_id, item in self.sources.items()
                        if item.get("adapter_status") in {"implemented", "implemented_partial"}
                        and source_id in self.adapters]
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
                 candidate_importer: Callable[[Path, str], Mapping[str, Any]] | None = None) -> None:
        self.catalog = catalog or RefreshCatalog()
        self.candidate_importer = candidate_importer

    def run(self, request: RefreshRequest) -> dict[str, Any]:
        selected = self.catalog.select(request)
        plan = canonical_plan(request, selected, self.catalog.capabilities)
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
            "selected_sources": list(selected), "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "counts": {"selected": len(results), "succeeded": sum(r["status"] == "succeeded" for r in results),
                       "resumed": sum(r["status"] == "resumed" for r in results),
                       "skipped": sum(r["status"] == "skipped" for r in results),
                       "unsupported": sum(r["status"] == "unsupported" for r in results),
                       "failed": sum(r["status"] == "failed" for r in results)},
            "results": results, "publication": {"release_created": False, "promoted": False, "published": False},
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
                      "adapter_status": entry.get("adapter_status"), "mode": request.mode}
            _json(result_path, result)
            return result
        artifact = Path(request.artifact_paths[source_id]) if source_id in request.artifact_paths else None
        if request.mode == "local-artifact" and artifact is None:
            result = {"source_id": source_id, "status": "failed", "error": "artifact path required for this mode", "mode": request.mode}
            _json(result_path, result)
            return result
        attempts: list[dict[str, Any]] = []
        for attempt in range(request.retries + 1):
            started = time.monotonic()
            try:
                summary = registered.adapter.refresh(mode=request.mode, run_dir=source_dir, artifact=artifact, options=request.options)
                safe = row_free_summary(summary)
                if request.import_candidates:
                    if self.candidate_importer is None:
                        raise RefreshRunnerError("candidate import requested but no generic importer was provided")
                    imported = self.candidate_importer(source_dir, str(request.database_url))
                    safe["candidate_import"] = row_free_summary(imported)
                result = {"source_id": source_id, "status": "succeeded", "mode": request.mode,
                          "attempts": attempt + 1, "elapsed_seconds": round(time.monotonic() - started, 6),
                          "summary": safe, "publication": {"release_created": False, "promoted": False, "published": False}}
                _json(result_path, result)
                return result
            except Exception as exc:  # isolate source failures by design
                attempts.append({"attempt": attempt + 1, "error_type": type(exc).__name__, "error": str(exc)})
                if attempt < request.retries:
                    continue
                result = {"source_id": source_id, "status": "failed", "mode": request.mode,
                          "attempts": attempts, "traceback": traceback.format_exc(limit=4)}
                _json(result_path, result)
                return result
        raise AssertionError("unreachable")


def run_refresh(request: RefreshRequest, *, catalog: RefreshCatalog | None = None) -> dict[str, Any]:
    return RefreshRunner(catalog).run(request)
