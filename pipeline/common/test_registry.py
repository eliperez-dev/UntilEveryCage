#!/usr/bin/env python3
import unittest
from pathlib import Path

from .adapter_registry import load


class RegistryTests(unittest.TestCase):
    def test_registered_adapters_have_versioned_capabilities(self):
        registry = load(Path(__file__).parents[1] / "adapter-capabilities.json")
        self.assertEqual({entry["country_code"] for entry in registry["adapters"]}, {"au", "be", "br", "ca", "de", "dk", "es", "eu", "fr", "gb", "mx", "nl", "no", "nz", "pl", "us"})
        eea = next(entry for entry in registry["adapters"] if entry["source_id"] == "eu.eea.intensive-livestock")
        self.assertEqual(eea["country_code"], "eu")  # Publisher scope; facility countries stay source-owned.
        by_source = {entry["source_id"]: entry for entry in registry["adapters"]}
        expected = {
            "no.fiskeridir.aquaculture": ("no", "no-fiskeridir-aquaculture-v2", "no-fiskeridir-mapserver-geojson-v1"),
            "gb.scot.marine.aquaculture": ("gb", "gb-scot-marine-aquaculture-v1", "gb-scot-aquaculture-wfs-geojson-v1"),
            "us.epa.echo-animal-production": ("us", "us-epa-echo-animal-adapter-v1", "us-epa-echo-facilities-cwa-animal-production-v1"),
        }
        for source_id, (country, adapter_version, schema_version) in expected.items():
            entry = by_source[source_id]
            self.assertEqual((entry["country_code"], entry["adapter_version"], entry["schema_version"]),
                             (country, adapter_version, schema_version))
            self.assertTrue(entry["live_callable"])
            self.assertEqual(entry["operational_classification"], "live")
        separate_geocoding = {"nl.nvwa.approved-food", "es.locations", "de.locations", "pl.giw.approved-food"}
        for source_id, entry in by_source.items():
            with self.subTest(source_id=source_id):
                self.assertEqual(
                    entry["geocoding"],
                    "separate-private-profile" if source_id in separate_geocoding else "disabled",
                )
        self.assertTrue(all(entry["publication"] == "human_gate_required" for entry in registry["adapters"]))
        self.assertEqual({entry.get("source_kind", "facility_master") for entry in registry["adapters"]}, {"facility_master", "evidence_event"})


if __name__ == "__main__":
    unittest.main()
