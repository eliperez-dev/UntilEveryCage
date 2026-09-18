"""Disposable end-to-end rehearsal for the France DGAL private candidate."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

from .fixture import E2EEnvironment
from pipeline.scripts.maintenance.rehearse_candidate_private_frontend import rehearse_candidate
from pipeline.sources.france.refresh import refresh


ROOT = Path(__file__).resolve().parents[3]
IMPORTER = ROOT / "pipeline/scripts/maintenance/import-candidate.py"
FIXTURES = ROOT / "pipeline/sources/france/fixtures"


class FranceCandidateImportE2E(unittest.TestCase):
    """Keep the France golden-country proof private and disposable."""

    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")

        cls.release_id = "candidate-france-e2e"
        cls.env = E2EEnvironment()
        cls.env.test_release_id = cls.release_id
        cls.env = cls.env.start()
        cls.temp = tempfile.TemporaryDirectory(prefix="uec-france-e2e-")
        root = Path(cls.temp.name)
        cls.runs: dict[str, Path] = {}
        cls.summaries: dict[str, dict] = {}

        for section, fixture_name in (("I", "section_i.csv"), ("II", "section_ii.csv")):
            source = FIXTURES / fixture_name
            first_root = root / f"{section.lower()}-first"
            first = refresh(
                section=section,
                raw_path=source,
                run_dir=first_root,
                retrieved_at_utc="2026-09-18T00:00:00Z",
            )
            if first["report"]["lifecycle_status"] != "candidate-ready":
                raise RuntimeError(first)
            first_run = Path(first["report"]["run_dir"])

            second_root = root / f"{section.lower()}-rerun"
            second = refresh(
                section=section,
                raw_path=source,
                run_dir=second_root,
                retrieved_at_utc="2026-09-18T00:00:00Z",
                previous_normalized=first_run / "normalized" / "records.jsonl",
            )
            if second["report"]["lifecycle_status"] != "candidate-ready":
                raise RuntimeError(second)
            run = Path(second["report"]["run_dir"])
            review_diff = json.loads((run / "release-diff.json").read_text(encoding="utf-8"))
            if review_diff.get("status") != "delta-ready":
                raise RuntimeError(f"France {section} rerun was not delta-ready: {review_diff}")

            handoff = run / "candidate-handoff"
            handoff_manifest = json.loads((handoff / "manifest.json").read_text(encoding="utf-8"))
            private_manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            graph_manifest = json.loads((handoff / "graph-candidates" / "manifest.json").read_text(encoding="utf-8"))
            review_packet = json.loads((run / "operator-review-packet.json").read_text(encoding="utf-8"))
            raw = source.read_bytes()
            if handoff_manifest["checksum_sha256"] != hashlib.sha256(raw).hexdigest():
                raise RuntimeError(f"France {section} handoff lost raw provenance")
            if handoff_manifest["byte_size"] != len(raw):
                raise RuntimeError(f"France {section} handoff lost raw byte size")
            if review_packet["row_payloads_included"] is not False:
                raise RuntimeError(f"France {section} operator packet is not row-free")
            if graph_manifest["publication_status"] != "not_eligible":
                raise RuntimeError(f"France {section} graph candidates escaped the publication gate")

            cls.runs[section] = run
            cls.summaries[section] = {
                "input_rows": private_manifest["input_rows"],
                "normalized_rows": private_manifest["normalized_rows"],
                "quarantined_rows": private_manifest["quarantined_rows"],
                "graph_candidate_rows": graph_manifest["candidate_rows"],
            }

        commands = []
        for section in ("I", "II"):
            run = cls.runs[section]
            source = FIXTURES / ("section_i.csv" if section == "I" else "section_ii.csv")
            commands.append([
                sys.executable,
                str(IMPORTER),
                "--manifest",
                str(run / "candidate-handoff" / "manifest.json"),
                "--normalized",
                str(run / "candidate-handoff" / "normalized" / "records.jsonl"),
                "--raw",
                str(source),
                "--release-id",
                cls.release_id,
                "--database-url",
                cls.env.database_url,
                "--disposable-db",
            ])
        for command in commands:
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            if first.returncode or second.returncode:
                raise RuntimeError(
                    f"France candidate import failed:\n{first.stdout}\n{first.stderr}\n"
                    f"rerun:\n{second.stdout}\n{second.stderr}"
                )

        with psycopg.connect(cls.env.database_url) as db:
            cls.imported_counts = db.execute(
                """SELECT
                       (SELECT count(*) FROM uec.source_records WHERE source_id IN ('fr.dgal.section-i','fr.dgal.section-ii')),
                       (SELECT count(*) FROM uec.observations o JOIN uec.source_records s USING (source_record_id)
                          WHERE s.source_id IN ('fr.dgal.section-i','fr.dgal.section-ii')),
                       (SELECT count(*) FROM uec.release_members WHERE release_id=%s),
                       (SELECT count(*) FROM uec.release_members WHERE release_id=%s AND default_visible),
                       (SELECT count(*) FROM uec.observations o JOIN uec.source_records s USING (source_record_id)
                          WHERE s.source_id IN ('fr.dgal.section-i','fr.dgal.section-ii')
                            AND o.coordinate_review_status='review_required')""",
                (cls.release_id, cls.release_id),
            ).fetchone()

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "temp", None):
            cls.temp.cleanup()
        if getattr(cls, "env", None):
            cls.env.stop()

    def request(self, path: str, *, preview: bool = False):
        headers = {"X-UEC-Dev-Preview-Token": self.env.dev_preview_token} if preview else {}
        return urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{self.env.api_port}{path}", headers=headers),
            timeout=10,
        )

    def test_private_lifecycle_counts_and_graphs_are_source_scoped(self) -> None:
        self.assertEqual(self.summaries["I"], {
            "input_rows": 3,
            "normalized_rows": 2,
            "quarantined_rows": 1,
            "graph_candidate_rows": 2,
        })
        self.assertEqual(self.summaries["II"], {
            "input_rows": 2,
            "normalized_rows": 1,
            "quarantined_rows": 1,
            "graph_candidate_rows": 1,
        })
        self.assertEqual(self.imported_counts, (3, 3, 3, 0, 3))

        for section in ("I", "II"):
            run = self.runs[section]
            handoff = json.loads((run / "candidate-handoff" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(handoff["release_state"], "not-created")
            self.assertEqual(handoff["publication_state"], "private-candidate")
            graph = json.loads((run / "candidate-handoff" / "graph-candidates" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(graph["storage_state"], "private")
            self.assertFalse(graph["publication_status"] == "eligible")

    def test_guarded_frontend_api_surfaces_are_private_and_geospatially_unresolved(self) -> None:
        with self.request("/api/v2/locations?profile=official") as response:
            self.assertEqual(json.loads(response.read())["data"], [])

        with self.request(
            "/api/dev/preview/test-release/locations?profile=official&country_code=FR&limit=10",
            preview=True,
        ) as response:
            body = json.loads(response.read())
        self.assertTrue(body["meta"]["test_only"])
        self.assertTrue(body["meta"]["private_preview"])
        self.assertEqual(body["meta"]["release_status"], "candidate")
        self.assertEqual({row["country_code"] for row in body["data"]}, {"FR"})
        self.assertTrue(all(row["display_precision"] == "unmapped" for row in body["data"]))
        self.assertTrue(all(row["latitude"] is None and row["longitude"] is None for row in body["data"]))
        self.assertNotIn("source_values", json.dumps(body))

        aggregate_manifest = Path(self.temp.name) / "france-frontend-candidate.json"
        aggregate_manifest.write_text(json.dumps({
            "publication": {
                "release_created": False,
                "release_promoted": False,
                "project_approval": "not-approved",
            },
            "sources": [
                {
                    "source_id": f"fr.dgal.section-{section.lower()}",
                    "status": "candidate-ready; private only",
                    "candidate_handoff_manifest": str(self.runs[section] / "candidate-handoff" / "manifest.json"),
                }
                for section in ("I", "II")
            ],
        }, indent=2), encoding="utf-8")
        frontend_report = rehearse_candidate(
            aggregate_manifest,
            root=Path(self.temp.name),
            base_url=f"http://127.0.0.1:{self.env.api_port}",
            token=self.env.dev_preview_token,
        )
        self.assertEqual(frontend_report["status"], "passed")
        self.assertEqual(frontend_report["frontend_preview"]["state"], "passed")
        self.assertFalse(frontend_report["private_payloads_included"])

        with self.request("/api/dev/preview/test-release/discovery/facets?profile=official", preview=True) as response:
            facets = json.loads(response.read())
        self.assertIn("FR", {item["value"] for item in facets["dimensions"]["country_code"]})
        self.assertNotIn("source_values", json.dumps(facets))

        with self.request("/api/dev/preview/test-release/locations.csv?profile=official", preview=True) as response:
            export = response.read().decode("utf-8")
            disposition = response.headers.get("Content-Disposition", "")
        self.assertIn("test_only", export)
        self.assertIn(",FR,", export)
        self.assertNotIn("source_values", export)
        self.assertIn("uec-test-only", disposition)

    def test_suppression_relocks_all_private_surfaces(self) -> None:
        with psycopg.connect(self.env.database_url) as db:
            record, facility = db.execute(
                """SELECT s.source_record_id, o.facility_id
                   FROM uec.source_records s JOIN uec.observations o USING (source_record_id)
                   WHERE s.source_id='fr.dgal.section-i' ORDER BY s.source_record_key LIMIT 1"""
            ).fetchone()
            db.execute(
                """INSERT INTO uec.record_access_events
                   (source_record_id,action,reason_category,policy_version,maintainer)
                   VALUES (%s,'public_access_revoked','privacy','ethics-v1','authorized-synthetic-operator')""",
                (record,),
            )

        with self.request("/api/dev/preview/test-release/locations?profile=official&country_code=FR&limit=10", preview=True) as response:
            listed = json.loads(response.read())
        self.assertNotIn(str(facility), {str(row["facility_id"]) for row in listed["data"]})
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(f"/api/dev/preview/test-release/locations/{facility}?profile=official", preview=True)
        self.assertIn(error.exception.code, (404, 410))
        with self.request("/api/dev/preview/test-release/locations.csv?profile=official", preview=True) as response:
            export = response.read().decode("utf-8")
        self.assertNotIn(str(facility), export)
        with self.request("/api/v2/locations?profile=official") as response:
            self.assertEqual(json.loads(response.read())["data"], [])


if __name__ == "__main__":
    unittest.main()
