"""Synthetic D4 private graph/evidence rehearsal.

This module is deliberately an in-memory contract harness.  It exercises the
control-plane guarantees needed by the D4 handoff without importing source
rows, contacting providers, creating a release, or making a public graph.
Identifiers are synthetic and source-scoped; the row-free report is the only
artifact intended to leave the rehearsal boundary.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from pipeline.common.d2_e2e_readiness import D2_SOURCE_IDS
from pipeline.common.d3_live_operations import D3_FACILITY_SOURCE_IDS, D3_EVIDENCE_SOURCE_IDS


D4_REPORT_VERSION = "d4-private-graph-e2e-v1"
D4_FACILITY_SOURCE_IDS = D2_SOURCE_IDS + D3_FACILITY_SOURCE_IDS
D4_SOURCE_IDS = D4_FACILITY_SOURCE_IDS + D3_EVIDENCE_SOURCE_IDS
D4_SOURCE_KINDS = {
    **{source_id: "facility_master" for source_id in D4_FACILITY_SOURCE_IDS},
    **{source_id: "evidence_event" for source_id in D3_EVIDENCE_SOURCE_IDS},
}


class GraphRehearsalError(ValueError):
    """A synthetic graph operation violated the private handoff contract."""


@dataclass(frozen=True)
class BatchReceipt:
    source_id: str
    source_kind: str
    batch_key: str
    status: str
    accepted: int
    review_required: int
    public_rows: int = 0


class SyntheticPrivateGraph:
    """Minimal state machine for D4's private graph/evidence boundaries."""

    def __init__(self, *, private_token: str = "d4-private-token") -> None:
        if not private_token:
            raise ValueError("private_token must be non-empty")
        self.private_token = private_token
        self._batches: dict[str, BatchReceipt] = {}
        self._pending: dict[str, tuple[str, str, int]] = {}
        self._entities: set[str] = set()
        self._evidence: set[str] = set()
        self._review: list[dict[str, str]] = []
        self._lineage: list[dict[str, str]] = []
        self._suppressed: set[str] = set()

    @staticmethod
    def _batch_key(source_id: str, source_kind: str, keys: Iterable[str]) -> str:
        ordered = "\n".join(sorted(str(key) for key in keys))
        return hashlib.sha256(f"{source_id}|{source_kind}|{ordered}".encode()).hexdigest()

    def import_batch(
        self,
        source_id: str,
        source_kind: str,
        keys: Iterable[str],
        *,
        corrupted: bool = False,
        interrupted_after: int | None = None,
    ) -> BatchReceipt:
        """Import a bounded synthetic batch, retaining review-only state."""
        expected = D4_SOURCE_KINDS.get(source_id)
        if expected is None:
            raise GraphRehearsalError("source is outside the D4 handoff scope")
        if source_kind != expected:
            raise GraphRehearsalError(f"source-kind mismatch for {source_id}")
        ordered = tuple(sorted(str(key) for key in keys))
        if not ordered or any(not key for key in ordered):
            raise GraphRehearsalError("batch keys must be non-empty")
        batch_key = self._batch_key(source_id, source_kind, ordered)
        existing = self._batches.get(batch_key)
        if existing is not None:
            return BatchReceipt(source_id, source_kind, batch_key, "already_present", 0, existing.review_required)
        prior = self._pending.get(batch_key)
        # Interrupted work is intentionally replayed from the beginning.  A
        # batch key makes that replay idempotent, while avoiding a half-written
        # private graph state in this rehearsal harness.
        start = 0 if prior is not None else 0
        if corrupted:
            raise GraphRehearsalError("corrupted source rejected before materialization")
        stop = len(ordered) if interrupted_after is None else max(0, min(len(ordered), interrupted_after))
        if stop < len(ordered):
            self._pending[batch_key] = (source_id, source_kind, len(ordered))
            return BatchReceipt(source_id, source_kind, batch_key, "interrupted", 0, 0)
        accepted = 0
        for key in ordered[start:]:
            digest = hashlib.sha256(f"{source_id}|{key}".encode()).hexdigest()[:20]
            if source_kind == "evidence_event":
                self._evidence.add(f"evidence:{source_id}:{digest}")
            else:
                self._entities.add(f"facility:{source_id}:{digest}")
            accepted += 1
        self._pending.pop(batch_key, None)
        receipt = BatchReceipt(source_id, source_kind, batch_key, "completed", accepted, len(ordered))
        self._batches[batch_key] = receipt
        return receipt

    def review_exact_id(self, source_id: str, source_record_key: str) -> str:
        """Queue an exact-ID US candidate; review never implies a merge."""
        if source_id != "us.fsis" or not source_record_key:
            raise GraphRehearsalError("exact-ID review fixture must be a US FSIS candidate")
        candidate_id = f"candidate:{source_id}:{hashlib.sha256(source_record_key.encode()).hexdigest()[:20]}"
        self._review.append({"candidate_id": candidate_id, "method": "exact-source-id", "state": "review_required"})
        return candidate_id

    def queue_match_candidate(self, method: str, subject: str) -> str:
        """Retain deterministic/probabilistic matches as review candidates."""
        if method not in {"deterministic", "probabilistic"} or not subject:
            raise GraphRehearsalError("unsupported match candidate")
        candidate_id = f"candidate:{method}:{hashlib.sha256(subject.encode()).hexdigest()[:20]}"
        self._review.append({"candidate_id": candidate_id, "method": method, "state": "review_required"})
        return candidate_id

    def record_lineage(self, action: str, *, subject: str, target: str) -> None:
        if action not in {"merge", "split", "reversal"}:
            raise GraphRehearsalError("unsupported lineage action")
        self._lineage.append({"action": action, "subject": subject, "target": target})

    def suppress(self, subject: str) -> None:
        if not subject:
            raise GraphRehearsalError("suppression subject is required")
        self._suppressed.add(subject)

    def private_query(self, token: str | None) -> dict[str, Any]:
        if token != self.private_token:
            raise PermissionError("private graph authentication failed closed")
        return {"entities": len(self._entities), "evidence": len(self._evidence), "review_required": len(self._review)}

    def public_query(self) -> dict[str, Any]:
        return {"entities": 0, "evidence": 0, "relationships": 0, "release_created": False}

    def report(self) -> dict[str, Any]:
        return {
            "schema_version": D4_REPORT_VERSION,
            "scope": {"source_ids": list(D4_SOURCE_IDS), "facility_sources": list(D4_FACILITY_SOURCE_IDS), "evidence_sources": list(D3_EVIDENCE_SOURCE_IDS), "execution": "sequential"},
            "batches": {"count": len(self._batches), "pending": len(self._pending), "accepted": sum(item.accepted for item in self._batches.values()), "review_required": sum(item.review_required for item in self._batches.values())},
            "review": {
                "exact_id_candidates": sum(item["method"] == "exact-source-id" for item in self._review),
                "deterministic_candidates": sum(item["method"] == "deterministic" for item in self._review),
                "probabilistic_candidates": sum(item["method"] == "probabilistic" for item in self._review),
                "auto_merge": False,
            },
            "lineage": {"events": len(self._lineage), "merge_split_reversal_preserved": True},
            "suppression": {"active": len(self._suppressed), "public_exposure": False},
            "public": self.public_query(),
            "publication": {"release_created": False, "promoted": False, "published": False},
        }


def run_scale_rehearsal(*, count: int = 10_000, batch_size: int = 500) -> dict[str, Any]:
    """Run a bounded synthetic scale pass and return aggregate timings only."""
    if count < 1 or count > 100_000 or batch_size < 1:
        raise ValueError("count must be 1..100000 and batch_size must be positive")
    started = time.perf_counter()
    graph = SyntheticPrivateGraph()
    for offset in range(0, count, batch_size):
        graph.import_batch("us.fsis", "facility_master", (f"synthetic-{index}" for index in range(offset, min(count, offset + batch_size))))
    elapsed = time.perf_counter() - started
    return {"count": count, "batch_size": batch_size, "batches": (count + batch_size - 1) // batch_size, "elapsed_seconds": round(elapsed, 6), "public_rows": graph.public_query()["entities"], "bounded": True}
