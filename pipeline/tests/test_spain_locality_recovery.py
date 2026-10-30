import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.sources.spain_rgseaa import locality_recovery as recovery


class SpainLocalityRecoveryTests(unittest.TestCase):
    def artifacts(self, root, *, address="Calle Example 4", province="Palma de Mallorca"):
        raw=("<table><tr><th>N RGSEAA</th><th>Dom. Indl.</th><th>Localidad</th><th>Provincia</th></tr>"
             f"<tr><td>10.7/PM</td><td>{address}</td><td>Example Town</td><td>{province}</td></tr></table>").encode()
        metadata={"source_id":"es.locations","source_url":recovery.FINDER_URL,
            "response_kind":"official_excel_export","query_scope":{"registration_number":"blank","province":"Illes Balears","sector":"10"},
            "response_sha256":hashlib.sha256(raw).hexdigest(),"retrieved_at_utc":"2026-10-25T00:00:00Z"}
        (root/"test.xls").write_bytes(raw)
        (root/"test.json").write_text(json.dumps(metadata),encoding="utf-8")
        return metadata

    def test_replay_requires_current_source_identity_same_address_and_verified_artifact(self):
        key="a"*64
        records={key:{"source_id":"es.locations","source_record_key":key,"normalized":{
            "establishment_id":"10.7/PM","address":"Calle Example 4","province":"Illes Balears"}}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.artifacts(root)
            with patch.dict(os.environ,{"UEC_REAL_PREVIEW_RUNS_ROOT":str(root)}), \
                 patch.object(recovery,"_load_records",return_value=(records,"b"*64)), \
                 patch.object(recovery,"_eligible_representatives",return_value=[("10.7/PM",key)]):
                result=recovery.recover("unused",root/"records.jsonl",root,root/"events.jsonl")
                self.assertEqual(result["events_appended"],1)
                self.assertEqual(result["provider_calls"],0)
                self.assertNotIn("Calle",(root/"events.jsonl").read_text(encoding="utf-8"))
                repeated=recovery.recover("unused",root/"records.jsonl",root,root/"events.jsonl")
                self.assertEqual(repeated["events_appended"],0)
                self.assertEqual(repeated["outcomes"]["already_checkpointed"],1)

    def test_tampered_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.artifacts(root)
            (root/"test.xls").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError,"provenance_mismatch"):
                recovery.retained_index(root)

    def test_different_address_does_not_recover_a_town(self):
        key="a"*64
        records={key:{"source_id":"es.locations","source_record_key":key,"normalized":{
            "establishment_id":"10.7/PM","address":"Calle Other 4","province":"Illes Balears"}}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.artifacts(root)
            with patch.dict(os.environ,{"UEC_REAL_PREVIEW_RUNS_ROOT":str(root)}), \
                 patch.object(recovery,"_load_records",return_value=(records,"b"*64)), \
                 patch.object(recovery,"_eligible_representatives",return_value=[("10.7/PM",key)]):
                result=recovery.recover("unused",root/"records.jsonl",root,root/"events.jsonl")
                self.assertEqual(result["events_appended"],0)
                self.assertEqual(result["outcomes"]["retained_address_differs"],1)


if __name__=="__main__":unittest.main()
