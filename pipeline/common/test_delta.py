import json
import tempfile
import unittest
from pathlib import Path

from delta import compare_runs


def write_run(root: Path, name: str, rows: list[dict], schema: str = "schema-a", terms: str = "pending_confirmation") -> Path:
    run = root / name
    (run / "normalized").mkdir(parents=True)
    (run / "normalized" / "records.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (run / "run-manifest.json").write_text(json.dumps({"checksum_sha256": name, "schema_fingerprint": schema, "config_fingerprint": "config-" + name, "mapping_version": "map-1", "adapter_version": "adapter-1", "schema_version": schema, "input_rows": len(rows), "normalized_rows": len(rows), "quarantined_rows": 0, "terms_status": terms}), encoding="utf-8")
    return run


def row(source_id: str, name: str, type_: str = "Meat Processing") -> dict:
    return {"source_id": source_id, "establishment_name": name, "type": type_, "provenance": {"run": name}, "source_values": {"name": name}}


class DeltaTests(unittest.TestCase):
    def test_reimport_change_add_missing_and_suppression(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = write_run(root, "old", [row("A", "same"), row("B", "removed")])
            new = write_run(root, "new", [row("A", "changed", "Meat Slaughter"), row("C", "added"), row("B", "removed")])
            result = compare_runs(old, new, {"C"})
            self.assertEqual(result["status"], "delta-ready")
            self.assertEqual(result["counts"], {"added": 0, "changed": 1, "not_observed": 0, "suppressed": 1})
            self.assertEqual(result["previous"]["config_fingerprint"], "config-old")
            self.assertEqual(result["current"]["config_fingerprint"], "config-new")
            self.assertEqual(set(result["public_surfaces"]), {"api", "map", "export", "cache", "history"})

    def test_missing_source_is_not_observed_not_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = write_run(root, "old", [row("A", "same"), row("B", "gone")])
            new = write_run(root, "new", [row("A", "same")])
            self.assertEqual(compare_runs(old, new)["counts"]["not_observed"], 1)

    def test_schema_change_and_id_reuse_are_blocked_or_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = write_run(root, "old", [row("A", "old site")])
            changed_schema = write_run(root, "new-schema", [row("A", "new site")], schema="schema-b")
            self.assertEqual(compare_runs(old, changed_schema)["status"], "schema-change-blocked")
            reused = write_run(root, "new", [row("A", "new site")])
            self.assertEqual(compare_runs(old, reused)["counts"]["changed"], 1)

    def test_failure_retains_prior_reference_and_blocks_surfaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = write_run(root, "old", [row("A", "same")])
            prior = {"release_id": "validated-1", "eligible": True}
            result = compare_runs(old, root / "missing", prior_eligible_release=prior)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["prior_eligible_release"], prior)
            self.assertFalse(any(result["public_surfaces"].values()))


if __name__ == "__main__":
    unittest.main()
