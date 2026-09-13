"""Disposable PostGIS and backend fixture used by API E2E tests."""
import os
import socket
import subprocess
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
import psycopg

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "docker-compose.e2e.yml"

def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

class E2EEnvironment:
    def __init__(self):
        self.project = f"uec-e2e-{uuid.uuid4().hex[:8]}"
        self.db_port = free_port()
        self.api_port = free_port()
        self.database_url = f"postgresql://uec:uec-e2e@localhost:{self.db_port}/uec"
        self.backend = None
        self.backend_log = None
        self.start_attempts = 0

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
                ready = subprocess.run(self.command("exec", "-T", "postgres", "pg_isready", "-U", "uec", "-d", "uec"), cwd=ROOT, capture_output=True, text=True, env=self.compose_env()).returncode == 0
                if ready: break
                time.sleep(.25)
            else: raise RuntimeError("PostGIS container did not become ready")
            try:
                subprocess.run(self.command("exec", "-T", "postgres", "psql", "-U", "uec", "-d", "uec"), input=migrations.encode("utf-8"), cwd=ROOT, check=True, env=self.compose_env())
            except subprocess.CalledProcessError as error:
                if error.returncode == 137 and self.start_attempts < 1:
                    self.start_attempts += 1
                    self.stop()
                    time.sleep(1)
                    return self.start()
                raise
            print("[e2e] building backend", flush=True)
            subprocess.run(["cargo", "build", "--quiet"], cwd=ROOT, check=True, timeout=180)
            env = os.environ.copy(); env.update({"UEC_DATABASE_URL": self.database_url, "PORT": str(self.api_port)})
            binary = ROOT / "target/debug/uec-api.exe"
            if not binary.exists():
                binary = ROOT / "target/debug/uec-api"
            self.backend_log = (ROOT / "target" / f"e2e-{self.project}.log").open("w", encoding="utf-8")
            self.backend = subprocess.Popen([str(binary)], cwd=ROOT, env=env, stdout=self.backend_log, stderr=subprocess.STDOUT, text=True)
            print(f"[e2e] waiting for backend on {self.api_port}", flush=True)
            import urllib.request
            for _ in range(80):
                try:
                    urllib.request.urlopen(f"http://localhost:{self.api_port}/api/v2/locations?limit=1", timeout=1)
                    return self
                except Exception:
                    time.sleep(.25)
            log_text = self.backend_log.read_text(encoding="utf-8") if self.backend_log else ""
            raise RuntimeError(f"backend did not become ready\n{log_text}")
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

    def seed_official_scenario(self):
        """Seed safe synthetic records for public API tests."""
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                db.execute("INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method) VALUES ('e2e.official','DK','Synthetic official source','https://example.invalid/official','fixture')")
                release = 'e2e-promoted'
                db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,summary) VALUES (%s,'promoted','e2e-v1','{}')", (release,))
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

    def restore_restricted_record(self):
        """Append a restoration event; the original evidence is unchanged."""
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                record = db.execute("SELECT source_record_id FROM uec.source_records WHERE source_record_key = 'restricted'").fetchone()[0]
                db.execute("INSERT INTO uec.record_access_events (source_record_id,action,reason_category,policy_version,maintainer) VALUES (%s,'public_access_restored','privacy','ethics-v1','e2e')", (record,))

    def seed_community_scenario(self):
        """Seed one eligible and one ineligible community claim."""
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                db.execute("INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method,origin_type) VALUES ('e2e.community','DK','Synthetic community source','https://example.invalid/community','fixture','user_submitted')")
                db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) VALUES ('e2e-official-empty','promoted','official-v1','official','{}')")
                db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) VALUES ('e2e-community','promoted','community-v1','community','{}')")
                for name, eligible in (("eligible", True), ("unreviewed", False)):
                    record = uuid.uuid4(); facility = uuid.uuid4(); observation = uuid.uuid4(); artifact = uuid.uuid4()
                    db.execute("INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,%s,%s,1,%s)", (artifact, f'e2e-community/{name}', uuid.uuid4().hex*2, now))
                    db.execute("INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,'e2e.community',%s,%s,'{}',%s)", (record,name,artifact,now))
                    db.execute("INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) VALUES (%s,%s,'DK','Communityby')", (facility, f'E2E community {name}'))
                    db.execute("INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at) VALUES (%s,%s,%s,%s,'{}','{}','community-v1','e2e','slaughter','approved',true,%s)", (observation,facility,record,now,now))
                    db.execute("INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES ('e2e-community',%s,%s,true)", (facility,observation))
                    db.execute("INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at) VALUES (%s,'e2e','community fixture','fixture','accepted',1,ST_SetSRID(ST_MakePoint(12,56),4326)::geography,%s)", (record,now))
                    if eligible:
                        db.execute("INSERT INTO uec.publication_review_events (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role,note) VALUES (%s,'reviewed','passed','approved',true,'maintainer','Synthetic eligible claim')", (record,))

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()
