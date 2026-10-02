from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.sources.brazil.sif_registered import (
    ADAPTER_VERSION, HEADERS, SCHEMA_VERSION, SOURCE_ID, SifRegisteredAdapter,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sif_registered.csv"


class SifRegisteredAdapterTests(unittest.TestCase):
    def test_fixture_retains_repeated_sif_rows_as_distinct_observations(self):
        parsed = SifRegisteredAdapter().parse_bytes(FIXTURE.read_bytes())
        self.assertEqual(parsed["input_rows"], 2)
        self.assertEqual(len(parsed["accepted"]), 2)
        self.assertEqual(parsed["accepted"][0]["normalized"]["establishment_id"], "0001")
        self.assertNotEqual(parsed["accepted"][0]["source_record_key"], parsed["accepted"][1]["source_record_key"])
        self.assertEqual(parsed["accepted"][0]["normalized"]["country_code"], "BR")
        self.assertIsNone(parsed["accepted"][0]["normalized"]["coordinates"])

    def test_full_source_fields_do_not_enter_candidate_handoff(self):
        adapter = SifRegisteredAdapter()
        parsed = adapter.parse_bytes(FIXTURE.read_bytes())
        safe_rows = adapter.minimize_for_handoff(parsed["accepted"])
        handoff = json.dumps(safe_rows, ensure_ascii=False)
        self.assertEqual(len(safe_rows), 2)
        self.assertTrue(all(row["source_values"] == {} for row in safe_rows))
        policy = json.loads((ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))
        allowed = set(policy["sources"][SOURCE_ID]["allowed_preview_fields"])
        self.assertTrue(all(set(row["normalized"]) <= allowed for row in safe_rows))
        for restricted in ("CPF_CNPJ", "LOGRADOURO", "TELEFONE", "EMAIL", "DESCRICAO_OCORRENCIA", "Fixture Operator"):
            self.assertNotIn(restricted, handoff)

    def test_missing_sif_is_quarantined_and_unknown_headers_fail_closed(self):
        row = dict.fromkeys(HEADERS, "")
        row["NR_SIF"] = ""
        content = (";".join(HEADERS) + "\n" + ";".join(row.get(header, "") for header in HEADERS) + "\n").encode()
        result = SifRegisteredAdapter().parse_bytes(content)
        self.assertEqual(len(result["accepted"]), 0)
        self.assertEqual(result["quarantined"][0]["reasons"], ["missing_sif_number"])
        with self.assertRaisesRegex(ValueError, "schema drift"):
            SifRegisteredAdapter().parse_bytes(content.replace(b"NR_SIF", b"UNKNOWN", 1))

    def test_artifact_contract_is_versioned_and_source_scoped(self):
        raw = FIXTURE.read_bytes()
        artifact = SourceArtifact(
            source_url="https://example.invalid/private-test.csv", retrieved_at_utc="2026-10-01T00:00:00Z",
            sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), code_version=ADAPTER_VERSION,
            config_version=SCHEMA_VERSION, rights_caveat="test", privacy_caveat="test", coverage="fixture only",
        )
        self.assertEqual(artifact.code_version, ADAPTER_VERSION)
        self.assertEqual(SOURCE_ID, "br.sif.registered")


if __name__ == "__main__":
    unittest.main()
