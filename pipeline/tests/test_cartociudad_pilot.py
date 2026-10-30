import copy
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from pipeline.geocoding import cartociudad_pilot as pilot


def context():
    return {"address": "Calle Example 4", "locality": "Example Town",
            "postcode": "28001", "province": "Madrid", "country_code": "ES"}


def candidate(**changes):
    return {"id": "synthetic-1", "type": "portal", "address": "CALLE EXAMPLE 4",
            "tip_via": "CALLE", "portalNumber": 4, "extension": "", "noNumber": False,
            "muni": "Example Town", "province": "Madrid", "postalCode": "28001",
            "countryCode": "011", "lat": 40.2, "lng": -3.1, **changes}


class CartociudadPilotTests(unittest.TestCase):
    def test_only_authorized_fields_are_sent(self):
        self.assertEqual(set(pilot.parameters(context())), {"q", "countrycodes", "limit"})
        for changes in ({"business_name": "Forbidden"}, {"country_code": "GB"},
                        {"locality": ""}, {"province": None}, {"postcode": True}):
            with self.assertRaises(ValueError):
                pilot.parameters({**context(), **changes})

    def test_exact_numbered_address_and_ambiguity(self):
        original = candidate()
        self.assertEqual(pilot.evaluate(context(), [original])["status"], "matched")
        self.assertEqual(pilot.evaluate(context(), [original, candidate(id="synthetic-2")])["status"], "ambiguous")
        self.assertEqual(original, candidate())

    def test_query_styles_change_only_transport_not_source_matching(self):
        source = context()
        self.assertEqual(pilot.parameters(source, query_style="address_town")["q"],
                         "calle example 4 Example Town")
        filtered = pilot.parameters(source, query_style="geographic_filters")
        self.assertEqual(filtered["q"], "calle example 4")
        self.assertEqual(filtered["municipio_filter"], source["locality"])
        self.assertEqual(filtered["cod_postal_filter"], source["postcode"])
        self.assertEqual(source, context())

    def test_component_conflicts_cannot_be_hidden_by_candidate_rank(self):
        for change in ({"address": "CALLE OTHER 4"}, {"portalNumber": 5},
                       {"address": "CALLE EXAMPLE 5", "portalNumber": 5},
                       {"extension": "A"}, {"muni": "Other Town"}, {"province": "Toledo"},
                       {"postalCode": "28002"}, {"noNumber": True}, {"type": "callejero"},
                       {"countryCode": "GB"}, {"lat": float("nan")}, {"lng": True}, {"lat": 0}):
            with self.subTest(change=change):
                self.assertEqual(pilot.evaluate(context(), [candidate(**change)])["status"], "unmatched")

    def test_projection_omits_unneeded_fields_and_transport_is_bounded(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def geturl(self): return pilot.ENDPOINT
            def read(self, size):
                return json.dumps([candidate(contact="omit", refCatastral="omit", arbitrary="omit")]).encode()[:size]
        def opener(request, timeout):
            self.assertEqual(set(parse_qs(urlsplit(request.full_url).query)), {"q", "countrycodes", "limit"})
            return Response()
        rows, digest = pilot.fetch(context(), opener=opener)
        self.assertNotIn("contact", rows[0])
        self.assertNotIn("refCatastral", rows[0])
        self.assertEqual(len(digest), 64)

    def test_resume_does_not_repeat_requests_and_changed_plan_is_rejected(self):
        cases = [{"context": context(), "targets": [{"candidate_id": "synthetic"}]}]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"pilot"
            def offline(*_a, **_k): raise OSError("synthetic failure")
            first = pilot.run(cases, output, approved_root=directory, opener=offline, sleep=lambda _: None)
            self.assertEqual(first["outcomes"], {"request_failed": 1})
            def forbidden(*_a, **_k): raise AssertionError("must not send again")
            self.assertEqual(pilot.run(cases, output, approved_root=directory,
                opener=forbidden, sleep=lambda _: None), first)
            changed = copy.deepcopy(cases)
            changed[0]["context"]["address"] = "Calle Other 4"
            with self.assertRaisesRegex(ValueError, "plan_changed"):
                pilot.run(changed, output, approved_root=directory, opener=forbidden)

    def test_scope_is_capped_before_any_request(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "scope_invalid"):
                pilot.run([{"context": context()}]*25, Path(directory)/"pilot", approved_root=directory)

    def test_cross_origin_redirect_is_rejected_before_following_it(self):
        for url in ("https://example.invalid/elsewhere", "http://www.cartociudad.es/geocoder"):
            with self.assertRaisesRegex(ValueError, "redirect_out_of_scope"):
                pilot._SameOriginRedirect().redirect_request(None, None, 302, "redirect", {}, url)

    def test_interrupted_request_is_not_repeated(self):
        cases = [{"context": context()}]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"pilot"
            def interrupted(*_a, **_k): raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                pilot.run(cases, output, approved_root=directory, opener=interrupted, sleep=lambda _: None)
            def forbidden(*_a, **_k): raise AssertionError("must not retry an interrupted call")
            report = pilot.run(cases, output, approved_root=directory, opener=forbidden, sleep=lambda _: None)
            self.assertEqual(report["outcomes"], {"interrupted_request_not_retried": 1})

    def test_retained_reader_checks_plan_and_preserves_real_attempts(self):
        cases = [{"context": context(), "targets": []}]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"pilot"
            def offline(*_a, **_k): raise OSError("synthetic failure")
            pilot.run(cases, output, approved_root=directory, opener=offline, sleep=lambda _: None)
            attempts = list(pilot.retained_attempts(output))
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0][1], "full_context")
            self.assertEqual(attempts[0][3]["evaluation"]["status"], "request_failed")
            result_path = output/"result-00.json"
            changed = json.loads(result_path.read_text(encoding="utf-8"))
            changed["plan_sha256"] = "0"*64
            result_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "result_mismatch"):
                list(pilot.retained_attempts(output))

    def test_history_import_rejects_other_databases_before_writing(self):
        class Connection:
            def execute(self, sql):
                if sql != "SELECT current_database()":
                    raise AssertionError("must not write")
                return self
            def fetchone(self): return ("different_database",)
        with self.assertRaisesRegex(ValueError, "wrong_source_test_database"):
            pilot.import_attempt_history(Connection(), [])


if __name__ == "__main__":
    unittest.main()
