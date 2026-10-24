"""Discover and rehearse retained real-data graph handoffs.

The operator deliberately works from private manifests and handoff contracts.
It never copies rows into the repository and only returns aggregate data.  A
manifest is evidence of a private processing run, not evidence that a row is
approved, current, or safe to publish.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import psycopg

from pipeline.common.d5_connection_analysis import (_iter_probabilistic_candidates,
    iter_shared_business_name_candidates, _observed_from_json, _observed_from_row, _observed_json)
from pipeline.common.d5_connection_analysis import RULESET_VERSION as D5_MATCHER_VERSION
from pipeline.common.d5_connection_analysis import SHARED_BUSINESS_NAME_RULESET_VERSION
from pipeline.common.graph_edges import RULESET_VERSION as D6_EDGE_RULESET_VERSION
from pipeline.common.graph_persistence import (ConnectionEdgeBuilder, import_evidence_events,
    completed_edge_materialization, import_graph_candidates, iter_graph_candidate_handoff,
    load_evidence_handoff, require_private_graph_target, _ensure_source_artifact,
    _validate_private_graph_writer)


REPORT_VERSION = "d7-real-private-graph-v1"
NATIVE_ENDPOINT_CONTRACT_VERSION = "native-source-identifier-v2"
GRAPH_EDGE_MATERIALIZATION_VERSION = "private-graph-materialization-v6"
GRAPH_CONTEXT_PERSISTENCE_VERSION = "private-graph-context-persistence-v2"
GRAPH_MATERIALIZATION_FINGERPRINT = hashlib.sha256(
    "|".join((GRAPH_EDGE_MATERIALIZATION_VERSION, D5_MATCHER_VERSION,
              D6_EDGE_RULESET_VERSION, SHARED_BUSINESS_NAME_RULESET_VERSION,
              NATIVE_ENDPOINT_CONTRACT_VERSION,
              GRAPH_CONTEXT_PERSISTENCE_VERSION)).encode("utf-8")
).hexdigest()
EVIDENCE_CONTRACTS = {"us-aphis-observation-handoff-v1"}


def _source_artifact_sha256(manifest: dict[str, Any]) -> str:
    return str(manifest.get("checksum_sha256") or manifest.get("source_artifact_sha256") or "").strip()


def _has_actual_artifact_sha256(manifest: dict[str, Any]) -> bool:
    value = _source_artifact_sha256(manifest)
    return len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)


def _rss_bytes() -> int | None:
    try:
        import psutil  # type: ignore
        return int(psutil.Process().memory_info().rss)
    except Exception:
        try:
            import resource  # type: ignore
            value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            return value * (1024 if os.name != "nt" else 1)
        except Exception:
            return None


def graph_corpus_materialization_fingerprint(handoff_roots: Iterable[str | Path]) -> str:
    """Bind a materialization to every handoff participating in matching."""
    inputs: list[dict[str, Any]] = []
    for root in handoff_roots:
        kind, manifest, digest, count = _describe_handoff(root)
        metadata_fields = (
            "contract_version", "source_kind", "checksum_sha256", "source_artifact_sha256",
            "artifact_sha256", "retrieved_at_utc", "as_of_utc", "adapter_version",
            "source_revision", "ruleset_version", "entity_scope", "normalized_sha256",
        )
        inputs.append({"kind": kind, "source_id": str(manifest["source_id"]), "handoff_sha256": digest,
                       "item_count": int(count),
                       "manifest": {key: manifest[key] for key in metadata_fields if key in manifest}})
    canonical_inputs = json.dumps(sorted(inputs, key=lambda item: (
        item["source_id"], item["kind"], item["handoff_sha256"], item["item_count"])),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((GRAPH_MATERIALIZATION_FINGERPRINT + "\n" + canonical_inputs).encode("utf-8")).hexdigest()


def _describe_handoff(root: str | Path) -> tuple[str, dict[str, Any], str, int]:
    """Validate a handoff and identify its family without treating events as facilities."""
    path = Path(root)
    manifest_path = path / "manifest.json" if path.is_dir() else path.with_name("manifest.json")
    try:
        declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("graph handoff manifest is unavailable") from exc
    evidence = (
        declared.get("entity_scope") == "evidence_event"
        or declared.get("source_kind") == "evidence_event"
        or declared.get("contract_version") in EVIDENCE_CONTRACTS
    )
    if evidence:
        manifest, rows, digest = load_evidence_handoff(root)
        return "evidence", manifest, digest, len(rows)
    manifest, _rows, digest, count = iter_graph_candidate_handoff(root)
    return "facility", manifest, digest, count


def _register_corpus_sources(database_url: str,
                             described: list[tuple[Path, str, dict[str, Any], str, int]],
                             private_target: tuple[str, str] | None) -> int:
    """Register every validated source before any cross-source edge is written."""
    if private_target is None:
        return 0
    expected_database, purpose = private_target
    require_private_graph_target(database_url, expected_database=expected_database, purpose=purpose)
    with psycopg.connect(database_url) as db:
        _validate_private_graph_writer(db, expected_database)
        db.commit()
        with db.transaction():
            for _root, _kind, manifest, digest, _count in described:
                # Use the importer's canonical upsert to preserve source metadata
                # and the exact artifact identity from each validated handoff.
                _ensure_source_artifact(db, manifest, digest)
    return len({str(manifest["source_id"]) for _root, _kind, manifest, _digest, _count in described})


class _MatcherStage:
    """Private disk-backed bridge between source handoffs and the matcher."""

    def __init__(self) -> None:
        parent = Path.cwd() / ".tmp"
        parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="uec-d6-graph-", suffix=".sqlite3", dir=str(parent))
        os.close(fd)
        self.path = Path(name)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=OFF")
        self.db.executescript("""
            CREATE TABLE observations(source_id TEXT NOT NULL, source_record_key TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(source_id, source_record_key, artifact_sha256));
            CREATE TABLE edges(source_id TEXT NOT NULL, source_record_key TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL, candidate TEXT NOT NULL,
                PRIMARY KEY(source_id, source_record_key, artifact_sha256, candidate));
            CREATE INDEX edges_lookup ON edges(source_id, source_record_key, artifact_sha256);
        """)
        self.rows_staged = 0
        self.edges_staged = 0

    def add_handoff(self, handoff_root: Path) -> None:
        manifest, candidates, _, _ = iter_graph_candidate_handoff(handoff_root)
        source_id = str(manifest["source_id"])
        artifact_sha256 = _source_artifact_sha256(manifest)
        for item in candidates:
            key = str(item["source_record_key"])
            observed = _observed_from_row(
                {**item, "source_id": item.get("source_id") or source_id}, source_id,
                fallback_artifact_sha256=artifact_sha256,
            )
            payload = _observed_json(observed)
            inserted = self.db.execute(
                "INSERT OR IGNORE INTO observations(source_id,source_record_key,artifact_sha256,payload) VALUES (?,?,?,?)",
                (source_id, key, artifact_sha256, payload),
            ).rowcount
            if not inserted:
                existing = self.db.execute(
                    "SELECT payload FROM observations WHERE source_id=? AND source_record_key=? AND artifact_sha256=?",
                    (source_id, key, artifact_sha256),
                ).fetchone()
                if existing and existing[0] != payload:
                    raise ValueError("conflicting candidate for one source artifact record")
            self.rows_staged += int(inserted)
        self.db.commit()

    def observed(self) -> Iterable[Any]:
        for (payload,) in self.db.execute("SELECT payload FROM observations ORDER BY source_id, source_record_key, artifact_sha256"):
            yield _observed_from_json(payload)

    def build_candidates(self) -> dict[str, int]:
        # Matching uses normalized IDs, but persisted endpoint keys must retain
        # the exact source-native assertion value for release resolution.
        generated, matcher_counters = _iter_probabilistic_candidates(
            self.observed(), preserve_native_endpoints=True,
        )
        for inferred in generated:
            endpoints = inferred.get("endpoints") or []
            if len(endpoints) != 2:
                continue
            owner = endpoints[0]
            source_id = str(owner.get("source_id") or "")
            key = str(owner.get("source_record_key") or "")
            artifact_sha256 = str(owner.get("artifact_sha256") or "")
            if not source_id or not key:
                continue
            inserted = self.db.execute(
                "INSERT OR IGNORE INTO edges(source_id,source_record_key,artifact_sha256,candidate) VALUES (?,?,?,?)",
                (source_id, key, artifact_sha256, json.dumps(inferred, ensure_ascii=False, separators=(",", ":"))),
            ).rowcount
            self.edges_staged += inserted
        shared_name_candidates, shared_name_counters = iter_shared_business_name_candidates(
            self.observed(), preserve_native_endpoints=True,
        )
        for inferred in shared_name_candidates:
            endpoints = inferred.get("endpoints") or []
            if len(endpoints) != 2:
                continue
            owner = endpoints[0]
            source_id = str(owner.get("source_id") or "")
            key = str(owner.get("source_record_key") or "")
            artifact_sha256 = str(owner.get("artifact_sha256") or "")
            if not source_id or not key:
                continue
            inserted = self.db.execute(
                "INSERT OR IGNORE INTO edges(source_id,source_record_key,artifact_sha256,candidate) VALUES (?,?,?,?)",
                (source_id, key, artifact_sha256, json.dumps(inferred, ensure_ascii=False, separators=(",", ":"))),
            ).rowcount
            self.edges_staged += inserted
        self.db.commit()
        return {"rows_staged": self.rows_staged, "inferred_candidates_staged": self.edges_staged,
                **matcher_counters, **{f"shared_business_name_{key}": value for key, value in shared_name_counters.items()}}

    def edge_builder(self, candidate: dict[str, Any], manifest: dict[str, Any]) -> Iterable[dict[str, Any]]:
        source_id = str(candidate.get("source_id") or manifest["source_id"])
        key = str(candidate.get("source_record_key") or "")
        artifact_sha256 = _source_artifact_sha256(manifest)
        for (payload,) in self.db.execute("SELECT candidate FROM edges WHERE source_id=? AND source_record_key=? AND artifact_sha256=? ORDER BY candidate", (source_id, key, artifact_sha256)):
            yield json.loads(payload)

    def close(self) -> None:
        self.db.close()
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                self.path.with_name(self.path.name + suffix).unlink()
            except OSError:
                pass


def materialize_graph_corpus(
    database_url: str,
    handoff_roots: Iterable[str | Path],
    *,
    private_target: tuple[str, str],
    batch_size: int = 250,
    on_batch_committed: Any | None = None,
) -> dict[str, Any]:
    """Match all supplied source handoffs together and persist serially.

    This is the shared refresh/rebuild entry point. It fingerprints every
    current input, uses the same disk-backed matcher as the maintenance CLI,
    and keeps all writes behind the configured private-target guard.
    """
    handoffs = [Path(root) for root in handoff_roots]
    if not handoffs:
        raise ValueError("at least one graph candidate handoff is required")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    described = [(root, *_describe_handoff(root)) for root in handoffs]
    if private_target and any(not _has_actual_artifact_sha256(manifest)
                              for _, _kind, manifest, _digest, _count in described):
        raise ValueError("private graph corpus requires source artifact sha256 provenance")
    facility_roots = [root for root, kind, _manifest, _digest, _count in described if kind == "facility"]
    evidence_roots = [root for root, kind, _manifest, _digest, _count in described if kind == "evidence"]
    if len({(str(manifest["source_id"]), kind, digest)
            for _, kind, manifest, digest, _ in described}) != len(described):
        raise ValueError("duplicate handoff in graph corpus")
    fingerprint = graph_corpus_materialization_fingerprint(handoffs)
    registered_source_count = _register_corpus_sources(database_url, described, private_target)
    completed = [completed_edge_materialization(
        database_url, root, private_target=private_target, fingerprint=fingerprint,
    ) for root in facility_roots]

    # Evidence events remain their own typed family, are never staged as
    # facilities, and are ingested through the private-target guarded importer.
    evidence_results = [import_evidence_events(
        database_url, root, private_target=private_target, batch_size=batch_size,
        on_batch_committed=on_batch_committed,
    ) for root in evidence_roots]
    if all(item is not None for item in completed):
        status = "already_present" if all(item.get("status") == "already_present" for item in evidence_results) else "completed"
        imports = [*completed, *[{
            "source_id": result.get("source_id"), "status": result.get("status"),
            "item_count": result.get("item_count"), "kind": "evidence",
        } for result in evidence_results]]
        return {"status": status, "materialization_fingerprint": fingerprint,
                "imports": imports, "matcher": {"skipped": "identical complete facility corpus"},
                "registered_source_count": registered_source_count}

    matcher = _MatcherStage()
    try:
        for root in facility_roots:
            matcher.add_handoff(root)
        matcher_summary = matcher.build_candidates()
        results = []
        for root in facility_roots:
            result = import_graph_candidates(
                database_url, root, batch_size=batch_size,
                private_target=private_target, edge_builder=matcher.edge_builder,
                materialization_fingerprint=fingerprint, matcher_summary=matcher_summary,
                on_batch_committed=on_batch_committed,
            )
            results.append({"source_id": result.get("source_id"), "status": result.get("status"),
                            "item_count": result.get("item_count"),
                            "edge_inserted_count": result.get("edge_inserted_count"),
                            "edge_updated_count": result.get("edge_updated_count"),
                            "edge_unchanged_count": result.get("edge_unchanged_count"),
                            "persisted_edge_counts": result.get("persisted_edge_counts"), "kind": "facility"})
        results.extend({"source_id": result.get("source_id"), "status": result.get("status"),
                        "item_count": result.get("item_count"), "kind": "evidence"}
                       for result in evidence_results)
        return {"status": "completed", "materialization_fingerprint": fingerprint,
                "imports": results, "matcher": matcher_summary,
                "registered_source_count": registered_source_count}
    finally:
        matcher.close()


@dataclass(frozen=True)
class ManifestRecord:
    path: Path
    source_id: str
    normalized_rows: int | None
    quarantined_rows: int | None
    candidate_rows: int | None
    graph_edges: int | None
    facility_candidates: int | None
    organization_candidates: int | None
    coordinate_states: dict[str, int]
    identity_counts: dict[str, int]
    digest: str
    integrity_status: str


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _source_id(payload: dict[str, Any]) -> str | None:
    if isinstance(payload.get("source_id"), str) and payload["source_id"].strip():
        return payload["source_id"].strip()
    source = payload.get("source")
    if isinstance(source, dict) and isinstance(source.get("source_id"), str):
        return source["source_id"].strip() or None
    return None


def _nested_int(payload: dict[str, Any], *paths: tuple[str, ...]) -> int | None:
    for path in paths:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        value = _integer(current)
        if value is not None:
            return value
    return None


def _counter(payload: dict[str, Any], *paths: tuple[str, ...]) -> dict[str, int]:
    for path in paths:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if isinstance(current, dict):
            return {str(key): value for key, value in current.items() if isinstance(value, int) and value >= 0}
    return {}


def _manifest_record(path: Path, payload: dict[str, Any]) -> ManifestRecord | None:
    source_id = _source_id(payload)
    if not source_id:
        return None
    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    summary = payload.get("graph_candidate_summary") if isinstance(payload.get("graph_candidate_summary"), dict) else {}
    expected_normalized = payload.get("normalized_sha256")
    normalized_candidates = (
        path.parent / "normalized" / "records.jsonl",
        path.parent / "candidate-handoff" / "normalized" / "records.jsonl",
        path.parent / "records.jsonl",
    )
    normalized_path = next((candidate for candidate in normalized_candidates if candidate.is_file()), None)
    if isinstance(expected_normalized, str) and normalized_path is not None:
        try:
            actual = hashlib.sha256(normalized_path.read_bytes()).hexdigest()
            integrity_status = "verified-normalized" if actual == expected_normalized else "hash-mismatch"
        except OSError:
            integrity_status = "unavailable"
    else:
        source_meta = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        source_url = payload.get("source_url") or payload.get("stable_url") or source_meta.get("source_url")
        retrieved = payload.get("retrieved_at_utc") or source_meta.get("retrieved_at_utc")
        declared_hash = (
            payload.get("sha256") or payload.get("checksum_sha256") or payload.get("source_artifact_sha256")
            or payload.get("operator_sha256") or payload.get("bytes_sha256") or source_meta.get("sha256")
        )
        if source_url and retrieved and declared_hash:
            integrity_status = "declared-artifact"
        else:
            integrity_status = "missing-provenance"
    return ManifestRecord(
        path=path,
        source_id=source_id,
        normalized_rows=_nested_int(payload, ("normalized_rows",), ("source", "private_rehearsal_normalized_rows")),
        quarantined_rows=_nested_int(payload, ("quarantined_rows",), ("source", "private_rehearsal_validation_findings")),
        candidate_rows=_nested_int(payload, ("candidate_rows",), ("candidate_handoff", "normalized_rows"), ("graph_candidate_summary", "candidate_count")),
        graph_edges=_nested_int(payload, ("graph_edges",), ("graph", "accepted_relationships"), ("graph_candidate_summary", "operator_relationship_candidates"), ("graph_candidates", "count")),
        facility_candidates=_nested_int(payload, ("graph_candidate_summary", "facility_identifier_candidates"), ("review_metrics", "facility_observation", "accepted_distinct_provisional_facility_keys")),
        organization_candidates=_nested_int(payload, ("graph_candidate_summary", "organization_identifier_candidates")),
        coordinate_states=_counter(payload, ("review_metrics", "geospatial", "coordinate_state_counts"), ("coordinate_state_counts",)),
        identity_counts=_counter(payload, ("review_metrics", "facility_observation", "identity_state_counts"), ("identity_state_counts",)),
        digest=hashlib.sha256(path.read_bytes()).hexdigest(),
        integrity_status=integrity_status,
    )


def _json_paths(root: Path) -> Iterable[Path]:
    if root.is_file() and root.suffix.lower() == ".json":
        yield root
    elif root.is_dir():
        for path in sorted(root.rglob("*.json")):
            # Avoid opening row-level JSON payloads while walking a large
            # private archive.  Operators can pass a specific JSON file when
            # a nonstandard aggregate manifest is required.
            name = path.name.casefold()
            parent = path.parent.name.casefold()
            if name == "manifest.json" or "manifest" in name or parent == "manifests" or any(
                token in name for token in ("report", "rehearsal", "release", "proof", "candidate", "evaluation", "status")
            ):
                yield path


def discover_manifests(roots: Iterable[str | Path]) -> list[ManifestRecord]:
    """Read only JSON metadata and return source aggregates, deduplicated."""
    records: list[ManifestRecord] = []
    seen: set[tuple[str, str]] = set()
    for value in roots:
        root = Path(value)
        for path in _json_paths(root):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            record = _manifest_record(path, payload)
            if record is None:
                # Some aggregate manifests contain a source list.  Expand
                # only the source summaries; no row-level content is read.
                for source in payload.get("sources", []):
                    if isinstance(source, dict):
                        child = dict(source)
                        child.setdefault("source_id", source.get("source_id"))
                        child.setdefault("normalized_rows", source.get("normalized_rows"))
                        child.setdefault("quarantined_rows", source.get("quarantined_rows"))
                        child_record = _manifest_record(path, child)
                        if child_record is not None:
                            key = (child_record.source_id, child_record.digest)
                            if key not in seen:
                                seen.add(key)
                                records.append(child_record)
                continue
            key = (record.source_id, record.digest)
            if key not in seen:
                seen.add(key)
                records.append(record)
    return sorted(records, key=lambda item: (item.source_id, str(item.path)))


def _private_state(payload: dict[str, Any]) -> bool:
    return (
        payload.get("release_state") in {None, "not-created", "candidate"}
        and payload.get("publication_state") in {None, "private-candidate"}
        and payload.get("publication_eligibility") in {None, "blocked"}
        and payload.get("public_release_created") is not True
        and payload.get("release_promoted") is not True
    )


def _handoffs(roots: Iterable[str | Path], source_ids: set[str]) -> list[tuple[str, str, Path]]:
    """Find explicit graph/evidence handoff roots without reading rows."""
    found: dict[tuple[str, str, str], tuple[str, str, Path]] = {}
    for value in roots:
        root = Path(value)
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or not _private_state(payload):
                continue
            source_id = _source_id(payload)
            if source_id not in source_ids:
                continue
            handoff_root = manifest_path.parent
            has_records = (handoff_root / "records.jsonl").is_file()
            has_graph_records = (
                (handoff_root / "graph-candidates" / "records.jsonl").is_file()
                or (handoff_root / "graph-candidates.jsonl").is_file()
                or (handoff_root / "graph-candidates" / "graph-candidates.jsonl").is_file()
            )
            if not (has_records or has_graph_records):
                continue
            kind = "evidence" if (
                payload.get("entity_scope") == "evidence_event"
                or payload.get("source_kind") == "evidence_event"
                or payload.get("contract_version") in EVIDENCE_CONTRACTS
            ) else "facility"
            artifact_key = _source_artifact_sha256(payload)
            if not artifact_key:
                artifact_key = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            key = (source_id, kind, artifact_key)
            # Prefer the most recently declared artifact without exposing its
            # path in reports.  Stable lexical ordering breaks ties.
            existing = found.get(key)
            candidate = (source_id, kind, handoff_root)
            if existing is None or str(handoff_root) > str(existing[2]):
                found[key] = candidate
    return sorted(found.values(), key=lambda item: (item[0], item[1], str(item[2])))


def build_report(roots: Iterable[str | Path], *, selected_sources: Iterable[str] | None = None) -> dict[str, Any]:
    records = discover_manifests(roots)
    selected = {item.strip() for item in selected_sources or () if item.strip()}
    if selected:
        records = [item for item in records if item.source_id in selected]
    by_source: dict[str, list[ManifestRecord]] = {}
    for record in records:
        by_source.setdefault(record.source_id, []).append(record)
    sources = []
    for source_id in sorted(by_source):
        entries = by_source[source_id]
        # Acquisition retries and private QA copies commonly leave several
        # manifests for one source.  Select the most informative run rather
        # than summing retries, which would over-count real observations.
        def score(item: ManifestRecord) -> tuple[int, int, int, int, int, int, str]:
            return (
                item.normalized_rows or 0,
                item.quarantined_rows or 0,
                item.candidate_rows or 0,
                item.graph_edges or 0,
                item.facility_candidates or 0,
                item.organization_candidates or 0,
                item.digest,
            )
        chosen = max(entries, key=score)
        sources.append({
            "source_id": source_id,
            "manifest_count_seen": len(entries),
            "selected_manifest_digest": chosen.digest,
            "normalized_rows": chosen.normalized_rows,
            "quarantined_rows": chosen.quarantined_rows,
            "candidate_rows": chosen.candidate_rows,
            "graph_edge_candidates": chosen.graph_edges,
            "facility_identifier_candidates": chosen.facility_candidates,
            "organization_identifier_candidates": chosen.organization_candidates,
            "coordinate_state_counts": dict(sorted(chosen.coordinate_states.items())),
            "identity_state_counts": dict(sorted(chosen.identity_counts.items())),
            "integrity_status": chosen.integrity_status,
        })
    return {
        "schema_version": REPORT_VERSION,
        "scope": "private retained manifests only; raw rows and private filesystem paths excluded",
        "publication": {"release_created": False, "promoted": False, "public_rows": 0, "approval_inferred": False},
        "source_count": len(sources),
        "sources": sources,
        "totals": {
            key: sum(item[key] or 0 for item in sources)
            for key in ("normalized_rows", "quarantined_rows", "candidate_rows", "graph_edge_candidates", "facility_identifier_candidates", "organization_identifier_candidates")
        },
        "limitations": [
            "Manifest counts are not a completeness or accuracy claim.",
            "All rows remain private and review-required; no approval is inferred.",
            "A candidate edge is not a canonical identity or published relationship.",
            "Real precision and recall remain unmeasured without human-adjudicated labels.",
        ],
    }


def discover_graph_handoffs(roots: Iterable[str | Path], *,
                           selected_sources: Iterable[str] | None = None) -> list[tuple[str, str, Path]]:
    """Discover the latest private facility/evidence handoff for each source family."""
    report = build_report(roots, selected_sources=selected_sources)
    source_ids = {item["source_id"] for item in report["sources"]}
    return _handoffs(roots, source_ids)


def materialize_discovered_graph_corpus(
    roots: Iterable[str | Path], *, database_url: str,
    private_target: tuple[str, str], selected_sources: Iterable[str] | None = None,
    batch_size: int = 250,
) -> dict[str, Any]:
    """Production refresh entry point: discover all source families, then match/import."""
    handoffs = discover_graph_handoffs(roots, selected_sources=selected_sources)
    if not handoffs:
        raise ValueError("no private graph candidate or evidence handoffs were discovered")
    return materialize_graph_corpus(
        database_url, [path for _, _, path in handoffs],
        private_target=private_target, batch_size=batch_size,
    )


def run_rehearsal(
    roots: Iterable[str | Path],
    *,
    selected_sources: Iterable[str] | None = None,
    database_url: str = "",
    disposable_db: bool = False,
    private_target: tuple[str, str] | None = None,
    batch_size: int = 250,
    edge_builder: ConnectionEdgeBuilder | None = None,
) -> dict[str, Any]:
    report = build_report(roots, selected_sources=selected_sources)
    source_ids = {item["source_id"] for item in report["sources"]}
    handoffs = _handoffs(roots, source_ids)
    report["handoffs"] = {
        "discovered": len(handoffs),
        "facility": sum(kind == "facility" for _, kind, _ in handoffs),
        "evidence": sum(kind == "evidence" for _, kind, _ in handoffs),
        "source_ids": sorted({source_id for source_id, _, _ in handoffs}),
    }
    report["database"] = {"attempted": bool(database_url), "imports": [], "public_rows": 0}
    if database_url:
        if private_target is not None:
            if disposable_db:
                raise ValueError("choose either disposable or configured private target")
            result = materialize_graph_corpus(
                database_url, [path for _, _, path in handoffs],
                private_target=private_target, batch_size=batch_size,
            )
            report["database"].update({
                "status": result.get("status"),
                "materialization_fingerprint": result.get("materialization_fingerprint"),
                "imports": result.get("imports", []),
                "matcher": result.get("matcher", {}),
                "public_rows": 0,
            })
            report["database"]["completed"] = sum(
                item.get("status") in {"completed", "already_present"}
                for item in report["database"]["imports"])
            report["database"]["blocked"] = 0
            return report
        if not disposable_db:
            raise ValueError("database rehearsal requires disposable_db=True")
        phases: dict[str, float] = {}
        stage_started = time.perf_counter()
        matcher_stage: _MatcherStage | None = None
        try:
            if edge_builder is None:
                matcher_stage = _MatcherStage()
                for _, kind, handoff_root in handoffs:
                    if kind == "facility":
                        matcher_stage.add_handoff(handoff_root)
                stage_stats = matcher_stage.build_candidates()
                phases["matcher_staging_and_generation"] = round(time.perf_counter() - stage_started, 6)
                edge_builder = matcher_stage.edge_builder
            for source_id, kind, handoff_root in handoffs:
                importer = import_evidence_events if kind == "evidence" else import_graph_candidates
                try:
                    import_kwargs = {"disposable_db": True}
                    if kind == "facility" and edge_builder is not None:
                        import_kwargs["edge_builder"] = edge_builder
                    result = importer(database_url, handoff_root, **import_kwargs)
                    result_summary = {key: value for key, value in result.items() if isinstance(value, (int, float, bool, str))}
                    for key in ("phase_timings_seconds", "peak_rss_bytes"):
                        if key in result:
                            result_summary[key] = result[key]
                    report["database"]["imports"].append({"source_id": source_id, "kind": kind, "status": "completed", "result": result_summary})
                except Exception as exc:  # operator report records aggregate blocker, never payload
                    report["database"]["imports"].append({"source_id": source_id, "kind": kind, "status": "blocked", "error_type": type(exc).__name__})
            phases["database_import"] = round(time.perf_counter() - stage_started, 6) - phases.get("matcher_staging_and_generation", 0)
            report["database"]["runtime"] = {
                "phase_timings_seconds": phases,
                "peak_rss_bytes": _rss_bytes(),
                "staging": stage_stats if matcher_stage is not None else {"external_edge_builder": True},
                "candidate_processing": "disk-backed observation and edge staging; no global candidate cap",
            }
        finally:
            if matcher_stage is not None:
                matcher_stage.close()
    report["database"]["completed"] = sum(item["status"] == "completed" for item in report["database"]["imports"])
    report["database"]["blocked"] = sum(item["status"] == "blocked" for item in report["database"]["imports"])
    return report


def write_report(report: dict[str, Any], output: str | Path) -> str:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()
