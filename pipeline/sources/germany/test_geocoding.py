import os
import unittest
from unittest.mock import patch

from pipeline.geocoding.private_profiles import profile_by_id, profile_for_source
from pipeline.geocoding.registry import get_adapter


class GermanyPrivateGeocodingTests(unittest.TestCase):
    def test_profile_is_country_and_source_scoped_private_only(self):
        profile = profile_for_source("de.locations")
        self.assertEqual(profile["profile_id"], "geoapify-de-bltu")
        self.assertEqual(profile["country_code"], "DE")
        self.assertEqual(profile["status"], "enabled-private-only")
        self.assertNotIn("facility name", profile["source_scope"])
        self.assertEqual(profile_by_id("geoapify-de-bltu"), profile)

    def test_profile_adapter_applies_germany_filter_without_ip_bias(self):
        with patch.dict(os.environ, {"GEOAPIFY_API_KEY": "synthetic-test-key"}):
            adapter = get_adapter("geoapify", private_source_profile_id="geoapify-de-bltu")
        self.assertEqual(adapter.country_code, "de")
        self.assertTrue(adapter.private_source_profile)
        self.assertTrue(adapter.strict_matching)


if __name__ == "__main__":
    unittest.main()
