import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.sources.australia.npi import (
    ADAPTER_VERSION, CATALOG_URL, LICENSE_TITLE, LICENSE_URL, RESOURCE_ID,
    RESOURCE_URL, SCHEMA_VERSION, NpiFacilitiesAdapter, SOURCE_ID, SOURCE_URL, fetch,
)


ROOT = Path(__file__).parent
FIXTURE = ROOT / "fixtures" / "npi_facilities.csv"
TERMS_REVIEW = ROOT.parents[2] / "data" / "terms-reviews" / "au.npi.facilities.json"


def artifact_for(raw: bytes) -> SourceArtifact:
    return SourceArtifact(
        source_url=SOURCE_URL,
        retrieved_at_utc="2026-09-22T00:00:00Z",
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        code_version=ADAPTER_VERSION,
        config_version=SCHEMA_VERSION,
        rights_caveat="synthetic fixture; source terms remain a human gate",
        privacy_caveat="private staging; privacy review required",
        coverage="NPI reporting facilities; no completeness claim",
    )


class NpiAdapterTests(unittest.TestCase):
    def test_fixture_parses_coordinates_and_quarantines_bad_identity_and_point(self):
        result = NpiFacilitiesAdapter().parse_bytes(FIXTURE.read_bytes())
        self.assertEqual(result["input_rows"], 5)
        self.assertEqual(len(result["accepted"]), 4)
        self.assertEqual(len(result["quarantined"]), 1)
        self.assertEqual(result["accepted"][0]["normalized"]["coordinate_state"], "source-coordinate")
        self.assertEqual(result["accepted"][0]["normalized"]["coordinates"], {
            "latitude": -32.9283, "longitude": 151.7817, "precision": "source-provided",
            "method": "source_coordinates", "provider": "Australian National Pollutant Inventory",
            "confidence": "high_source_reported_location",
        })
        self.assertEqual(result["accepted"][0]["normalized"]["address"], "1 Example Road")
        self.assertEqual(result["accepted"][0]["normalized"]["address_state"], "source-reported-facility-address")
        self.assertTrue(result["accepted"][0]["normalized"]["in_default_map_scope"])
        self.assertEqual(result["accepted"][0]["source_values"]["latitude"], "-32.9283")
        self.assertEqual(result["accepted"][2]["normalized"]["coordinate_state"], "not-supplied-by-source")
        self.assertFalse(result["accepted"][2]["normalized"]["in_default_map_scope"])
        self.assertEqual(result["accepted"][3]["normalized"]["coordinate_state"], "invalid-source-coordinate")
        self.assertTrue(result["accepted"][3]["normalized"]["address"])
        reasons = {reason for item in result["quarantined"] for reason in item["reasons"]}
        self.assertEqual(reasons, {"missing_facility_id"})

    def test_missing_column_is_schema_drift(self):
        raw = FIXTURE.read_bytes().replace(b",reports\r\n", b"\r\n", 1)
        with self.assertRaisesRegex(ValueError, "schema drift"):
            NpiFacilitiesAdapter().parse_bytes(raw)

    def test_industry_codes_remain_source_claims_not_operation_facts(self):
        result = NpiFacilitiesAdapter().parse_bytes(FIXTURE.read_bytes())
        poultry = result["accepted"][2]["normalized"]
        meat = result["accepted"][0]["normalized"]
        self.assertEqual(poultry["animal_relevance"], "poultry-meat-farming-industry-candidate")
        self.assertEqual(poultry["activity_categories"], ["animal_production"])
        self.assertEqual(poultry["operation_state"], "unknown; NPI reporting does not prove current operation")
        self.assertEqual(meat["animal_relevance"], "meat-processing-industry-candidate")
        self.assertEqual(meat["activity_categories"], ["processing"])
        self.assertEqual(meat["privacy_gate"], "pending-review")
        self.assertEqual(meat["coordinate_gate"], "source-coordinate")
        self.assertTrue(meat["in_default_map_scope"])
        self.assertIsNotNone(meat["coordinates"])

    def test_animal_industry_codes_are_scoped_and_mines_are_not(self):
        raw = FIXTURE.read_bytes().replace(b"1111,Meat processing", b"1090,Metal ore mining", 1)
        mined = NpiFacilitiesAdapter().parse_bytes(raw)["accepted"][0]["normalized"]
        self.assertEqual(mined["activity_categories"], [])
        self.assertFalse(mined["in_default_map_scope"])
        self.assertEqual(mined["map_scope_reason"], "outside_animal_industry_scope")
        pig_raw = FIXTURE.read_bytes().replace(b"1111,Meat processing", b"0192,Pig farming", 1)
        pig = NpiFacilitiesAdapter().parse_bytes(pig_raw)["accepted"][0]["normalized"]
        self.assertEqual(pig["activity_categories"], ["animal_production"])
        self.assertTrue(pig["in_default_map_scope"])

    def test_anzsic_scope_matches_official_animal_classes(self):
        from pipeline.sources.australia.npi import ANZSIC_ANIMAL_RELEVANCE
        from pipeline.taxonomy_crosswalk import project_observation
        for code in ANZSIC_ANIMAL_RELEVANCE:
            with self.subTest(code=code):
                projected = project_observation({"source_id": SOURCE_ID, "normalized": {
                    "primary_anzsic_class_code": code}})
                self.assertEqual(projected["taxonomy_mapping_status"], "mapped")
        for code in ("0146", "0149", "1711", "1411", "0804"):
            with self.subTest(code=code):
                raw = FIXTURE.read_bytes().replace(b"1111,Meat processing", (code + ",Non-animal industry").encode(), 1)
                normalized = NpiFacilitiesAdapter().parse_bytes(raw)["accepted"][0]["normalized"]
                self.assertFalse(normalized["in_default_map_scope"])

    def test_live_fetch_checks_official_catalogue_and_records_immutable_provenance(self):
        raw = FIXTURE.read_bytes()
        catalog = {
            "success": True,
            "result": {
                "id": "043f58e0-a188-4458-b61c-04e5b540aea4",
                "title": "National Pollutant Inventory",
                "license_title": LICENSE_TITLE,
                "license_url": LICENSE_URL,
                "metadata_modified": "2026-09-27T00:00:00Z",
                "resources": [{"id": RESOURCE_ID, "name": "Facilities", "format": "CSV", "url": RESOURCE_URL,
                               "last_modified": "2026-03-31T07:24:23Z", "size": len(raw)}],
            },
        }

        class Response(io.BytesIO):
            status = 200
            def __init__(self, body, url, content_type):
                super().__init__(body)
                self._url = url
                self.headers = {"Content-Type": content_type, "ETag": '"fixture"'}
            def geturl(self):
                return self._url

        class Opener:
            def __init__(self, payloads):
                self.payloads = payloads
                self.requests = []
            def urlopen(self, request, timeout):
                url = request.full_url
                self.requests.append(url)
                body, content_type = self.payloads[url]
                return Response(body, url, content_type)

        payloads = {
            CATALOG_URL: (json.dumps(catalog).encode(), "application/json"),
            RESOURCE_URL: (raw, "text/csv; charset=utf-8"),
        }
        opener = Opener(payloads)
        directory = Path(tempfile.mkdtemp(prefix="uec-au-npi-fetch-"))
        try:
            metadata = fetch(output_root=directory, run_id="fetch-test-001",
                             terms_review_path=TERMS_REVIEW,
                             opener=opener)
            artifact = Path(metadata["artifact_path"])
            self.assertEqual(artifact.read_bytes(), raw)
            self.assertEqual(metadata["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(metadata["license"], LICENSE_TITLE)
            self.assertEqual(metadata["retrieved_at_utc"].endswith("Z"), True)
            self.assertEqual(len(opener.requests), 2)
            with self.assertRaisesRegex(FileExistsError, "already exists"):
                fetch(output_root=directory, run_id="fetch-test-001",
                      terms_review_path=TERMS_REVIEW,
                      opener=opener)
            self.assertEqual(len(opener.requests), 2)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_private_lifecycle_is_deterministic_and_private(self):
        raw = FIXTURE.read_bytes()
        directory = Path(tempfile.mkdtemp(prefix="uec-e2-npi-adapter-"))
        try:
            result = run_private_lifecycle(FIXTURE, directory / "run", artifact_for(raw), NpiFacilitiesAdapter())
            self.assertEqual(result["status"], "candidate-ready")
            manifest = json.loads((Path(result["run_dir"]) / "manifest.json").read_text())
            self.assertEqual(manifest["source_id"], SOURCE_ID)
            self.assertEqual(manifest["input_rows"], 5)
            self.assertEqual(manifest["normalized_rows"], 4)
            self.assertEqual(manifest["quarantined_rows"], 1)
            self.assertEqual(manifest["geocode_queue"]["records_queued"], 2)
            self.assertEqual(manifest["geocode_queue"]["records_with_source_coordinates"], 2)
            queue_path = Path(result["run_dir"]) / "geocode-queue" / "geocode-queue.jsonl"
            queue_rows = [json.loads(line) for line in queue_path.read_text().splitlines()]
            self.assertTrue(all(item["status"] == "pending-provider-configuration" for item in queue_rows))
            self.assertTrue(any("Example Crescent" in item["geocoder_query"] for item in queue_rows))
            self.assertTrue(all("Synthetic" not in item["geocoder_query"] for item in queue_rows))
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertFalse(manifest.get("published", False))
        finally:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
