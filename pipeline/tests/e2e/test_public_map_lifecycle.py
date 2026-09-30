"""Disposable lifecycle check for the cached public MVT route.

When a local retained real-preview handoff is available, its first valid
coordinate is used only as test input. All approvals, rights decisions,
release state, and API serving occur in this module's disposable Postgres
stack. They are explicitly hypothetical test fixtures, not human approvals.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

import psycopg

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment


ROOT = Path(__file__).resolve().parents[3]
_BUILDER_SPEC = importlib.util.spec_from_file_location(
    "build_public_map_artifacts", ROOT / "pipeline/scripts/maintenance/build_public_map_artifacts.py"
)
BUILDER = importlib.util.module_from_spec(_BUILDER_SPEC)
assert _BUILDER_SPEC.loader
_BUILDER_SPEC.loader.exec_module(BUILDER)
_PROMOTE_SPEC = importlib.util.spec_from_file_location(
    "promote_release_map_artifacts", ROOT / "pipeline/scripts/stages/promote-release.py"
)
PROMOTE = importlib.util.module_from_spec(_PROMOTE_SPEC)
assert _PROMOTE_SPEC.loader
_PROMOTE_SPEC.loader.exec_module(PROMOTE)
_VALIDATE_SPEC = importlib.util.spec_from_file_location(
    "validate_release_map_lifecycle", ROOT / "pipeline/scripts/stages/validate-release.py"
)
VALIDATE = importlib.util.module_from_spec(_VALIDATE_SPEC)
assert _VALIDATE_SPEC.loader
_VALIDATE_SPEC.loader.exec_module(VALIDATE)


DEFAULT_SNAPSHOT = Path(
    r"D:\UntilEveryCage-private\d6-graph-mvp\handoffs\us.fsis\normalized\records.jsonl"
)
RELEASE_ID = "e2e-real-snapshot-map"
SOURCE_ID = "e2e-real-snapshot-map"
TEST_ONLY_NOTE = "TEST-ONLY hypothetical lifecycle fixture; not a human review or rights decision"
ALLOWED_PROPERTIES = {
    "feature_key", "kind", "count", "exact_count", "coarse_count", "next_zoom",
    "record_id", "category_key",
}


def _sample_coordinate(path: Path) -> tuple[float, float]:
    """Read one bounded coordinate without printing or retaining source fields."""
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            try:
                normalized = json.loads(line).get("normalized", {})
                point = normalized.get("coordinates") or {}
                latitude = float(point.get("latitude"))
                longitude = float(point.get("longitude"))
            except (TypeError, ValueError, AttributeError, json.JSONDecodeError):
                continue
            if (-90 <= latitude <= 90 and -180 <= longitude <= 180
                    and (latitude != 0 or longitude != 0)):
                return longitude, latitude
    raise unittest.SkipTest("retained snapshot has no valid coordinate for the local lifecycle check")


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    value = shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift > 70:
            break
    raise ValueError("invalid protobuf varint")


def _protobuf_fields(data: bytes):
    offset = 0
    while offset < len(data):
        tag, offset = _varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if wire == 0:
            value, offset = _varint(data, offset)
        elif wire == 1:
            value, offset = data[offset:offset + 8], offset + 8
        elif wire == 2:
            length, offset = _varint(data, offset)
            value, offset = data[offset:offset + length], offset + length
        elif wire == 5:
            value, offset = data[offset:offset + 4], offset + 4
        else:
            raise ValueError("unsupported protobuf wire type")
        yield number, wire, value


def _packed_varints(data: bytes) -> list[int]:
    values = []
    offset = 0
    while offset < len(data):
        value, offset = _varint(data, offset)
        values.append(value)
    return values


def _decode_value(data: bytes):
    for field, wire, value in _protobuf_fields(data):
        if field == 1 and wire == 2:
            return value.decode("utf-8")
        if field in (4, 5) and wire == 0:
            return value
        if field == 7 and wire == 0:
            return bool(value)
    return None


def _decode_mvt(data: bytes) -> tuple[str, list[dict]]:
    layers = [value for field, wire, value in _protobuf_fields(data) if field == 3 and wire == 2]
    if len(layers) != 1:
        raise AssertionError(f"expected one MVT layer, got {len(layers)}")
    layer = layers[0]
    layer_name = next(
        value.decode("utf-8") for field, wire, value in _protobuf_fields(layer)
        if field == 1 and wire == 2
    )
    keys = [value.decode("utf-8") for field, wire, value in _protobuf_fields(layer) if field == 3 and wire == 2]
    values = [_decode_value(value) for field, wire, value in _protobuf_fields(layer) if field == 4 and wire == 2]
    features = []
    for field, wire, feature in _protobuf_fields(layer):
        if field != 2 or wire != 2:
            continue
        properties = {}
        for feature_field, feature_wire, tags in _protobuf_fields(feature):
            if feature_field == 2 and feature_wire == 2:
                pairs = _packed_varints(tags)
                properties.update({keys[pairs[index]]: values[pairs[index + 1]] for index in range(0, len(pairs), 2)})
        features.append(properties)
    return layer_name, features


def _get(url: str, headers: dict | None = None):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        response = urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    return response.status, response.headers, response.read()


class PublicMapLifecycleE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.snapshot = Path(os.environ.get("UEC_TEST_REAL_PRIVATE_MAP_SNAPSHOT", str(DEFAULT_SNAPSHOT)))
        if not cls.snapshot.is_file():
            raise unittest.SkipTest("no retained local real-preview snapshot; no reacquisition is attempted")
        cls.snapshot_point = _sample_coordinate(cls.snapshot)
        cls.artifact_temp = tempfile.TemporaryDirectory(prefix="uec-map-lifecycle-artifacts-")
        cls.artifact_root = Path(cls.artifact_temp.name)
        cls.previous_artifact_root = os.environ.get("UEC_PUBLIC_MAP_ARTIFACT_ROOT")
        os.environ["UEC_PUBLIC_MAP_ARTIFACT_ROOT"] = str(cls.artifact_root)
        cls.env = E2EEnvironment()
        try:
            cls.env.start()
            cls._prepare_release()
        except Exception:
            cls.env.stop()
            cls._restore_artifact_root()
            cls.artifact_temp.cleanup()
            raise

    @classmethod
    def _restore_artifact_root(cls):
        if cls.previous_artifact_root is None:
            os.environ.pop("UEC_PUBLIC_MAP_ARTIFACT_ROOT", None)
        else:
            os.environ["UEC_PUBLIC_MAP_ARTIFACT_ROOT"] = cls.previous_artifact_root

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "env", None):
            cls.env.stop()
        if getattr(cls, "artifact_temp", None):
            cls.artifact_temp.cleanup()
        cls._restore_artifact_root()

    @classmethod
    def _prepare_release(cls):
        now = datetime.now(timezone.utc)
        exact_lon, exact_lat = cls.snapshot_point
        coarse_lon, coarse_lat = round(exact_lon, 1), round(exact_lat, 1)
        snapshot_digest = _digest_file(cls.snapshot)
        cases = [
            ("exact-a", "accepted", exact_lon, exact_lat),
            ("exact-b", "accepted", exact_lon, exact_lat),
            ("coarse", "review_required", None, None),
            ("unmapped", "unresolved", None, None),
        ]
        facilities = {}
        records = {}
        artifact_id = uuid.uuid4()
        with psycopg.connect(cls.env.database_url) as db, db.transaction():
            # Test-only copy of one geometry from a retained private handoff.
            # Source labels and all record identities below are synthetic.
            db.execute(
                "INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method,attribution) "
                "VALUES (%s,'US','TEST-ONLY retained snapshot','https://example.invalid/test-only-snapshot','test-fixture','')",
                (SOURCE_ID,),
            )
            db.execute(
                "INSERT INTO uec.releases (release_id,status,ruleset_version,profile,test_only,summary) "
                "VALUES (%s,'candidate','e2e-map-v1','official',false,%s::jsonb)",
                (RELEASE_ID, json.dumps({"test_only_simulation": True})),
            )
            db.execute(
                "INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (artifact_id, "test-only-snapshot-sha256:" + snapshot_digest, snapshot_digest, cls.snapshot.stat().st_size, now),
            )
            db.execute(
                "INSERT INTO uec.city_reference_points "
                "(country_code,city_name,reference_location,reference_source,source_retrieved_at,source_reference_id) "
                "VALUES ('US','TEST-ONLY coarse place',ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,'test-only rounded snapshot point',%s,'test-only-coarse-reference')",
                (coarse_lon, coarse_lat, now),
            )
            for key, status, longitude, latitude in cases:
                record_id, facility_id, observation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
                records[key], facilities[key] = record_id, facility_id
                db.execute(
                    "INSERT INTO uec.source_records "
                    "(source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) "
                    "VALUES (%s,%s,%s,%s,'{}',%s)",
                    (record_id, SOURCE_ID, "test-only-" + key, artifact_id, now),
                )
                db.execute(
                    "INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) "
                    "VALUES (%s,%s,'US','TEST-ONLY coarse place')",
                    (facility_id, "TEST-ONLY " + key),
                )
                db.execute(
                    "INSERT INTO uec.observations "
                    "(observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,"
                    "classification_category,classification_review_status,default_visible,first_observed_at) "
                    "VALUES (%s,%s,%s,%s,'{}','{}','e2e-map-v1','test-only','slaughter','approved',true,%s)",
                    (observation_id, facility_id, record_id, now, now),
                )
                db.execute(
                    "INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) "
                    "VALUES (%s,%s,%s,true)",
                    (RELEASE_ID, facility_id, observation_id),
                )
                point = f"ST_SetSRID(ST_MakePoint({longitude},{latitude}),4326)::geography" if longitude is not None else "NULL"
                db.execute(
                    "INSERT INTO uec.geocode_results "
                    "(source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at) "
                    f"VALUES (%s,'test-only-snapshot','TEST-ONLY', 'test-fixture',%s,1,{point},%s)",
                    (record_id, status, now),
                )
                db.execute(
                    "INSERT INTO uec.publication_review_events "
                    "(source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role,note) "
                    "VALUES (%s,%s,'reviewed','passed','approved',true,'maintainer',%s)",
                    (record_id, RELEASE_ID, TEST_ONLY_NOTE),
                )
            db.execute(
                "INSERT INTO uec.source_rights_decisions "
                "(source_id,profile,release_id,artifact_id,artifact_sha256,redistribution_status,decision_actor,decision_reference,decided_at) "
                "VALUES (%s,'official',%s,%s,%s,'cleared','TEST-ONLY fixture','TEST-ONLY hypothetical rights decision',%s)",
                (SOURCE_ID, RELEASE_ID, artifact_id, snapshot_digest, now),
            )
        # Seed and reject the malformed candidate before building the good
        # release so its TEST-ONLY gate events are part of the artifact's
        # captured suppression generation.
        cls._prepare_unsafe_coordinate_candidate(now, artifact_id, snapshot_digest)
        validation = VALIDATE.validate(cls.env.database_url, RELEASE_ID, 4, True)
        cls.validation_metrics = validation["metrics"]
        if validation["status"] != "passed":
            raise AssertionError(f"TEST-ONLY lifecycle candidate did not validate: {validation['findings']}")
        if (cls.validation_metrics["exact_display_ready"], cls.validation_metrics["city_display_ready"],
                cls.validation_metrics["unmapped_display"], cls.validation_metrics["coordinate_not_ready"]) != (2, 1, 1, 0):
            raise AssertionError("TEST-ONLY exact/coarse/unmapped release metrics do not match the fixture")

        build_result = BUILDER.build(cls.env.database_url, RELEASE_ID, cls.artifact_root)
        cls.artifact_path = Path(build_result["map_artifact_manifest"])
        cls.map_artifact = json.loads(cls.artifact_path.read_text(encoding="utf-8"))
        cls.generation = cls.map_artifact["suppression_generation"]
        PROMOTE.validate_map_artifact(cls.artifact_path, RELEASE_ID, "official", cls.generation)
        # The real validate/promote predicates run only in this disposable
        # database. These TEST-ONLY approvals are not human decisions and the
        # ephemeral release is served only by the loopback E2E server.
        cls.promoted = PROMOTE.promote(cls.env.database_url, RELEASE_ID, [], cls.map_artifact)
        cls.env.build_public_read_model(RELEASE_ID)
        cls.records = records
        cls.facilities = facilities

    @classmethod
    def _prepare_unsafe_coordinate_candidate(cls, now, artifact_id, snapshot_digest):
        release_id = "e2e-map-unsafe-coordinate"
        record_id, facility_id, observation_id = (uuid.uuid4() for _ in range(3))
        with psycopg.connect(cls.env.database_url) as db, db.transaction():
            db.execute(
                "INSERT INTO uec.releases (release_id,status,ruleset_version,profile,test_only,summary) "
                "VALUES (%s,'candidate','e2e-map-v1','official',false,'{\"test_only_simulation\":true}')",
                (release_id,),
            )
            db.execute(
                "INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) "
                "VALUES (%s,%s,'test-only-invalid-zero-point',%s,'{}',%s)",
                (record_id, SOURCE_ID, artifact_id, now),
            )
            db.execute(
                "INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) "
                "VALUES (%s,'TEST-ONLY invalid zero coordinate','US','TEST-ONLY coarse place')",
                (facility_id,),
            )
            db.execute(
                "INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at) "
                "VALUES (%s,%s,%s,%s,'{}','{}','e2e-map-v1','test-only','slaughter','approved',true,%s)",
                (observation_id, facility_id, record_id, now, now),
            )
            db.execute(
                "INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,true)",
                (release_id, facility_id, observation_id),
            )
            db.execute(
                "INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at) "
                "VALUES (%s,'test-only','TEST-ONLY invalid','test-fixture','accepted',1,ST_SetSRID(ST_MakePoint(0,0),4326)::geography,%s)",
                (record_id, now),
            )
            db.execute(
                "INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role,note) "
                "VALUES (%s,%s,'reviewed','passed','approved',true,'maintainer',%s)",
                (record_id, release_id, TEST_ONLY_NOTE),
            )
            db.execute(
                "INSERT INTO uec.source_rights_decisions (source_id,profile,release_id,artifact_id,artifact_sha256,redistribution_status,decision_actor,decision_reference,decided_at) "
                "VALUES (%s,'official',%s,%s,%s,'cleared','TEST-ONLY fixture','TEST-ONLY hypothetical rights decision',%s)",
                (SOURCE_ID, release_id, artifact_id, snapshot_digest, now),
            )
        validation = VALIDATE.validate(cls.env.database_url, release_id, 1, False)
        if validation["status"] != "blocked" or validation["metrics"]["coordinate_not_ready"] != 1:
            raise AssertionError("malformed TEST-ONLY coordinate was not blocked during validation")
        with psycopg.connect(cls.env.database_url) as db:
            db.execute("UPDATE uec.releases SET status='validated' WHERE release_id=%s", (release_id,))
        try:
            PROMOTE.promote(cls.env.database_url, release_id, [])
        except ValueError as error:
            if "coordinate_not_ready=1" not in str(error):
                raise
        else:
            raise AssertionError("promotion accepted a malformed TEST-ONLY zero coordinate")

    def test_manifest_tiles_precision_cache_pinning_and_suppression_revocation(self):
        base = f"http://127.0.0.1:{self.env.api_port}"
        manifest_url = base + "/api/v2/releases/manifest?profile=official"
        status, headers, body = _get(manifest_url)
        self.assertEqual(status, 200)
        manifest_envelope = json.loads(body)
        data = manifest_envelope["data"]
        map_artifact = data["manifest"]["map_artifact"]
        self.assertEqual(data["release_id"], RELEASE_ID)
        self.assertEqual(map_artifact["release_id"], RELEASE_ID)
        self.assertEqual(map_artifact["profile"], "official")
        self.assertEqual(data["suppression_generation"], self.generation)
        self.assertEqual(map_artifact["tile_url_template"], f"/api/v2/releases/{RELEASE_ID}/map/tiles/{{z}}/{{x}}/{{y}}.mvt?profile=official")
        self.assertEqual(headers["ETag"], f'"{data["manifest_sha256"]}-{self.generation}"')
        status_304, _, _ = _get(manifest_url, {"If-None-Match": headers["ETag"]})
        self.assertEqual(status_304, 304)
        self.assertEqual(map_artifact["tiles"], self.map_artifact["tiles"])
        self.assertEqual(PROMOTE.validate_map_artifact(self.artifact_path, RELEASE_ID, "official", self.generation)["source_layer"], "uec_map")

        list_status, _, list_body = _get(base + "/api/v2/locations?limit=10&release_id=" + RELEASE_ID)
        self.assertEqual(list_status, 200)
        listed = json.loads(list_body)["data"]
        self.assertEqual(len(listed), 4)
        self.assertEqual({row["display_precision"] for row in listed}, {"exact", "city", "unmapped"})
        self.assertEqual(sum(row["display_precision"] == "unmapped" for row in listed), 1)

        high_zoom_tiles = [tile for tile in map_artifact["tiles"] if tile["z"] == 14]
        self.assertTrue(high_zoom_tiles)
        tile_features = []
        tile_url = None
        tile_etag = None
        for index, high_zoom in enumerate(high_zoom_tiles):
            url = f"{base}/api/v2/releases/{RELEASE_ID}/map/tiles/{high_zoom['z']}/{high_zoom['x']}/{high_zoom['y']}.mvt?profile=official"
            if index == 0:
                tile_url = url
                tile_etag = high_zoom["etag"]
            status_tile, tile_headers, tile_body = _get(url)
            self.assertEqual(status_tile, 200)
            self.assertEqual(tile_headers["Content-Type"], "application/vnd.mapbox-vector-tile")
            self.assertEqual(tile_headers["ETag"], f'"{hashlib.sha256(tile_body).hexdigest()}"')
            self.assertEqual(hashlib.sha256(tile_body).hexdigest(), high_zoom["sha256"])
            self.assertEqual(int(tile_headers["X-Uec-Suppression-Generation"]), self.generation)
            layer_name, features_on_tile = _decode_mvt(tile_body)
            self.assertEqual(layer_name, "uec_map")
            tile_features.extend(features_on_tile)
        self.assertIsNotNone(tile_url)
        features = tile_features
        self.assertTrue(features)
        self.assertTrue(all(set(feature) <= ALLOWED_PROPERTIES for feature in features))
        exact_ids = {str(self.facilities[key]) for key in ("exact-a", "exact-b")}
        exact_features = [feature for feature in features if feature.get("kind") == "exact"]
        coarse_features = [feature for feature in features if feature.get("kind") == "coarse"]
        self.assertEqual({feature.get("record_id") for feature in exact_features}, exact_ids)
        self.assertEqual(len(coarse_features), 1)
        self.assertNotIn("record_id", coarse_features[0])
        serialized_features = json.dumps(features)
        self.assertNotIn(str(self.facilities["unmapped"]), serialized_features)
        self.assertFalse(set(features[0]) & {"address", "street_address", "source_url", "evidence", "token"})
        status_tile_304, _, _ = _get(tile_url, {"If-None-Match": tile_etag})
        self.assertEqual(status_tile_304, 304)

        low_zoom_tiles = [tile for tile in map_artifact["tiles"] if tile["z"] == 0]
        low_features = []
        for low_zoom in low_zoom_tiles:
            low_url = f"{base}/api/v2/releases/{RELEASE_ID}/map/tiles/0/{low_zoom['x']}/{low_zoom['y']}.mvt?profile=official"
            low_status, _, low_body = _get(low_url)
            self.assertEqual(low_status, 200)
            low_name, features_on_tile = _decode_mvt(low_body)
            self.assertEqual(low_name, "uec_map")
            low_features.extend(features_on_tile)
        cluster = next(feature for feature in low_features if feature.get("kind") == "cluster")
        self.assertEqual(cluster.get("exact_count"), 2)
        self.assertEqual(cluster.get("next_zoom"), 1)
        self.assertNotIn("record_id", cluster)

        occupied = {(tile["z"], tile["x"], tile["y"]) for tile in map_artifact["tiles"]}
        missing = next((14, x, y) for x in range(1 << 14) for y in range(1 << 14) if (14, x, y) not in occupied)
        status_missing, _, missing_body = _get(f"{base}/api/v2/releases/{RELEASE_ID}/map/tiles/{missing[0]}/{missing[1]}/{missing[2]}.mvt?profile=official")
        self.assertEqual(status_missing, 404)
        self.assertEqual(json.loads(missing_body)["error"]["code"], "map_tile_not_found")
        status_wrong_profile, _, _ = _get(tile_url.replace("profile=official", "profile=secondary"))
        self.assertEqual(status_wrong_profile, 410)
        status_old_release, _, _ = _get(tile_url.replace(RELEASE_ID, "e2e-map-not-promoted"))
        self.assertEqual(status_old_release, 410)

        with psycopg.connect(self.env.database_url) as db:
            db.execute(
                "INSERT INTO uec.record_access_events (source_record_id,action,reason_category,policy_version,maintainer) "
                "VALUES (%s,'public_access_revoked','privacy','test-only','TEST-ONLY lifecycle test')",
                (self.records["exact-a"],),
            )
            current_generation = db.execute("SELECT generation FROM uec.public_suppression_generation").fetchone()[0]
        self.assertGreater(current_generation, self.generation)
        status_changed, changed_headers, changed_body = _get(manifest_url)
        self.assertEqual(status_changed, 200)
        changed_data = json.loads(changed_body)["data"]
        self.assertEqual(changed_data["suppression_generation"], current_generation)
        self.assertNotEqual(changed_headers["ETag"], headers["ETag"])
        status_changed_304, _, _ = _get(manifest_url, {"If-None-Match": changed_headers["ETag"]})
        self.assertEqual(status_changed_304, 304)
        status_revoked, _, revoked_body = _get(tile_url)
        self.assertEqual(status_revoked, 410)
        self.assertEqual(json.loads(revoked_body)["error"]["code"], "map_artifact_revoked")
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM uec.release_manifests WHERE release_id='e2e-map-unsafe-coordinate'").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
