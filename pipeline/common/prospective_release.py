"""Row-free, approval-neutral prospective release measurements.

The private preview pool is deliberately not a release.  This module measures
an explicit policy against that pool and emits only aggregate counts and
digests, so a later operator review can bind the exact same selected identity
set without treating this preparation as approval or publication.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


POLICY_VERSION = "render-v1-prospective-policy-v1"
ANIMAL_CATEGORIES = (
    "animal_keeping_and_production",
    "slaughter",
    "processing_and_preparation",
    "research_and_animal_use",
)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest()


def policy() -> dict[str, Any]:
    """Return the approved scope rule; it contains no source-record identity."""
    return {
        "policy_version": POLICY_VERSION,
        "exclude_country_codes": ["FR"],
        "australia_allowed_display_categories": list(ANIMAL_CATEGORIES),
        "denmark_excluded_display_categories": ["other_regulated_premises"],
        "inherit_existing_record_exclusions": True,
        "approval_state": "human_stamp_required",
    }


def selection_cte() -> str:
    """Reusable candidate selection with stable-identity inherited exclusions.

    ``representative_observation_id`` is the preview pool's stable handoff
    identity.  The digest query below never projects it (or candidate IDs) to
    a report.
    """
    return """
, selected AS (
  SELECT geometry.release_id, geometry.facility_id, geometry.observation_id,
         geometry.source_record_id, geometry.source_id, geometry.country_code,
         geometry.classification_category, geometry.display_location,
         geometry.display_precision, geometry.candidate_geometry_valid
    FROM eligible_geometry geometry
   WHERE geometry.country_code IS DISTINCT FROM 'FR'
     AND NOT (geometry.country_code='AU'
              AND COALESCE(geometry.classification_category = ANY(%s::text[]), false) IS FALSE)
     AND NOT (geometry.country_code='DK'
              AND geometry.classification_category='other_regulated_premises')
     AND NOT (geometry.facility_id = ANY(%s::uuid[]))
)
"""


def measure(connection: Any, inventory_sha256: str, candidate_release_id: str,
            inherited_facility_ids: list[str], inherited_facility_sha256: str) -> dict[str, Any]:
    if not isinstance(inventory_sha256, str) or len(inventory_sha256) != 64:
        raise ValueError("inventory_sha256 must be a SHA-256 digest")
    contract = policy()
    if not candidate_release_id:
        raise ValueError("candidate release ID is required")
    if len(inherited_facility_sha256) != 64:
        raise ValueError("inherited exclusion identity digest is required")
    # GEOMETRY_MEMBERS_CTE is the existing display contract. The candidate is not
    # candidate_only, so it evaluates its actual current display evidence while
    # this proposal remains non-public and unapproved.
    from pipeline.common.release_geometry import GEOMETRY_MEMBERS_CTE
    geometry = GEOMETRY_MEMBERS_CTE
    params = (candidate_release_id, candidate_release_id, list(ANIMAL_CATEGORIES), inherited_facility_ids)
    query_prefix = geometry + "\n" + selection_cte()
    summary = connection.execute(query_prefix + """
SELECT count(*)::bigint,
       count(*) FILTER (WHERE display_location IS NOT NULL)::bigint,
       count(*) FILTER (WHERE display_location IS NULL)::bigint,
       count(*) FILTER (WHERE candidate_geometry_valid IS TRUE)::bigint,
       encode(digest(string_agg(facility_id::text || ':' || observation_id::text, E'\\n' ORDER BY facility_id, observation_id), 'sha256'), 'hex'),
       encode(digest(string_agg(source_record_id::text, E'\\n' ORDER BY source_record_id), 'sha256'), 'hex')
  FROM selected
""", params).fetchone()
    if summary is None or int(summary[0]) < 1 or not summary[3] or not summary[4]:
        raise ValueError("prospective selection is empty or lacks a stable digest")
    coverage = connection.execute(query_prefix + """
SELECT source_id, count(*)::bigint,
       count(*) FILTER (WHERE display_location IS NOT NULL)::bigint,
       count(*) FILTER (WHERE display_location IS NULL)::bigint
  FROM selected
 GROUP BY source_id
 ORDER BY source_id
""", params).fetchall()
    release = connection.execute("SELECT status,profile,test_only FROM uec.releases WHERE release_id=%s", (candidate_release_id,)).fetchone()
    if release != ("candidate", "official", False):
        raise ValueError("prospective source must be the exact non-test official candidate")
    payload = {
        "schema_version": "uec-prospective-release-snapshot-v1",
        "publication_state": "private_prospective_not_authorized",
        "approval_state": "human_stamp_required",
        "candidate_release_id": candidate_release_id,
        "inventory_sha256": inventory_sha256,
        "selection_policy": contract,
        "cohort": {
            "candidate_count": int(summary[0]), "mapped_candidate_count": int(summary[1]),
            "unmapped_candidate_count": int(summary[2]),
            "conditional_geometry_valid_count": int(summary[3]),
            "member_identity_sha256": summary[4],
            "representative_source_record_sha256": summary[5],
        },
        "source_coverage": [
            {"source_id": row[0], "candidate_count": int(row[1]),
             "mapped_candidate_count": int(row[2]), "unmapped_candidate_count": int(row[3])}
            for row in coverage
        ],
        "inherited_exclusions": {
            "stable_facility_count": len(inherited_facility_ids),
            "stable_facility_sha256": inherited_facility_sha256,
        },
        "geometry_contract": "pipeline.common.release_geometry.geometry_rows_sql",
    }
    payload["freeze_proposal_sha256"] = canonical_sha256(payload)
    return payload
