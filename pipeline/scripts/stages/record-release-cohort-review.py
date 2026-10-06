#!/usr/bin/env python3
"""Verify and optionally record an operator-authored whole-cohort review.

The command defaults to a serializable read-only dry run. `--apply` appends
release-scoped review and rights events and applies only release-member
visibility plus the candidate control summary. It does not perform privacy,
factual, legal, or geometry checks on behalf of an operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.common.release_cohort_review import (  # noqa: E402
    CohortReviewError,
    canonical_sha256,
    validate_document,
)


MEMBERS_SQL = """
SELECT member.release_id, member.facility_id::text, member.observation_id::text,
       observation.source_record_id::text, record.source_id, record.artifact_id::text,
       artifact.sha256,
       taxonomy.contract
FROM uec.release_members member
JOIN uec.observations observation ON observation.observation_id=member.observation_id
JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
LEFT JOIN LATERAL (
    SELECT jsonb_build_object(
        'taxonomy_version', assignment_set.taxonomy_version,
        'crosswalk_version', assignment_set.crosswalk_version,
        'ruleset_version', assignment_set.ruleset_version,
        'display_category', assignment_set.display_category,
        'assignments', COALESCE(jsonb_agg(jsonb_build_object(
            'assignment_ordinal', assignment.assignment_ordinal,
            'primary_key', assignment.primary_key, 'leaf_key', assignment.leaf_key,
            'leaf_label', assignment.leaf_label,
            'source_code_reference', assignment.source_code_reference,
            'source_label_reference', assignment.source_label_reference,
            'source_code', assignment.source_code, 'source_label', assignment.source_label,
            'mapping_method', assignment.mapping_method, 'mapping_status', assignment.mapping_status
        ) ORDER BY assignment.assignment_ordinal), '[]'::jsonb)
    ) AS contract
    FROM uec.observation_taxonomy_assignment_sets assignment_set
    LEFT JOIN uec.observation_taxonomy_assignments assignment USING (assignment_set_id)
    WHERE assignment_set.observation_id=observation.observation_id
      AND assignment_set.source_record_id=observation.source_record_id
      AND assignment_set.source_id=record.source_id
      AND assignment_set.artifact_id=record.artifact_id
      AND NOT EXISTS (
          SELECT 1 FROM uec.observation_taxonomy_assignment_sets newer
          WHERE newer.observation_id=assignment_set.observation_id
            AND newer.taxonomy_version=assignment_set.taxonomy_version
            AND (newer.created_at,newer.assignment_set_id)>(assignment_set.created_at,assignment_set.assignment_set_id)
      )
    GROUP BY assignment_set.assignment_set_id
    ORDER BY assignment_set.created_at DESC, assignment_set.assignment_set_id DESC
    LIMIT 1
) taxonomy ON true
WHERE member.release_id=%s
ORDER BY member.release_id, member.facility_id, member.observation_id,
         observation.source_record_id, record.source_id, record.artifact_id
"""

SCOPES_SQL = """
SELECT record.source_id, record.artifact_id::text, artifact.sha256,
       count(*)::bigint AS member_count,
       array_agg(DISTINCT assignment_set.taxonomy_version ORDER BY assignment_set.taxonomy_version) AS taxonomy_versions,
       array_agg(DISTINCT assignment_set.crosswalk_version ORDER BY assignment_set.crosswalk_version) AS crosswalk_versions,
       array_agg(DISTINCT assignment_set.ruleset_version ORDER BY assignment_set.ruleset_version) AS classification_rulesets,
       array_agg(DISTINCT assignment_set.display_category ORDER BY assignment_set.display_category) AS display_categories,
       count(*) FILTER (WHERE restricted.source_record_id IS NOT NULL)::bigint AS suppressed_count,
       COALESCE(jsonb_agg(DISTINCT record.source_record_id::text)
           FILTER (WHERE restricted.source_record_id IS NOT NULL), '[]'::jsonb) AS active_restricted_record_ids
FROM uec.release_members member
JOIN uec.observations observation ON observation.observation_id=member.observation_id
JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
JOIN LATERAL (
    SELECT assignment_set.taxonomy_version, assignment_set.crosswalk_version,
           assignment_set.ruleset_version, assignment_set.display_category
    FROM uec.observation_taxonomy_assignment_sets assignment_set
    WHERE assignment_set.observation_id=observation.observation_id
      AND assignment_set.source_record_id=observation.source_record_id
      AND assignment_set.source_id=record.source_id AND assignment_set.artifact_id=record.artifact_id
      AND NOT EXISTS (
          SELECT 1 FROM uec.observation_taxonomy_assignment_sets newer
          WHERE newer.observation_id=assignment_set.observation_id
            AND newer.taxonomy_version=assignment_set.taxonomy_version
            AND (newer.created_at,newer.assignment_set_id)>(assignment_set.created_at,assignment_set.assignment_set_id)
      )
    ORDER BY assignment_set.created_at DESC, assignment_set.assignment_set_id DESC LIMIT 1
) assignment_set ON true
LEFT JOIN uec.public_access_restricted restricted ON restricted.source_record_id=record.source_record_id
WHERE member.release_id=%s
GROUP BY record.source_id, record.artifact_id, artifact.sha256
ORDER BY record.source_id, record.artifact_id
"""


def _field(row, key: str, index: int):
    return row[key] if isinstance(row, dict) else row[index]


def _member_digest(connection, release_id: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    cursor = connection.execute(MEMBERS_SQL, (release_id,))
    while True:
        rows = cursor.fetchmany(1000)
        if not rows:
            break
        for row in rows:
            values = [_field(row, name, index) for index, name in enumerate((
                "release_id", "facility_id", "observation_id", "source_record_id",
                "source_id", "artifact_id", "sha256", "contract"))]
            if values[7] is None:
                raise CohortReviewError("taxonomy assignment coverage is incomplete")
            payload = (json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            digest.update(payload)
            count += 1
    return count, digest.hexdigest()


def _validate_database_url(database_url: str, expected_database: str) -> None:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise CohortReviewError("database must be a loopback PostgreSQL URL")
    if not re.fullmatch(r"uec_v0_review(?:_[a-z0-9]+)?", expected_database):
        raise CohortReviewError("expected database must be an isolated uec_v0_review database")
    if parsed.path.lstrip("/") != expected_database:
        raise CohortReviewError("database URL does not match expected database")


def prepare_template(connection, release_id: str, output: Path) -> dict:
    """Write a row-free-identity, non-approving review template under ignored storage."""
    report_root = (ROOT / "data" / "reports").resolve(strict=True)
    target = output.resolve(strict=False)
    try:
        target.relative_to(report_root)
    except ValueError:
        raise CohortReviewError("prepared review must be written under ignored data/reports") from None
    if output.is_symlink() or target.exists():
        raise CohortReviewError("prepared review output must be a new non-symlink file")
    if not target.parent.is_dir():
        raise CohortReviewError("prepared review output directory must already exist")

    release = connection.execute(
        "SELECT status,profile,test_only,ruleset_version,summary FROM uec.releases WHERE release_id=%s",
        (release_id,),
    ).fetchone()
    if release is None:
        raise CohortReviewError("candidate release is missing")
    status, profile, test_only, ruleset, summary = release
    summary = summary if isinstance(summary, dict) else {}
    if status != "candidate" or test_only is not False or summary.get("candidate_only") is not True:
        raise CohortReviewError("preparation requires a non-test frozen candidate")
    freeze_sha = summary.get("freeze_sha256")
    inventory_sha = summary.get("inventory_sha256")
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
           for value in (freeze_sha, inventory_sha)):
        raise CohortReviewError("candidate freeze or inventory hash is missing")
    member_count, member_sha = _member_digest(connection, release_id)
    if member_count < 1:
        raise CohortReviewError("candidate release has no members")
    actual = connection.execute(SCOPES_SQL, (release_id,)).fetchall()
    scopes = []
    for row in actual:
        source_id, artifact_id, artifact_sha, _count, taxonomy_versions, crosswalks, rulesets, _categories, suppressed, _restricted_ids = row
        if int(suppressed):
            raise CohortReviewError("active suppression exists inside candidate cohort")
        if len(taxonomy_versions) != 1 or len(crosswalks) != 1 or len(rulesets) != 1:
            raise CohortReviewError("source/artifact taxonomy interpretation is ambiguous")
        if taxonomy_versions[0] != "uec-taxonomy-v1":
            raise CohortReviewError("candidate taxonomy version is unsupported")
        scopes.append({
            "source_id": source_id, "artifact_id": artifact_id, "artifact_sha256": artifact_sha,
            "factual_review_status": "unreviewed", "privacy_screening_status": "pending",
            "privacy_method": "", "privacy_evidence_reference": "", "maintainer_approval": "pending",
            "publication_eligible": False, "project_approval_method": "",
            "project_approval_evidence_reference": "", "redistribution_status": "unknown",
            "rights_actor": "", "rights_reference": "", "rights_decided_at": "",
            "classification_interpretation_status": "unreviewed", "classification_method": "",
            "classification_evidence_reference": "", "geometry_interpretation_status": "unreviewed",
            "geometry_method": "", "geometry_evidence_reference": "",
            "taxonomy_version": taxonomy_versions[0], "crosswalk_version": crosswalks[0],
            "classification_ruleset_version": rulesets[0], "excluded_display_categories": [],
        })
    selected = summary.get("selected_sources")
    if not isinstance(selected, list) or set(selected) != {scope["source_id"] for scope in scopes}:
        raise CohortReviewError("candidate source coverage does not match control summary")
    template = {
        "schema_version": "uec-release-cohort-review-v1", "release_id": release_id,
        "profile": profile, "ruleset_version": ruleset, "freeze_sha256": freeze_sha,
        "inventory_sha256": inventory_sha, "member_sha256": member_sha,
        "member_count": member_count,
        "reviewer": {"actor": "", "role": "", "reviewed_at": ""},
        "review_method": "", "review_evidence_reference": "",
        "source_artifact_scopes": scopes,
    }
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(template, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return {"status": "prepared", "member_count": member_count,
            "source_artifact_scope_count": len(scopes), "output": str(target),
            "approval_fields_initialized": False}


def _read_operator_document(path: Path) -> dict:
    report_root = (ROOT / "data" / "reports").resolve(strict=True)
    if path.is_symlink():
        raise CohortReviewError("review document must not be a symlink")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(report_root)
    except ValueError:
        raise CohortReviewError("review document must be kept under ignored data/reports") from None
    try:
        return validate_document(json.loads(resolved.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CohortReviewError("review document could not be read as JSON") from error


def _verify(connection, document: dict, *, apply_changes: bool) -> dict:
    validate_document(document)
    release = connection.execute(
        "SELECT status,profile,test_only,ruleset_version,summary FROM uec.releases WHERE release_id=%s" +
        (" FOR UPDATE" if apply_changes else ""), (document["release_id"],)
    ).fetchone()
    if release is None:
        raise CohortReviewError("candidate release is missing")
    status, profile, test_only, ruleset, summary = release
    summary = summary if isinstance(summary, dict) else {}
    if status != "candidate" or test_only is not False:
        raise CohortReviewError("release must be a non-test candidate")
    if (profile != document["profile"] or ruleset != document["ruleset_version"]
            or summary.get("candidate_only") is not True
            or summary.get("freeze_sha256") != document["freeze_sha256"]
            or summary.get("inventory_sha256") != document["inventory_sha256"]):
        raise CohortReviewError("release profile, ruleset, freeze or inventory binding mismatch")

    member_count, member_sha = _member_digest(connection, document["release_id"])
    if member_count != document["member_count"] or member_sha != document["member_sha256"]:
        raise CohortReviewError("exact release membership or taxonomy digest mismatch")

    actual = connection.execute(SCOPES_SQL, (document["release_id"],)).fetchall()
    expected = {(scope["source_id"], scope["artifact_id"]): scope for scope in document["source_artifact_scopes"]}
    if len(actual) != len(expected):
        raise CohortReviewError("source/artifact review coverage is incomplete")
    scopes = []
    suppressed_count = 0
    excluded_record_count = 0
    for row in actual:
        source_id, artifact_id, artifact_sha, count, taxonomy_versions, crosswalk_versions, rulesets, categories, suppressed, restricted_ids = row
        scope = expected.get((source_id, artifact_id))
        if scope is None or artifact_sha != scope["artifact_sha256"]:
            raise CohortReviewError("source/artifact review coverage or digest mismatch")
        if (taxonomy_versions != [scope["taxonomy_version"]]
                or crosswalk_versions != [scope["crosswalk_version"]]
                or rulesets != [scope["classification_ruleset_version"]]):
            raise CohortReviewError("source/artifact taxonomy interpretation binding mismatch")
        if not set(scope.get("excluded_display_categories", [])).issubset(set(categories)):
            raise CohortReviewError("category exclusion is outside this source/artifact taxonomy scope")
        excluded_ids = set(scope.get("excluded_source_record_ids", []))
        restricted_ids = set(restricted_ids or [])
        if not restricted_ids.issubset(excluded_ids):
            raise CohortReviewError("active restriction inside candidate cohort is not explicitly excluded")
        if excluded_ids:
            unbound = connection.execute("""
                SELECT count(*) FROM jsonb_array_elements_text(%s::jsonb) AS excluded(source_record_id)
                WHERE NOT EXISTS (
                    SELECT 1 FROM uec.release_members member
                    JOIN uec.observations observation ON observation.observation_id=member.observation_id
                    JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
                    WHERE member.release_id=%s
                      AND record.source_record_id=excluded.source_record_id::uuid
                      AND record.source_id=%s AND record.artifact_id=%s::uuid
                )
            """, (json.dumps(sorted(excluded_ids)), document["release_id"], source_id, artifact_id)).fetchone()[0]
            if unbound:
                raise CohortReviewError("record exclusion is outside its exact release source/artifact membership")
        excluded_record_count += len(excluded_ids)
        suppressed_count += int(suppressed)
        scopes.append({**scope,
                       "excluded_display_categories": scope.get("excluded_display_categories", []),
                       "excluded_source_record_ids": scope.get("excluded_source_record_ids", []),
                       "member_count": int(count)})
    if sum(scope["member_count"] for scope in scopes) != member_count:
        raise CohortReviewError("source/artifact member coverage does not match cohort")

    document_sha = canonical_sha256(document)
    previous = connection.execute(
        "SELECT document_sha256,member_sha256,member_count FROM uec.release_cohort_review_documents WHERE release_id=%s",
        (document["release_id"],),
    ).fetchone()
    if previous:
        if (previous[0] == document_sha and previous[1] == member_sha and int(previous[2]) == member_count):
            return {"status": "already_recorded", "member_count": member_count,
                    "scope_count": len(scopes), "document_sha256": document_sha}
        raise CohortReviewError("release already has a different immutable cohort review")

    # Reject stale/tied review timestamps and rights decision conflicts before
    # any writes. The incoming decisions must be newer than all current events.
    stale_review = connection.execute("""
        SELECT EXISTS (
            SELECT 1 FROM uec.release_members member
            JOIN uec.observations observation ON observation.observation_id=member.observation_id
            JOIN uec.publication_review_release_current current
              ON current.release_id=member.release_id AND current.source_record_id=observation.source_record_id
            WHERE member.release_id=%s AND current.reviewed_at >= %s
        )
    """, (document["release_id"], document["reviewer"]["reviewed_at"])).fetchone()[0]
    if stale_review:
        raise CohortReviewError("review timestamp is stale or conflicts with current release event")
    for scope in scopes:
        latest = connection.execute("""
            SELECT max(decided_at) FROM uec.source_rights_decisions
            WHERE source_id=%s AND profile=%s AND release_id=%s AND artifact_id=%s
        """, (scope["source_id"], profile, document["release_id"], scope["artifact_id"])).fetchone()[0]
        if latest is not None:
            incoming = scope["rights_decided_at"].replace("Z", "+00:00")
            from datetime import datetime
            if datetime.fromisoformat(incoming) <= latest:
                raise CohortReviewError("rights decision timestamp is stale or conflicts with existing history")

    report = {"status": "verified", "member_count": member_count,
              "scope_count": len(scopes), "excluded_record_count": excluded_record_count,
              "document_sha256": document_sha}
    if not apply_changes:
        report["default_visible_count"] = int(connection.execute("""
            WITH reviewed_scope AS (
                SELECT * FROM jsonb_to_recordset(%s::jsonb) AS scope(
                    release_id text, source_id text, artifact_id text, redistribution_status text,
                    privacy_screening_status text, publication_eligible boolean,
                    factual_review_status text, maintainer_approval text,
                    classification_interpretation_status text, geometry_interpretation_status text,
                    excluded_display_categories jsonb, excluded_source_record_ids jsonb,
                    taxonomy_version text,
                    crosswalk_version text, classification_ruleset_version text
                )
            )
            SELECT count(*) FILTER (WHERE
                scope.redistribution_status='cleared'
                AND scope.privacy_screening_status='passed'
                AND scope.publication_eligible
                AND scope.factual_review_status<>'rejected'
                AND (scope.maintainer_approval='approved' OR
                     (release.profile='community' AND source.origin_type='user_submitted'
                      AND scope.factual_review_status='unreviewed' AND scope.maintainer_approval='pending'))
                AND scope.classification_interpretation_status='approved'
                    AND scope.geometry_interpretation_status='approved'
                    AND NOT (scope.excluded_display_categories ? assignment_set.display_category)
                    AND NOT (scope.excluded_source_record_ids ? observation.source_record_id::text)
            )::bigint
            FROM uec.release_members member
            JOIN uec.releases release ON release.release_id=member.release_id
            JOIN uec.observations observation ON observation.observation_id=member.observation_id
            JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
            JOIN uec.sources source ON source.source_id=record.source_id
            JOIN reviewed_scope scope
              ON scope.release_id=member.release_id AND scope.source_id=record.source_id
             AND scope.artifact_id::uuid=record.artifact_id
            JOIN uec.observation_taxonomy_assignment_sets assignment_set
              ON assignment_set.observation_id=observation.observation_id
             AND assignment_set.taxonomy_version=scope.taxonomy_version
             AND assignment_set.crosswalk_version=scope.crosswalk_version
             AND assignment_set.ruleset_version=scope.classification_ruleset_version
            WHERE member.release_id=%s
              AND NOT EXISTS (
                  SELECT 1 FROM uec.observation_taxonomy_assignment_sets newer
                  WHERE newer.observation_id=assignment_set.observation_id
                    AND newer.taxonomy_version=assignment_set.taxonomy_version
                    AND (newer.created_at,newer.assignment_set_id)>(assignment_set.created_at,assignment_set.assignment_set_id)
              )
        """, (json.dumps([{"release_id": document["release_id"], **scope} for scope in scopes]),
              document["release_id"])).fetchone()[0])
        report["apply_required"] = True
        return report

    reviewer = document["reviewer"]
    connection.execute("""
        INSERT INTO uec.release_cohort_review_documents
            (release_id,profile,ruleset_version,freeze_sha256,inventory_sha256,member_sha256,
             member_count,document_sha256,reviewer_actor,reviewer_role,reviewed_at,
             review_method,review_evidence_reference)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (document["release_id"], profile, ruleset, document["freeze_sha256"],
          document["inventory_sha256"], member_sha, member_count, document_sha,
          reviewer["actor"], reviewer["role"], reviewer["reviewed_at"],
          document["review_method"], document["review_evidence_reference"]))
    for scope in scopes:
        connection.execute("""
            INSERT INTO uec.release_cohort_review_scopes
                (release_id,source_id,artifact_id,artifact_sha256,factual_review_status,
                 privacy_screening_status,privacy_method,privacy_evidence_reference,maintainer_approval,
                 publication_eligible,project_approval_method,project_approval_evidence_reference,
                 redistribution_status,rights_actor,rights_reference,rights_decided_at,
                 classification_interpretation_status,classification_method,classification_evidence_reference,
                 geometry_interpretation_status,geometry_method,geometry_evidence_reference,
                 taxonomy_version,crosswalk_version,classification_ruleset_version,
                 excluded_display_categories,excluded_source_record_ids,
                 exclusion_reason_category,exclusion_policy_reference)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
        """, (document["release_id"], scope["source_id"], scope["artifact_id"], scope["artifact_sha256"],
              scope["factual_review_status"], scope["privacy_screening_status"], scope["privacy_method"],
              scope["privacy_evidence_reference"], scope["maintainer_approval"], scope["publication_eligible"],
              scope["project_approval_method"], scope["project_approval_evidence_reference"],
              scope["redistribution_status"], scope["rights_actor"], scope["rights_reference"],
              scope["rights_decided_at"], scope["classification_interpretation_status"],
              scope["classification_method"], scope["classification_evidence_reference"],
              scope["geometry_interpretation_status"], scope["geometry_method"],
              scope["geometry_evidence_reference"], scope["taxonomy_version"],
              scope["crosswalk_version"], scope["classification_ruleset_version"],
              json.dumps(scope.get("excluded_display_categories", [])),
              json.dumps(scope.get("excluded_source_record_ids", [])),
              scope.get("exclusion_reason_category"), scope.get("exclusion_policy_reference")))
        connection.execute("""
            INSERT INTO uec.source_rights_decisions
                (source_id,profile,release_id,artifact_id,artifact_sha256,redistribution_status,
                 decision_actor,decision_reference,decided_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (scope["source_id"], profile, document["release_id"], scope["artifact_id"],
              scope["artifact_sha256"], scope["redistribution_status"], scope["rights_actor"],
              scope["rights_reference"], scope["rights_decided_at"]))

    # Append one release-scoped publication event per source record. It is an
    # explicit operator statement, never a privacy scan performed by this CLI.
    publication_insert = connection.execute("""
        INSERT INTO uec.publication_review_events
            (source_record_id,release_id,factual_review_status,privacy_screening_status,
             maintainer_approval,publication_eligible,reviewer_role,reviewed_at,note)
        SELECT observation.source_record_id, member.release_id,
               min(scope.factual_review_status), min(scope.privacy_screening_status),
               min(scope.maintainer_approval),
               bool_and(scope.publication_eligible AND scope.privacy_screening_status='passed'
                        AND scope.factual_review_status<>'rejected'
                        AND NOT (scope.excluded_source_record_ids ? observation.source_record_id::text)
                        AND NOT (scope.excluded_display_categories ? assignment_set.display_category)),
               %s, %s, %s
        FROM uec.release_members member
        JOIN uec.observations observation ON observation.observation_id=member.observation_id
        JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
        JOIN uec.release_cohort_review_scopes scope
          ON scope.release_id=member.release_id AND scope.source_id=record.source_id
         AND scope.artifact_id=record.artifact_id
        JOIN uec.observation_taxonomy_assignment_sets assignment_set
          ON assignment_set.observation_id=observation.observation_id
         AND assignment_set.taxonomy_version=scope.taxonomy_version
         AND assignment_set.crosswalk_version=scope.crosswalk_version
         AND assignment_set.ruleset_version=scope.classification_ruleset_version
        WHERE member.release_id=%s
          AND NOT EXISTS (
              SELECT 1 FROM uec.observation_taxonomy_assignment_sets newer
              WHERE newer.observation_id=assignment_set.observation_id
                AND newer.taxonomy_version=assignment_set.taxonomy_version
                AND (newer.created_at,newer.assignment_set_id)>(assignment_set.created_at,assignment_set.assignment_set_id)
          )
        GROUP BY member.release_id,observation.source_record_id
    """, (reviewer["role"], reviewer["reviewed_at"],
          f"Cohort review document sha256 {document_sha}", document["release_id"]))

    updated = connection.execute("""
        WITH desired_visibility AS (
          SELECT member.release_id, member.facility_id, member.observation_id,
            (
            scope.redistribution_status='cleared'
            AND scope.privacy_screening_status='passed'
            AND scope.publication_eligible
            AND scope.factual_review_status<>'rejected'
            AND (scope.maintainer_approval='approved' OR
                 (release.profile='community' AND source.origin_type='user_submitted'
                  AND scope.factual_review_status='unreviewed' AND scope.maintainer_approval='pending'))
            AND scope.classification_interpretation_status='approved'
            AND scope.geometry_interpretation_status='approved'
            AND NOT (scope.excluded_display_categories ? assignment_set.display_category)
            AND NOT (scope.excluded_source_record_ids ? observation.source_record_id::text)
            ) AS default_visible
          FROM uec.release_members member
        JOIN uec.releases release ON release.release_id=member.release_id
        JOIN uec.observations observation ON observation.observation_id=member.observation_id
        JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
        JOIN uec.sources source ON source.source_id=record.source_id
        JOIN uec.release_cohort_review_scopes scope
          ON scope.release_id=member.release_id AND scope.source_id=record.source_id
         AND scope.artifact_id=record.artifact_id
        JOIN uec.observation_taxonomy_assignment_sets assignment_set
          ON assignment_set.observation_id=observation.observation_id
         AND assignment_set.taxonomy_version=scope.taxonomy_version
         AND assignment_set.crosswalk_version=scope.crosswalk_version
         AND assignment_set.ruleset_version=scope.classification_ruleset_version
        WHERE member.release_id=%s
          AND NOT EXISTS (
              SELECT 1 FROM uec.observation_taxonomy_assignment_sets newer
              WHERE newer.observation_id=assignment_set.observation_id
                AND newer.taxonomy_version=assignment_set.taxonomy_version
                AND (newer.created_at,newer.assignment_set_id)>(assignment_set.created_at,assignment_set.assignment_set_id)
          )
        )
        UPDATE uec.release_members member
           SET default_visible=desired.default_visible
          FROM desired_visibility desired
         WHERE desired.release_id=member.release_id AND desired.facility_id=member.facility_id
           AND desired.observation_id=member.observation_id
    """, (document["release_id"],))
    visible_count = connection.execute(
        "SELECT count(*) FROM uec.release_members WHERE release_id=%s AND default_visible",
        (document["release_id"],)).fetchone()[0]
    summary.update({"cohort_review": {"document_sha256": document_sha,
                                      "member_sha256": member_sha,
                                      "member_count": member_count,
                                      "source_artifact_scope_count": len(scopes),
                                      "recorded_at": reviewer["reviewed_at"]}})
    connection.execute("UPDATE uec.releases SET summary=%s WHERE release_id=%s",
                       (json.dumps(summary), document["release_id"]))
    report.update({"status": "recorded", "default_visible_count": int(visible_count),
                   "visibility_rows_changed": updated.rowcount,
                   "publication_events_created": publication_insert.rowcount,
                   "excluded_record_count": excluded_record_count})
    return report


def record(database_url: str, expected_database: str, review_path: Path, *, apply_changes: bool) -> dict:
    _validate_database_url(database_url, expected_database)
    document = _read_operator_document(review_path)
    import psycopg
    with psycopg.connect(database_url, prepare_threshold=None) as connection:
        with connection.transaction():
            isolation = "SERIALIZABLE" if apply_changes else "SERIALIZABLE, READ ONLY"
            connection.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation}")
            database_name = connection.execute("SELECT current_database()").fetchone()[0]
            if database_name != expected_database:
                raise CohortReviewError("connected database does not match expected database")
            return _verify(connection, document, apply_changes=apply_changes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--review", type=Path, help="ignored/local operator-authored JSON review document")
    mode.add_argument("--prepare", help="candidate release ID to measure and prepare as an unapproved local template")
    parser.add_argument("--output", type=Path, help="new ignored data/reports JSON template; required with --prepare")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--apply", action="store_true", help="append the verified review and apply eligible visibility")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    if args.prepare and (args.output is None or args.apply):
        parser.error("--prepare requires --output and cannot be combined with --apply")
    if args.review and args.output is not None:
        parser.error("--output is only used with --prepare")
    try:
        if args.prepare:
            _validate_database_url(args.database_url, args.expected_database)
            import psycopg
            with psycopg.connect(args.database_url, prepare_threshold=None) as connection:
                with connection.transaction():
                    connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE, READ ONLY")
                    if connection.execute("SELECT current_database()").fetchone()[0] != args.expected_database:
                        raise CohortReviewError("connected database does not match expected database")
                    receipt = prepare_template(connection, args.prepare, args.output)
        else:
            receipt = record(args.database_url, args.expected_database, args.review, apply_changes=args.apply)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except Exception as error:
        # Database exceptions can include SQL/values; keep stdout/stderr row-free.
        message = error.args[0] if isinstance(error, CohortReviewError) and error.args else "database verification failed"
        print(json.dumps({"status": "blocked", "reason": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
