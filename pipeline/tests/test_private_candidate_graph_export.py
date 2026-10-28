from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from pipeline.common.release_cohort_review import canonical_sha256


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "pipeline" / "scripts" / "export_private_graph_handoffs.py"
SPEC = importlib.util.spec_from_file_location("private_graph_export_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


def member_row(*, restricted: bool = False):
    return (
        "release-2026-10-27-r2", "facility-1", "observation-1", "record-1",
        "de.locations", "artifact-1", "a" * 64,
        {"taxonomy_version": "uec-taxonomy-v1", "assignments": []},
        "native-key-1", {"normalized": {"country_code": "DE", "facility_id": "native-key-1"}},
        {"native": "value"}, "2026-10-27T00:00:00+00:00", "2026-10-27T00:00:00+00:00", restricted,
    )


class FakeCursor:
    def __init__(self, rows, *, export_order=False):
        self.rows = list(rows)
        self.export_order = export_order
        self.query = None
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params
        if self.export_order and "ORDER BY record.source_id, artifact.sha256, record.source_record_key," in query:
            self.rows.sort(key=lambda row: (row[0], row[4], row[1]))

    def __iter__(self):
        return iter(self.rows)


class FakeConnection:
    def __init__(self, rows, release_summary):
        self.rows = rows
        self.export_rows = [
            (row[4], row[8], row[9], row[10], row[6], row[11], row[12], row[13]) for row in rows
        ]
        self.release_summary = release_summary
        self.executed = []
        self.cursor_value = None
        self.rolled_back = False
        self.closed = False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if query.startswith("SET TRANSACTION"):
            return self
        if query == "SELECT current_database()":
            return FakeResult(("uec_country_release_test_20261027",))
        if "FROM uec.releases" in query:
            return FakeResult(("candidate", "official", False, "v0-candidate-freeze-v1", self.release_summary))
        if "count(*) FROM uec.release_members" in query:
            return FakeResult((len(self.rows),))
        raise AssertionError("unexpected SQL in synthetic test")

    def cursor(self, name=None):
        if name == "uec_frozen_candidate_membership_verify":
            self.cursor_value = FakeCursor(self.rows)
        else:
            assert name == "uec_frozen_candidate_graph_export"
            self.cursor_value = FakeCursor(self.export_rows, export_order=True)
        return self.cursor_value

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FrozenCandidateExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data" / "reports").mkdir(parents=True)
        (self.root / "data" / "staging").mkdir(parents=True)
        self.freeze_path = self.root / "data" / "reports" / "freeze.json"
        self.review_path = self.root / "data" / "reports" / "review.json"
        self.output = self.root / "data" / "staging" / "candidate-graph"
        self.freeze = {
            "schema_version": "v0-candidate-freeze-v1",
            "release_id": "v0-candidate-country-2026-10-27",
            "inventory_sha256": "b" * 64,
            "selected_sources": [{"source_id": "de.locations", "source_artifact_sha256": "a" * 64}],
        }
        self.review = {
            "schema_version": "uec-release-cohort-review-v1",
            "release_id": "release-2026-10-27-r2",
            "profile": "official",
            "ruleset_version": "v0-candidate-freeze-v1",
            "freeze_sha256": canonical_sha256({**self.freeze, "release_id": "release-2026-10-27"}),
            "inventory_sha256": "b" * 64,
            "member_count": 1,
            "member_sha256": "",
        }

    def _write_controls(self, rows):
        payload = hashlib.sha256()
        for row in rows:
            payload.update(EXPORTER._member_payload(list(row[:8])))
        self.review["member_count"] = len(rows)
        self.review["member_sha256"] = payload.hexdigest()
        self.freeze_path.write_text(json.dumps(self.freeze), encoding="utf-8")
        self.review_path.write_text(json.dumps(self.review), encoding="utf-8")

    def _run(self, rows, *, expected_member_sha=None, real_writer=False):
        self._write_controls(rows)
        if expected_member_sha is not None:
            self.review["member_sha256"] = expected_member_sha
            self.review_path.write_text(json.dumps(self.review), encoding="utf-8")
        release_summary = {
            "candidate_only": True,
            "freeze_sha256": self.review["freeze_sha256"],
            "inventory_sha256": self.review["inventory_sha256"],
            "selected_sources": sorted({row[4] for row in rows}),
            "replacement_sources": ["de.locations"],
        }
        connection = FakeConnection(rows, release_summary)
        captured = {}

        def write_source(export_rows, output_root, *, scope, source_urls):
            captured["rows"] = list(export_rows)
            captured["scope"] = scope
            return {"scope": scope, "sources": {}, "total_candidates": len(captured["rows"])}

        patches = [
            mock.patch.object(EXPORTER.Path, "cwd", return_value=self.root),
            mock.patch.object(EXPORTER.psycopg, "connect", return_value=connection),
            mock.patch.object(EXPORTER, "_source_urls", return_value={"de.locations": "https://source.invalid"}),
        ]
        if real_writer:
            patches.extend([
                mock.patch.object(EXPORTER, "source_identifier", return_value={"identifier_type": "test", "value": "key"}),
                mock.patch.object(EXPORTER, "build_graph_candidate", side_effect=lambda record, **kwargs: {
                    "source_id": record["source_id"], "source_record_key": record["source_record_key"],
                    "facilities": [], "organizations": [], "name_assertions": [],
                }),
                mock.patch.object(EXPORTER, "validate_graph_candidate"),
                mock.patch.object(EXPORTER, "canonical_json_bytes", side_effect=lambda value: (json.dumps(value) + "\n").encode()),
            ])
        else:
            patches.append(mock.patch.object(EXPORTER, "_write_source", side_effect=write_source))
            patches.append(mock.patch.object(EXPORTER, "_verify_candidate_export", side_effect=lambda _root, groups: sum(groups.values())))
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            try:
                result = EXPORTER.export_frozen_candidate(
                    "postgresql://user:secret@127.0.0.1/uec_country_release_test_20261027",
                    expected_database="uec_country_release_test_20261027",
                    release_id="release-2026-10-27-r2", freeze_path=self.freeze_path,
                    review_path=self.review_path, output_root=self.output,
                )
            except EXPORTER.CandidateExportError as error:
                if real_writer and error.category == "candidate_export_failed" and error.__context__:
                    raise error.__context__
                raise
        return result, connection, captured

    def test_exports_only_unrestricted_exact_release_rows_and_writes_row_free_receipt(self):
        rows = [member_row(), member_row(restricted=True)]
        self._write_controls(rows)
        # Keep distinct member identities while retaining all other synthetic fields.
        rows[1] = (*rows[1][:3], "record-2", *rows[1][4:])
        self._write_controls(rows)
        result, connection, captured = self._run(rows)

        self.assertEqual(result["member_count"], 2)
        self.assertEqual(result["restricted_member_count_excluded"], 1)
        self.assertEqual(result["exported_member_count"], 1)
        self.assertEqual(captured["scope"], "frozen-candidate-membership")
        self.assertEqual(len(captured["rows"]), 1)
        self.assertEqual(captured["rows"][0][1], "native-key-1")
        self.assertEqual(connection.cursor_value.params, ("release-2026-10-27-r2",))
        self.assertIn("WHERE member.release_id=%s", connection.cursor_value.query)
        self.assertNotIn("ranked_current", connection.cursor_value.query)
        receipt = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["member_sha256"], self.review["member_sha256"])
        self.assertEqual(receipt["release"]["total_candidates"], 1)

    def test_member_digest_mismatch_fails_without_final_output(self):
        row = member_row()
        with self.assertRaisesRegex(EXPORTER.CandidateExportError, "candidate_member_hash_mismatch"):
            self._run([row], expected_member_sha="c" * 64)
        self.assertFalse(self.output.exists())

    def test_exports_full_candidate_scope_not_only_replacement_sources(self):
        first = member_row()
        second = list(member_row())
        second[0] = "release-2026-10-27-r2"
        second[1] = "facility-legacy"
        second[2] = "observation-legacy"
        second[3] = "record-legacy"
        second[4] = "legacy.source"
        second[5] = "artifact-legacy"
        second[6] = "d" * 64
        second[8] = "legacy-native-key"
        result, _, captured = self._run([first, tuple(second)])

        self.assertEqual(result["exported_member_count"], 2)
        self.assertEqual({row[0] for row in captured["rows"]}, {"de.locations", "legacy.source"})

    def test_interleaved_members_are_exported_in_source_artifact_order_without_truncation(self):
        de_first = list(member_row())
        de_first[1], de_first[2], de_first[3], de_first[8] = "facility-de-1", "obs-de-1", "rec-de-1", "de-key-1"
        legacy = list(member_row())
        legacy[1], legacy[2], legacy[3], legacy[4], legacy[5], legacy[6], legacy[8] = (
            "facility-legacy", "obs-legacy", "rec-legacy", "legacy.source", "legacy-artifact", "d" * 64,
            "legacy-key",
        )
        de_second = list(member_row())
        de_second[1], de_second[2], de_second[3], de_second[8] = "facility-de-2", "obs-de-2", "rec-de-2", "de-key-2"
        result, connection, _ = self._run([tuple(de_first), tuple(legacy), tuple(de_second)], real_writer=True)

        self.assertEqual(result["exported_member_count"], 3)
        self.assertEqual(connection.cursor_value.query, EXPORTER._CANDIDATE_EXPORT_SQL)
        released = self.output / "released"
        manifests = sorted(released.rglob("manifest.json"))
        self.assertEqual(len(manifests), 2)
        grouped_counts = {}
        for manifest_path in manifests:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            grouped_counts[manifest["source_id"]] = manifest["candidate_count"]
            records = manifest_path.parent / "graph-candidates.jsonl"
            self.assertEqual(len(records.read_text(encoding="utf-8").splitlines()), manifest["candidate_count"])
        self.assertEqual(grouped_counts, {"de.locations": 2, "legacy.source": 1})

    def test_database_must_be_exact_loopback_candidate_database(self):
        with self.assertRaisesRegex(EXPORTER.CandidateExportError, "candidate_database_mismatch"):
            EXPORTER._validate_candidate_database_url(
                "postgresql://user:secret@127.0.0.1/uec_graph_repair_test_20261022",
                "uec_graph_repair_test_20261022",
            )
        with self.assertRaisesRegex(EXPORTER.CandidateExportError, "candidate_database_mismatch"):
            EXPORTER._validate_candidate_database_url(
                "postgresql://user:secret@example.invalid/uec_country_release_test_20261027",
                "uec_country_release_test_20261027",
            )
        with self.assertRaisesRegex(EXPORTER.CandidateExportError, "candidate_database_mismatch"):
            EXPORTER._validate_candidate_database_url(
                "postgresql://user:secret@127.0.0.1/uec_country_release_test_20261027?host=remote.invalid",
                "uec_country_release_test_20261027",
            )

    def test_existing_output_is_never_overwritten(self):
        self._write_controls([member_row()])
        self.output.mkdir()
        with mock.patch.object(EXPORTER.Path, "cwd", return_value=self.root):
            with self.assertRaisesRegex(EXPORTER.CandidateExportError, "candidate_output_must_be_new"):
                EXPORTER._candidate_paths(self.freeze_path, self.review_path, self.output)

    def test_freeze_hash_mismatch_is_rejected_before_database_connection(self):
        self._write_controls([member_row()])
        self.review["freeze_sha256"] = "e" * 64
        self.review_path.write_text(json.dumps(self.review), encoding="utf-8")
        with (
            mock.patch.object(EXPORTER.Path, "cwd", return_value=self.root),
            mock.patch.object(EXPORTER.psycopg, "connect") as connect,
        ):
            with self.assertRaisesRegex(EXPORTER.CandidateExportError, "candidate_control_hash_mismatch"):
                EXPORTER.export_frozen_candidate(
                    "postgresql://user:secret@127.0.0.1/uec_country_release_test_20261027",
                    expected_database="uec_country_release_test_20261027",
                    release_id="release-2026-10-27-r2", freeze_path=self.freeze_path,
                    review_path=self.review_path, output_root=self.output,
                )
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
