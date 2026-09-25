#!/usr/bin/env python3
import unittest
from pathlib import Path

from .adapter_registry import load


class RegistryTests(unittest.TestCase):
    def test_registered_adapters_have_versioned_capabilities(self):
        registry = load(Path(__file__).parents[1] / "adapter-capabilities.json")
        self.assertEqual({entry["country_code"] for entry in registry["adapters"]}, {"au", "be", "ca", "de", "dk", "fr", "gb", "us"})
        self.assertTrue(all(entry["geocoding"] == "disabled" for entry in registry["adapters"]))
        self.assertTrue(all(entry["publication"] == "human_gate_required" for entry in registry["adapters"]))
        self.assertEqual({entry.get("source_kind", "facility_master") for entry in registry["adapters"]}, {"facility_master", "evidence_event"})


if __name__ == "__main__":
    unittest.main()
