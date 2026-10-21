"""Opt-in real-source graph activation acceptance for Italy 853.

This test is intentionally disabled in ordinary CI. It reads the locally
retained source artifact and generated private handoff, validates graph
assertions independently against the source's native identifiers, then uses
the normal private materializer against the specifically named disposable
database. It emits counts only; identifier values and source rows remain
private.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections import Counter
from pathlib import Path
import secrets
import subprocess
import sys
import time
import unittest
import unicodedata
from urllib.parse import urlencode
import urllib.request

import psycopg


SOURCE_ID = "it.853-2004"
DATABASE_NAME = "uec_real_preview_test_graph_20261020"
MATERIALIZER = Path(__file__).parents[2] / "scripts" / "maintenance" / "materialize-private-graph.py"
SOURCE_IDENTIFIER_FIELDS = (
    ("italian_vat", "p_iva"),
    ("italian_fiscal_code", "cod_fiscale"),
)


def _safe_path_env(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise AssertionError(f"required real graph QA setting is missing: {name}")
    return Path(value)


def _pair_token(key: bytes, source_row: int, identifier_type: str, identifier: str,
                recognition: str) -> bytes:
    payload = "\0".join((str(source_row), identifier_type, identifier, recognition)).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).digest()


@unittest.skipUnless(os.environ.get("UEC_RUN_REAL_GRAPH_ACTIVATION") == "1",
                     "set UEC_RUN_REAL_GRAPH_ACTIVATION=1 for approved local real-data acceptance")
class RealItalyGraphActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("UEC_GRAPH_DATABASE_NAME") != DATABASE_NAME:
            raise AssertionError("real graph QA target must be the approved disposable clone")
        if os.environ.get("UEC_GRAPH_DATABASE_PURPOSE") != "private-graph-materialization-v1":
            raise AssertionError("private graph materialization purpose is missing")
        cls.database_url = os.environ.get("UEC_GRAPH_DATABASE_URL", "")
        cls.source_path = _safe_path_env("UEC_GRAPH_REAL_ITALY_SOURCE")
        cls.source_manifest_path = _safe_path_env("UEC_GRAPH_REAL_ITALY_SOURCE_MANIFEST")
        cls.handoff_path = _safe_path_env("UEC_GRAPH_REAL_ITALY_HANDOFF")
        cls.source_manifest = json.loads(cls.source_manifest_path.read_text(encoding="utf-8"))
        if cls.source_manifest.get("source_id") != SOURCE_ID:
            raise AssertionError("source manifest does not identify the expected Italian source")
        source_digest = hashlib.sha256(cls.source_path.read_bytes()).hexdigest()
        digest_field = "parsed_sha256" if cls.source_path.parent.name == "parsed" else "normalized_sha256"
        expected_digest = cls.source_manifest.get(digest_field)
        if not expected_digest or source_digest != expected_digest:
            raise AssertionError("retained parsed/normalized source evidence failed manifest integrity checks")

    def _database_url(self) -> str:
        if not self.database_url:
            self.skipTest("database-backed real graph acceptance requires a clone-scoped reader/writer URL")
        return self.database_url

    def _source_expected_pairs(self) -> tuple[Counter[bytes], int]:
        token_key = secrets.token_bytes(32)
        expected: Counter[bytes] = Counter()
        rows = 0
        with self.source_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                row = record.get("source_values", {})
                source_row = record.get("source_row")
                rows += 1
                recognition = (row.get("num_identificativo_produzione_commercializzazione") or "").strip()
                if not recognition:
                    continue
                for identifier_type, source_field in SOURCE_IDENTIFIER_FIELDS:
                    identifier = (row.get(source_field) or "").strip()
                    if identifier:
                        expected[_pair_token(token_key, source_row, identifier_type,
                                             identifier, recognition)] += 1
        self._token_key = token_key
        return expected, rows

    def test_handoff_is_derived_from_source_native_operator_assertions(self) -> None:
        from pipeline.common.graph_persistence import inspect_graph_candidate_handoff

        expected, source_rows = self._source_expected_pairs()
        manifest, _digest, candidate_count = inspect_graph_candidate_handoff(self.handoff_path)
        self.assertEqual(manifest.get("source_id"), SOURCE_ID)
        self.assertEqual(candidate_count, source_rows)

        actual: Counter[bytes] = Counter()
        mismatch_count = 0
        private_count = 0
        graph_root = self.handoff_path
        if graph_root.is_file():
            graph_root = graph_root.parent
        if (graph_root / "graph-candidates" / "records.jsonl").is_file():
            records_path = graph_root / "graph-candidates" / "records.jsonl"
        elif (graph_root / "graph-candidates.jsonl").is_file():
            records_path = graph_root / "graph-candidates.jsonl"
        elif (graph_root / "records.jsonl").is_file():
            records_path = graph_root / "records.jsonl"
        else:
            raise AssertionError("validated graph handoff has no recognized records file")

        with self.source_path.open("r", encoding="utf-8") as handle:
            source_by_line = {}
            for line in handle:
                record = json.loads(line)
                source_by_line[record.get("source_row")] = record.get("source_values", {})
        with records_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                candidate = json.loads(line)
                source_row = candidate.get("source_row")
                source = source_by_line.get(source_row)
                if source is None:
                    mismatch_count += 1
                    continue
                recognition = (source.get("num_identificativo_produzione_commercializzazione") or "").strip()
                identifiers = {
                    identifier_type: (source.get(source_field) or "").strip()
                    for identifier_type, source_field in SOURCE_IDENTIFIER_FIELDS
                }
                facilities = {item.get("local_ref"): item.get("source_identifier", {})
                              for item in candidate.get("facilities", [])}
                organizations = {item.get("local_ref"): item.get("source_identifier", {})
                                 for item in candidate.get("organizations", [])}
                relationships = candidate.get("relationships", [])
                row_expected = 0
                for relationship in relationships:
                    organization = organizations.get(relationship.get("from_organization_ref"), {})
                    facility = facilities.get(relationship.get("target_facility_ref"), {})
                    identifier_type = organization.get("identifier_type")
                    identifier_value = organization.get("value")
                    if (identifier_type not in identifiers or identifier_value != identifiers.get(identifier_type)
                            or facility.get("identifier_type") != "eu_recognition_number"
                            or facility.get("value") != recognition
                            or relationship.get("relationship_type") != "operator"
                            or relationship.get("assertion_status") != "asserted"
                            or relationship.get("connection_type") != "exact"):
                        mismatch_count += 1
                        continue
                    token = _pair_token(self._token_key, source_row, identifier_type,
                                        identifier_value, recognition)
                    actual[token] += 1
                    row_expected += 1
                expected_for_row = sum(bool(value and recognition) for value in identifiers.values())
                if row_expected != expected_for_row:
                    mismatch_count += abs(row_expected - expected_for_row) or 1
                publication = candidate.get("publication", {})
                private_count += int(
                    publication.get("storage_state") == "private"
                    and publication.get("privacy_status") == "pending"
                    and publication.get("review_state") == "review_required"
                    and publication.get("publication_status") == "not_eligible"
                    and publication.get("release_id") is None
                )

        differences = sum((expected - actual).values()) + sum((actual - expected).values())
        self.assertEqual(mismatch_count, 0, "generated edge did not match the same row's source assertions")
        self.assertEqual(differences, 0, "generated edge set differs from independently derived source pairs")
        self.assertEqual(private_count, candidate_count, "a candidate was not private and review-required")

    def test_real_name_collision_controls_do_not_create_identity_merges(self) -> None:
        from pipeline.common.graph_persistence import inspect_graph_candidate_handoff

        name_groups: dict[str, tuple[set[str], set[str]]] = {}
        with self.source_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line).get("source_values", {})
                name = " ".join(unicodedata.normalize("NFKC", (row.get("ragione_sociale") or "")).casefold().split())
                vat = (row.get("p_iva") or "").strip()
                recognition = (row.get("num_identificativo_produzione_commercializzazione") or "").strip()
                if name and vat and recognition:
                    identifiers = name_groups.setdefault(name, (set(), set()))
                    identifiers[0].add(vat)
                    identifiers[1].add(recognition)
        real_collision_count = sum(1 for vats, facilities in name_groups.values()
                                   if len(vats) > 1 and len(facilities) > 1)
        self.assertGreater(real_collision_count, 0, "source no-name-merge control set is empty")

        manifest, _digest, candidate_count = inspect_graph_candidate_handoff(self.handoff_path)
        self.assertEqual(manifest.get("source_id"), SOURCE_ID)
        graph_root = self.handoff_path.parent if self.handoff_path.is_file() else self.handoff_path
        if (graph_root / "graph-candidates" / "records.jsonl").is_file():
            records_path = graph_root / "graph-candidates" / "records.jsonl"
        elif (graph_root / "graph-candidates.jsonl").is_file():
            records_path = graph_root / "graph-candidates.jsonl"
        else:
            records_path = graph_root / "records.jsonl"
        candidates = 0
        unsafe_identity_fields = 0
        cross_entity_links = 0
        with records_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                candidate = json.loads(line)
                candidates += 1
                unsafe_identity_fields += int(any(
                    key.casefold() in {"canonical_id", "global_id", "universal_id", "universal_identity", "auto_merge"}
                    for key in candidate
                ))
                unsafe_identity_fields += int(any(
                    item.get("identity_scope", "source_scoped") != "source_scoped"
                    for item in candidate.get("facilities", []) + candidate.get("organizations", [])
                ))
                unsafe_identity_fields += int(bool(candidate.get("crosswalks")))
                organization_refs = {item.get("local_ref") for item in candidate.get("organizations", [])}
                facility_refs = {item.get("local_ref") for item in candidate.get("facilities", [])}
                cross_entity_links += sum(
                    int(relationship.get("from_organization_ref") not in organization_refs
                        or relationship.get("target_facility_ref") not in facility_refs)
                    for relationship in candidate.get("relationships", [])
                )
        self.assertEqual(candidates, candidate_count)
        self.assertEqual(unsafe_identity_fields, 0,
                         "same-name source identifiers must remain source-scoped without a merge")
        self.assertEqual(cross_entity_links, 0,
                         "source assertions must link only identifiers co-occurring in their own row")

    @unittest.skipUnless(os.environ.get("UEC_RUN_REAL_GRAPH_FULL_REPLAY") == "1",
                         "full normal materializer replay is expensive and separately opt-in")
    def test_full_normal_materializer_replay_is_separately_opt_in(self) -> None:
        database_url = self._database_url()
        environment = os.environ.copy()
        environment.update({
            "UEC_GRAPH_DATABASE_URL": database_url,
            "UEC_GRAPH_DATABASE_NAME": DATABASE_NAME,
            "UEC_GRAPH_DATABASE_PURPOSE": "private-graph-materialization-v1",
            "PYTHONPATH": str(Path(__file__).parents[3]),
        })
        with psycopg.connect(database_url) as connection:
            release_membership_before = connection.execute(
                "SELECT r.release_id, count(DISTINCT p.facility_id), count(p.facility_id) "
                "FROM uec.releases r LEFT JOIN uec.map_facilities_public_discovery_read_model p "
                "ON p.release_id=r.release_id GROUP BY r.release_id ORDER BY r.release_id"
            ).fetchall()
        command = [sys.executable, str(MATERIALIZER), "--handoff", str(self.handoff_path)]
        first = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
        self.assertEqual(first.returncode, 0, "normal private graph materialization failed (details redacted)")
        try:
            first_result = json.loads(first.stdout)
        except json.JSONDecodeError:
            self.fail("normal private graph materializer returned an invalid aggregate result")
        self.assertEqual(first_result.get("source_id"), SOURCE_ID)
        expected_rows = self.source_manifest.get("input_rows")
        if expected_rows is None:
            expected_rows = self.source_manifest.get("counts", {}).get("input_rows")
        self.assertEqual(first_result.get("item_count"), expected_rows)
        self.assertEqual(first_result.get("public_rows"), 0)
        matcher = first_result.get("matcher", {})
        self.assertEqual(matcher.get("rows_staged"), expected_rows)
        self.assertIsInstance(matcher.get("inferred_candidates_staged"), int)

        second = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
        self.assertEqual(second.returncode, 0, "full normal graph replay failed (details redacted)")
        try:
            second_result = json.loads(second.stdout)
        except json.JSONDecodeError:
            self.fail("full normal graph replay returned an invalid aggregate result")
        self.assertEqual(second_result.get("item_count"), first_result.get("item_count"))
        self.assertEqual(second_result.get("inserted_count"), 0)
        self.assertEqual(second_result.get("edge_inserted_count"), 0)
        self.assertEqual(second_result.get("edge_updated_count"), 0)
        self.assertEqual(second_result.get("public_rows"), 0)
        self.assertEqual(second_result.get("run_id"), first_result.get("run_id"))

        with psycopg.connect(database_url) as connection:
            runs = connection.execute(
                "SELECT count(*), count(*) FILTER (WHERE status='completed') "
                "FROM uec.graph_ingest_runs WHERE ingest_run_id=%s",
                (first_result.get("run_id"),),
            ).fetchone()
            self.assertEqual(runs[0], 1)
            self.assertEqual(runs[1], 1)
            stored = connection.execute(
                "SELECT connection_type, count(*) FROM uec.graph_connection_edges "
                "WHERE from_source_id=%s OR to_source_id=%s GROUP BY connection_type",
                (SOURCE_ID, SOURCE_ID),
            ).fetchall()
            release_membership_after = connection.execute(
                "SELECT r.release_id, count(DISTINCT p.facility_id), count(p.facility_id) "
                "FROM uec.releases r LEFT JOIN uec.map_facilities_public_discovery_read_model p "
                "ON p.release_id=r.release_id GROUP BY r.release_id ORDER BY r.release_id"
            ).fetchall()
        self.assertEqual(release_membership_after, release_membership_before,
                         "private graph import changed approved release membership")
        stored_by_type = {kind: count for kind, count in stored}
        self.assertEqual(first_result.get("edge_counts_by_type"), stored_by_type)
        self.assertGreater(stored_by_type.get("exact", 0), 0,
                           "source-native exact assertions were not persisted")
        self.assertGreaterEqual(stored_by_type.get("inferred", 0), 0,
                                "inferred matcher count must be present even when zero")
        self.assertEqual(first_result.get("source_assertion_rows"),
                         sum(self._source_expected_pairs()[0].values()),
                         "persisted exact assertion count differs from independent source scan")

    def test_public_api_redacts_identifiers_and_returns_only_eligible_edges(self) -> None:
        database_url = self._database_url()
        from pipeline.common.graph_persistence import inspect_graph_candidate_handoff

        origin = os.environ.get("UEC_GRAPH_PUBLIC_API_ORIGIN", "").rstrip("/")
        self.assertTrue(origin, "local public graph API origin is required for real acceptance")
        _manifest, handoff_digest, candidate_count = inspect_graph_candidate_handoff(self.handoff_path)
        with psycopg.connect(database_url) as connection:
            run = connection.execute(
                "SELECT ingest_run_id::text,status,item_count FROM uec.graph_ingest_runs "
                "WHERE source_id=%s AND handoff_sha256=%s",
                (SOURCE_ID, handoff_digest),
            ).fetchone()
            self.assertIsNotNone(run, "verified handoff is not materialized in the named clone")
            self.assertEqual(run[1], "completed")
            self.assertEqual(run[2], candidate_count)
            private_counts = connection.execute(
                "SELECT connection_type,count(*) FROM uec.graph_connection_edges "
                "WHERE from_source_id=%s OR to_source_id=%s GROUP BY connection_type",
                (SOURCE_ID, SOURCE_ID),
            ).fetchall()
        private_by_type = {kind: count for kind, count in private_counts}

        def read_pages(connection_type: str, *, include_conflicting: bool = False,
                       min_confidence: float | None = None,
                       max_pages: int = 2
                       ) -> tuple[list[dict[str, object]], list[int], bool, bool]:
            cursor: str | None = None
            edges_found: list[dict[str, object]] = []
            latencies: list[int] = []
            cursor_advanced = False
            exhausted = False
            for page_index in range(max_pages):
                query = {"profile": "official", "source_id": SOURCE_ID, "limit": 100,
                         "connection_type": connection_type}
                if include_conflicting:
                    query["include_conflicting"] = "true"
                if min_confidence is not None:
                    query["min_confidence"] = str(min_confidence)
                if cursor:
                    query["cursor"] = cursor
                url = f"{origin}/api/v2/graph/connections?{urlencode(query)}"
                started = time.perf_counter()
                with urllib.request.urlopen(url, timeout=30) as response:
                    body = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                latencies.append(round((time.perf_counter() - started) * 1000))
                meta = body.get("meta", {})
                self.assertTrue(meta.get("public_projection"))
                self.assertEqual(meta.get("profile"), "official")
                self.assertTrue(meta.get("release_id"))
                page = body.get("data", [])
                self.assertLessEqual(len(page), 100)
                edges_found.extend(page)
                next_cursor = meta.get("next_cursor")
                if page_index == 0 and next_cursor:
                    cursor_advanced = True
                # A short page can still carry a continuation cursor. Only an
                # explicit empty page proves exhaustion for this endpoint.
                if not page:
                    exhausted = True
                    return edges_found, latencies, cursor_advanced, exhausted
                if next_cursor:
                    self.assertNotEqual(next_cursor, cursor, "cursor did not advance")
                self.assertTrue(next_cursor, "full page has no continuation cursor")
                cursor = next_cursor
            return edges_found, latencies, cursor_advanced, exhausted

        exact_edges, exact_latency, exact_cursor, exact_exhausted = read_pages("exact")
        inferred_edges, inferred_latency, inferred_cursor, inferred_exhausted = read_pages(
            "inferred", max_pages=3
        )
        inferred_confidence_edges, confidence_latency, _, confidence_exhausted = read_pages(
            "inferred", min_confidence=0.6, max_pages=3
        )
        inferred_conflict_edges, conflict_latency, _, conflict_exhausted = read_pages(
            "inferred", include_conflicting=True, max_pages=3
        )
        for edges in (exact_edges, inferred_edges, inferred_confidence_edges, inferred_conflict_edges):
            ids = [edge.get("connection_edge_id") for edge in edges]
            self.assertEqual(len(ids), len(set(ids)), "cursor traversal repeated a graph edge")
        self.assertGreater(len(exact_edges), 0, "source-native exact assertions were not publicly resolved")
        self.assertGreater(len(inferred_edges), 0, "eligible real matcher inference was not publicly resolved")
        self.assertTrue(exact_cursor and inferred_cursor, "cursor did not advance on a real positive page")
        self.assertFalse(exact_exhausted, "exact-edge pages are only a bounded sample")
        self.assertTrue(inferred_exhausted and confidence_exhausted and conflict_exhausted,
                        "inferred filters did not reach an explicit empty terminal page")
        self.assertEqual(len(inferred_conflict_edges), 148,
                         "conflict-inclusive inference does not match the repaired private set")
        self.assertEqual(len(inferred_edges), 147,
                         "the default projection should suppress the single conflicting edge")
        self.assertEqual({edge["connection_edge_id"] for edge in inferred_confidence_edges},
                         {edge["connection_edge_id"] for edge in inferred_edges
                          if float(edge["confidence"]) >= 0.6})
        self.assertEqual({edge["connection_edge_id"] for edge in inferred_edges},
                         {edge["connection_edge_id"] for edge in inferred_conflict_edges
                          if not edge.get("conflicting")})

        all_edges = exact_edges + inferred_edges + inferred_conflict_edges
        first_body_release = all_edges[0].get("provenance", {}).get("release_id")
        self.assertTrue(first_body_release)
        for edge in all_edges:
            self.assertIn(edge.get("connection_type"), {"exact", "inferred"})
            self.assertGreaterEqual(float(edge.get("confidence", -1)), 0)
            self.assertLessEqual(float(edge.get("confidence", 2)), 1)
            self.assertEqual(edge.get("provenance", {}).get("release_id"), first_body_release)
            self.assertFalse(edge.get("automatic_merge", False))
            self.assertFalse(edge.get("claim_transfer", False))
            encoded = json.dumps(edge, ensure_ascii=False).casefold()
            for forbidden in ("source_values", "raw_fields", "p_iva", "cod_fiscale",
                              "from_source_identifier", "to_source_identifier"):
                self.assertNotIn(forbidden, encoded)
            for side in ("from", "to"):
                endpoint = edge.get(side, {})
                self.assertIsNotNone(endpoint.get("entity_id"), "published endpoint did not resolve")
                self.assertIn(endpoint.get("entity_type"), {"facility", "organization"})
                self.assertEqual(endpoint.get("source_id"), SOURCE_ID)
                self.assertTrue(str(endpoint.get("source_identifier", "")).startswith("entity:"))
        self.assertTrue(all(float(edge["confidence"]) == 1 for edge in exact_edges))
        self.assertTrue(all(float(edge["confidence"]) < 1 for edge in inferred_edges))

        sampled_ids = list({edge["connection_edge_id"] for edge in all_edges})
        release_id = first_body_release
        with psycopg.connect(database_url) as connection:
            approved_facilities = connection.execute(
                "SELECT DISTINCT facility_id::text FROM uec.map_facilities_public_discovery_read_model "
                "WHERE release_id=%s", (release_id,),
            ).fetchall()
            approved_organizations = connection.execute(
                "SELECT DISTINCT i.organization_id::text FROM uec.source_entity_identifiers i "
                "JOIN uec.organizations o ON o.organization_id=i.organization_id "
                "JOIN uec.source_records record ON record.source_record_id=i.source_record_id "
                "AND record.source_id=i.source_id "
                "JOIN uec.map_facilities_public_discovery_read_model approved_facility "
                "ON approved_facility.source_record_id=record.source_record_id "
                "AND approved_facility.release_id=%s "
                "JOIN uec.source_entity_identifiers same_record_facility "
                "ON same_record_facility.source_record_id=i.source_record_id "
                "AND same_record_facility.source_id=i.source_id "
                "AND same_record_facility.entity_type='facility' "
                "AND same_record_facility.facility_id=approved_facility.facility_id "
                "WHERE i.source_id=%s AND i.entity_type='organization' "
                "AND i.identifier_type IN ('vat','vat_number','italian_vat','p_iva')",
                (release_id, SOURCE_ID),
            ).fetchall()
            private_rows = connection.execute(
                "SELECT connection_edge_id::text,connection_type,suppressed,supporting_source_refs "
                "FROM uec.graph_connection_edges WHERE connection_edge_id::text=ANY(%s)",
                (sampled_ids,),
            ).fetchall()
        approved = {facility_id for (facility_id,) in approved_facilities}
        approved_orgs = {organization_id for (organization_id,) in approved_organizations}
        for edge in all_edges:
            for side in ("from", "to"):
                endpoint = edge[side]
                eligible = approved if endpoint["entity_type"] == "facility" else approved_orgs
                self.assertIn(str(endpoint["entity_id"]), eligible,
                              "endpoint did not resolve through the selected approved release")
        private_by_id = {edge_id: (kind, suppressed, refs)
                         for edge_id, kind, suppressed, refs in private_rows}
        self.assertEqual(set(sampled_ids), set(private_by_id),
                         "public API returned an edge without retained private evidence")
        support_ids: set[str] = set()
        for edge_id in sampled_ids:
            kind, suppressed, refs = private_by_id[edge_id]
            self.assertFalse(suppressed, "suppressed private evidence crossed the public boundary")
            self.assertIn(kind, {"exact", "inferred"})
            for ref in refs:
                if ref.get("source_id") == SOURCE_ID:
                    self.assertTrue(ref.get("source_record_id"),
                                    "public edge lacked a version-qualified private support reference")
                    support_ids.add(str(ref["source_record_id"]))
        self.assertTrue(support_ids)
        with psycopg.connect(database_url) as connection:
            eligible_support_count = connection.execute(
                "SELECT count(DISTINCT supplied.record_id) FROM unnest(%s::uuid[]) supplied(record_id) "
                "WHERE EXISTS (SELECT 1 FROM uec.graph_record_release_bindings binding "
                "WHERE binding.private_source_record_id=supplied.record_id AND binding.release_id=%s) "
                "OR EXISTS (SELECT 1 FROM uec.source_entity_identifiers identifier "
                "WHERE identifier.source_record_id=supplied.record_id AND identifier.release_id=%s "
                "AND identifier.storage_state='released' AND identifier.publication_status='released' "
                "AND identifier.privacy_status='passed')",
                (list(support_ids), release_id, release_id),
            ).fetchone()[0]
        self.assertEqual(eligible_support_count, len(support_ids),
                         "support reference did not map to a selected approved release version")
        exact_public_keys = {
            "connection_edge_id", "from", "to", "relationship_type", "connection_type",
            "confidence", "confidence_band", "match_method", "signals", "contradictions",
            "provenance", "source_references", "observed_at", "computed_at", "ruleset",
            "conflicting", "publication_warning", "disclaimer",
        }
        for edge in all_edges:
            self.assertEqual(set(edge), exact_public_keys,
                             "public edge shape contains unexpected private/name fields")
            for side in ("from", "to"):
                endpoint = edge[side]
                self.assertEqual(set(endpoint), {
                    "entity_id", "entity_type", "source_id", "identifier_type", "source_identifier"
                }, "public endpoint contains unexpected private identity fields")
                self.assertEqual(endpoint["source_id"], SOURCE_ID,
                                 "source-filtered API returned an unrelated source endpoint")
                if endpoint["entity_type"] == "facility":
                    self.assertIn(str(endpoint["entity_id"]), approved,
                                  "public facility did not resolve through selected approved release")
                else:
                    self.assertIn(str(endpoint["entity_id"]), approved_orgs,
                                  "public operator did not resolve through selected approved release")

        # The receipt is aggregate-only evidence for this local acceptance run.
        staging = Path("data/staging/graph-source-expansion-20261020")
        staging.mkdir(parents=True, exist_ok=True)
        receipt = {
            "source_id": SOURCE_ID,
            "database_name": DATABASE_NAME,
            "run_id": run[0],
            "candidate_count": candidate_count,
            "private_edges_by_type": private_by_type,
            "public_exact_sample_count": len(exact_edges),
            "public_inferred_count": len(inferred_edges),
            "public_inferred_conflict_inclusive_count": len(inferred_conflict_edges),
            "public_inferred_min_confidence_count": len(inferred_confidence_edges),
            "public_page_count": {"exact_sample": len(exact_latency), "inferred": len(inferred_latency),
                                  "inferred_conflict_inclusive": len(conflict_latency)},
            "inferred_traversals_exhausted_by_empty_page": {
                "default": inferred_exhausted, "min_confidence": confidence_exhausted,
                "include_conflicting": conflict_exhausted,
            },
            "api_latency_ms": {"exact_sample": exact_latency, "inferred": inferred_latency,
                               "inferred_min_confidence": confidence_latency,
                               "inferred_conflict_inclusive": conflict_latency},
            "release_id": release_id,
            "public_projection": True,
            "source_assertions_verification": "separate_source_assertion_test",
            "same_name_negative_controls_verification": "separate_collision_test",
            "suppression_filter_verified": True,
            "full_normal_materializer_replay_verified": False,
            "native_name_address_city_value_comparison_pending_approval": True,
        }
        (staging / "real-graph-activation-aggregate.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    unittest.main()
