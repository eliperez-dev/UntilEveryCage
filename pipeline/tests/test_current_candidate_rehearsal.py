import tempfile
import unittest
from pathlib import Path

from pipeline.scripts.maintenance import rehearse_current_candidate as rehearsal


class CurrentCandidateRehearsalTests(unittest.TestCase):
    def test_artifact_resolution_requires_one_exact_hash_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "data" / "raw" / "source" / "source.csv"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"private fixture")
            digest, size = rehearsal._sha256(artifact)
            self.assertEqual(rehearsal._find_artifact(root, "source", digest, size), artifact)
            with self.assertRaises(rehearsal.RehearsalError) as error:
                rehearsal._find_artifact(root, "source", "0" * 64, size)
            self.assertIn("raw artifact resolution failed closed", str(error.exception))

    def test_report_safety_rejects_row_bearing_keys(self):
        with self.assertRaises(rehearsal.RehearsalError):
            rehearsal._assert_report_safe({"sources": [{"source_values": {"name": "private"}}]})


if __name__ == "__main__":
    unittest.main()
