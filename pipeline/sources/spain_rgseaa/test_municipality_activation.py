"""Focused tests for the append-only Spain municipality queue lane."""
from __future__ import annotations

import unittest
from pathlib import Path

from .municipality_activation import PROFILE_ID, activate


def evidence_row(*, evidence_id="evidence-current", candidate_id="candidate-1", snapshot="snapshot-current",
                 country="ES", location_class="unmapped_private_observation", map_scope=True,
                 evidence_country="ES", restriction_clear=True, municipality="Test Municipality",
                 province="Test Province", artifact_sha="a" * 64, artifact_id="artifact-1"):
    return (evidence_id,candidate_id,snapshot,"source-group-1",municipality,province,artifact_sha,
            artifact_id,country,location_class,map_scope,evidence_country,restriction_clear)


class _Result:
    def __init__(self, one=None, many=None):
        self.one = one
        self.many = list(many or [])

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class _FakeConnection:
    def __init__(self, *, database="uec_launch_sources_test_20261025", profile=True,
                 rows=None, restricted_source_records=()):
        self.database = database
        self.profile = profile
        self.rows = list(rows or [])
        self.restricted_source_records = set(restricted_source_records)
        self.source_records = {}
        self.jobs = {}
        self.targets = set()
        self.queued_jobs = set()
        self.calls = []

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def transaction(self): return self

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized,params))
        if normalized == "SELECT current_database()":
            return _Result((self.database,))
        if "FROM real_preview.private_geocoding_source_profiles" in normalized:
            return _Result((1,) if self.profile else None)
        if "WITH latest AS" in normalized:
            return _Result(many=self.rows)
        if normalized.startswith("INSERT INTO uec.source_records"):
            key = (params[0],params[1],params[2])
            if key in self.source_records:
                return _Result()
            source_record_id = f"source-record-{len(self.source_records)+1}"
            self.source_records[key] = source_record_id
            return _Result((source_record_id,))
        if normalized.startswith("SELECT source_record_id FROM uec.source_records"):
            return _Result((self.source_records.get(tuple(params)),))
        if normalized.startswith("SELECT 1 FROM uec.public_access_restricted"):
            return _Result((1,) if params[0] in self.restricted_source_records else None)
        if normalized.startswith("INSERT INTO uec.geocode_jobs"):
            key = (params[0],"geoapify",params[1])
            if key in self.jobs:
                return _Result()
            job_id = f"job-{len(self.jobs)+1}"
            self.jobs[key] = job_id
            return _Result((job_id,))
        if normalized.startswith("SELECT job_id FROM uec.geocode_jobs"):
            return _Result((self.jobs.get((params[0],"geoapify",params[1])),))
        if normalized.startswith("INSERT INTO real_preview.geocode_targets"):
            key = (params[0],params[1],params[2],params[3],params[4])
            if key in self.targets:
                return _Result()
            self.targets.add(key)
            return _Result((params[1],))
        if normalized.startswith("INSERT INTO uec.geocode_job_events"):
            self.queued_jobs.add(params[0])
        return _Result()


class SpainMunicipalityActivationTests(unittest.TestCase):
    def test_rejects_wrong_database_before_any_other_work(self):
        connection = _FakeConnection(database="wrong_database", rows=[evidence_row()])
        with self.assertRaisesRegex(RuntimeError,"database_identity_invalid"):
            activate("unused",connect=lambda *_args,**_kwargs:connection)
        self.assertEqual(len(connection.calls),1)

    def test_requires_exact_enabled_spain_profile(self):
        connection = _FakeConnection(profile=False,rows=[evidence_row()])
        with self.assertRaisesRegex(RuntimeError,"spain_verified_municipality_profile_unavailable"):
            activate("unused",connect=lambda *_args,**_kwargs:connection)
        self.assertEqual(len(connection.calls),2)
        self.assertEqual(connection.source_records,{})

    def test_missing_verified_evidence_creates_no_rows(self):
        connection = _FakeConnection(rows=[])
        counts = activate("unused",connect=lambda *_args,**_kwargs:connection)
        self.assertEqual(counts,{"evidence_available":0,"evidence_ineligible":0,
                                 "jobs_created":0,"targets_created":0,"provider_calls":0})
        self.assertEqual(connection.source_records,{})

    def test_queues_only_eligible_verified_evidence_and_calls_no_provider(self):
        rows = [
            evidence_row(),
            evidence_row(evidence_id="other-country",candidate_id="candidate-2",country="PT"),
            evidence_row(evidence_id="mapped",candidate_id="candidate-3",location_class="city_postal"),
            evidence_row(evidence_id="not-default-map",candidate_id="candidate-4",map_scope=False),
            evidence_row(evidence_id="location-country",candidate_id="candidate-5",evidence_country="PT"),
            evidence_row(evidence_id="restricted",candidate_id="candidate-6",restriction_clear=False),
            evidence_row(evidence_id="comma",candidate_id="candidate-7",municipality="Town, District"),
            evidence_row(evidence_id="no-artifact",candidate_id="candidate-8",artifact_id=None),
        ]
        connection = _FakeConnection(rows=rows)
        counts = activate("unused",connect=lambda *_args,**_kwargs:connection)
        self.assertEqual(counts,{"evidence_available":8,"evidence_ineligible":7,
                                 "jobs_created":1,"targets_created":1,"provider_calls":0})
        query_call = next(params for sql,params in connection.calls if sql.startswith("INSERT INTO uec.geocode_jobs"))
        self.assertEqual(query_call[1],"Test Municipality, Test Province, Spain")
        self.assertNotIn("ORIGINAL INDUSTRIAL ADDRESS",str(connection.calls))
        self.assertNotIn("business_name",str(connection.calls))
        queued = next(params for sql,params in connection.calls if sql.startswith("INSERT INTO uec.geocode_job_events"))
        self.assertIn(PROFILE_ID,queued[1])
        self.assertIn("evidence-current",queued[1])
        restriction_sql = next(sql for sql,_ in connection.calls if "AS restriction_clear" in sql)
        self.assertIn("FROM real_preview.geocode_targets",restriction_sql)
        self.assertNotIn("FROM uec.geocode_targets",restriction_sql)

    def test_restricted_new_source_record_is_not_queued(self):
        connection = _FakeConnection(rows=[evidence_row()],restricted_source_records={"source-record-1"})
        counts = activate("unused",connect=lambda *_args,**_kwargs:connection)
        self.assertEqual(counts["evidence_ineligible"],1)
        self.assertEqual(counts["jobs_created"],0)
        self.assertEqual(counts["targets_created"],0)
        self.assertEqual(counts["provider_calls"],0)

    def test_queue_activation_is_idempotent(self):
        connection = _FakeConnection(rows=[evidence_row()])
        connect = lambda *_args,**_kwargs:connection
        first = activate("unused",connect=connect)
        second = activate("unused",connect=connect)
        self.assertEqual((first["jobs_created"],first["targets_created"]),(1,1))
        self.assertEqual((second["jobs_created"],second["targets_created"]),(0,0))
        self.assertEqual((first["provider_calls"],second["provider_calls"]),(0,0))
        self.assertEqual(len(connection.source_records),1)
        self.assertEqual(len(connection.jobs),1)
        self.assertEqual(len(connection.targets),1)
        self.assertEqual(len(connection.queued_jobs),1)

    def test_latest_evidence_is_selected_once_per_candidate_and_binds_display_trigger(self):
        connection = _FakeConnection(rows=[evidence_row()])
        activate("unused",connect=lambda *_args,**_kwargs:connection)
        selection_sql = next(sql for sql,_ in connection.calls if "WITH latest AS" in sql)
        self.assertIn("DISTINCT ON (evidence.candidate_id)",selection_sql)
        self.assertIn("ORDER BY evidence.candidate_id,evidence.retrieved_at DESC,evidence.evidence_event_id DESC",
                      selection_sql)
        self.assertIn("JOIN latest USING(snapshot_sha256)",selection_sql)
        migration = (Path(__file__).parents[2] / "migrations" /
                     "094_spain_verified_municipality_geocoding.sql").read_text(encoding="utf-8")
        self.assertIn("queued.details->>'locality_evidence_event_id'=evidence.evidence_event_id::text",migration)
        self.assertIn("FROM real_preview.spain_verified_locality_evidence newer",migration)
        self.assertIn("newer.evidence_event_id)",migration)


if __name__ == "__main__":
    unittest.main()
