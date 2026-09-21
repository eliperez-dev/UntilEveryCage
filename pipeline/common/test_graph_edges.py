import unittest

from .graph_edges import (
    EntityRef,
    SignalDefinition,
    SourceRef,
    build_connection_edge,
    default_signal_registry,
    score_connection,
    validate_connection_edge,
)


class D6GraphEdgeScoringTests(unittest.TestCase):
    def setUp(self):
        self.registry = default_signal_registry()

    def test_known_source_assertion_is_exact_and_source_scoped(self):
        # A source-native assertion is the strongest kind of known connection;
        # identifiers remain source-qualified even when the edge is exact.
        result = score_connection([self.registry.signal("source_assertion", details={"assertion": "operator"})], registry=self.registry)
        self.assertEqual(result.connection_type, "exact")
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.confidence_band, "exact")
        edge = build_connection_edge(
            from_ref=EntityRef("organization", "dk.smiley", "cvr", "known-source-cvr"),
            to_ref=EntityRef("facility", "dk.smiley", "approval_id", "known-source-facility"),
            relationship_type="operator", scoring=result,
            supporting_source_refs=[SourceRef("dk.smiley", source_record_key="known-source-record")],
            observed_at="2026-09-20T00:00:00Z",
        )
        self.assertEqual(edge["connection_type"], "exact")
        self.assertEqual(edge["from"]["identity_scope"], "source_scoped")
        self.assertEqual(edge["publication_status"], "not_eligible")

    def test_name_postal_anchor_compounds_with_independent_groups(self):
        anchored = score_connection([
            self.registry.signal("organization_name_normalized"),
            self.registry.signal("postal_match"),
        ], registry=self.registry)
        compounded = score_connection([
            self.registry.signal("organization_name_normalized"),
            self.registry.signal("postal_match"),
            self.registry.signal("address_match"),
            self.registry.signal("business_phone_match"),
            self.registry.signal("temporal_compatibility"),
        ], registry=self.registry)
        self.assertTrue(anchored.eligible)
        self.assertEqual(anchored.connection_type, "inferred")
        self.assertGreater(compounded.confidence, anchored.confidence)
        self.assertIn("location", compounded.explanation["group_contributions"])
        self.assertIn("contact", compounded.explanation["group_contributions"])

    def test_correlated_signals_have_diminishing_returns(self):
        registry = default_signal_registry()
        registry.register(SignalDefinition("same_city_alias", "location", 0.10))
        registry.register(SignalDefinition("same_region_alias", "location", 0.10))
        one = score_connection([registry.signal("organization_name_normalized"), registry.signal("postal_match")], registry=registry)
        two = score_connection([registry.signal("organization_name_normalized"), registry.signal("postal_match"), registry.signal("same_city_alias")], registry=registry)
        three = score_connection([registry.signal("organization_name_normalized"), registry.signal("postal_match"), registry.signal("same_city_alias"), registry.signal("same_region_alias")], registry=registry)
        first_increment = two.confidence - one.confidence
        second_increment = three.confidence - two.confidence
        self.assertGreater(first_increment, 0)
        self.assertGreater(second_increment, 0)
        self.assertLess(second_increment, first_increment)

    def test_contradictions_reduce_but_do_not_hide_an_inferred_edge(self):
        clean = score_connection([
            self.registry.signal("organization_name_normalized"),
            self.registry.signal("postal_match"),
            self.registry.signal("address_match"),
        ], registry=self.registry)
        conflict = score_connection([
            self.registry.signal("organization_name_normalized"),
            self.registry.signal("postal_match"),
            self.registry.signal("address_match"),
            self.registry.signal("conflicting_address"),
        ], registry=self.registry)
        self.assertTrue(conflict.eligible)
        self.assertEqual(conflict.connection_type, "inferred")
        self.assertLess(conflict.confidence, clean.confidence)
        self.assertEqual(len(conflict.contradictions), 1)

    def test_weak_signal_alone_does_not_create_edge(self):
        for name in ("name_only", "address_only", "phone_only", "domain_only", "proximity_only", "fuzzy_only"):
            result = score_connection([self.registry.signal(name)], registry=self.registry)
            self.assertFalse(result.eligible, name)
            self.assertIsNone(result.connection_type, name)

    def test_rules_are_reproducible_independent_of_input_order(self):
        values = [
            self.registry.signal("organization_name_normalized", details={"normalized": "example"}),
            self.registry.signal("postal_match", details={"postal": "00000"}),
            self.registry.signal("business_phone_match"),
            self.registry.signal("conflicting_address"),
        ]
        first = score_connection(values, registry=self.registry).as_dict()
        second = score_connection(reversed(values), registry=self.registry).as_dict()
        self.assertEqual(first, second)

    def test_future_signal_can_be_added_without_a_schema_change(self):
        registry = default_signal_registry(version="d6-signal-rules-v2")
        registry.register(SignalDefinition("independent_registry_crosswalk", "source", 0.21, qualifies=True))
        result = score_connection([
            registry.signal("organization_name_normalized"),
            registry.signal("independent_registry_crosswalk"),
        ], registry=registry)
        self.assertTrue(result.eligible)
        self.assertEqual(result.ruleset_version, "d6-signal-rules-v2")
        self.assertIn("independent_registry_crosswalk", result.match_method)

    def test_universal_identity_fields_are_rejected(self):
        result = score_connection([self.registry.signal("identifier_cooccurrence")], registry=self.registry)
        with self.assertRaises(ValueError):
            edge = build_connection_edge(
                from_ref=EntityRef("organization", "it.853-2004", "vat", "org-1"),
                to_ref=EntityRef("facility", "it.853-2004", "facility_id", "fac-1"),
                relationship_type="operator", scoring=result,
                supporting_source_refs=[SourceRef("it.853-2004", source_record_key="record-1")],
                observed_at="2026-09-20T00:00:00Z",
            )
            edge["from"]["global_id"] = "do-not-use"
            validate_connection_edge(edge)


if __name__ == "__main__":
    unittest.main()
