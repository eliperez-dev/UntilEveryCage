import unittest

from pipeline.common.review_console import (
    READINESS_CLASSES,
    build_review_console_snapshot,
    classify_country,
)
from pipeline.platform_registry import build_platform_registry


def source(acquisition="not_run", metadata="verified", *, approved=False, public=False):
    return {
        "source_id": "aa.synthetic",
        "country_code": "AA",
        "jurisdiction_scope": "synthetic scope",
        "source_url": "https://example.test/source",
        "access_method": "synthetic",
        "cadence": "unknown",
        "status": {
            "metadata": metadata,
            "acquisition": acquisition,
            "runtime_health": "unknown",
            "publication_eligibility": "eligible_pending_release_approval" if public else "blocked",
            "evidence": [],
            "next_action": "review",
        },
        "readiness": {"state": "approved-for-release" if approved else "awaiting-owner-review", "owner_review": "approved" if approved else "awaiting-owner-review", "private_candidate": True, "public_release_allowed": public, "reasons": []},
        "owner_review": {"state": "approved" if approved else "awaiting-owner-review", "decision_id": "decision-1" if approved else None},
        "publication": {"state": "approved-for-release" if approved else "blocked", "approval_required": True, "reason": "synthetic"},
        "coverage": {"completeness": "not-claimed", "disappearance_semantics": "not-observed; never inferred as closure", "limitations": []},
        "attribution": {"source_origin": "synthetic", "terms_status": "reviewed", "attribution_required": True, "notice": "synthetic"},
    }


class ReviewConsoleTests(unittest.TestCase):
    def test_classification_is_conservative_and_ordered(self):
        self.assertEqual(classify_country([source("blocked")]), "blocked")
        self.assertEqual(classify_country([source("not_run")]), "acquisition-ready")
        self.assertEqual(classify_country([source("artifact_private_only"), source("not_run")]), "private-candidate-ready")
        self.assertEqual(classify_country([source("verified")]), "human-review-ready")
        self.assertEqual(classify_country([source("verified", approved=True, public=True)]), "publication-eligible")
        self.assertEqual(classify_country([source("not_run", metadata="unknown")]), "infrastructure-only")

    def test_snapshot_is_row_free_and_covers_all_contract_countries(self):
        registry = {
            "contract_versions": {"country": "country-contract-v1"},
            "sources": [source("verified")],
            "countries": [{"country_code": "AA", "display_name": "AA", "owner_review": {"state": "awaiting-owner-review"}, "publication": {"state": "blocked"}, "readiness": {"reasons": ["review"]}}],
        }
        snapshot = build_review_console_snapshot(registry, generated_at="2026-09-18T00:00:00Z")
        self.assertEqual(snapshot["country_count"], 1)
        self.assertEqual(snapshot["source_count"], 1)
        self.assertEqual(snapshot["countries"]["AA"]["state"], "human-review-ready")
        self.assertEqual(snapshot["generated_at"], "2026-09-18T00:00:00Z")
        self.assertTrue(snapshot["derived_context"])
        self.assertEqual(set(snapshot["states"]), set(READINESS_CLASSES))
        serialized = str(snapshot)
        for forbidden in ("source_values", "raw_fields", "address", "street_address", "geocoder_query", "reviewer_identity"):
            self.assertNotIn(forbidden, serialized)

    def test_checked_in_registry_produces_a_classification_for_every_country(self):
        snapshot = build_review_console_snapshot(build_platform_registry(), generated_at="2026-09-18T00:00:00Z")
        self.assertEqual(snapshot["country_count"], 46)
        self.assertEqual(set(snapshot["countries"]), {record["country_code"] for record in snapshot["country_records"]})
        self.assertTrue(all(record["readiness_class"] in READINESS_CLASSES for record in snapshot["country_records"]))


if __name__ == "__main__":
    unittest.main()
