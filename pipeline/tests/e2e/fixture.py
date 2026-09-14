"""Disposable PostGIS and backend fixture used by API E2E tests."""
import os
import socket
import subprocess
import tempfile
import shutil
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
import psycopg

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "docker-compose.e2e.yml"

def free_port():
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

class E2EEnvironment:
    def __init__(self):
        self.project = f"uec-e2e-{uuid.uuid4().hex[:8]}"
        self.db_port = free_port()
        self.api_port = free_port()
        while self.api_port == self.db_port:
            self.api_port = free_port()
        self.database_url = f"postgresql://uec:uec-e2e@localhost:{self.db_port}/uec"
        self.backend = None
        self.backend_log = None
        self.build_temp = tempfile.TemporaryDirectory(prefix="uec-e2e-cargo-")
        self.cargo_target_dir = Path(self.build_temp.name)
        self.cargo_cache_dir = ROOT / "target" / "e2e-cache"
        self.start_attempts = 0
        # Synthetic only: this token is scoped to the disposable test server.
        self.dev_preview_token = "uec-e2e-preview-token"
        self.test_release_id = None

    def command(self, *args):
        return ["docker", "compose", "-p", self.project, "-f", str(COMPOSE), *args]

    def compose_env(self):
        env = os.environ.copy(); env["UEC_E2E_DB_PORT"] = str(self.db_port); return env

    def start(self):
        try:
            print(f"[e2e] starting {self.project}", flush=True)
            startup = subprocess.run(self.command("up", "-d", "--wait"), cwd=ROOT, capture_output=True, text=True, env=self.compose_env())
            if startup.returncode:
                raise RuntimeError(f"Docker Compose startup failed (exit {startup.returncode})\n{startup.stdout}\n{startup.stderr}")
            migrations = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "pipeline/migrations").glob("*.sql")))
            print("[e2e] applying migrations", flush=True)
            for _ in range(60):
                # pg_isready only confirms that Postgres accepts connections;
                # during container bootstrap it may report ready before the
                # POSTGRES_DB database has been created. Query the target DB
                # directly so migrations never race initialization in CI.
                ready = subprocess.run(
                    self.command("exec", "-T", "postgres", "psql", "-U", "uec", "-d", "uec", "-c", "SELECT 1"),
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    env=self.compose_env(),
                ).returncode == 0
                if ready: break
                time.sleep(.25)
            else: raise RuntimeError("PostGIS container did not become ready")
            try:
                subprocess.run(self.command("exec", "-T", "postgres", "psql", "-U", "uec", "-d", "uec"), input=migrations.encode("utf-8"), cwd=ROOT, check=True, env=self.compose_env())
            except subprocess.CalledProcessError:
                # Docker Desktop can restart a freshly initialized PostGIS
                # container while the first large SQL stream is attached.
                # Recreate the disposable environment once; never retry a
                # partially applied migration set in place.
                if self.start_attempts < 1:
                    self.start_attempts += 1
                    self.stop()
                    time.sleep(1)
                    return self.start()
                raise
            print("[e2e] building backend", flush=True)
            build_env = os.environ.copy()
            build_env["CARGO_TARGET_DIR"] = str(self.cargo_cache_dir)
            subprocess.run(["cargo", "build", "--quiet"], cwd=ROOT, check=True, timeout=180, env=build_env)
            env = os.environ.copy(); env.update({"UEC_DATABASE_URL": self.database_url, "PORT": str(self.api_port), "UEC_RUNTIME_MODE": "development", "UEC_BIND_HOST": "127.0.0.1", "UEC_DEV_PREVIEW": "true", "UEC_DEV_PREVIEW_TOKEN": self.dev_preview_token})
            if self.test_release_id:
                env.update({"UEC_TEST_RELEASE_ID": self.test_release_id, "UEC_TEST_RELEASE_TOKEN": self.dev_preview_token})
            cached_binary = self.cargo_cache_dir / "debug/uec-api.exe"
            if not cached_binary.exists():
                cached_binary = self.cargo_cache_dir / "debug/uec-api"
            binary = self.cargo_target_dir / cached_binary.name
            shutil.copy2(cached_binary, binary)
            self.backend_log = (self.cargo_target_dir / f"e2e-{self.project}.log").open("w", encoding="utf-8")
            self.backend = subprocess.Popen([str(binary)], cwd=ROOT, env=env, stdout=self.backend_log, stderr=subprocess.STDOUT, text=True)
            print(f"[e2e] waiting for backend on {self.api_port}", flush=True)
            import urllib.error
            import urllib.request
            last_error = None
            for _ in range(80):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{self.api_port}/health/ready", timeout=1) as response:
                        if response.status == 200:
                            return self
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
                    last_error = repr(exc)
                    if self.backend.poll() is not None:
                        break
                    time.sleep(.25)
            exit_code = self.backend.poll() if self.backend else None
            log_path = self.backend_log.name if self.backend_log else None
            if self.backend_log:
                self.backend_log.flush()
                log_path = self.backend_log.name
                self.backend_log.close()
                self.backend_log = None
            log_text = Path(log_path).read_text(encoding="utf-8") if log_path else ""
            raise RuntimeError(
                f"backend did not become ready; last_error={last_error}; "
                f"exit_code={exit_code}; log_path={log_path}\n{log_text}"
            )
        except Exception:
            self.stop()
            raise

    def stop(self):
        if self.backend and self.backend.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(self.backend.pid), "/T", "/F"], check=False, capture_output=True)
            else:
                self.backend.terminate()
            self.backend.wait(timeout=10)
        if self.backend_log:
            self.backend_log.close()
            self.backend_log = None
        subprocess.run(self.command("down", "-v", "--remove-orphans"), cwd=ROOT, check=False, capture_output=True, text=True, env=self.compose_env())
        if self.build_temp:
            self.build_temp.cleanup()
            self.build_temp = None

    def seed_official_scenario(self):
        """Seed safe synthetic records for public API tests."""
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                db.execute("INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method) VALUES ('e2e.official','DK','Synthetic official source','https://example.invalid/official','fixture')")
                release = 'e2e-promoted'
                db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,summary) VALUES (%s,'promoted','e2e-v1','{}')", (release,))
                db.execute("INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256) VALUES ('e2e-promoted','{\"eligible_record_count\":3,\"manifest_version\":\"v1\",\"profile\":\"official\",\"release_id\":\"e2e-promoted\",\"ruleset_version\":\"e2e-v1\",\"source_ids\":[\"e2e.official\"]}', 'dcf1cb50c078057cac2527936332e35892c2c13ecdcf2f545176acd17897cde7')")
                city = 'Testby'
                db.execute("INSERT INTO uec.city_reference_points (country_code,city_name,reference_location,reference_source,source_retrieved_at,source_reference_id) VALUES ('DK',%s,ST_SetSRID(ST_MakePoint(10,55),4326)::geography,'https://example.invalid/cities',%s,'e2e-city')", (city, now))
                cases = [('exact','slaughter', 'accepted', True, True), ('city','fish_processing','review_required', False, True), ('unmapped','logistics_and_storage','unresolved', False, True), ('restricted','slaughter','accepted', True, True), ('unapproved','retail_and_prepared_food','accepted', True, False)]
                for name, category, status, has_point, approved in cases:
                    record = uuid.uuid4(); facility = uuid.uuid4(); observation = uuid.uuid4()
                    db.execute("INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,%s,%s,1,%s)", (uuid.uuid4(), f'e2e/{name}', uuid.uuid4().hex*2, now))
                    artifact = db.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE storage_key=%s", (f'e2e/{name}',)).fetchone()[0]
                    db.execute("INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,'e2e.official',%s,%s,'{}',%s)", (record,name,artifact,now))
                    db.execute("INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) VALUES (%s,%s,'DK',%s)", (facility, f'E2E {name}', city))
                    db.execute("INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at) VALUES (%s,%s,%s,%s,'{}','{}','e2e-v1','e2e',%s::text,'approved',true,%s)", (observation,facility,record,now,category,now))
                    db.execute("INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,true)", (release,facility,observation))
                    if has_point:
                        db.execute("INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at) VALUES (%s,'e2e','fixture','fixture',%s,1,ST_SetSRID(ST_MakePoint(12,56),4326)::geography,%s)", (record,status,now))
                    else:
                        db.execute("INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,attempt_number,queried_at) VALUES (%s,'e2e','fixture','fixture',%s,1,%s)", (record,status,now))
                    if name == 'restricted':
                        db.execute("INSERT INTO uec.record_access_events (source_record_id,action,reason_category,policy_version,maintainer) VALUES (%s,'public_access_revoked','privacy','ethics-v1','e2e')", (record,))
                    if approved:
                        db.execute("INSERT INTO uec.publication_review_events (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,'reviewed','passed','approved',true,'maintainer')", (record,))
                    if name == 'exact':
                        db.execute("INSERT INTO uec.facility_lifecycle_events (facility_id,status,effective_at,evidence_note) VALUES (%s,'active_observed',%s,'Synthetic official observation')", (facility, now))

    def create_failed_candidate(self):
        """Create an invalid candidate without touching the promoted release."""
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,summary) VALUES ('e2e-failed-candidate','candidate','e2e-v2','{}') ON CONFLICT (release_id) DO NOTHING")
                db.execute("INSERT INTO uec.validation_findings (severity,code,details) VALUES ('error','synthetic_failure','{}')")

    def seed_private_candidate_scenario(self):
        """Seed candidate-only data; review fields alone must not make it public.

        The fixture is disposable and synthetic. Its accepted coordinate and
        approval-shaped event intentionally test that release status remains a
        separate publication gate.
        """
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                db.execute("INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method) VALUES ('e2e.private-candidate','DK','Synthetic private candidate source','https://example.invalid/private-candidate','fixture')")
                db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,profile,test_only,summary) VALUES ('e2e-private-candidate','candidate','e2e-private-v1','official',true,'{}')")
                record, facility, observation, artifact = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
                db.execute("INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,'e2e/private-candidate',%s,1,%s)", (artifact, uuid.uuid4().hex * 2, now))
                db.execute("INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,'e2e.private-candidate','candidate-only',%s,'{}',%s)", (record, artifact, now))
                db.execute("INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) VALUES (%s,'E2E private candidate','DK','Candidateby')", (facility,))
                db.execute("INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,coordinate_review_status,first_observed_at) VALUES (%s,%s,%s,%s,'{}','{}','e2e-private-v1','e2e','slaughter','approved',true,'approved',%s)", (observation, facility, record, now, now))
                db.execute("INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES ('e2e-private-candidate',%s,%s,true)", (facility, observation))
                db.execute("INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at) VALUES (%s,'e2e','synthetic candidate','fixture','accepted',1,ST_SetSRID(ST_MakePoint(12,56),4326)::geography,%s)", (record, now))
                db.execute("INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,'e2e-private-candidate','reviewed','passed','approved',true,'maintainer')", (record,))
                # Same privacy/review state, but no coordinate decision: the
                # preview must omit it rather than treating geocoder success as clearance.
                pending_record, pending_facility, pending_observation, pending_artifact = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
                db.execute("INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,'e2e/private-candidate-pending',%s,1,%s)", (pending_artifact, uuid.uuid4().hex * 2, now))
                db.execute("INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,'e2e.private-candidate','candidate-pending',%s,'{}',%s)", (pending_record, pending_artifact, now))
                db.execute("INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) VALUES (%s,'E2E pending coordinate candidate','DK','Candidateby')", (pending_facility,))
                db.execute("INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at) VALUES (%s,%s,%s,%s,'{}','{}','e2e-private-v1','e2e','slaughter','approved',true,%s)", (pending_observation, pending_facility, pending_record, now, now))
                db.execute("INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES ('e2e-private-candidate',%s,%s,true)", (pending_facility, pending_observation))
                db.execute("INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at) VALUES (%s,'e2e','synthetic candidate','fixture','accepted',1,ST_SetSRID(ST_MakePoint(12,56),4326)::geography,%s)", (pending_record, now))
                db.execute("INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,'e2e-private-candidate','reviewed','passed','approved',true,'maintainer')", (pending_record,))
        self.private_candidate_facility_id = facility

    def restore_restricted_record(self):
        """Append a restoration event; the original evidence is unchanged."""
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                record = db.execute("SELECT source_record_id FROM uec.source_records WHERE source_record_key = 'restricted'").fetchone()[0]
                db.execute("INSERT INTO uec.record_access_events (source_record_id,action,reason_category,policy_version,maintainer) VALUES (%s,'public_access_restored','privacy','ethics-v1','e2e')", (record,))

    def seed_community_scenario(self):
        """Seed approved, screened-unreviewed, and unscreened community claims."""
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                db.execute("INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method,origin_type) VALUES ('e2e.community','DK','Synthetic community source','https://example.invalid/community','fixture','user_submitted')")
                db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) VALUES ('e2e-official-empty','promoted','official-v1','official','{}')")
                db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) VALUES ('e2e-community','promoted','community-v1','community','{}')")
                for name, review_state in (("eligible", "approved"), ("screened-unreviewed", "screened-unreviewed"), ("unscreened", "unscreened")):
                    record = uuid.uuid4(); facility = uuid.uuid4(); observation = uuid.uuid4(); artifact = uuid.uuid4()
                    db.execute("INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,%s,%s,1,%s)", (artifact, f'e2e-community/{name}', uuid.uuid4().hex*2, now))
                    db.execute("INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,'e2e.community',%s,%s,'{}',%s)", (record,name,artifact,now))
                    db.execute("INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) VALUES (%s,%s,'DK','Communityby')", (facility, f'E2E community {name}'))
                    db.execute("INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at) VALUES (%s,%s,%s,%s,'{}','{}','community-v1','e2e','slaughter','approved',true,%s)", (observation,facility,record,now,now))
                    db.execute("INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES ('e2e-community',%s,%s,true)", (facility,observation))
                    db.execute("INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at) VALUES (%s,'e2e','community fixture','fixture','accepted',1,ST_SetSRID(ST_MakePoint(12,56),4326)::geography,%s)", (record,now))
                    if review_state == "approved":
                        db.execute("INSERT INTO uec.publication_review_events (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role,note) VALUES (%s,'reviewed','passed','approved',true,'maintainer','Synthetic eligible claim')", (record,))
                    elif review_state == "screened-unreviewed":
                        db.execute("INSERT INTO uec.publication_review_events (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role,note) VALUES (%s,'unreviewed','passed','pending',true,NULL,'Synthetic screened but unreviewed claim')", (record,))

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()
