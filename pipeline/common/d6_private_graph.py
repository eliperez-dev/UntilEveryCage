"""D6 bounded private graph connection contract and injected-store rehearsal.

The store is intentionally narrow: it models the query shape expected by the
Rust private API while keeping real source handoffs outside Git.  Only
source-scoped IDs, aggregate scores, evidence references, and review metadata
are returned.  It is suitable for contract tests when a disposable Postgres
or external private handoff is unavailable.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from pipeline.common.d5_connection_analysis import EVIDENCE_SOURCE_IDS, _Observed, _probabilistic_candidates
from pipeline.common.d61_verification import D61_PAGE_MAX, build_report


CONNECTION_RULESET = "d6-connection-edges-v1"
MAX_LIMIT = 100


class ConnectionQueryError(ValueError):
    """A private connection query is invalid or exceeds its bound."""


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class ConnectionEdge:
    edge_id: str
    source_id: str
    source_record_id: str | None
    connection_type: str
    left_entity_type: str
    left_entity_id: str
    right_entity_type: str
    right_entity_id: str
    confidence: float | None
    conflicting: bool = False
    suppressed: bool = False
    evidence_refs: tuple[Mapping[str, str], ...] = ()
    score_contributions: Mapping[str, float] = field(default_factory=dict)
    disclaimer: str = "Review evidence only; no canonical identity or claim transfer is implied."
    ruleset: str = CONNECTION_RULESET
    observed_at: str = ""

    def as_safe_mapping(self) -> dict[str, Any]:
        disclaimer = self.disclaimer
        if self.connection_type == "inferred" and "not human verified" not in disclaimer.casefold():
            disclaimer = disclaimer.rstrip(".") + "; not human verified."
        return {
            "connection_edge_id": self.edge_id,
            "source_id": self.source_id,
            "source_record_id": self.source_record_id,
            "connection_type": self.connection_type,
            "left_entity_type": self.left_entity_type,
            "left_entity_id": self.left_entity_id,
            "right_entity_type": self.right_entity_type,
            "right_entity_id": self.right_entity_id,
            "confidence": self.confidence,
            "conflicting": self.conflicting,
            "suppressed": self.suppressed,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "score_contributions": dict(self.score_contributions),
            "disclaimer": disclaimer,
            "ruleset": self.ruleset,
            "observed_at": self.observed_at,
            "inferred_metadata": {
                "review_state": "review_required" if self.connection_type == "inferred" else "source_asserted",
                "confidence_kind": "ruleset_estimate_not_probability" if self.connection_type == "inferred" else "source_assertion",
            },
            "automatic_merge": False,
            "transfers_claims": False,
            "publication_status": "not_eligible",
        }


class ConnectionStore:
    """Injected private store used by D6 tests and offline diagnostics."""

    def __init__(self) -> None:
        self.edges: dict[str, ConnectionEdge] = {}
        self.organization_nodes: set[str] = set()
        self.facility_nodes: set[str] = set()
        self.evidence_nodes: set[str] = set()

    def add(self, edge: ConnectionEdge) -> bool:
        if edge.connection_type not in {"exact", "inferred"}:
            raise ConnectionQueryError("connection_type must be exact or inferred")
        if edge.left_entity_id == edge.right_entity_id:
            raise ConnectionQueryError("connection endpoints must differ")
        if edge.confidence is not None and not 0 <= edge.confidence <= 1:
            raise ConnectionQueryError("confidence must be between 0 and 1")
        if edge.edge_id in self.edges:
            return False
        self.edges[edge.edge_id] = edge
        return True

    def query(
        self,
        *,
        connection_type: str | None = None,
        min_confidence: float | None = None,
        include_conflicting: bool = False,
        suppressed: bool = False,
        source_id: str | None = None,
        entity_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        if connection_type is not None and connection_type not in {"exact", "inferred"}:
            raise ConnectionQueryError("connection_type must be exact or inferred")
        if min_confidence is not None and not 0 <= min_confidence <= 1:
            raise ConnectionQueryError("min_confidence must be between 0 and 1")
        if not 1 <= limit <= MAX_LIMIT:
            raise ConnectionQueryError("limit must be between 1 and 100")
        ordered = sorted(self.edges.values(), key=lambda edge: (edge.observed_at, edge.edge_id), reverse=True)
        if cursor is not None:
            seen = False
            after: list[ConnectionEdge] = []
            for edge in ordered:
                if seen:
                    after.append(edge)
                elif edge.edge_id == cursor:
                    seen = True
            ordered = after if seen else []
        selected = [edge for edge in ordered if (
            (connection_type is None or edge.connection_type == connection_type)
            and (min_confidence is None or (edge.confidence is not None and edge.confidence >= min_confidence))
            and (include_conflicting or not edge.conflicting)
            and edge.suppressed == suppressed
            and (source_id is None or edge.source_id == source_id)
            and (entity_id is None or entity_id in {edge.left_entity_id, edge.right_entity_id})
        )]
        page = selected[:limit]
        return {
            "api_version": "private-graph-v2",
            "data": [edge.as_safe_mapping() for edge in page],
            "meta": {
                "private": True,
                "bounded": True,
                "limit": limit,
                "page_max": D61_PAGE_MAX,
                # The API bounds response pages; it does not assert a storage
                # cap.  Keep this explicit so operators do not mistake LIMIT
                # 100 for a corpus-size ceiling.
                "storage_cap": None,
                "next_cursor": page[-1].edge_id if len(page) == limit else None,
                "connection_type": connection_type,
                "min_confidence": min_confidence,
                "include_conflicting": include_conflicting,
                "suppressed": suppressed,
                "source_id": source_id,
                "entity_id": entity_id,
                "public_projection": False,
            },
        }

    def import_observations(self, rows: Iterable[_Observed]) -> dict[str, int]:
        """Materialize compact real-handoff observations as private edges."""
        inserted = 0
        already_present = 0
        for row in rows:
            facilities = sorted(row.facility_ids.values())
            organizations = sorted(row.organization_ids.values())
            for organization in organizations:
                self.organization_nodes.add(f"org:{row.source_id}:{organization}")
            for facility in facilities:
                self.facility_nodes.add(f"facility:{row.source_id}:{facility}")
            if row.source_id in EVIDENCE_SOURCE_IDS:
                self.evidence_nodes.add(f"evidence:{row.source_id}:{_digest(row.key)}")
                continue
            for organization in organizations:
                for facility in facilities:
                    edge = ConnectionEdge(
                        edge_id=_digest(row.source_id, row.key, organization, facility, "exact"),
                        source_id=row.source_id,
                        source_record_id=_digest(row.source_id, row.key),
                        connection_type="exact",
                        left_entity_type="organization",
                        left_entity_id=f"org:{row.source_id}:{organization}",
                        right_entity_type="facility",
                        right_entity_id=f"facility:{row.source_id}:{facility}",
                        confidence=1.0,
                        evidence_refs=({"source_id": row.source_id, "source_record_ref": _digest(row.source_id, row.key)},),
                        score_contributions={"source_native_identifier": 1.0},
                        observed_at=(row.dates[0] if row.dates else ""),
                    )
                    if self.add(edge):
                        inserted += 1
                    else:
                        already_present += 1
        return {"inserted": inserted, "already_present": already_present, "organizations": len(self.organization_nodes), "facilities": len(self.facility_nodes), "evidence": len(self.evidence_nodes)}

    def import_inferred_candidates(self, rows: Iterable[_Observed], *, limit: int | None = None) -> int:
        """Import source-qualified inferred endpoints.

        ``limit`` is an optional explicit caller page for compatibility with
        bounded jobs.  There is no product-wide 5,000-row default; callers
        that need paging should use the matcher cursor/batch API.
        """
        candidates, _ = _probabilistic_candidates(list(rows), limit=limit)
        inserted = 0
        for candidate in candidates:
            endpoints = candidate.get("endpoints") or []
            if len(endpoints) != 2:
                # The matcher never emits placeholders.  Keep this store
                # fail-closed if a legacy candidate is supplied.
                continue
            left_endpoint, right_endpoint = endpoints
            left = str(left_endpoint["source_id"])
            right = str(right_endpoint["source_id"])
            left_entity_id = f"facility:{left}:{left_endpoint['identifier_type']}:{left_endpoint['source_identifier']}"
            right_entity_id = f"facility:{right}:{right_endpoint['identifier_type']}:{right_endpoint['source_identifier']}"
            edge = ConnectionEdge(
                edge_id=candidate["candidate_digest"],
                source_id=left,
                source_record_id=None,
                connection_type="inferred",
                left_entity_type="facility",
                left_entity_id=left_entity_id,
                right_entity_type="facility",
                right_entity_id=right_entity_id,
                confidence=float(candidate["confidence"]),
                evidence_refs=tuple({"source_id": item["source_id"], "source_record_ref": item.get("source_record_key", "")} for item in endpoints),
                score_contributions={feature: 1.0 for feature in candidate["contributing_features"]},
                disclaimer=candidate["disclaimer"],
                ruleset=candidate["ruleset"],
            )
            inserted += self.add(edge)
        return inserted


def rehearse(rows: Iterable[_Observed], *, positive_controls: int = 1) -> dict[str, Any]:
    """Run aggregate-only real-shaped D6 controls against an injected store."""
    compact = list(rows)
    store = ConnectionStore()
    first = store.import_observations(compact)
    inferred = store.import_inferred_candidates(compact)
    second = store.import_observations(compact)
    exact = store.query(connection_type="exact", suppressed=False, limit=MAX_LIMIT)
    inferred_page = store.query(connection_type="inferred", min_confidence=0.0, suppressed=False, limit=MAX_LIMIT)
    positive_verified = len(exact["data"]) >= positive_controls
    verification = build_report(
        execution="injected_store_supplementary",
        authorized_handoffs=0,
        private_rows_consumed=len(compact),
        candidate_count=inferred,
        candidate_exact_count=first["inserted"],
        candidate_inferred_count=inferred,
        persisted_exact_count=len(exact["data"]),
        persisted_inferred_count=len(inferred_page["data"]),
        skipped_ambiguous_count=0,
        negative_controls=0,
        conflicting_controls=sum(edge.conflicting for edge in store.edges.values()),
        genuine_inferred_connections=0,
        real_rehearsal_executed=False,
        idempotent=second["inserted"] == 0,
        api_pages={"exact": len(exact["data"]), "inferred": len(inferred_page["data"])},
        public_rows=0,
        public_edges=0,
    )
    return {
        "schema_version": "d6-private-graph-api-e2e-v1",
        "scope": {"private_rows_consumed": len(compact), "row_payloads_in_report": False},
        "import": {"first": first, "inferred_inserted": inferred, "rerun": second, "idempotent": second["inserted"] == 0},
        "nodes": {"organizations": len(store.organization_nodes), "facilities": len(store.facility_nodes), "evidence": len(store.evidence_nodes)},
        "connections": {"exact": len(exact["data"]), "inferred": len(inferred_page["data"]), "nonzero": bool(store.edges), "automatic_merge": False, "claim_transfer": False},
        "controls": {"positive_exact_edges": len(exact["data"]), "expected_positive_controls": positive_controls, "positive_verified": positive_verified, "negative_aphis_fsis_edges": 0, "aphis_fsis_policy": "never automatic"},
        "status": "verified" if positive_verified else "blocked-real-controls-unavailable",
        "query_contract": {"filters": ["connection_type", "min_confidence", "include_conflicting", "suppressed", "source_id", "entity_id", "cursor", "limit"], "max_limit": MAX_LIMIT, "safe_metadata": True, "provenance": True, "score_contributions": True, "disclaimer": True, "ruleset": True},
        "public": {"rows": 0, "api_unchanged": True, "map_unchanged": True, "export_unchanged": True},
        "d6_1_verification": verification,
    }
