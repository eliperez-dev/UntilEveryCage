"""Assertions shared by the mandatory D6.1 real Docker/Postgres rehearsal."""
from __future__ import annotations

from typing import Any


def assert_real_inferred_control(connection: Any) -> dict[str, int]:
    """Require at least one evidence-backed inferred edge in disposable DB.

    The caller must load an authorized retained handoff through the integrated
    matcher/persistence lane before invoking this assertion.  No synthetic
    seed is accepted: the query requires non-empty source references and the
    ruleset disclaimer on each counted edge.  All counted edges must remain
    private and publication-ineligible.
    """
    inferred = connection.execute(
        """
        SELECT count(*)
        FROM uec.graph_connection_edges
        WHERE connection_type = 'inferred'
          AND confidence_band <> 'exact'
          AND supporting_source_refs <> '[]'::jsonb
          AND COALESCE(signal_explanation->>'disclaimer', '') <> ''
          AND storage_state = 'private'
          AND publication_status = 'not_eligible'
        """
    ).fetchone()[0]
    public_edges = connection.execute(
        "SELECT count(*) FROM uec.graph_public_relationships"
    ).fetchone()[0]
    if inferred < 1:
        raise AssertionError(
            "D6.1 real rehearsal requires at least one genuine inferred connection; found zero"
        )
    if public_edges != 0:
        raise AssertionError("D6.1 real rehearsal must leave the public relationship projection empty")
    return {"genuine_inferred_connections": int(inferred), "public_edges": int(public_edges)}
