"""Carry an existing APHIS metadata-only decision to an identical public release.

This operator utility is dry-run by default. It never approves novel source
facts: it only copies existing, exact-scope decisions for the same immutable
source record and artifact to the fixed successor release.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from urllib.parse import urlsplit

TARGET_DATABASE = "uec_country_release_test_20261027"
SOURCE_RELEASE = "release-2026-10-18"
TARGET_RELEASE = "release-2026-10-27-r2"
TARGET_FREEZE_SHA256 = "86d32bf5c0dcfd56dc93773b42040d40cfca082c5cd3d8424dfc88b249bcde0e"
DECISION_REFERENCE = (
    "user-approved-reference-metadata-only;"
    "https://www.aphis.usda.gov/animal-care/awa-services/usda-animal-care-public-search-tool"
)
SCOPE_VERSION = "aphis-public-reference-metadata-v1"
APPROVED_FIELDS = [
    "source_id", "evidence_type", "event_date", "event_period",
    "observed_at", "source_url", "match_method",
]
ALLOWED_SOURCES = ("us.aphis.annual-reports", "us.inspections")


class CarryForwardError(ValueError):
    """Safe, non-row-bearing error for a failed carry-forward precondition."""


def validate_database_url(database_url: str, expected_database: str) -> None:
    if expected_database != TARGET_DATABASE:
        raise CarryForwardError("expected_database_not_allowed")
    try:
        parsed = urlsplit(database_url)
        _ = parsed.port
    except ValueError as exc:
        raise CarryForwardError("database_url_invalid") from exc
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise CarryForwardError("database_url_scheme_invalid")
    if parsed.path.lstrip("/") != TARGET_DATABASE:
        raise CarryForwardError("database_url_database_mismatch")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise CarryForwardError("database_url_host_not_loopback")
    if parsed.username is None or parsed.password is None:
        raise CarryForwardError("database_url_credentials_required")
    if parsed.query or parsed.fragment:
        raise CarryForwardError("database_url_routing_options_forbidden")


def _eligible_rows(connection, *, candidate_target: bool = False):
    """Return only rows passing all source/target and current-safety gates."""
    target_gate = (
        "target_release.profile='official' AND target_release.test_only IS FALSE "
        "AND target_release.status IN ('candidate','validated') "
        "AND target_release.summary->>'candidate_only'='true' "
        "AND target_release.summary->>'freeze_sha256'=%s"
        if candidate_target else
        "target_release.profile='official' AND target_release.test_only IS FALSE "
        "AND (target_release.status='promoted' OR (target_release.status='validated' "
        "AND EXISTS (SELECT 1 FROM uec.public_release_history history "
        "WHERE history.release_id=target_release.release_id "
        "AND history.profile=target_release.profile)))"
    )
    return connection.execute(
        f"""
        WITH eligible_release AS (
            SELECT release.release_id
            FROM uec.releases release
            WHERE release.profile='official'
              AND release.test_only IS FALSE
              AND (release.status='promoted' OR (
                    release.status='validated' AND EXISTS (
                        SELECT 1 FROM uec.public_release_history history
                        WHERE history.release_id=release.release_id
                          AND history.profile=release.profile)))
        ),
        source_decision AS (
            SELECT DISTINCT ON (source_id,profile,release_id,artifact_id)
                   clearance.clearance_event_id, clearance.source_id,
                   clearance.profile, clearance.release_id, clearance.artifact_id,
                   clearance.artifact_sha256, clearance.scope_version,
                   clearance.decision_status, clearance.approved_fields,
                   clearance.decision_actor, clearance.decision_reference
            FROM uec.graph_public_evidence_metadata_clearance_events clearance
            WHERE clearance.source_id = ANY(%s)
              AND clearance.profile='official'
              AND clearance.release_id=%s
            ORDER BY source_id,profile,release_id,artifact_id,
                     decided_at DESC,clearance_event_id DESC
        ),
        source_review AS (
            SELECT DISTINCT ON (review.source_record_id,scope.release_id)
                   review.source_record_id,scope.release_id,
                   review.publication_review_event_id,review.factual_review_status,
                   review.privacy_screening_status,review.maintainer_approval,
                   review.publication_eligible,review.reviewer_role,review.note
            FROM uec.publication_review_events review
            JOIN uec.publication_review_release_scopes scope
              USING(publication_review_event_id)
            WHERE scope.release_id=%s
            ORDER BY review.source_record_id,scope.release_id,
                     review.reviewed_at DESC,review.publication_review_event_id DESC
        ),
        target_review AS (
            SELECT DISTINCT ON (review.source_record_id,scope.release_id)
                   review.source_record_id,scope.release_id,
                   review.publication_review_event_id,review.factual_review_status,
                   review.privacy_screening_status,review.maintainer_approval,
                   review.publication_eligible,review.reviewer_role,review.note
            FROM uec.publication_review_events review
            JOIN uec.publication_review_release_scopes scope
              USING(publication_review_event_id)
            WHERE scope.release_id=%s
            ORDER BY review.source_record_id,scope.release_id,
                     review.reviewed_at DESC,review.publication_review_event_id DESC
        ),
        target_clearance AS (
            SELECT DISTINCT ON (source_id,profile,release_id,artifact_id)
                   clearance.clearance_event_id, clearance.source_id,
                   clearance.profile, clearance.release_id, clearance.artifact_id,
                   clearance.artifact_sha256, clearance.scope_version,
                   clearance.decision_status, clearance.approved_fields,
                   clearance.decision_actor, clearance.decision_reference
            FROM uec.graph_public_evidence_metadata_clearance_events clearance
            WHERE clearance.source_id = ANY(%s)
              AND clearance.profile='official'
              AND clearance.release_id=%s
            ORDER BY source_id,profile,release_id,artifact_id,
                     decided_at DESC,clearance_event_id DESC
        )
        SELECT record.source_record_id, record.source_id, record.artifact_id,
               artifact.sha256, decision.clearance_event_id,
               decision.decision_actor, decision.decision_reference,
               source_review.publication_review_event_id,
               source_review.factual_review_status,
               source_review.privacy_screening_status,
               source_review.maintainer_approval,
               source_review.publication_eligible, source_review.reviewer_role,
               source_review.note, target_review.publication_review_event_id,
               target_review.factual_review_status,
               target_review.privacy_screening_status,
               target_review.maintainer_approval,
               target_review.publication_eligible, target_review.reviewer_role,
               target_review.note, target_clearance.clearance_event_id,
               target_clearance.decision_status,target_clearance.approved_fields,
               target_clearance.artifact_sha256,target_clearance.scope_version,
               target_clearance.decision_reference
        FROM source_decision decision
        JOIN uec.raw_artifacts artifact
          ON artifact.artifact_id=decision.artifact_id
         AND artifact.sha256=decision.artifact_sha256
        JOIN uec.source_records record
          ON record.source_id=decision.source_id
         AND record.artifact_id=decision.artifact_id
        JOIN eligible_release source_release ON source_release.release_id=%s
        JOIN uec.releases target_release
          ON target_release.release_id=%s AND {target_gate}
        JOIN source_review
          ON source_review.source_record_id=record.source_record_id
         AND source_review.release_id=source_release.release_id
        LEFT JOIN target_review
          ON target_review.source_record_id=record.source_record_id
         AND target_review.release_id=target_release.release_id
        LEFT JOIN target_clearance
          ON target_clearance.source_id=record.source_id
         AND target_clearance.profile='official'
         AND target_clearance.release_id=target_release.release_id
         AND target_clearance.artifact_id=record.artifact_id
        WHERE decision.decision_status='approved'
          AND decision.scope_version=%s
          AND decision.approved_fields=%s::text[]
          AND decision.decision_reference=%s
          AND source_review.publication_eligible IS TRUE
          AND source_review.privacy_screening_status='passed'
          AND source_review.factual_review_status<>'rejected'
          AND source_review.maintainer_approval='approved'
          AND NOT EXISTS (
                SELECT 1 FROM uec.public_access_restricted restricted
                WHERE restricted.source_record_id=record.source_record_id)
          AND NOT EXISTS (
                SELECT 1 FROM uec.observations observation
                JOIN uec.release_members member USING(observation_id)
                WHERE observation.source_record_id=record.source_record_id
                  AND member.release_id IN (source_release.release_id,target_release.release_id))
          AND EXISTS (
                SELECT 1 FROM uec.graph_evidence_events event
                WHERE event.source_record_id=record.source_record_id
                  AND event.source_id=record.source_id
                  AND ((record.source_id='us.aphis.annual-reports'
                        AND event.event_type='annual_reports'
                        AND event.event_period ~ '^[0-9]{{4}}$')
                    OR (record.source_id='us.inspections'
                        AND event.event_type='inspections'
                        AND event.event_date IS NOT NULL)))
        ORDER BY record.source_id,record.source_record_id
        """,
        (list(ALLOWED_SOURCES), SOURCE_RELEASE, SOURCE_RELEASE, TARGET_RELEASE,
         list(ALLOWED_SOURCES), TARGET_RELEASE, SOURCE_RELEASE, TARGET_RELEASE,
         *((TARGET_FREEZE_SHA256,) if candidate_target else ()),
         SCOPE_VERSION, APPROVED_FIELDS, DECISION_REFERENCE),
    ).fetchall()


def _review_is_same(row) -> bool:
    note = row[20]
    return (
        row[14] is not None
        and tuple(row[15:20]) == tuple(row[8:13])
        and isinstance(note, str)
        and note.startswith(_provenance_prefix(row))
        and " Operator recording carry-forward: " in note
    )


def _clearance_is_same(row) -> bool:
    return (
        row[21] is not None
        and row[22] == "approved"
        and row[23] == APPROVED_FIELDS
        and row[24] == row[3]
        and row[25] == SCOPE_VERSION
        and row[26] == DECISION_REFERENCE
    )


def _already_complete(row) -> bool:
    return _review_is_same(row) and _clearance_is_same(row)


def _provenance_prefix(row) -> str:
    prior_clearance_id, prior_actor = row[4:6]
    prior_review_id = row[7]
    source_review = row[8:14]
    return (
        f"Carry-forward only; prior clearance outcome approved under "
        f"{DECISION_REFERENCE}; prior clearance event {prior_clearance_id} "
        f"(original decision actor: {prior_actor}); prior publication review "
        f"{prior_review_id} (factual={source_review[0]}, privacy={source_review[1]}, "
        f"maintainer={source_review[2]}, eligible={source_review[3]}, "
        f"reviewer_role={source_review[4]})."
    )


def carry_forward(connection, *, actor: str, apply: bool = False,
                  prepare_reviews_only: bool = False) -> dict[str, int | str]:
    actor = actor.strip()
    if not re.fullmatch(r"[A-Za-z0-9 ._@:/+-]{1,200}", actor):
        raise CarryForwardError("operator_actor_invalid")
    if connection.execute("SELECT current_database()").fetchone()[0] != TARGET_DATABASE:
        raise CarryForwardError("connected_database_mismatch")
    schema = connection.execute(
        """SELECT to_regclass('uec.publication_review_release_scopes') IS NOT NULL,
                  EXISTS(SELECT 1 FROM information_schema.columns
                         WHERE table_schema='uec' AND table_name='publication_review_events'
                           AND column_name='release_id'),
                  EXISTS(SELECT 1 FROM pg_trigger trigger
                         JOIN pg_class relation ON relation.oid=trigger.tgrelid
                         JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
                         WHERE namespace.nspname='uec'
                           AND relation.relname='publication_review_events'
                           AND trigger.tgname='publication_review_events_scope'
                           AND NOT trigger.tgisinternal)"""
    ).fetchone()
    if schema != (True, True, True):
        raise CarryForwardError("release_scoped_review_schema_unavailable")
    release_rows = connection.execute(
        """SELECT release_id,profile,test_only,status,
                  EXISTS(SELECT 1 FROM uec.public_release_history history
                         WHERE history.release_id=release.release_id
                           AND history.profile=release.profile) AS was_public,
                  summary->>'candidate_only',summary->>'freeze_sha256'
           FROM uec.releases release
           WHERE release_id = ANY(%s)""",
        ([SOURCE_RELEASE, TARGET_RELEASE],),
    ).fetchall()
    release_map = {row[0]: row[1:] for row in release_rows}
    for release_id in (SOURCE_RELEASE, TARGET_RELEASE):
        release = release_map.get(release_id)
        if release is None:
            raise CarryForwardError("release_missing")
        profile, test_only, status, was_public, candidate_only, freeze_sha = release
        if profile != "official" or test_only is not False:
            raise CarryForwardError("release_not_historically_public_official")
        if release_id == TARGET_RELEASE and prepare_reviews_only:
            if (status not in {"candidate", "validated"} or candidate_only != "true"
                    or freeze_sha != TARGET_FREEZE_SHA256):
                raise CarryForwardError("target_candidate_identity_mismatch")
        elif not (status == "promoted" or (status == "validated" and was_public)):
            raise CarryForwardError("release_not_historically_public_official")
    rows = _eligible_rows(connection, candidate_target=prepare_reviews_only)
    already = (
        sum(1 for row in rows if _review_is_same(row))
        if prepare_reviews_only
        else sum(1 for row in rows if _already_complete(row))
    )
    pending = (
        [row for row in rows if not _review_is_same(row)]
        if prepare_reviews_only
        else [row for row in rows if not _already_complete(row)]
    )
    conflicting = sum(
        1 for row in pending
        if (row[14] is not None and not _review_is_same(row))
        or (row[21] is not None and not _clearance_is_same(row))
    )
    if conflicting:
        raise CarryForwardError("target_review_conflict_exists")
    if not prepare_reviews_only and any(not _review_is_same(row) for row in rows):
        raise CarryForwardError("target_publication_reviews_not_prepared")
    if apply or prepare_reviews_only:
        inserted_clearances: set[tuple[str, str, str]] = set()
        for row in pending:
            source_record_id, source_id, artifact_id, digest = row[:4]
            prior_clearance_id, prior_actor = row[4:6]
            prior_review_id = row[7]
            source_review = row[8:14]
            if not re.fullmatch(r"[A-Za-z0-9 ._@:/+-]{1,200}", str(prior_actor)):
                raise CarryForwardError("prior_decision_actor_invalid")
            provenance = _provenance_prefix(row)
            artifact_scope = (source_id, artifact_id, digest)
            if (not prepare_reviews_only and not _clearance_is_same(row)
                    and artifact_scope not in inserted_clearances):
                connection.execute(
                """INSERT INTO uec.graph_public_evidence_metadata_clearance_events
                   (source_id,profile,release_id,artifact_id,artifact_sha256,scope_version,
                    decision_status,approved_fields,decision_actor,decision_reference,decided_at)
                   VALUES (%s,'official',%s,%s,%s,%s,'approved',%s,%s,%s,now())""",
                    (source_id, TARGET_RELEASE, artifact_id, digest, SCOPE_VERSION,
                 APPROVED_FIELDS,
                 f"{actor}; carried forward from clearance {prior_clearance_id} by {prior_actor}",
                 DECISION_REFERENCE),
                )
                inserted_clearances.add(artifact_scope)
            if prepare_reviews_only and not _review_is_same(row):
                inserted_review_id = connection.execute(
                    """INSERT INTO uec.publication_review_events
                       (source_record_id,release_id,factual_review_status,privacy_screening_status,
                        maintainer_approval,publication_eligible,reviewer_role,note)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING publication_review_event_id""",
                    (source_record_id, TARGET_RELEASE, *source_review[:5],
                     f"{provenance} Operator recording carry-forward: {actor}."),
                ).fetchone()[0]
                scoped_review = connection.execute(
                    """SELECT EXISTS(
                           SELECT 1 FROM uec.publication_review_release_scopes scope
                           WHERE scope.publication_review_event_id=%s
                             AND scope.release_id=%s)""",
                    (inserted_review_id, TARGET_RELEASE),
                ).fetchone()[0]
                if not scoped_review:
                    raise CarryForwardError("release_scoped_review_not_created")
    return {
        "status": "prepared_reviews" if prepare_reviews_only else "applied" if apply else "dry_run",
        "stage": "prepare_reviews_only" if prepare_reviews_only else "final_clearance",
        "release": TARGET_RELEASE,
        "eligible_records": len(rows),
        "already_identical": already,
        "would_copy_records": len(pending),
        "would_insert_clearance_artifacts": 0 if prepare_reviews_only else len({
            (row[1], row[2], row[3]) for row in pending
            if not _clearance_is_same(row)
        }),
        "would_insert_publication_reviews": sum(1 for row in pending if not _review_is_same(row))
        if prepare_reviews_only else 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", ""))
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--decision-reference", required=True)
    parser.add_argument("--actor", required=True, help="operator identity to record for this carry-forward")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true", help="append final metadata-clearance events")
    action.add_argument("--prepare-reviews-only", action="store_true",
                        help="copy exact prior reviews to the pinned candidate before public build/promotion")
    args = parser.parse_args(argv)
    try:
        if not args.database_url:
            raise CarryForwardError("database_url_required")
        validate_database_url(args.database_url, args.expected_database)
        if args.decision_reference != DECISION_REFERENCE:
            raise CarryForwardError("decision_reference_mismatch")
        import psycopg

        with psycopg.connect(args.database_url) as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                writes = args.apply or args.prepare_reviews_only
                if not writes:
                    connection.execute("SET TRANSACTION READ ONLY")
                result = carry_forward(connection, actor=args.actor, apply=args.apply,
                                       prepare_reviews_only=args.prepare_reviews_only)
        print(json.dumps(result, sort_keys=True))
        return 0
    except CarryForwardError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    except Exception:
        # Driver errors can contain DSNs and server detail; keep diagnostics safe.
        print(json.dumps({"error": "database_operation_failed"}, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
