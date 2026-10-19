"""Row-free, approval-neutral prospective release measurements.

The retained candidate is not a published release. This module measures
an explicit proposal against that candidate and emits only aggregate counts and
digests, so a later operator review can bind the exact same selected identity
set without treating this preparation as approval or publication.
"""

from __future__ import annotations

import hashlib
import json
import re
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
    """Return the proposed scope rule; it contains no source-record identity."""
    return {
        "policy_version": POLICY_VERSION,
        "exclude_source_ids": ["fr.dgal.section-i", "fr.dgal.section-ii"],
        "animal_category_filter_source": "au.npi.facilities",
        "animal_category_allowlist": list(ANIMAL_CATEGORIES),
        "other_regulated_filter_source": "dk.smiley",
        "other_regulated_excluded_categories": ["other_regulated_premises"],
        "inherit_existing_record_exclusions": True,
        "approval_state": "human_stamp_required",
    }


def selection_cte() -> str:
    """Reusable candidate selection with stable-identity inherited exclusions.

    The digest query never projects member identities to a report. Source
    scope rules must not accidentally apply to other sources in that country.
    """
    return """
, selected AS (
  SELECT geometry.release_id, geometry.facility_id, geometry.observation_id,
         geometry.source_record_id, geometry.source_id, geometry.country_code,
         geometry.classification_category, geometry.display_location,
         geometry.display_precision, geometry.candidate_geometry_valid,
         geometry.coordinate, geometry.evidence
    FROM eligible_geometry geometry
   WHERE geometry.source_id <> ALL(%s::text[])
     AND NOT (geometry.source_id='au.npi.facilities'
              AND COALESCE(geometry.classification_category = ANY(%s::text[]), false) IS FALSE)
     AND NOT (geometry.source_id='dk.smiley'
              AND geometry.classification_category='other_regulated_premises')
     AND NOT EXISTS (
       SELECT 1 FROM unnest(%s::text[], %s::uuid[]) inherited(source_id, facility_id)
        WHERE inherited.source_id=geometry.source_id AND inherited.facility_id=geometry.facility_id
     )
)
"""


def measure(connection: Any, inventory_sha256: str, candidate_release_id: str,
            inherited_facility_ids: list[str], inherited_facility_sha256: str,
            inherited_source_ids: list[str]) -> dict[str, Any]:
    if not isinstance(inventory_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", inventory_sha256):
        raise ValueError("inventory_sha256 must be a SHA-256 digest")
    contract = policy()
    if not candidate_release_id:
        raise ValueError("candidate release ID is required")
    if not isinstance(inherited_facility_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", inherited_facility_sha256):
        raise ValueError("inherited exclusion identity digest is required")
    # Reuse the existing evidence-validity rules without fabricating approval.
    # Current public availability and conditional geometry readiness are separate.
    from pipeline.common.release_geometry import GEOMETRY_MEMBERS_CTE
    geometry = GEOMETRY_MEMBERS_CTE
    if len(inherited_source_ids) != len(inherited_facility_ids):
        raise ValueError("inherited exclusion source/facility bindings are incomplete")
    params = (candidate_release_id, candidate_release_id,
              ["fr.dgal.section-i", "fr.dgal.section-ii"], list(ANIMAL_CATEGORIES),
              inherited_source_ids, inherited_facility_ids)
    query_prefix = geometry + "\n" + selection_cte()
    summary = connection.execute(query_prefix + """
SELECT count(*)::bigint,
       count(*) FILTER (WHERE display_location IS NOT NULL)::bigint,
       count(*) FILTER (WHERE display_location IS NULL)::bigint,
       count(*) FILTER (WHERE candidate_geometry_valid IS TRUE)::bigint,
       encode(digest(string_agg(facility_id::text || ':' || observation_id::text, E'\\n' ORDER BY facility_id, observation_id), 'sha256'), 'hex'),
       encode(digest(string_agg(source_record_id::text, E'\\n' ORDER BY source_record_id), 'sha256'), 'hex'),
       encode(digest(string_agg(
         observation_id::text || ':' || COALESCE(encode(ST_AsEWKB(coordinate::geometry), 'hex'), 'null')
         || ':' || COALESCE((evidence->'display_location')::text, 'null')
         || ':' || COALESCE(candidate_geometry_valid::text, 'null'),
         E'\\n' ORDER BY observation_id), 'sha256'), 'hex')
  FROM selected
""", params).fetchone()
    if summary is None or int(summary[0]) < 1 or not all(summary[index] for index in (4, 5, 6)):
        raise ValueError("prospective selection is empty or lacks a stable digest")
    coverage = connection.execute(query_prefix + """
SELECT source_id, count(*)::bigint,
       count(*) FILTER (WHERE display_location IS NOT NULL)::bigint,
       count(*) FILTER (WHERE display_location IS NULL)::bigint,
       count(*) FILTER (WHERE candidate_geometry_valid IS TRUE)::bigint
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
            "conditional_unmapped_count": int(summary[0]) - int(summary[3]),
            "member_identity_sha256": summary[4],
            "representative_source_record_sha256": summary[5],
            "geometry_evidence_sha256": summary[6],
        },
        "source_coverage": [
            {"source_id": row[0], "candidate_count": int(row[1]),
             "mapped_candidate_count": int(row[2]), "unmapped_candidate_count": int(row[3]),
             "conditional_geometry_valid_count": int(row[4])}
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
