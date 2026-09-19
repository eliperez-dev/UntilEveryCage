"""Disposable PostGIS and backend fixture used by API E2E tests."""
import os
import hashlib
import json
import socket
import subprocess
import tempfile
import shutil
import sys
import time
import uuid
import re
from pathlib import Path
from datetime import datetime, timezone
import psycopg

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "docker-compose.e2e.yml"

_READ_MODEL_SCRIPT = ROOT / "pipeline" / "scripts" / "maintenance" / "build_public_discovery_read_model.py"
_READ_MODEL_SPEC = None
_READ_MODEL_MODULE = None

MAX_START_ATTEMPTS = 2
_TRANSIENT_DATABASE_MARKERS = (
    "database system is shutting down",
    "database system is starting up",
    "could not connect to server",
    "connection refused",
    "server closed the connection unexpectedly",
)


def is_retryable_database_failure(output):
    """Return whether output describes a transient Postgres lifecycle failure.

    This deliberately excludes SQL/schema errors. Retrying those would hide a
    deterministic migration defect and would only produce a second failure.
    """
    text = output if isinstance(output, str) else str(output or "")
    lowered = text.lower()
    return any(marker in lowered for marker in _TRANSIENT_DATABASE_MARKERS)


class _RetryableStartupFailure(RuntimeError):
    """A bounded retry may recreate the disposable environment for this error."""


def _process_output(result):
    return "\n".join(part for part in (result.stdout, result.stderr) if part)


def _sanitize_diagnostics(text):
    """Keep Docker diagnostics useful without echoing credentials or URLs."""
    text = text or ""
    text = re.sub(r"(?i)postgres(?:ql)?://[^\s]+", "postgresql://[redacted]", text)
    text = re.sub(r"(?i)(password|token|secret)=([^\s]+)", r"\1=[redacted]", text)
    return text[-12000:]

def _read_model_builder():
    global _READ_MODEL_SPEC, _READ_MODEL_MODULE
    if _READ_MODEL_MODULE is None:
        import importlib.util
        _READ_MODEL_SPEC = importlib.util.spec_from_file_location("build_public_discovery_read_model", _READ_MODEL_SCRIPT)
        _READ_MODEL_MODULE = importlib.util.module_from_spec(_READ_MODEL_SPEC)
        assert _READ_MODEL_SPEC.loader
        _READ_MODEL_SPEC.loader.exec_module(_READ_MODEL_MODULE)
    return _READ_MODEL_MODULE

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
        self.private_graph_token = "uec-e2e-private-graph-token"
        self.test_release_id = None

    def _ensure_build_temp(self):
        """Recreate per-run paths after a failed-start cleanup before retrying."""
        if self.build_temp is None:
            self.build_temp = tempfile.TemporaryDirectory(prefix="uec-e2e-cargo-")
            self.cargo_target_dir = Path(self.build_temp.name)

    def command(self, *args):
        return ["docker", "compose", "-p", self.project, "-f", str(COMPOSE), *args]

    def compose_env(self):
        env = os.environ.copy(); env["UEC_E2E_DB_PORT"] = str(self.db_port); return env

    def _rotate_attempt(self):
        """Give a retry a new Compose identity, ports, container, and volume."""
        self.project = f"uec-e2e-{uuid.uuid4().hex[:8]}"
        self.db_port = free_port()
        self.api_port = free_port()
        while self.api_port == self.db_port:
            self.api_port = free_port()
        self.database_url = f"postgresql://uec:uec-e2e@localhost:{self.db_port}/uec"

    def _container_diagnostics(self):
        """Return bounded, redacted diagnostics before failed cleanup removes state."""
        parts = []
        for args in (("ps", "--all"), ("logs", "--no-color", "--tail", "120", "postgres")):
            try:
                result = subprocess.run(
                    self.command(*args),
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=self.compose_env(),
                )
                output = _sanitize_diagnostics(_process_output(result))
                if output:
                    parts.append(f"$ docker compose {' '.join(args)}\n{output}")
            except OSError as exc:
                parts.append(f"$ docker compose {' '.join(args)}\n{type(exc).__name__}: unavailable")
        return "\n".join(parts) or "(no container diagnostics available)"

    def _database_ready(self):
        result = subprocess.run(
            self.command(
                "exec", "-T", "postgres", "psql", "-At", "-U", "uec", "-d", "uec",
                "-c", "SELECT pg_postmaster_start_time()",
            ),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=self.compose_env(),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result
        return result

    def _start_once(self, files, wait_for_ready, schema_preflight):
        self._ensure_build_temp()
        print(f"[e2e] starting {self.project}", flush=True)
        startup = subprocess.run(self.command("up", "-d", "--wait"), cwd=ROOT, capture_output=True, text=True, env=self.compose_env())
        if startup.returncode:
            output = _process_output(startup)
            if is_retryable_database_failure(output):
                raise _RetryableStartupFailure(f"Docker Compose startup transiently failed (exit {startup.returncode})")
            raise RuntimeError(f"Docker Compose startup failed (exit {startup.returncode})\n{_sanitize_diagnostics(output)}")
        print("[e2e] applying migrations", flush=True)
        stable_postmaster = None
        stable_checks = 0
        last_ready = None
        for _ in range(120):
            # pg_isready only confirms that Postgres accepts connections;
            # during container bootstrap it may report ready before the
            # POSTGRES_DB database has been created. Query the target DB
            # directly so migrations never race initialization in CI. The
            # image can still replace its temporary bootstrap server after
            # the first successful query, so require the same postmaster
            # start time across several checks before attaching migrations.
            ready = self._database_ready()
            last_ready = ready
            if ready.returncode == 0 and (ready.stdout or "").strip():
                postmaster = ready.stdout.strip()
                if postmaster == stable_postmaster:
                    stable_checks += 1
                else:
                    stable_postmaster = postmaster
                    stable_checks = 1
                if stable_checks >= 3:
                    break
            else:
                stable_postmaster = None
                stable_checks = 0
            time.sleep(.25)
        else:
            if last_ready and is_retryable_database_failure(_process_output(last_ready)):
                raise _RetryableStartupFailure("Postgres did not stabilize before migrations")
            raise RuntimeError("PostGIS container did not become ready")
        # Apply files one at a time. A transient Postgres restart is retryable;
        # all SQL/schema errors remain deterministic and fail immediately.
        for migration in files:
            print(f"[e2e] applying {migration.name}", flush=True)
            result = subprocess.run(
                self.command("exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", "uec", "-d", "uec"),
                input=migration.read_text(encoding="utf-8"),
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                env=self.compose_env(),
            )
            if result.stdout:
                print(result.stdout, end="", flush=True)
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr, flush=True)
            if result.returncode:
                output = _process_output(result)
                if is_retryable_database_failure(output):
                    raise _RetryableStartupFailure(
                        f"migration {migration.name} hit a transient Postgres lifecycle failure"
                    )
                raise subprocess.CalledProcessError(
                    result.returncode,
                    result.args,
                    output=result.stdout,
                    stderr=result.stderr,
                )
        # Revalidate the database after migration application so a container
        # that restarted at the boundary cannot launch a backend against an
        # unstable database.
        final_ready = self._database_ready()
        if final_ready.returncode != 0 or not (final_ready.stdout or "").strip():
            output = _process_output(final_ready)
            if is_retryable_database_failure(output):
                raise _RetryableStartupFailure("Postgres became unavailable after migrations")
            raise RuntimeError(f"PostGIS database failed post-migration readiness\n{_sanitize_diagnostics(output)}")
        if schema_preflight:
            required = {
                "facilities",
                "organizations",
                "organization_relationship_observations",
                "claim_current",
                "source_entity_crosswalks",
                "source_records",
            }
            with psycopg.connect(self.database_url) as db:
                names = {
                    row[0]
                    for row in db.execute(
                        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='uec' AND c.relkind IN ('r','p','v','m','f')"
                    ).fetchall()
                }
                missing = sorted(required - names)
                if missing:
                    raise RuntimeError(
                        f"database/schema preflight failed; missing={missing}"
                    )
        print("[e2e] building backend", flush=True)
        build_env = os.environ.copy()
        build_env["CARGO_TARGET_DIR"] = str(self.cargo_cache_dir)
        subprocess.run(["cargo", "build", "--quiet"], cwd=ROOT, check=True, timeout=180, env=build_env)
        env = os.environ.copy(); env.update({"UEC_DATABASE_URL": self.database_url, "PORT": str(self.api_port), "UEC_RUNTIME_MODE": "development", "UEC_BIND_HOST": "127.0.0.1", "UEC_DEV_PREVIEW": "true", "UEC_DEV_PREVIEW_TOKEN": self.dev_preview_token, "UEC_PRIVATE_GRAPH_TOKEN": self.private_graph_token})
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
        if not wait_for_ready:
            return self
        import urllib.error
        import urllib.request
        last_error = None
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.api_port}/health/ready", timeout=1) as response:
                    payload = json.load(response)
                    if response.status == 200 and payload.get("schema") == "migrated":
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

    def start(self, migration_files=None, wait_for_ready=True, schema_preflight=True):
        files = tuple(migration_files if migration_files is not None else sorted((ROOT / "pipeline/migrations").glob("*.sql")))
        for attempt in range(MAX_START_ATTEMPTS):
            self.start_attempts = attempt + 1
            try:
                return self._start_once(files, wait_for_ready, schema_preflight)
            except _RetryableStartupFailure as exc:
                diagnostics = self._container_diagnostics()
                self.stop()
                if attempt + 1 >= MAX_START_ATTEMPTS:
                    raise RuntimeError(
                        f"E2E startup exhausted {MAX_START_ATTEMPTS} isolated attempts: {exc}\n"
                        f"sanitized container diagnostics:\n{diagnostics}"
                    ) from exc
                print(
                    f"[e2e] transient startup failure; cleaning {self.project} and rotating the next attempt",
                    flush=True,
                )
                self._rotate_attempt()
                time.sleep(1)
            except Exception:
                self.stop()
                raise

    def wait_for_listening(self, timeout=20):
        """Wait for the backend socket without requiring schema readiness."""
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            if self.backend and self.backend.poll() is not None:
                if self.backend_log:
                    self.backend_log.flush()
                    log_path = Path(self.backend_log.name)
                    log_text = log_path.read_text(encoding="utf-8")
                else:
                    log_text = ""
                raise RuntimeError(
                    f"backend exited before listening; exit_code={self.backend.returncode}\n{log_text}"
                )
            try:
                with socket.create_connection(("127.0.0.1", self.api_port), timeout=1):
                    return
            except OSError as exc:
                last_error = repr(exc)
                time.sleep(.1)
        raise RuntimeError(
            f"backend did not start listening within {timeout}s; last_error={last_error}"
        )

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
        restricted_record = None
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                db.execute("INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method,attribution) VALUES ('e2e.official','DK','Synthetic official source','https://example.invalid/official','fixture','Synthetic fixture attribution')")
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
                        restricted_record = record
                    if approved:
                        db.execute("INSERT INTO uec.publication_review_events (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,'reviewed','passed','approved',true,'maintainer')", (record,))
                    if name == 'exact':
                        db.execute("INSERT INTO uec.facility_lifecycle_events (facility_id,status,effective_at,evidence_note) VALUES (%s,'active_observed',%s,'Synthetic official observation')", (facility, now))
        self.build_public_read_model('e2e-promoted')
        # Build from the public projection before the synthetic restriction is
        # appended. The read view still applies the restriction live, and an
        # explicit restoration can therefore be tested without storing a
        # private row in the component.
        with psycopg.connect(self.database_url) as db:
            db.execute("INSERT INTO uec.record_access_events (source_record_id,action,reason_category,policy_version,maintainer) VALUES (%s,'public_access_revoked','privacy','ethics-v1','e2e')", (restricted_record,))

    def build_public_read_model(self, release_id):
        """Activate a synthetic model through the same atomic operator flow."""
        self._seed_synthetic_rights_decisions(release_id)
        return _read_model_builder().build(self.database_url, release_id)

    def _seed_synthetic_rights_decisions(self, release_id):
        """Record exact rights decisions for this disposable release.

        Migration 041 scopes each decision to the immutable source artifact
        and release profile. Synthetic E2E data can provide an attributable
        cleared decision for every release member before a model build or
        export gate is exercised.
        """
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                db.execute(
                    """
                    INSERT INTO uec.source_rights_decisions (
                        source_id, profile, release_id, artifact_id,
                        artifact_sha256, redistribution_status, decision_actor,
                        decision_reference, decided_at
                    )
                    SELECT DISTINCT
                        source.source_id,
                        release.profile,
                        release.release_id,
                        artifact.artifact_id,
                        artifact.sha256,
                        'cleared',
                        'synthetic-e2e-fixture',
                        'synthetic rights fixture',
                        %s
                    FROM uec.release_members member
                    JOIN uec.releases release
                      ON release.release_id = member.release_id
                    JOIN uec.observations observation
                      ON observation.observation_id = member.observation_id
                    JOIN uec.source_records record
                      ON record.source_record_id = observation.source_record_id
                    JOIN uec.sources source
                      ON source.source_id = record.source_id
                    JOIN uec.raw_artifacts artifact
                      ON artifact.artifact_id = record.artifact_id
                    WHERE member.release_id = %s
                      AND member.default_visible = true
                      AND NOT EXISTS (
                          SELECT 1
                          FROM uec.source_rights_decisions existing
                          WHERE existing.source_id = source.source_id
                            AND existing.profile = release.profile
                            AND existing.release_id = release.release_id
                            AND existing.artifact_id = artifact.artifact_id
                            AND existing.artifact_sha256 = artifact.sha256
                      )
                    """,
                    (now, release_id),
                )

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
        self._seed_synthetic_rights_decisions('e2e-private-candidate')

    def seed_private_graph_scenario(self):
        """Seed a bounded synthetic graph for authenticated HTTP contract tests."""
        now = datetime.now(timezone.utc)
        source_id = f"e2e.private-graph.{uuid.uuid4().hex}"
        artifact_id = uuid.uuid4()
        record_id = uuid.uuid4()
        organization_a, organization_b, organization_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        facility_one, facility_two = uuid.uuid4(), uuid.uuid4()
        with psycopg.connect(self.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method) VALUES (%s,'US','Synthetic private graph source','https://example.invalid/private-graph','fixture')",
                    (source_id,),
                )
                db.execute(
                    "INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,%s,%s,1,%s)",
                    (artifact_id, f"e2e/private-graph/{artifact_id}", uuid.uuid4().hex * 2, now),
                )
                db.execute(
                    "INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at,source_state) VALUES (%s,%s,'private-graph',%s,'{}',%s,'rejected')",
                    (record_id, source_id, artifact_id, now),
                )
                db.execute(
                    "INSERT INTO uec.organizations (organization_id,canonical_name,country_code) VALUES (%s,'Synthetic graph A','US'),(%s,'Synthetic graph B','US'),(%s,'Synthetic graph C','US')",
                    (organization_a, organization_b, organization_c),
                )
                db.execute(
                    "INSERT INTO uec.facilities (facility_id,canonical_name,country_code) VALUES (%s,'Synthetic graph facility one','US'),(%s,'Synthetic graph facility two','US')",
                    (facility_one, facility_two),
                )
                edges = [
                    (organization_a, None, organization_b, "operator", 0.8750, now),
                    (organization_b, None, organization_a, "owner", 0.6250, now.replace(microsecond=max(0, now.microsecond - 1))),
                    (organization_b, facility_one, None, "supplier", None, now.replace(microsecond=max(0, now.microsecond - 2))),
                    (organization_c, None, organization_b, "parent", 1.0, now.replace(microsecond=max(0, now.microsecond - 3))),
                    (organization_a, facility_two, None, "customer", 0.5, now.replace(microsecond=max(0, now.microsecond - 4))),
                ]
                for from_id, target_facility, target_org, relationship_type, confidence, observed_at in edges:
                    db.execute(
                        "INSERT INTO uec.organization_relationship_observations (source_id,source_record_id,from_organization_id,target_facility_id,target_organization_id,relationship_type,observed_at,confidence,review_state,storage_state,privacy_status,publication_status,note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'review_required','private','suppressed','not_eligible','synthetic private note')",
                        (source_id, record_id, from_id, target_facility, target_org, relationship_type, observed_at, confidence),
                    )
        self.private_graph_ids = {
            "organization_a": str(organization_a),
            "organization_b": str(organization_b),
            "organization_c": str(organization_c),
            "facility_one": str(facility_one),
            "facility_two": str(facility_two),
        }

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
            for release_id, profile, count in (
                ('e2e-official-empty', 'official', 0),
                ('e2e-community', 'community', 2),
            ):
                manifest = {
                    'eligible_record_count': count,
                    'manifest_version': 'v1',
                    'profile': profile,
                    'release_id': release_id,
                    'ruleset_version': f'{profile}-v1',
                    'source_ids': ['e2e.community'] if profile == 'community' else [],
                }
                serialized = json.dumps(manifest, sort_keys=True, separators=(',', ':'))
                db.execute(
                    "INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256) VALUES (%s,%s::jsonb,%s)",
                    (release_id, serialized, hashlib.sha256(serialized.encode()).hexdigest()),
                )
        self.build_public_read_model('e2e-official-empty')
        self.build_public_read_model('e2e-community')

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()
