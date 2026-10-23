"""Synthetic safety controls for the cross-source private matcher."""
from __future__ import annotations

import unittest

from pipeline.common.d5_connection_analysis import (
    _match_features,
    _observed_from_row,
    _iter_probabilistic_candidates,
    iter_shared_business_name_candidates,
)
from pipeline.common.graph_persistence import _matcher_edge


def observed(source: str, key: str, facility: str, *, name: str = "",
             name_assertions: list[dict[str, str]] | None = None,
             location_role: str = "unknown", address: str = "",
             postal: str = "", business_contacts: list[dict[str, str]] | None = None,
             org_identifier: dict[str, str] | None = None):
    row = {
        "source_id": source,
        "source_record_key": key,
        "source_record_key": key,
        "source_values": {"safe_synthetic_fixture": True},
        "source_artifact_sha256": "a" * 64,
        "source_row": 1,
        "normalized": {"establishment_id": facility, "name": name,
                       "address": address, "postal_code": postal},
        "location_role": location_role,
    }
    if name_assertions is not None:
        row["name_assertions"] = name_assertions
    if business_contacts is not None:
        row["business_contacts"] = business_contacts
    if org_identifier is not None:
        row["organizations"] = [{"local_ref": "org", "source_identifier": org_identifier}]
    return _observed_from_row(row)


class D7GraphConvergenceTests(unittest.TestCase):
    def test_declared_business_names_match_across_sources_and_large_groups_are_complete(self):
        rows = [
            observed("us.fsis", "one", "F-1", name_assertions=[
                {"value": "Acme Foods", "source_field": "operator", "role": "business"},
            ]),
            observed("ca.ontario.meat-plants", "two", "F-2", name_assertions=[
                {"value": "ACME Foods", "source_field": "legal_name", "role": "legal"},
            ]),
            observed("dk.smiley", "three", "F-3", name_assertions=[
                {"value": "Acme Foods", "source_field": "trade", "role": "trading"},
            ]),
            observed("br.sif.registered", "four", "F-4", name_assertions=[
                {"value": "Acme Foods", "source_field": "aka", "role": "dba"},
            ]),
        ]
        generated, counters = iter_shared_business_name_candidates(rows)
        candidates = list(generated)
        self.assertEqual(len(candidates), 6)
        self.assertEqual(counters["pairs_emitted"], 6)
        self.assertTrue(all(item["relationship_type"] == "shared_business_name" for item in candidates))
        self.assertEqual({source for item in candidates for source in item["source_pair"]},
                         {"us.fsis", "ca.ontario.meat-plants", "dk.smiley", "br.sif.registered"})
        edge = _matcher_edge(candidates[0], {"source_id": "us.fsis", "source_record_key": "one"},
                             {"source_id": "us.fsis", "retrieved_at_utc": "2026-10-23T00:00:00Z"})
        self.assertIsNotNone(edge, repr(candidates[0]))
        self.assertEqual(edge["relationship_type"], "shared_business_name")
        self.assertEqual(edge["connection_type"], "inferred")

    def test_placeholder_and_generic_names_do_not_form_name_or_site_candidates(self):
        names = ["Unknown", "N/A", "Food Processing Facility", "Slaughterhouse 12"]
        for name in names:
            left = observed("au.npi.facilities", "a", "A", name=name,
                            name_assertions=[{"value": name, "source_field": "name", "role": "business"}],
                            location_role="operating", address="1 Main Road", postal="1000")
            right = observed("nl.nvwa.approved-food", "b", "B", name=name,
                             name_assertions=[{"value": name, "source_field": "name", "role": "business"}],
                             location_role="operating", address="1 Main Road", postal="1000")
            names_generated, _ = iter_shared_business_name_candidates([left, right])
            site_generated, _ = _iter_probabilistic_candidates([left, right], max_block_size=2)
            self.assertEqual(list(names_generated), [], name)
            self.assertEqual(list(site_generated), [], name)

    def test_mailing_addresses_and_city_only_context_are_not_site_anchors(self):
        left = observed("au.npi.facilities", "a", "A", name="River Foods",
                        location_role="mailing", address="8 Dock Street", postal="3000")
        right = observed("nl.nvwa.approved-food", "b", "B", name="River Foods",
                         location_role="operating", address="8 Dock Street", postal="3000")
        generated, _ = _iter_probabilistic_candidates([left, right])
        self.assertEqual(list(generated), [])

    def test_large_site_block_is_not_truncated_and_normalized_values_are_consumed(self):
        rows = []
        for index, source in enumerate(("au.npi.facilities", "nl.nvwa.approved-food", "dk.smiley")):
            rows.append(_observed_from_row({
                "contract_version": "graph-candidate-handoff-v1",
                "source_id": source,
                "source_record_key": f"site-{index}",
                "source_values": {"synthetic": True},
                "source_artifact_sha256": "b" * 64,
                "facilities": [{"local_ref": "site", "source_identifier": {
                    "identifier_type": "permit", "value": f"P-{index}",
                }}],
                "name_assertions": [{"value": "River Foods", "source_field": "operator", "role": "business"}],
                "normalized_values": {"name": "River Foods", "postal_code": "5000", "address": "2 Mill Road"},
                "location_role": "operating",
            }))
        generated, counters = _iter_probabilistic_candidates(rows, max_block_size=2, preserve_native_endpoints=True)
        self.assertEqual(len(list(generated)), 3)
        self.assertEqual(counters["blocks_ambiguous"], 0)

    def test_eligible_phone_and_domain_match_but_government_host_is_rejected(self):
        left = observed("au.npi.facilities", "a", "A", name="River Foods",
                        business_contacts=[{"kind": "website_domain", "value": "https://river.example/"},
                                           {"kind": "phone", "value": "+1 (555) 010-1234"}])
        right = observed("nl.nvwa.approved-food", "b", "B", name="Other Company",
                         business_contacts=[{"kind": "website_domain", "value": "river.example"},
                                            {"kind": "phone", "value": "+1 (555) 010-1234"}])
        candidates, _ = _iter_probabilistic_candidates([left, right])
        self.assertEqual(len(list(candidates)), 1)
        government = observed("us.fsis", "g", "G", business_contacts=[
            {"kind": "website_domain", "value": "https://inspection.gov.example/"},
        ])
        self.assertFalse(government.business_contacts)

    def test_cross_source_identifiers_require_same_explicit_authority_namespace(self):
        local_left = observed("au.npi.facilities", "a", "A", org_identifier={
            "identifier_type": "registration", "value": "123",
        })
        local_right = observed("ca.ontario.meat-plants", "b", "B", org_identifier={
            "identifier_type": "registration", "value": "123",
        })
        self.assertIn("conflicting_identifier", [item["signal"] for item in _match_features(local_left, local_right)[1]])
        authority_left = observed("au.npi.facilities", "c", "C", org_identifier={
            "identifier_type": "registration", "id_namespace": "authority-x",
            "value": "123",
        })
        authority_right = observed("ca.ontario.meat-plants", "d", "D", org_identifier={
            "identifier_type": "registration", "id_namespace": "authority-x",
            "value": "123",
        })
        self.assertNotIn("conflicting_identifier", [item["signal"] for item in _match_features(authority_left, authority_right)[1]])


if __name__ == "__main__":
    unittest.main()
