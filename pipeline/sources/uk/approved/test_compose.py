import json
import tempfile
import unittest
from pathlib import Path

from ..fsa_approved.adapter import FsaApprovedEstablishmentsAdapter
from ..fss_approved.adapter import FssApprovedEstablishmentsAdapter
from .compose import CompositionError, compose_sources

BASE = Path(__file__).parents[4] / "pipeline/sources/uk"
FSS_FIXTURE = BASE / "fss_approved/fixtures/valid.csv"
FSA_FIXTURE = BASE / "fsa_approved/fixtures/valid.csv"


class UkCompositionTests(unittest.TestCase):
    def _runs(self, root):
        fss_dir, fsa_dir = root / "fss", root / "fsa"
        fss = FssApprovedEstablishmentsAdapter()
        fsa = FsaApprovedEstablishmentsAdapter()
        fss_manifest = fss.run(FSS_FIXTURE, fss_dir)
        fsa_manifest = fsa.run(FSA_FIXTURE, fsa_dir)
        return [
            {"source_id": fss.source_id, "manifest": fss_manifest, "normalized_path": fss_dir / "normalized/records.jsonl", "terms_state": "unresolved", "review_state": "human-review-required"},
            {"source_id": fsa.source_id, "manifest": fsa_manifest, "normalized_path": fsa_dir / "normalized/records.jsonl", "terms_state": "unresolved", "review_state": "human-review-required"},
        ]

    def test_mixed_sources_preserve_provenance_and_duplicate_ids_by_jurisdiction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._runs(root)
            manifest = compose_sources(inputs, root / "country")
            rows = [json.loads(line) for line in (root / "country/reviewable/records.jsonl").read_text().splitlines()]
            self.assertEqual(manifest["source_ids"], ["fsa_approved_establishments", "fss_approved_establishments"])
            self.assertEqual(len(rows), 5)
            fsa_rows = [r for r in rows if r["source_id"] == "fsa_approved_establishments"]
            self.assertEqual({r["source_record_id"] for r in fsa_rows}, {"00017", "NI-004"})
            self.assertEqual({r["source_record"]["normalized"]["nation"] for r in fsa_rows}, {"England", "Wales", "Northern Ireland"})
            self.assertTrue(all("manifest" in row["source_state"] for row in rows))
            self.assertFalse((root / "country/released/records.jsonl").exists())

    def test_source_specific_suppression_survives_reimport(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._runs(root)
            suppressed = {("fsa_approved_establishments", "00017")}
            for suffix in ("one", "reimport"):
                compose_sources(inputs, root / suffix, suppressed=suppressed)
                rows = [json.loads(line) for line in (root / suffix / "reviewable/records.jsonl").read_text().splitlines()]
                self.assertFalse(any(r["source_id"] == "fsa_approved_establishments" and r["source_record_id"] == "00017" for r in rows))
                self.assertTrue(any(r["source_id"] == "fss_approved_establishments" for r in rows))

    def test_exact_cross_source_name_postcode_is_signal_not_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._runs(root)
            fss_path = inputs[0]["normalized_path"]
            fss_record = json.loads(fss_path.read_text().splitlines()[0])
            fss_record["normalized"]["trading_name"] = "East March Foods"
            fss_record["normalized"]["postcode"] = "PE1 2AB"
            fss_path.write_text(json.dumps(fss_record) + "\n")
            manifest = compose_sources(inputs, root / "country")
            signals = [json.loads(line) for line in (root / "country/reviewable/possible-match-signals.jsonl").read_text().splitlines()]
            self.assertEqual(manifest["possible_match_signals"], 1)
            self.assertEqual(len(signals[0]["record_refs"]), 2)
            self.assertFalse(any("merged" in row for row in signals))

    def test_outage_and_incompatible_version_do_not_replace_prior_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._runs(root)
            prior = root / "country/manifest.json"
            prior.parent.mkdir(parents=True)
            prior.write_text("previous-view\n")
            missing = [dict(inputs[0]), dict(inputs[1], normalized_path=root / "missing.jsonl")]
            with self.assertRaises(CompositionError):
                compose_sources(missing, root / "country", prior_view={"manifest": "previous"})
            self.assertEqual(prior.read_text(), "previous-view\n")
            incompatible = [dict(inputs[0]), dict(inputs[1], manifest={**inputs[1]["manifest"], "schema_version": "wrong"})]
            with self.assertRaises(CompositionError):
                compose_sources(incompatible, root / "other")

    def test_terms_and_review_gates_block_candidate_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = compose_sources(self._runs(root), root / "country")
            self.assertFalse(manifest["candidate_created"])
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertIn("fsa_approved_establishments:unresolved", manifest["blockers"])
            self.assertEqual(manifest["publication_state"], "human-gate-required")


if __name__ == "__main__":
    unittest.main()
