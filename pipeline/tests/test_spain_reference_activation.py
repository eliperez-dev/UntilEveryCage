import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.sources.spain_rgseaa import reference_activation as activation
from pipeline.sources.spain_rgseaa.location_enrichment import match_official_result
from pipeline.sources.spain_rgseaa.municipality_reference import SOURCE_URL


def _event(key: str, registration: str = "10.123456/CO") -> dict:
    record = {"source_id": "es.locations", "source_record_key": key,
              "source_values": {"N_RGSEAA": registration, "Provincia": "Córdoba"},
              "normalized": {"establishment_id": registration, "province": "Córdoba"}}
    return match_official_result(record, [{"registration": registration,
        "municipality": "Villa Test", "province": "Córdoba"}],
        retrieved_at="2026-10-25T00:00:00Z",
        result_url="https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal_excel.jsp",
        request_url="https://rgsa-web-aesan.mscbs.es/rgsa/procesaBusquedaServlet")


class SpainReferenceActivationTests(unittest.TestCase):
    def test_full_event_reader_exceeds_old_geoapify_pilot_cap_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            rows = []
            for number in range(30):
                rows.append(_event(f"{number:064x}", f"10.{number + 1:06d}/CO"))
            rows.append(rows[0])
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            accepted = activation.load_locality_events(path)
        self.assertEqual(len(accepted), 30)

    def test_activation_appends_exact_official_coarse_evidence_and_never_jobs(self):
        event = _event("a" * 64)
        event["source_record_key"] = "a" * 64
        reference = {"source_id": "ign-ngmep-2026", "source_url": SOURCE_URL,
            "source_sha256": "b" * 64, "attribution": "IGN attribution",
            "municipalities": [{"municipality_code": "14000" + "00000" + "1",
                "municipality_name": "Villa Test", "province_code": "14",
                "province_name": "Córdoba", "latitude": 37.0, "longitude": -4.8,
                "coordinate_origin": "Mapa", "population": 100}]}
        class Result:
            def __init__(self, row=None): self.row = row
            def fetchone(self): return self.row
            def fetchall(self): return self.row or []
        class Connection:
            def __init__(self): self.statements, self.calls, self.existing = [], [], None
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def transaction(self): return self
            def execute(self, sql, params=()):
                self.statements.append(sql)
                self.calls.append((sql, params))
                if sql.startswith("SET TRANSACTION"):
                    return Result(None)
                if "SELECT current_database()" in sql:
                    return Result((activation.DATABASE,))
                if "SELECT snapshot_sha256 FROM real_preview.source_preview_runs" in sql:
                    return Result(("c" * 64,))
                if "FROM real_preview.candidates candidate" in sql:
                    return Result([("candidate", "c" * 64, "10.123456/CO", "a" * 64,
                                    "ES", "unmapped_private_observation", True, "ES", True)])
                if "FROM real_preview.local_reference_display_evidence" in sql:
                    return Result(self.existing)
                if "INSERT INTO real_preview.local_reference_display_evidence" in sql:
                    self.existing = (params[1], params[2], params[3], params[4],
                                     "locality_reference_coarse", params[5], params[6], params[7])
                    return Result(("evidence-id",))
                raise AssertionError("unexpected SQL")
        connection = Connection()
        with tempfile.TemporaryDirectory() as directory:
            events_path = Path(directory) / "events.jsonl"
            reference_path = Path(directory) / "reference.json"
            events_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            import hashlib
            import json as json_module
            reference["version"] = "ign-ngmep-2026"
            reference["normalized_reference_sha256"] = hashlib.sha256(json_module.dumps(
                reference["municipalities"], ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
            reference_path.write_text(json.dumps(reference), encoding="utf-8")
            with patch.object(activation, "load_ign_reference_index", return_value=reference):
                result = activation.activate("unused", events_path, reference_path,
                                             connect=lambda *args, **kwargs: connection)
                repeated = activation.activate("unused", events_path, reference_path,
                                               connect=lambda *args, **kwargs: connection)
        self.assertEqual(result["evidence_appended"], 1)
        self.assertEqual(result["provider_calls"], 0)
        sql = " ".join(connection.statements).lower()
        self.assertIn("local_reference_display_evidence", sql)
        self.assertNotIn("insert into uec.geocode_jobs", sql)
        self.assertNotIn("update real_preview.candidates", sql)
        insert = next(params for statement, params in connection.calls
                      if "INSERT INTO real_preview.local_reference_display_evidence" in statement)
        self.assertEqual(insert[5], "IGN NGMEP 2026 municipality reference; Mapa")
        self.assertEqual(insert[6], "ign-ngmep-2026:14000000001")
        self.assertIn("dataset_sha256=" + "b" * 64, insert[7])
        self.assertEqual(repeated["already_present"], 1)
        self.assertEqual(repeated.get("evidence_appended", 0), 0)

    def test_candidate_gates_reject_foreign_country_and_restriction(self):
        allowed = {"restriction_clear": True, "country_code": "ES", "evidence_country_code": "ES",
                   "location_class": "unmapped_private_observation", "default_map_scope": True}
        self.assertEqual(activation._candidate_rejection({**allowed, "country_code": "FR"}),
                         "events_ineligible")
        self.assertEqual(activation._candidate_rejection({**allowed, "evidence_country_code": "FR"}),
                         "events_ineligible")
        self.assertEqual(activation._candidate_rejection({**allowed, "restriction_clear": False}),
                         "events_restricted")
        self.assertIsNone(activation._candidate_rejection(allowed))

    def test_candidate_index_ignores_foreign_snapshot_even_if_returned_by_database(self):
        class Result:
            def fetchall(self):
                return [("candidate", "d" * 64, "10.123456/CO", "a" * 64,
                         "ES", "unmapped_private_observation", True, "ES", True)]
        class Connection:
            def __init__(self): self.sql, self.params = "", ()
            def execute(self, sql, params): self.sql, self.params = sql, params; return Result()
        connection = Connection()
        self.assertEqual(activation._candidate_index(connection, "c" * 64), {})
        self.assertIn("candidate.snapshot_sha256=%s", connection.sql)
        self.assertEqual(connection.params, ("c" * 64, "es.locations"))


if __name__ == "__main__":
    unittest.main()
