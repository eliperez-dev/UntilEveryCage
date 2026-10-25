import json
import tempfile
import unittest
from pathlib import Path

from .location_enrichment import LOOKUP_METHOD_VERSION, LOOKUP_SOURCE_ID, registration_key_sha256
from .map_activation import activate, load_verified_events, verified_address_query, verified_event

ROOT = Path(__file__).parents[2]


class _Result:
    def __init__(self, one=None, many=None):
        self.one, self.many = one, many or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class _FakeConnection:
    def __init__(self, *, database="uec_launch_sources_test_20261025", restricted=True,
                 candidate_rows=None):
        self.database = database
        self.restricted = restricted
        self.candidate_rows = candidate_rows
        self.calls = []

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def transaction(self): return self

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.calls.append((sql, params))
        if sql == "SELECT current_database()": return _Result((self.database,))
        if "FROM real_preview.private_geocoding_source_profiles" in sql: return _Result((1,))
        if "WITH latest AS" in sql: return _Result(many=self.candidate_rows or [])
        if "INSERT INTO real_preview.spain_verified_locality_evidence" in sql: return _Result(("evidence-id",))
        if "INSERT INTO uec.source_records" in sql: return _Result(("source-record-id",))
        if "FROM uec.public_access_restricted WHERE source_record_id=%s" in sql:
            return _Result(None if self.restricted else (1,))
        if "INSERT INTO uec.geocode_jobs" in sql: return _Result(("job-id",))
        if "INSERT INTO real_preview.geocode_targets" in sql: return _Result(("candidate-id",))
        return _Result()


def event(registration="10.025892/CO"):
    url = "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal.jsp"
    return {
        "event_type": "official_locality_lookup", "outcome": "matched",
        "source_id": "es.locations", "source_record_key": "a" * 64,
        "registration_key_sha256": registration_key_sha256(registration),
        "source_url": url, "request_url": "https://rgsa-web-aesan.mscbs.es/rgsa/procesaBusquedaServlet",
        "retrieved_at": "2026-10-25T15:00:00Z", "method_source_id": LOOKUP_SOURCE_ID,
        "method_version": LOOKUP_METHOD_VERSION,
        "location_evidence_addition": {"municipality": "Test Municipality", "city": "Test Municipality",
            "province": "Test Province", "precision": "municipality", "source_id": LOOKUP_SOURCE_ID,
            "source_url": url, "retrieved_at": "2026-10-25T15:00:00Z",
            "match_method": "exact_rgseaa_components_and_province"},
    }


def candidate_row(registration="10.25892/CO", *, restriction_clear=True, source_record_key_hash="a" * 64):
    values = ["candidate-id", "b" * 64, registration, source_record_key_hash, "ES",
              "unmapped_private_observation", True, "ORIGINAL INDUSTRIAL ROAD 7",
              "ORIGINAL INDUSTRIAL ROAD 7", "ES", "c" * 64,
              "https://www.aesan.gob.es/source.xlsx", "2026-10-25T00:00:00Z", "artifact-id", restriction_clear]
    return tuple(values)


class SpainMapActivationTests(unittest.TestCase):
    def test_corrected_query_preserves_original_address_and_adds_verified_city_province_country(self):
        query = verified_address_query("  Polígono Los Pinos, Nave 3  ", "Test Municipality", "Test Province")
        self.assertEqual(query, "Polígono Los Pinos, Nave 3, Test Municipality, Test Province, Spain")

    def test_query_does_not_guess_missing_locality_or_street(self):
        with self.assertRaisesRegex(ValueError, "verified_locality_query_incomplete"):
            verified_address_query("Original address", "", "Test Province")

    def test_event_requires_official_host_and_current_exact_match_method(self):
        self.assertIsNotNone(verified_event(event()))
        bad_host = event()
        bad_host["request_url"] = "https://example.test/rgsa/procesaBusquedaServlet"
        with self.assertRaisesRegex(ValueError, "lookup_url_out_of_scope"):
            verified_event(bad_host)
        bad_method = event()
        bad_method["location_evidence_addition"]["match_method"] = "name_guess"
        with self.assertRaisesRegex(ValueError, "locality_match_method_invalid"):
            verified_event(bad_method)

    def test_nonmatched_lookup_events_are_not_queued(self):
        self.assertIsNone(verified_event({"event_type": "official_locality_lookup", "outcome": "not_found"}))

    def test_event_file_is_bounded_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.jsonl")
            path.write_text("\n".join(json.dumps(item) for item in (event(), event(),
                {"event_type": "official_locality_lookup", "outcome": "not_found"})), encoding="utf-8")
            self.assertEqual(len(load_verified_events(path, limit=1)), 1)
            with self.assertRaises(ValueError):
                load_verified_events(path, limit=25)

    def test_source_enrichment_uses_the_same_candidate_representative_rule(self):
        from .location_enrichment import enrich_records
        rows = [
            {"source_id": "es.locations", "source_record_key": "f" * 64,
             "source_values": {"N_RGSEAA": "10.025892/CO"},
             "normalized": {"establishment_id": "10.025892/CO", "address": "address f"}},
            {"source_id": "es.locations", "source_record_key": "a" * 64,
             "source_values": {"N_RGSEAA": "10.25892/CO"},
             "normalized": {"establishment_id": "10.25892/CO", "address": "address a"}},
        ]
        seen = []
        def lookup(keys):
            seen.extend(keys)
            return [{"results": [], "retrieved_at": "2026-10-25T15:00:00Z",
                     "result_url": "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal.jsp"}]
        enrich_records(rows, limit=1, lookup=lookup)
        self.assertEqual(seen, ["10.25892/CO"])

    def test_activator_creates_fresh_standard_worker_job_and_target_only(self):
        record = event()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.jsonl")
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            connection = _FakeConnection(candidate_rows=[candidate_row()])
            counts = activate("unused", path, limit=1, connect=lambda _: connection)
        self.assertEqual(counts["provider_calls"], 0)
        self.assertEqual(counts["jobs_created"], 1)
        self.assertEqual(counts["targets_created"], 1)
        evidence_call = next(call for call in connection.calls if "INSERT INTO real_preview.spain_verified_locality_evidence" in call[0])
        self.assertEqual(evidence_call[1][5], record["source_record_key"])
        job_call = next(call for call in connection.calls if "INSERT INTO uec.geocode_jobs" in call[0])
        self.assertEqual(job_call[1][1], "ORIGINAL INDUSTRIAL ROAD 7, Test Municipality, Test Province, Spain")
        self.assertTrue(any("INSERT INTO uec.geocode_job_events" in sql for sql, _ in connection.calls))
        self.assertTrue(any("INSERT INTO real_preview.geocode_targets" in sql for sql, _ in connection.calls))
        self.assertFalse(any("UPDATE " in sql or "DELETE " in sql for sql, _ in connection.calls))

    def test_candidate_must_match_registration_hash_and_be_unrestricted(self):
        record = event()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.jsonl")
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            wrong_key = _FakeConnection(candidate_rows=[candidate_row("12.987/CO")])
            result = activate("unused", path, limit=1, connect=lambda _: wrong_key)
            self.assertEqual(result["events_ineligible"], 1)
            wrong_row = _FakeConnection(candidate_rows=[candidate_row(source_record_key_hash="b" * 64)])
            result = activate("unused", path, limit=1, connect=lambda _: wrong_row)
            self.assertEqual(result["events_ineligible"], 1)
            restricted = _FakeConnection(candidate_rows=[candidate_row(restriction_clear=False)])
            result = activate("unused", path, limit=1, connect=lambda _: restricted)
            self.assertEqual(result["events_restricted"], 1)
            self.assertFalse(any("INSERT INTO " in sql for sql, _ in restricted.calls))

    def test_exact_database_guard_stops_before_activation(self):
        record = event()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.jsonl")
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            connection = _FakeConnection(database="wrong_database")
            with self.assertRaisesRegex(RuntimeError, "database_identity_invalid"):
                activate("unused", path, limit=1, connect=lambda _: connection)
        self.assertEqual(len(connection.calls), 1)

    def test_forward_migration_is_append_only_and_keeps_original_location_row_untouched(self):
        sql = (ROOT / "migrations" / "093_spain_verified_locality_evidence.sql").read_text(encoding="utf-8")
        for required in (
            "spain_verified_locality_evidence", "source_id TEXT NOT NULL CHECK (source_id = 'es.locations')",
            "candidate_id UUID NOT NULL", "snapshot_sha256 CHAR(64) NOT NULL",
            "lookup_hash CHAR(64) NOT NULL", "source_record_key_hash CHAR(64) NOT NULL",
            "lookup_url TEXT NOT NULL", "lookup_request_url TEXT NOT NULL",
            "retrieved_at TIMESTAMPTZ NOT NULL", "municipality TEXT NOT NULL", "province TEXT NOT NULL",
            "BEFORE UPDATE OR DELETE", "real_preview.reject_mutation()",
        ):
            with self.subTest(required=required):
                self.assertIn(required, sql)
        self.assertNotIn("ALTER TABLE real_preview.candidate_private_location_evidence", sql)
        self.assertNotIn("UPDATE real_preview.candidate_private_location_evidence", sql)
        self.assertNotIn("DROP TABLE", sql.upper())


if __name__ == "__main__":
    unittest.main()
