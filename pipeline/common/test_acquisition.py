import json
import tempfile
import unittest
from pathlib import Path

from .acquisition import AcquisitionError, archive_stream, require_terms_review


class AcquisitionContractTests(unittest.TestCase):
    def test_terms_review_requires_explicit_approved_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "terms.json"
            path.write_text(json.dumps({"reviewer": "operator", "reference": "OGL", "reviewed_at": "2026-09-15T00:00:00Z", "decision": "pending", "notes": "restricted"}), encoding="utf-8")
            with self.assertRaises(AcquisitionError):
                require_terms_review(path)

    def test_archive_stream_enforces_bound_and_removes_partial(self):
        class Stream:
            def read(self, _size):
                return b"123456"

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "artifact.csv"
            with self.assertRaises(AcquisitionError):
                archive_stream(Stream(), target, max_bytes=5)
            self.assertFalse(target.exists())
            self.assertFalse(list(Path(directory).glob("*.part")))


if __name__ == "__main__":
    unittest.main()
