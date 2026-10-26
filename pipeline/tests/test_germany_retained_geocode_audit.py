import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from pipeline.tests.test_locationiq_adapter import row

SPEC = importlib.util.spec_from_file_location("retained_geocode_audit", Path(__file__).resolve().parents[1]
                                            / "scripts/diagnostics/audit-germany-retained-geocodes.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
QUERY = "Musterstr. 12, 12345, Berlin, Berlin, Germany"


class RetainedGeocodeAuditTests(unittest.TestCase):
    def classify(self, items, query=QUERY):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")), \
             patch("urllib.request.build_opener", side_effect=AssertionError("network forbidden")):
            return AUDIT.classify(query, {"results": items})

    def test_spelling_recovery_is_offline_and_does_not_change_evidence(self):
        item = row()
        before = repr(item)
        self.assertEqual(self.classify([item]), "street_spelling_recovery_candidate")
        self.assertEqual(repr(item), before)

    def test_other_address_checks_still_apply(self):
        for field, value in (("house_number", "13"), ("postcode", "54321"), ("city", "Potsdam"),
                             ("state", "Bayern"), ("country_code", "at"), ("road", "Otherstraße")):
            item = row()
            item["address"][field] = value
            with self.subTest(field=field):
                self.assertEqual(self.classify([item]), "still_requires_review")
        for changes in ({"class": "highway"}, {"type": "road"}, {"lat": "NaN"}, {"lon": "999"}):
            self.assertEqual(self.classify([row(**changes)]), "still_requires_review")

    def test_ambiguity_is_not_recovery_and_existing_match_is_distinct(self):
        self.assertEqual(self.classify([row(), row(place_id=456)]), "ambiguous_after_street_normalization")
        self.assertEqual(self.classify([row()], "Musterstraße 12, 12345, Berlin, Berlin, Germany"),
                         "already_matches_current_rule")

    def test_malformed_response_is_rejected_without_network(self):
        for response in (None, {}, {"results": []}, {"results": "invalid"}, {"results": [row()] * 3}):
            self.assertEqual(AUDIT.classify(QUERY, response), "invalid_retained_response")

    def test_database_guard_and_read_only_connection_are_required(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = ("another_database",)
        context = MagicMock()
        context.__enter__.return_value = connection
        with patch.object(AUDIT.psycopg, "connect", return_value=context) as connect:
            with self.assertRaisesRegex(ValueError, "wrong_disposable_database"):
                AUDIT.audit("postgresql://localhost/another_database")
        self.assertIn("default_transaction_read_only=on", connect.call_args.kwargs["options"])
        self.assertEqual(connection.execute.call_count, 1)
        with patch.object(AUDIT.psycopg, "connect") as connect:
            with self.assertRaises(ValueError):
                AUDIT.audit("postgresql://remote.example/database")
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
