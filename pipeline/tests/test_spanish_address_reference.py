"""Bounded reference acquisition and offline exact-match controls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from pipeline.geocoding import spanish_address_reference as reference


def feature(ident="synthetic-1", **changes):
    props = {"inspireId_localId": ident, "inspireId_namespace": "synthetic-reference",
             "component_ThoroughfareName": "Calle Example", "locator_designator_addressNumber": "4",
             "locator_designator_addressNumberExtension": None, "component_PostalDescriptor": "28001",
             "component_AdminUnitName_4": "Example Town", "component_AdminUnitName_3": "Madrid",
             "component_AddressAreaName": None, "beginLifespanVersion": "2026-01-01", "dataProvider": "Test"}
    props.update(changes)
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-3.7, 40.4]}, "properties": props}


class Response:
    def __init__(self, payload, url): self.payload, self.url = json.dumps(payload).encode(), url
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self, size=-1): return self.payload[:size] if size >= 0 else self.payload
    def geturl(self): return self.url


class SpanishAddressReferenceTests(unittest.TestCase):
    def test_projection_requires_numbered_valid_geometry_and_identity(self):
        row = reference.project(feature(locator_designator_addressNumberExtension="A"))
        self.assertEqual(row["house"], "4a")
        self.assertNotIn("component_AddressAreaName", row)
        self.assertIsNone(reference.project(feature(locator_designator_addressNumber="S/N")))
        self.assertIsNone(reference.project(feature(locator_designator_addressNumber="0")))
        bad = feature(); bad["geometry"]["coordinates"] = [True, 40]
        self.assertIsNone(reference.project(bad))
        with self.assertRaises(ValueError): reference.project(feature(inspireId_localId=None))
        top_level = feature(); top_level["id"] = top_level["properties"].pop("inspireId_localId")
        self.assertEqual(reference.project(top_level)["reference_id"], row["reference_id"])

    def test_checkpointed_pagination_reuses_complete_pages_without_network(self):
        seen = []
        def opener(request, **_):
            params = parse_qs(urlsplit(request.full_url).query)
            seen.append(params)
            offset = int(params["offset"][0])
            return Response({"numberMatched": 2, "numberReturned": 1,
                             "features": [feature(f"synthetic-{offset}")]}, request.full_url)
        with tempfile.TemporaryDirectory() as root:
            args = dict(approved_root=root, page_size=1, max_records=2, sleep=lambda _: None)
            rows, report = reference.fetch_municipality("Example Town", Path(root)/"capture", opener=opener, **args)
            self.assertEqual((len(rows), report["source_records"], report["pages"]), (2, 2, 2))
            self.assertFalse(report["facility_addresses_sent"])
            def forbidden(*_, **__): raise AssertionError("cached pages must not call network")
            again, _ = reference.fetch_municipality("Example Town", Path(root)/"capture", opener=forbidden, **args)
            self.assertEqual(rows, again)
            self.assertTrue(all(set(p) <= {"f", "limit", "offset", "component_AdminUnitName_4", "sortby", "properties"} for p in seen))

    def test_reference_count_drift_duplicate_ids_and_ignored_filter_fail(self):
        for problem in ("count", "duplicate", "filter", "empty"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as root:
                def opener(request, **_):
                    offset = int(parse_qs(urlsplit(request.full_url).query)["offset"][0])
                    item = feature("same" if problem == "duplicate" else str(offset))
                    if problem == "filter": item["properties"]["component_AdminUnitName_4"] = "Other Town"
                    rows = [] if problem == "empty" else [item]
                    return Response({"numberMatched": 3 if problem == "count" and offset else 2,
                                     "numberReturned": len(rows), "features": rows}, request.full_url)
                with self.assertRaises(ValueError):
                    reference.fetch_municipality("Example Town", Path(root)/"capture", approved_root=root,
                        page_size=1, max_records=2, opener=opener, sleep=lambda _: None)

    def test_changed_cached_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)/"capture"
            def opener(request, **_):
                return Response({"numberMatched": 1, "numberReturned": 1, "features": [feature()]}, request.full_url)
            reference.fetch_municipality("Example Town", output, approved_root=root, opener=opener, sleep=lambda _: None)
            path = output/"page-00000.json"
            saved = json.loads(path.read_text(encoding="utf-8")); saved["payload"]["features"][0]["geometry"]["coordinates"] = [-4, 41]
            path.write_text(json.dumps(saved), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content_changed"):
                reference.fetch_municipality("Example Town", output, approved_root=root, opener=opener, sleep=lambda _: None)

    def test_small_page_size_cannot_create_an_unbounded_download(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            def opener(request, **_):
                offset = int(parse_qs(urlsplit(request.full_url).query)["offset"][0])
                calls.append(offset)
                return Response({"numberMatched": 14, "numberReturned": 1,
                                 "features": [feature(f"synthetic-{offset}")]}, request.full_url)
            with self.assertRaisesRegex(ValueError, "pagination_incomplete"):
                reference.fetch_municipality("Example Town", Path(root)/"capture", approved_root=root,
                    page_size=1, max_records=14, opener=opener, sleep=lambda _: None)
            self.assertEqual(len(calls), 12)

    def test_exact_matching_rejects_wrong_components_and_ambiguity(self):
        context = {"address": "Calle de Example 4", "locality": "Example Town", "province": "Madrid", "postcode": "28001"}
        primary = [{"case_id": "test", "context": context}]
        row = reference.project(feature())
        self.assertEqual(len(reference.exact_matches(primary, [row])[0]), 1)
        omitted = [{"case_id": "test", "context": {**context, "address": "Example 4"}}]
        self.assertEqual(reference.exact_matches(omitted, [row])[1]["matched"], 1)
        for field, value in (("street", "Calle Other"), ("house", "5"), ("municipality", "Other Town"),
                             ("province", "Sevilla"), ("postcode", "28002")):
            changed = {**row, field: value}
            self.assertEqual(reference.exact_matches(primary, [changed])[1]["matched"], 0)
        duplicate = {**row, "reference_id": ["synthetic-reference", "different"]}
        self.assertEqual(reference.exact_matches(primary, [row, duplicate])[1]["ambiguous"], 1)
        original = copy.deepcopy(primary)
        reference.exact_matches(primary, [row])
        self.assertEqual(primary, original)

    def test_no_number_and_distance_addresses_are_not_exact_reference_matches(self):
        row = reference.project(feature())
        for address in ("Calle Example s/n", "Carretera Example km 4"):
            self.assertEqual(reference.exact_matches([{"case_id": "test", "context": {
                "address": address, "locality": "Example Town", "province": "Madrid"}}], [row])[1]["matched"], 0)


if __name__ == "__main__": unittest.main()
