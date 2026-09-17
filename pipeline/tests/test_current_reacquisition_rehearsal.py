import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.scripts.maintenance.rehearse_current_reacquisition import EXPECTED, build_report


class CurrentReacquisitionRehearsalTests(unittest.TestCase):
    def test_validates_all_sources_and_writes_row_free_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); profiles = []
            for index, source_id in enumerate(EXPECTED):
                raw = root / f"raw-{index}.bin"; raw.write_bytes(f"raw-{index}".encode())
                run = root / source_id; (run / "candidate-handoff" / "normalized").mkdir(parents=True)
                rows = '{"source_id":"%s","source_row":1}\n' % source_id
                norm = run / "candidate-handoff" / "normalized" / "records.jsonl"; norm.write_text(rows)
                raw_hash = hashlib.sha256(raw.read_bytes()).hexdigest(); norm_hash = hashlib.sha256(norm.read_bytes()).hexdigest()
                manifest = {"source_id": source_id, "release_state":"not-created", "publication_state":"private-candidate", "normalized_sha256":norm_hash}
                (run / "manifest.json").write_text(json.dumps(manifest)); (run / "candidate-handoff" / "manifest.json").write_text(json.dumps({"source_id": source_id, "normalized_sha256": norm_hash}))
                profiles.append({"source_id":source_id,"private_manifest":str((run / "manifest.json").relative_to(root)),"candidate_handoff_manifest":str((run / "candidate-handoff" / "manifest.json").relative_to(root)),"raw_artifact":str(raw.relative_to(root)),"raw_sha256":raw_hash,"raw_bytes":raw.stat().st_size,"input_rows":1,"normalized_rows":1,"quarantined_rows":0})
            source_manifest = root / "sources.json"; source_manifest.write_text(json.dumps({"publication":{"candidate_release":"candidate-test"},"sources":profiles}))
            output = root / "report.json"; report = build_report(source_manifest, root, output)
            self.assertEqual(report["totals"], {"input": 7, "normalized": 7, "quarantined": 0})
            text = output.read_text(); self.assertNotIn("source_values", text); self.assertNotIn("establishment_id", text)

    def test_rejects_reconciliation_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = root / "raw"; raw.write_bytes(b"x")
            profiles = []
            for source_id in EXPECTED:
                run = root / source_id; (run / "candidate-handoff" / "normalized").mkdir(parents=True)
                norm = run / "candidate-handoff" / "normalized" / "records.jsonl"; norm.write_text('{"x":1}\n')
                (run / "manifest.json").write_text(json.dumps({"source_id":source_id,"release_state":"not-created","publication_state":"private-candidate"}))
                (run / "candidate-handoff" / "manifest.json").write_text(json.dumps({"source_id":source_id}))
                profiles.append({"source_id":source_id,"private_manifest":str((run/"manifest.json").relative_to(root)),"candidate_handoff_manifest":str((run/"candidate-handoff"/"manifest.json").relative_to(root)),"raw_artifact":"raw","raw_sha256":hashlib.sha256(b"x").hexdigest(),"raw_bytes":1,"input_rows":2,"normalized_rows":1,"quarantined_rows":0})
            manifest = root / "sources.json"; manifest.write_text(json.dumps({"publication":{"candidate_release":"candidate-test"},"sources":profiles}))
            with self.assertRaises(ValueError): build_report(manifest, root, root / "out.json")


if __name__ == "__main__": unittest.main()
