"""Exact, release-scoped source redistribution rights gates.

The ledger is append-only and records attributable owner decisions.  This
module only verifies that a trusted operator has recorded a matching decision;
it does not grant authority, make a legal determination, or perform approval
writes.  Acquisition permission and source attribution remain separate.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


class SourceRightsBlocked(ValueError):
    """A release has no unambiguous cleared decision for every input artifact."""


@dataclass(frozen=True)
class RightsRequirement:
    source_id: str
    profile: str
    release_id: str
    artifact_id: str
    artifact_sha256: str
    status: str
    decision_ids: tuple[str, ...]


# The requirement set is deliberately based on every default-visible release
# member, deduplicated by immutable artifact digest.  A release made from two
# source snapshots therefore needs two exact decisions.  Current suppression
# removes a record from the output and is already independently enforced by
# every projection/package query.
REQUIRED_ARTIFACTS_SQL = """
SELECT DISTINCT
       source.source_id,
       release.profile,
       release.release_id,
       artifact.artifact_id,
       artifact.sha256
FROM uec.release_members member
JOIN uec.releases release ON release.release_id = member.release_id
JOIN uec.observations observation ON observation.observation_id = member.observation_id
JOIN uec.source_records record ON record.source_record_id = observation.source_record_id
JOIN uec.sources source ON source.source_id = record.source_id
JOIN uec.raw_artifacts artifact ON artifact.artifact_id = record.artifact_id
WHERE member.release_id = %s
  AND member.default_visible = true
  AND NOT EXISTS (
      SELECT 1
      FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id = record.source_record_id
  )
ORDER BY source.source_id, release.profile, release.release_id, artifact.artifact_id
"""

DECISIONS_SQL = """
SELECT source_rights_decision_id::text,
       source_id,
       profile,
       release_id,
       artifact_id::text,
       artifact_sha256,
       redistribution_status,
       decision_actor,
       decision_reference,
       decided_at
FROM uec.source_rights_decisions
WHERE source_id = ANY(%s)
  AND profile = %s
  AND release_id = %s
  AND artifact_id = ANY(%s::uuid[])
ORDER BY source_id, artifact_id, decided_at DESC, source_rights_decision_id DESC
"""


def _field(row: Any, name: str, index: int) -> Any:
    if isinstance(row, dict):
        return row[name]
    return row[index]


def evaluate(connection: Any, release_id: str) -> dict[str, Any]:
    """Return exact rights status for all artifact versions in a release.

    Multiple decisions at the newest timestamp are allowed only when they
    agree.  Conflicting newest decisions are ambiguous and block the release;
    an older cleared decision cannot override a newer unknown/restricted one.
    """

    required_rows = connection.execute(REQUIRED_ARTIFACTS_SQL, (release_id,)).fetchall()
    if not required_rows:
        return {"requirements": [], "blockers": [], "status": "cleared"}

    required = [
        {
            "source_id": _field(row, "source_id", 0),
            "profile": _field(row, "profile", 1),
            "release_id": _field(row, "release_id", 2),
            "artifact_id": str(_field(row, "artifact_id", 3)),
            "artifact_sha256": str(_field(row, "sha256", 4)),
        }
        for row in required_rows
    ]
    source_ids = sorted({item["source_id"] for item in required})
    profiles = {item["profile"] for item in required}
    release_ids = {item["release_id"] for item in required}
    if len(profiles) != 1 or release_ids != {release_id}:
        return {
            "requirements": required,
            "blockers": [{**item, "reason": "release identity is ambiguous"} for item in required],
            "status": "blocked",
        }
    artifact_ids = [item["artifact_id"] for item in required]
    decision_rows = connection.execute(
        DECISIONS_SQL,
        (source_ids, next(iter(profiles)), release_id, artifact_ids),
    ).fetchall()
    by_scope: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in decision_rows:
        by_scope[(str(_field(row, "source_id", 1)), str(_field(row, "artifact_id", 4)))].append(
            {
                "decision_id": str(_field(row, "source_rights_decision_id", 0)),
                "status": _field(row, "redistribution_status", 6),
                "actor": _field(row, "decision_actor", 7),
                "reference": _field(row, "decision_reference", 8),
                "decided_at": _field(row, "decided_at", 9),
            }
        )

    evaluated: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for item in required:
        decisions = by_scope.get((item["source_id"], item["artifact_id"]), [])
        latest_at = max((decision["decided_at"] for decision in decisions), default=None)
        latest = [decision for decision in decisions if decision["decided_at"] == latest_at] if latest_at is not None else []
        statuses = {decision["status"] for decision in latest}
        status = next(iter(statuses)) if len(statuses) == 1 else "ambiguous"
        if not latest:
            reason = "missing exact decision"
        elif len(statuses) > 1:
            reason = "conflicting decisions at the latest decision time"
        elif status != "cleared":
            reason = f"redistribution decision is {status}"
        else:
            reason = None
        result = {
            **item,
            "status": status if latest else "unknown",
            "decision_ids": tuple(decision["decision_id"] for decision in latest),
        }
        evaluated.append(result)
        if reason:
            blockers.append({**item, "reason": reason, "decision_ids": result["decision_ids"]})
    return {
        "requirements": evaluated,
        "blockers": blockers,
        "status": "cleared" if not blockers else "blocked",
    }


def require_cleared(connection: Any, release_id: str) -> dict[str, Any]:
    result = evaluate(connection, release_id)
    if result["blockers"]:
        details = "; ".join(
            f"{item['source_id']}:{item['artifact_sha256']} ({item['reason']})"
            for item in result["blockers"]
        )
        raise SourceRightsBlocked(f"source redistribution rights gate failed: {details}")
    return result
