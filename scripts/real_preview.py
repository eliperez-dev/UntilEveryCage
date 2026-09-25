#!/usr/bin/env python3
"""Lifecycle for the private, disposable real V2 local preview."""
from __future__ import annotations

import json
import contextlib
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROJECT = os.environ.get("UEC_REAL_PREVIEW_PROJECT", "uec-real-preview-e2e-source")
VOLUME = os.environ.get("UEC_REAL_PREVIEW_VOLUME", "uec-real-preview-e2e-source-postgres")
DB_PORT = int(os.environ.get("UEC_REAL_PREVIEW_DB_PORT", "55433"))
API_PORT = int(os.environ.get("UEC_REAL_PREVIEW_API_PORT", "38001"))
WEB_PORT = int(os.environ.get("UEC_REAL_PREVIEW_WEB_PORT", "34174"))
PRIVATE_ROOT = Path(os.environ.get("UEC_REAL_PREVIEW_ROOT", r"D:\UntilEveryCage-private"))
SESSION_TOKEN: str | None = None
IMPORTER = ROOT / "pipeline" / "scripts" / "maintenance" / "import-real-preview.py"
MIGRATIONS = ROOT / "pipeline" / "scripts" / "maintenance" / "apply-migrations.py"
ACTIVE_PREVIEW_TOKEN: str | None = None


class PreviewError(RuntimeError):
    pass


def _runtime_dir() -> Path:
    """Return project-scoped local secrets/state without breaking the legacy default."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", PROJECT):
        raise PreviewError("real-preview project name is invalid")
    base = ROOT / "target" / "real-preview"
    if PROJECT == "uec-real-preview-e2e-source":
        return base
    return base / "projects" / PROJECT


def _legacy_state_for_project() -> Path | None:
    legacy = ROOT / "target" / "real-preview" / "processes.json"
    if legacy == _state() or not legacy.is_file():
        return None
    try:
        value = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return legacy if isinstance(value, dict) and value.get("project") == PROJECT else None


@contextlib.contextmanager
def source_lock(source_id: str):
    if not source_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for ch in source_id):
        raise PreviewError("invalid source identifier")
    lock_dir = ROOT / "target" / "real-preview" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    handle = (lock_dir / f"{source_id}.lock").open("a+b")
    try:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            raise PreviewError("source refresh already running") from None
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()


def _local_database_url() -> str:
    configured = os.environ.get("UEC_DATABASE_URL")
    if configured:
        from urllib.parse import urlsplit
        parsed = urlsplit(configured)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise PreviewError("preview refresh accepts only a loopback database")
        return configured
    password = _password(create=False)
    if not password:
        raise PreviewError("preview database password is missing")
    verify_resources(require_container=True)
    if not _socket_busy(DB_PORT):
        raise PreviewError("owned preview database is not accepting local connections")
    from urllib.parse import quote
    return f"postgresql://uec:{quote(password, safe='')}@127.0.0.1:{DB_PORT}/uec?sslmode=disable"


def compose(*args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["UEC_REAL_PREVIEW_DB_PORT"] = str(DB_PORT)
    env["UEC_REAL_PREVIEW_VOLUME"] = VOLUME
    db_password = _password(create=False)
    if db_password:
        env["POSTGRES_PASSWORD"] = db_password
    return subprocess.run(["docker", "compose", "-p", PROJECT, "-f", str(ROOT / "docker-compose.real-preview.yml"), *args], cwd=ROOT, env=env, capture_output=capture, text=True)


def _password(*, create: bool) -> str | None:
    path = _runtime_dir() / "db-password"
    if not path.is_file():
        # One-time compatibility for a stack started before runtime files became
        # project-scoped. Only accept it when this exact project owns a legacy
        # process marker, Docker container, or exact labeled persistent volume.
        legacy = ROOT / "target" / "real-preview" / "db-password"
        legacy_state = _legacy_state_for_project()
        try:
            owns_container = bool(_docker_json(["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{json .}}"]))
        except PreviewError:
            owns_container = False
        try:
            owned_volumes = _docker_json(["docker", "volume", "ls", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{json .}}"])
        except PreviewError:
            owned_volumes = []
        owns_volume = any(item.get("Name") == VOLUME and f"com.docker.compose.project={PROJECT}" in str(item.get("Labels", "")) for item in owned_volumes)
        if legacy.is_file() and (legacy_state is not None or owns_container or owns_volume):
            password = legacy.read_text(encoding="ascii").strip()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(password, encoding="ascii")
            if os.name != "nt":
                path.chmod(0o600)
            return password
    if path.is_file():
        return path.read_text(encoding="ascii").strip()
    if not create:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(32)
    path.write_text(value, encoding="ascii")
    if os.name != "nt":
        path.chmod(0o600)
    return value


def _socket_busy(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _docker_json(args: list[str]) -> list[dict[str, object]]:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise PreviewError("Docker ownership inspection failed")
    try:
        return [json.loads(line) for line in result.stdout.splitlines() if line]
    except json.JSONDecodeError as exc:
        raise PreviewError("Docker returned invalid ownership metadata") from exc


def verify_resources(*, require_container: bool = False) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", VOLUME):
        raise PreviewError("real-preview volume name is invalid")
    containers = _docker_json(["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{json .}}"])
    for item in containers:
        labels = item.get("Labels", "")
        if (f"com.docker.compose.project={PROJECT}" not in str(labels)
                or "com.docker.compose.service=postgres" not in str(labels)
                or item.get("Names") != f"{PROJECT}-postgres-1"):
            raise PreviewError("refusing to operate on a container without exact real-preview ownership markers")
    if require_container and not containers:
        raise PreviewError("owned preview database container is absent")
    volumes = _docker_json(["docker", "volume", "ls", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{json .}}"])
    for item in volumes:
        labels = item.get("Labels", "")
        name = item.get("Name")
        if name != VOLUME or f"com.docker.compose.project={PROJECT}" not in str(labels):
            raise PreviewError("refusing to operate on an ambiguously owned volume")


def _state() -> Path:
    return _runtime_dir() / "processes.json"


def _read_state() -> dict[str, object]:
    path = _state()
    legacy = _legacy_state_for_project()
    if not path.exists() and legacy is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        legacy.replace(path)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreviewError("real-preview process state is malformed; inspect it before cleanup") from exc
    if not isinstance(value, dict) or value.get("project") != PROJECT:
        raise PreviewError("real-preview process state has invalid ownership markers")
    return value


def _write_state(value: dict[str, object]) -> None:
    path = _state()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _process_owned(pid: int, marker: str) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if not ps:
            return False
        script = f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' -ErrorAction SilentlyContinue; if($p){{ $p.CommandLine }}"
        r = subprocess.run([ps, "-NoProfile", "-Command", script], capture_output=True, text=True)
        command = r.stdout.lower()
    else:
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").lower()
        except OSError:
            return False
    return marker.lower() in command


def _http(url: str, token: str | None = None) -> tuple[int | None, dict[str, object] | None]:
    headers = {"X-UEC-Dev-Preview-Token": token} if token else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=3) as response:
            data = json.loads(response.read()) if "json" in response.headers.get("Content-Type", "") else None
            return response.status, data if isinstance(data, dict) else None
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None, None


def _http_status(url: str, token: str | None = None) -> int | None:
    headers = {"X-UEC-Dev-Preview-Token": token} if token else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=3) as response:
            response.read()
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (OSError, urllib.error.URLError):
        return None


def _italy_acquisition_evidence(source_dir: Path, source_id: str, run_id: str) -> dict[str, object]:
    """Return row-free official acquisition provenance for the runtime ledger."""
    path = source_dir / "acquisition" / source_id / run_id / "acquisition-metadata.json"
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise PreviewError("Italy acquisition metadata is unavailable for runtime ledger reconciliation") from None
    if (not isinstance(metadata, dict) or metadata.get("source_id") != source_id
            or metadata.get("run_id") != run_id or metadata.get("catalog_url") is None
            or metadata.get("final_url") is None or metadata.get("retrieved_at_utc") is None
            or metadata.get("adapter_version") is None or metadata.get("config_version") is None):
        raise PreviewError("Italy acquisition metadata does not match the exact preview run")
    raw_sha256 = metadata.get("sha256")
    catalog_sha256 = metadata.get("catalog_sha256")
    byte_size = metadata.get("byte_size")
    if (not isinstance(raw_sha256, str) or len(raw_sha256) != 64
            or any(character not in "0123456789abcdef" for character in raw_sha256.lower())
            or not isinstance(catalog_sha256, str) or len(catalog_sha256) != 64
            or any(character not in "0123456789abcdef" for character in catalog_sha256.lower())
            or not isinstance(byte_size, int) or byte_size <= 0):
        raise PreviewError("Italy acquisition metadata has invalid content digests")
    return {
        "source_id": source_id,
        "run_id": run_id,
        "catalog_url": metadata["catalog_url"],
        "catalog_final_url": metadata.get("catalog_final_url"),
        "catalog_sha256": catalog_sha256,
        "artifact_url": metadata["final_url"],
        "retrieved_at_utc": metadata["retrieved_at_utc"],
        "requested_at_utc": metadata.get("requested_at_utc"),
        "raw_sha256": raw_sha256,
        "raw_byte_size": byte_size,
        "publication_date": metadata.get("filename_publication_date"),
        "adapter_version": metadata["adapter_version"],
        "config_version": metadata["config_version"],
    }


def prerequisites() -> None:
    missing = [name for name in ("docker", "cargo") if not shutil.which(name)]
    frontend = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    if frontend.is_file():
        missing.extend(name for name in ("node",) if not shutil.which(name))
    if shutil.which("docker") and subprocess.run(["docker", "compose", "version"], capture_output=True).returncode:
        missing.append("docker compose")
    if missing:
        raise PreviewError("missing prerequisites: " + ", ".join(missing))
    if not PRIVATE_ROOT.is_dir():
        raise PreviewError("private preview handoff root is unavailable")
    if not IMPORTER.is_file():
        raise PreviewError("lane 1 importer is not installed; expected pipeline/scripts/maintenance/import-real-preview.py")
    verify_resources()
    owned_containers = _docker_json(["docker", "ps", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{json .}}"])
    owned_database_running = any(item.get("Names") == f"{PROJECT}-postgres-1" for item in owned_containers)
    for port in (DB_PORT, API_PORT, *([WEB_PORT] if frontend.is_file() else [])):
        if _socket_busy(port) and not (port == DB_PORT and owned_database_running):
            raise PreviewError(f"required loopback port {port} is occupied by a foreign service")


def _run_checked(args: list[str], env: dict[str, str], label: str) -> str:
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode:
        # Child command output can contain addresses or other source fields; only
        # expose stable, allowlisted error codes to the scheduler's stderr.
        code = None
        try:
            for output in (result.stdout, result.stderr):
                candidate = json.loads(output).get("error_code")
                if isinstance(candidate, str) and candidate.replace("_", "").isalnum():
                    code = candidate
                    break
        except (json.JSONDecodeError, AttributeError):
            pass
        if code is None:
            diagnostic = (result.stdout + "\n" + result.stderr).lower()
            if "password authentication failed" in diagnostic:
                code = "database_authentication_failed"
            elif "connection refused" in diagnostic:
                code = "database_connection_refused"
            elif "timed out" in diagnostic or "timeout expired" in diagnostic:
                code = "database_connection_timed_out"
            elif "operationalerror" in diagnostic or "could not connect" in diagnostic:
                code = "database_connection_failed"
            elif "permissionerror" in diagnostic or "access is denied" in diagnostic:
                code = "local_permission_failed"
            elif "modulenotfounderror" in diagnostic or "no module named" in diagnostic:
                code = "python_dependency_missing"
            elif "undefinedtable" in diagnostic or "syntaxerror" in diagnostic or "programmingerror" in diagnostic:
                code = "database_migration_rejected"
        suffix = f" (code={code})" if code else ""
        raise PreviewError(f"{label} failed{suffix}; private details were not emitted")
    return result.stdout


def _build_api() -> None:
    # Let rustup/toolchain discovery use the invoking shell while building.
    # The long-lived API below still receives only its documented runtime env.
    result = subprocess.run([shutil.which("cargo") or "cargo", "build", "--quiet", "--bin", "uec-api"], cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True)
    if result.returncode:
        raise PreviewError("local API build failed; see private local diagnostic output")


def up() -> dict[str, object]:
    global SESSION_TOKEN, ACTIVE_PREVIEW_TOKEN
    prerequisites()
    token = secrets.token_urlsafe(32)
    SESSION_TOKEN = token
    ACTIVE_PREVIEW_TOKEN = token
    password = _password(create=True)
    assert password is not None
    db_url = f"postgresql://uec:{password}@127.0.0.1:{DB_PORT}/uec?sslmode=disable"
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "HOME": os.environ.get("HOME", ""),
           "UEC_DATABASE_URL": db_url, "UEC_DEV_PREVIEW_TOKEN": token, "UEC_RUNTIME_MODE": "development", "UEC_DEV_PREVIEW": "true",
           "UEC_BIND_HOST": "127.0.0.1", "PORT": str(API_PORT), "UEC_CORS_ORIGIN": f"http://127.0.0.1:{WEB_PORT}",
           "UEC_REAL_PREVIEW_ROOT": str(PRIVATE_ROOT), "UEC_PREVIEW_PROJECT": PROJECT,
           "UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP": os.environ.get("UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP", "0")}
    for key in ("TMP", "TEMP", "USERPROFILE", "CARGO_HOME", "RUSTUP_HOME", "LIB", "INCLUDE", "VCToolsInstallDir", "WindowsSdkDir"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    started: list[subprocess.Popen[str]] = []
    try:
        result = compose("up", "-d", "--wait")
        if result.returncode:
            raise PreviewError("isolated preview database failed to start")
        verify_resources(require_container=True)
        _run_checked([sys.executable, str(MIGRATIONS), "--database-url", db_url], env, "preview migrations")
        if env.get("UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP") == "1" and not any(PRIVATE_ROOT.iterdir()):
            # An explicitly empty local workspace is valid for source-first
            # acquisition: it must never be populated with fixtures or stale
            # artifacts just to make the preview server start.
            summary = {"status": "imported", "observation_count": 0,
                       "source_scoped_candidate_count": 0, "numeric_coordinate_count": 0,
                       "city_postal_count": 0, "public_release_count": 0,
                       "public_projection_count": 0}
        else:
            output = _run_checked([sys.executable, str(IMPORTER), "--root", str(PRIVATE_ROOT), "--database-url-env", "UEC_DATABASE_URL", "--json"], env, "private preview import")
            try:
                summary = json.loads(output)
                if not isinstance(summary, dict) or summary.get("status") != "imported" or not isinstance(summary.get("observation_count"), int):
                    raise ValueError
            except (ValueError, json.JSONDecodeError) as exc:
                raise PreviewError("lane 1 importer violated the aggregate-only JSON contract") from exc
        _build_api()
        api_log = (ROOT / "target" / "real-preview" / "api.log").open("a", encoding="utf-8")
        executable = ROOT / "target" / "debug" / ("uec-api.exe" if os.name == "nt" else "uec-api")
        api = subprocess.Popen([str(executable)], cwd=ROOT, env=env, stdout=api_log, stderr=subprocess.STDOUT)
        api_log.close(); started.append(api)
        vite_path = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
        vite = None
        if vite_path.is_file():
            vite_log = (ROOT / "target" / "real-preview" / "vite.log").open("a", encoding="utf-8")
            # The preview token is consumed only by vite.config.ts's dev-server
            # proxy. Do not expose it through VITE_* variables (which Vite
            # publishes to the client bundle), URLs, or browser storage.
            vite_env = {"PATH": env["PATH"], "SYSTEMROOT": env["SYSTEMROOT"],
                        "UEC_DEV_PREVIEW_TOKEN": token,
                        "VITE_LOCAL_DATA_MODE": "real-preview",
                        "VITE_API_ORIGIN": f"http://127.0.0.1:{API_PORT}"}
            vite = subprocess.Popen([shutil.which("node") or "node", str(vite_path), "--host", "127.0.0.1", "--port", str(WEB_PORT), "--strictPort"], cwd=ROOT / "frontend", env=vite_env, stdout=vite_log, stderr=subprocess.STDOUT)
            vite_log.close(); started.append(vite)
        _write_state({"project": PROJECT, "api_pid": api.pid, "vite_pid": vite.pid if vite else None, "ports": [API_PORT, WEB_PORT] if vite else [API_PORT]})
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if api.poll() is not None or (vite is not None and vite.poll() is not None):
                raise PreviewError("preview process exited during startup")
            api_ready = _http(f"http://127.0.0.1:{API_PORT}/health/ready")[0] == 200
            frontend_ready = vite is None or _http_status(f"http://127.0.0.1:{WEB_PORT}/") == 200
            if api_ready and frontend_ready:
                break
            time.sleep(.3)
        else:
            raise PreviewError("preview startup probe timed out")
        counts_url = f"http://127.0.0.1:{API_PORT}/dev/real-preview/counts"
        if _http_status(counts_url) != 401:
            raise PreviewError("real-preview API authentication check failed")
        auth_status, payload = _http(counts_url, token)
        api_counts = payload.get("data") if payload else None
        if auth_status != 200 or not isinstance(api_counts, dict):
            raise PreviewError("authenticated real-preview API count probe failed")
        expected_api_counts = {
            "facility_candidate_count": summary.get("source_scoped_candidate_count"),
            "numeric_coordinate_count": summary.get("numeric_coordinate_count"),
            "city_postal_count": summary.get("city_postal_count"),
        }
        if any(api_counts.get(key) != value for key, value in expected_api_counts.items()):
            raise PreviewError("authenticated API aggregates differ from importer output")
        list_status, page = _http(f"{counts_url.rsplit('/', 1)[0]}/locations?limit=1", token)
        page_data = page.get("data") if page else None
        if list_status != 200 or not isinstance(page_data, list):
            raise PreviewError("authenticated real-preview candidate list probe failed")
        if not page_data and summary.get("source_scoped_candidate_count") == 0:
            return {"status": "backend_ready_frontend_unavailable" if vite is None else "ready",
                    "api_url": f"http://127.0.0.1:{API_PORT}",
                    "url": f"http://127.0.0.1:{WEB_PORT}/" if vite else None,
                    "aggregates": summary, "api_auth_check": "passed",
                    "authenticated_api_counts": api_counts,
                    "candidate_list_detail_check": "passed-empty-private-preview",
                    "public_release_count": summary.get("public_release_count"),
                    "public_projection_count": summary.get("public_projection_count")}
        candidate = page_data[0]
        candidate_id = candidate.get("candidate_id") if isinstance(candidate, dict) else None
        if not isinstance(candidate_id, str) or candidate.get("project_approval") is not False:
            raise PreviewError("candidate response omitted its safe opaque identity or approval boundary")
        detail_status, detail = _http(f"{counts_url.rsplit('/', 1)[0]}/locations/{candidate_id}", token)
        detail_data = detail.get("data") if detail else None
        if detail_status != 200 or not isinstance(detail_data, dict) or detail_data.get("candidate_id") != candidate_id:
            raise PreviewError("authenticated real-preview detail probe failed")
        if any(key in detail_data for key in ("source_identifier", "source_group_key", "source_values", "address", "latitude_raw", "longitude_raw")):
            raise PreviewError("candidate detail contains a restricted source field")
        return {"status": "backend_ready_frontend_unavailable" if vite is None else "ready", "api_url": f"http://127.0.0.1:{API_PORT}", "url": f"http://127.0.0.1:{WEB_PORT}/" if vite else None, "aggregates": summary,
                "api_auth_check": "passed", "authenticated_api_counts": api_counts, "candidate_list_detail_check": "passed",
                "public_release_count": summary.get("public_release_count"), "public_projection_count": summary.get("public_projection_count")}
    except Exception:
        for process in reversed(started):
            if process.poll() is None:
                process.terminate()
        if _state().exists():
            _state().unlink()
        raise


def down() -> None:
    state = _read_state()
    for key, marker in (("vite_pid", "vite.js"), ("api_pid", "uec-api")):
        pid = state.get(key)
        if isinstance(pid, int):
            if _process_owned(pid, marker):
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
                else:
                    os.kill(pid, signal.SIGTERM)
            elif _pid_exists(pid):
                raise PreviewError("refusing to stop a process without the expected real-preview ownership markers")
    if _state().exists():
        _state().unlink()
    verify_resources()
    result = compose("down", "--remove-orphans")
    if result.returncode:
        raise PreviewError("owned preview services could not be stopped; database volume preserved")


def _pid_exists(pid: int) -> bool:
    if os.name == "nt":
        return bool(_process_owned(pid, ""))
    try:
        os.kill(pid, 0); return True
    except OSError:
        return False


def reset() -> None:
    down()
    verify_resources()
    volumes = _docker_json(["docker", "volume", "ls", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{json .}}"])
    if any(v.get("Name") != VOLUME or f"com.docker.compose.project={PROJECT}" not in str(v.get("Labels", "")) for v in volumes):
        raise PreviewError("refusing reset because volume ownership could not be proven")
    result = compose("down", "-v", "--remove-orphans")
    if result.returncode:
        raise PreviewError("verified disposable preview volume could not be removed")
    password_path = _runtime_dir() / "db-password"
    if password_path.exists():
        password_path.unlink()


def status() -> dict[str, object]:
    state = _read_state()
    verify_resources()
    db = _socket_busy(DB_PORT)
    api_port = _socket_busy(API_PORT)
    web_port = _socket_busy(WEB_PORT) if isinstance(state.get("vite_pid"), int) else False
    api_owned = isinstance(state.get("api_pid"), int) and _process_owned(int(state["api_pid"]), "uec-api")
    web_owned = isinstance(state.get("vite_pid"), int) and _process_owned(int(state["vite_pid"]), "vite.js")
    if (api_port and not api_owned) or (web_port and not web_owned):
        raise PreviewError("a preview port is occupied by a process without verified real-preview ownership")
    running_containers = _docker_json(["docker", "ps", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{json .}}"])
    if db and not any(c.get("Names") == f"{PROJECT}-postgres-1" for c in running_containers):
        raise PreviewError("the database port is occupied without the verified real-preview container")
    frontend_available = (ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js").is_file()
    frontend_ready = web_port and _http_status(f"http://127.0.0.1:{WEB_PORT}/") == 200
    return {"project": PROJECT, "database": "running" if db else "stopped", "api": api_port and _http(f"http://127.0.0.1:{API_PORT}/health/live")[0] == 200,
            "frontend": frontend_ready, "frontend_available": frontend_available, "owned_process_state": bool(state)}


def probe() -> dict[str, object]:
    ready = _http(f"http://127.0.0.1:{API_PORT}/health/ready")[0] == 200
    web = _socket_busy(WEB_PORT)
    frontend_available = (ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js").is_file()
    frontend_ready = web and _http_status(f"http://127.0.0.1:{WEB_PORT}/") == 200
    return {"ok": ready and (not frontend_available or frontend_ready), "api_ready": ready, "frontend_loopback": frontend_ready, "frontend_available": frontend_available}


def _refresh_source_locked(source_id: str = "be.locations", existing_runner_run_id: str | None = None) -> dict[str, object]:
    """Freshly acquire one policy-enabled source and import its exact handoff."""
    import uuid
    from pipeline.source_runtime_classification import (
        RuntimeClassificationError,
        require_production_preview_source,
    )

    try:
        require_production_preview_source(source_id)
    except RuntimeClassificationError as error:
        raise PreviewError(str(error)) from error
    policy_path = ROOT / "pipeline" / "preview-enabled-sources.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    source_policy = policy.get("sources", {}).get(source_id)
    if not isinstance(source_policy, dict) or source_policy.get("enabled") is not True:
        raise PreviewError("source is not enabled for private preview")
    database_url = _local_database_url()
    env = os.environ.copy()
    env["UEC_DATABASE_URL"] = database_url
    run_id = f"preview-{source_id.replace('.', '-')}-{uuid.uuid4()}"
    output_root = ROOT / "target" / "real-preview" / "runs"
    job_dir = ROOT / "target" / "real-preview" / "jobs"
    job_path = job_dir / f"{run_id}.json"
    job: dict[str, object] = {"ledger_version": "source-preview-job-v1", "source_id": source_id,
                              "run_id": run_id, "status": "running", "phase": "acquisition",
                              "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                              "public_rows": 0}

    def write_job(status: str, phase: str, error_code: str | None = None) -> None:
        job.update({"status": status, "phase": phase,
                    "updated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        if error_code:
            job["error_code"] = error_code
        job_dir.mkdir(parents=True, exist_ok=True)
        temporary = job_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(job, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(job_path)

    try:
        if existing_runner_run_id:
            runner_run_id = existing_runner_run_id
            source_root = output_root / runner_run_id / "sources" / source_id
            run_manifest = json.loads((output_root / runner_run_id / "manifest.json").read_text(encoding="utf-8"))
            if source_id == "be.locations":
                evidence_files = list((source_root / "acquisition" / source_id).glob("*/pair-metadata.json"))
                evidence = json.loads(evidence_files[0].read_text(encoding="utf-8")) if evidence_files else {}
                run_id = evidence.get("operator", {}).get("run_id")
            elif source_id == "us.fsis":
                evidence_files = list((source_root / "acquisition" / "us.fsis.directory").glob("*/acquisition-metadata.json"))
                evidence = json.loads(evidence_files[0].read_text(encoding="utf-8")) if len(evidence_files) == 1 else {}
                run_id = evidence.get("run_id")
            else:
                evidence_files = list((source_root / "acquisition" / source_id).glob("*/acquisition-metadata.json"))
                evidence = json.loads(evidence_files[0].read_text(encoding="utf-8")) if evidence_files else {}
                run_id = evidence.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                write_job("failed", "lifecycle", "acquisition_run_id_missing")
                raise PreviewError("completed source run lacks its unique acquisition id")
            job.update({"run_id": run_id, "runner_run_id": runner_run_id})
            job_path = job_dir / f"{run_id}.json"
            refresh_result = run_manifest
            write_job("running", "administrative_geography")
        else:
            write_job("running", "acquisition")
            if source_id == "dk.smiley":
                # The Denmark adapter has source-specific validation and
                # quarantine stages; keep that lifecycle in the source-owned
                # runner while binding its output to the common private
                # preview run and importer contracts.
                runner_run_id = run_id
                source_root = output_root / runner_run_id / "sources" / source_id
                source_root.mkdir(parents=True, exist_ok=True)
                review = ROOT / str(source_policy["terms_review"])
                staged = subprocess.run([
                    sys.executable, str(ROOT / "pipeline" / "sources" / "denmark" / "run-denmark-pipeline.py"),
                    "--fetch", "--terms-review", str(review), "--raw-output-root",
                    str(source_root / "acquisition"), "--run-id", run_id,
                    "--output-dir", str(source_root),
                ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
                if staged.returncode:
                    write_job("failed", "lifecycle", "source_lifecycle_failed")
                    raise PreviewError("source acquisition or lifecycle failed; no preview import was attempted")
                handoff_manifest_path = source_root / "candidate-handoff" / "manifest.json"
                try:
                    handoff_manifest = json.loads(handoff_manifest_path.read_text(encoding="utf-8"))
                    acquisition = json.loads((source_root / "acquisition" / source_id / run_id / "acquisition-metadata.json").read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    write_job("failed", "lifecycle", "source_candidate_handoff_missing")
                    raise PreviewError("Denmark lifecycle did not produce complete acquisition and handoff evidence") from None
                preview_fields = source_policy.get("allowed_preview_fields")
                schema_fingerprint = __import__("hashlib").sha256(
                    json.dumps(preview_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                summary = {
                    "lifecycle_status": "candidate-ready", "candidate_handoff": True,
                    "candidate_handoff_sha256": handoff_manifest.get("normalized_sha256"),
                    "schema_fingerprint": schema_fingerprint,
                    "input_rows": (json.loads((source_root / "01-parse" / "run-metadata.json").read_text(encoding="utf-8")).get("rows_parsed")),
                    "candidate_observation_rows": handoff_manifest.get("normalized_rows"),
                    "quarantined_rows": json.loads((source_root / "manifest.json").read_text(encoding="utf-8")).get("quarantined_rows"),
                    "out_of_scope_rows": 0,
                }
                refresh_result = {
                    "run_id": runner_run_id, "completed_at_utc": acquisition.get("retrieved_at_utc"),
                    "results": [{"source_id": source_id, "status": "succeeded",
                                 "acquisition_classification": "live", "summary": summary}],
                    "publication": {"release_created": False, "promoted": False, "published": False},
                }
                runtime_manifest = output_root / runner_run_id / "manifest.json"
                runtime_manifest.parent.mkdir(parents=True, exist_ok=True)
                runtime_manifest.write_text(json.dumps(refresh_result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            else:
                review = ROOT / str(source_policy["terms_review"])
                refresh = subprocess.run([
                    sys.executable, "-m", "pipeline.refresh_private", "--source", source_id,
                    "--mode", "live-acquisition", "--authorize-live-source", source_id,
                    "--terms-review", f"{source_id}={review}", "--output-root", str(output_root),
                    "--retries", "1", "--timeout-seconds", "180", "--run-id", run_id,
                ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
                try:
                    refresh_result = json.loads(refresh.stdout)
                except json.JSONDecodeError:
                    write_job("failed", "acquisition", "acquisition_result_invalid")
                    raise PreviewError("source acquisition failed; inspect private job evidence") from None
                if refresh.returncode or refresh_result.get("exit_status") != "ok":
                    write_job("failed", "lifecycle", "source_lifecycle_failed")
                    raise PreviewError("source acquisition or lifecycle failed; no preview import was attempted")
            if source_id == "it.1069-2009":
                results = refresh_result.get("results")
                result = next((item for item in results or []
                               if isinstance(item, dict) and item.get("source_id") == source_id), None)
                summary = result.get("summary") if isinstance(result, dict) else None
                if (not isinstance(summary, dict) or result.get("status") != "succeeded"
                        or summary.get("lifecycle_status") != "candidate-ready"
                        or summary.get("candidate_handoff") is not True
                        or not isinstance(summary.get("candidate_handoff_sha256"), str)):
                    write_job("failed", "lifecycle", "source_candidate_handoff_missing")
                    raise PreviewError("Italy 1069 lifecycle did not produce a validated candidate handoff; no preview import was attempted")
            runner_run_id = refresh_result.get("run_id")
            if not isinstance(runner_run_id, str) or not runner_run_id:
                write_job("failed", "lifecycle", "source_run_id_missing")
                raise PreviewError("source runner returned no unique run identifier")
        source_dir = output_root / runner_run_id / "sources" / source_id
        handoff_manifest = source_dir / "candidate-handoff" / "manifest.json"
        geography = None
        municipality_index = None
        if source_id == "be.locations":
            write_job("running", "administrative_geography")
            from pipeline.sources.belgium.municipality_reference import acquire_centroids
            try:
                geography = acquire_centroids(output_root=source_dir / "geography", run_id=run_id)
            except Exception:
                write_job("failed", "administrative_geography", "approved_geometry_acquisition_failed")
                raise PreviewError("approved administrative geography acquisition failed") from None
            municipality_index = source_dir / "geography" / "municipality-centroids.json"
            job["geometry_sha256"] = geography.get("sha256")
            write_job("running", "transactional_preview_import")
        elif source_id in {"fr.dgal.section-i", "fr.dgal.section-ii"}:
            write_job("running", "administrative_geography")
            from pipeline.sources.france.commune_reference import acquire_centres
            try:
                geography = acquire_centres(output_root=source_dir / "geography", run_id=run_id,
                                           timeout_seconds=60.0)
            except Exception:
                write_job("failed", "administrative_geography", "approved_commune_reference_acquisition_failed")
                raise PreviewError("approved French administrative commune reference acquisition failed") from None
            municipality_index = Path(str(geography["path"]))
            job["geometry_sha256"] = geography.get("derived_index_sha256")
            write_job("running", "transactional_preview_import")
        imported = subprocess.run([
            sys.executable, str(ROOT / "pipeline" / "scripts" / "maintenance" / "import-real-preview.py"),
            "--root", str(source_dir), "--manifest", str(handoff_manifest), "--source-id", source_id,
            "--database-url-env", "UEC_DATABASE_URL", "--json",
            *( ["--municipality-index", str(municipality_index)] if municipality_index is not None else []),
            "--run-id", run_id, "--run-manifest", str(output_root / runner_run_id / "manifest.json"),
        ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
        try:
            import_result = json.loads(imported.stdout)
        except json.JSONDecodeError:
            write_job("failed", "transactional_preview_import", "import_result_invalid")
            raise PreviewError("preview import failed; no readiness ledger was written") from None
        if imported.returncode or import_result.get("status") != "imported":
            code = import_result.get("error_code")
            safe_code = code if isinstance(code, str) and code.replace("_", "").isalnum() else "transactional_import_failed"
            write_job("failed", "transactional_preview_import", safe_code)
            raise PreviewError(f"transactional preview import failed (code={safe_code}); see private job ledger")
    except subprocess.TimeoutExpired:
        write_job("failed", str(job.get("phase", "acquisition")), "bounded_job_timeout")
        raise PreviewError("source refresh exceeded its bounded runtime") from None
    ledger = {
        "ledger_version": "source-preview-runtime-v1", "source_id": source_id,
        "run_id": run_id, "status": "imported", "retrieved_at_utc": refresh_result.get("completed_at_utc"),
        "source_run": refresh_result, "preview_import": import_result,
        "coarse_geometry": geography,
        "preview_policy_version": policy.get("contract_version"),
        "public_rows": import_result.get("public_release_count", 0) + import_result.get("public_projection_count", 0),
        "map_visible_count": import_result.get("numeric_coordinate_count", 0) + import_result.get("coarse_placeable_facility_count", 0),
        "map_readiness": "coarse-city-reference" if geography and import_result.get("coarse_placeable_facility_count", 0) else ("source-precision-unknown" if import_result.get("numeric_coordinate_count", 0) else "unmapped"),
    }
    if source_id == "dk.smiley":
        acquisition_path = source_dir / "acquisition" / source_id / run_id / "acquisition-metadata.json"
        acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
        source_result = next((item for item in refresh_result.get("results", [])
                              if isinstance(item, dict) and item.get("source_id") == source_id), None)
        summary = source_result.get("summary") if isinstance(source_result, dict) else None
        if not isinstance(summary, dict):
            raise PreviewError("Denmark lifecycle summary is unavailable for runtime ledger reconciliation")
        ledger.update({
            "acquisition": {"source_id": source_id, "run_id": run_id,
                            "requested_url": acquisition.get("requested_url"),
                            "final_url": acquisition.get("final_url"),
                            "retrieved_at_utc": acquisition.get("retrieved_at_utc"),
                            "raw_sha256": acquisition.get("sha256"),
                            "byte_size": acquisition.get("byte_size"),
                            "publication_metadata": acquisition.get("publication_metadata"),
                            "effective_date": None},
            "normalized_sha256": import_result.get("normalized_sha256"),
            "candidate_handoff_sha256": summary.get("candidate_handoff_sha256"),
            "schema_fingerprint": summary.get("schema_fingerprint"),
            "quarantine": {"input_rows": summary.get("input_rows"),
                           "candidate_observation_rows": summary.get("candidate_observation_rows"),
                           "quarantined_rows": summary.get("quarantined_rows"),
                           "out_of_scope_rows": summary.get("out_of_scope_rows", 0)},
            "coordinate_precision_breakdown": {
                "exact": 0, "city_or_postal_only": import_result.get("city_postal_count"),
                "unmapped": import_result.get("unmapped_map_candidate_count")},
        })
    elif source_id == "it.853-2004":
        acquisition_evidence = _italy_acquisition_evidence(source_dir, source_id, run_id)
        source_results = refresh_result.get("results") if isinstance(refresh_result, dict) else None
        source_result = next((item for item in source_results or []
                              if isinstance(item, dict) and item.get("source_id") == source_id), None)
        source_summary = source_result.get("summary") if isinstance(source_result, dict) else None
        if not isinstance(source_summary, dict):
            raise PreviewError("Italy lifecycle summary is unavailable for runtime ledger reconciliation")
        normalized_sha256 = import_result.get("normalized_sha256")
        handoff_sha256 = source_summary.get("candidate_handoff_sha256")
        schema_fingerprint = source_summary.get("schema_fingerprint")
        quarantine_reasons = source_summary.get("quarantine_reasons")
        if any(not isinstance(value, str) or len(value) != 64 for value in
               (normalized_sha256, handoff_sha256, schema_fingerprint)) or not isinstance(quarantine_reasons, dict):
            raise PreviewError("Italy lifecycle provenance is incomplete for runtime ledger reconciliation")
        ledger.update({
            "acquisition": acquisition_evidence,
            "normalized_sha256": normalized_sha256,
            "candidate_handoff_sha256": handoff_sha256,
            "schema_fingerprint": schema_fingerprint,
            "quarantine": {
                "input_rows": source_summary.get("input_rows"),
                "candidate_observation_rows": source_summary.get("candidate_observation_rows"),
                "quarantined_rows": source_summary.get("quarantined_rows"),
                "reasons": quarantine_reasons,
            },
            "source_counts": {
                key: import_result.get(key) for key in (
                    "observation_count", "facility_candidate_count", "numeric_coordinate_count",
                    "city_postal_count", "unmapped_observation_count", "mapped_non_candidate_observation_count",
                    "unmapped_map_candidate_count", "public_release_count", "public_projection_count",
                )
            },
            "coordinate_precision_breakdown": {
                "source_precision_unknown": import_result.get("source_precision_unknown_group_count"),
                "source_provided_unspecified": import_result.get("source_provided_coordinate_group_count"),
                "exact": 0,
                "city_or_postal_only": import_result.get("city_postal_count"),
                "unmapped": import_result.get("unmapped_map_candidate_count"),
            },
        })
    elif source_id == "ca.cfia.federal-meat":
        acquisition_path = source_dir / "acquisition" / source_id / run_id / "acquisition-metadata.json"
        if not acquisition_path.is_file() or acquisition_path.is_symlink():
            raise PreviewError("CFIA acquisition provenance is unavailable")
        acquisition_evidence = json.loads(acquisition_path.read_text(encoding="utf-8"))
        source_results = refresh_result.get("results") if isinstance(refresh_result, dict) else None
        source_result = next((item for item in source_results or []
                              if isinstance(item, dict) and item.get("source_id") == source_id), None)
        source_summary = source_result.get("summary") if isinstance(source_result, dict) else None
        if not isinstance(source_summary, dict) or acquisition_evidence.get("source_id") != source_id:
            raise PreviewError("CFIA lifecycle or acquisition identity is unavailable")
        if any(not isinstance(value, str) or len(value) != 64 for value in (
                import_result.get("normalized_sha256"), source_summary.get("candidate_handoff_sha256"),
                source_summary.get("schema_fingerprint"))) or not isinstance(source_summary.get("quarantine_reasons"), dict):
            raise PreviewError("CFIA lifecycle hashes or quarantine summary are incomplete")
        ledger.update({
            "acquisition": {key: acquisition_evidence.get(key) for key in (
                "source_id", "run_id", "requested_url", "final_url", "requested_at_utc", "retrieved_at_utc",
                "effective_date", "publication_date", "sha256", "byte_size", "response_headers",
                "terms_review", "rights_caveat", "privacy_caveat", "coverage", "adapter_version", "config_version")},
            "normalized_sha256": import_result.get("normalized_sha256"),
            "candidate_handoff_sha256": source_summary.get("candidate_handoff_sha256"),
            "schema_fingerprint": source_summary.get("schema_fingerprint"),
            "quarantine": {"input_rows": source_summary.get("input_rows"),
                           "accepted_rows": source_summary.get("candidate_observation_rows"),
                           "quarantined_rows": source_summary.get("quarantined_rows"),
                           "reasons": source_summary.get("quarantine_reasons", {})},
            "source_counts": {key: import_result.get(key) for key in (
                "observation_count", "facility_candidate_count", "numeric_coordinate_count", "city_postal_count",
                "unmapped_observation_count", "unmapped_facility_count",
                "public_release_count", "public_projection_count")},
            "preview_import": {**import_result,
                               "unmapped_map_candidate_count": 0},
            "coordinate_precision_breakdown": {"exact": 0, "source_numeric": 0,
                                                "city_or_postal_only": import_result.get("city_postal_count"),
                                                "unmapped": import_result.get("unmapped_facility_count")},
            "location_policy": "CFIA workbook provides no coordinates; city/postal candidates are listable, remain unmapped, and are not geocoded.",
        })
    elif source_id == "be.locations":
        acquisition_path = source_dir / "acquisition" / source_id / run_id / "pair-metadata.json"
        if not acquisition_path.is_file() or acquisition_path.is_symlink():
            raise PreviewError("Belgium paired acquisition provenance is unavailable")
        pair = json.loads(acquisition_path.read_text(encoding="utf-8"))
        source_results = refresh_result.get("results") if isinstance(refresh_result, dict) else None
        source_result = next((item for item in source_results or []
                              if isinstance(item, dict) and item.get("source_id") == source_id), None)
        source_summary = source_result.get("summary") if isinstance(source_result, dict) else None
        if not isinstance(source_summary, dict) or pair.get("source_id") != source_id:
            raise PreviewError("Belgium lifecycle summary or acquisition identity is unavailable")
        artifacts = {}
        for role in ("operator", "activity_codes"):
            artifact = pair.get(role)
            if not isinstance(artifact, dict) or artifact.get("run_id") != run_id:
                raise PreviewError("Belgium paired acquisition run identity does not match")
            if not isinstance(artifact.get("sha256"), str) or len(artifact["sha256"]) != 64:
                raise PreviewError("Belgium paired acquisition hash is unavailable")
            artifacts[role] = {key: artifact.get(key) for key in (
                "source_id", "run_id", "requested_url", "final_url", "retrieved_at_utc", "sha256",
                "byte_size", "response_headers", "terms_review", "attempts", "rights_caveat", "privacy_caveat")}
        if any(not isinstance(value, str) or len(value) != 64 for value in (
                import_result.get("normalized_sha256"), source_summary.get("candidate_handoff_sha256"),
                source_summary.get("schema_fingerprint"))):
            raise PreviewError("Belgium lifecycle hashes are incomplete")
        ledger.update({
            "acquisition": artifacts,
            "normalized_sha256": import_result.get("normalized_sha256"),
            "candidate_handoff_sha256": source_summary.get("candidate_handoff_sha256"),
            "schema_fingerprint": source_summary.get("schema_fingerprint"),
            "quarantine": {"input_rows": source_summary.get("input_rows"),
                           "accepted_rows": source_summary.get("valid_source_activity_rows"),
                           "quarantined_rows": source_summary.get("quarantined_rows"),
                           "out_of_scope_rows": source_summary.get("out_of_scope_rows", 0),
                           "reasons": source_summary.get("quarantine_reasons", {})},
            "source_counts": {key: import_result.get(key) for key in (
                "observation_count", "facility_candidate_count", "numeric_coordinate_count",
                "city_postal_count", "unmapped_observation_count", "mapped_non_candidate_observation_count",
                "unmapped_map_candidate_count", "coarse_placeable_facility_count",
                "public_release_count", "public_projection_count")},
            "coordinate_precision_breakdown": {
                "exact": 0, "city_or_postal_only": import_result.get("city_postal_count"),
                "approximate_city_display": import_result.get("coarse_placeable_facility_count"),
                "unmapped": import_result.get("unmapped_map_candidate_count")},
        })
    elif source_id == "it.1069-2009":
        acquisition_path = source_dir / "acquisition" / source_id / run_id / "acquisition-metadata.json"
        if not acquisition_path.is_file() or acquisition_path.is_symlink():
            raise PreviewError("Italy 1069 acquisition provenance is unavailable")
        acquisition_evidence = json.loads(acquisition_path.read_text(encoding="utf-8"))
        source_results = refresh_result.get("results") if isinstance(refresh_result, dict) else None
        source_result = next((item for item in source_results or []
                              if isinstance(item, dict) and item.get("source_id") == source_id), None)
        source_summary = source_result.get("summary") if isinstance(source_result, dict) else None
        if not isinstance(source_summary, dict):
            raise PreviewError("Italy 1069 lifecycle summary is unavailable for runtime ledger reconciliation")
        if any(not isinstance(value, str) or len(value) != 64 for value in (
                import_result.get("normalized_sha256"), source_summary.get("candidate_handoff_sha256"),
                source_summary.get("schema_fingerprint"))):
            raise PreviewError("Italy 1069 lifecycle hashes are incomplete")
        ledger.update({
            "acquisition": {key: acquisition_evidence.get(key) for key in (
                "source_id", "run_id", "requested_url", "final_url", "requested_at_utc", "retrieved_at_utc",
                "effective_date", "publication_metadata", "sha256", "byte_size", "terms_review",
                "adapter_version", "config_version", "response_headers", "catalog_url", "catalog_final_url",
                "catalog_sha256")},
            "normalized_sha256": import_result.get("normalized_sha256"),
            "candidate_handoff_sha256": source_summary.get("candidate_handoff_sha256"),
            "schema_fingerprint": source_summary.get("schema_fingerprint"),
            "quarantine": {"input_rows": source_summary.get("input_rows"),
                           "accepted_rows": source_summary.get("normalized_rows"),
                           "quarantined_rows": source_summary.get("quarantined_rows"),
                           "reasons": source_summary.get("quarantine_reasons", {})},
            "coordinate_rejections": source_summary.get("coordinate_rejections", {}),
            "source_counts": {key: import_result.get(key) for key in (
                "observation_count", "facility_candidate_count", "numeric_coordinate_count",
                "city_postal_count", "unmapped_observation_count", "mapped_non_candidate_observation_count",
                "unmapped_map_candidate_count", "public_release_count", "public_projection_count")},
            "coordinate_precision_breakdown": {
                "source_precision_unknown": import_result.get("source_precision_unknown_group_count"),
                "source_provided_unspecified": import_result.get("source_provided_coordinate_group_count"),
                "exact": 0, "city_or_postal_only": import_result.get("city_postal_count"),
                "unmapped": import_result.get("unmapped_map_candidate_count")},
        })
    elif source_id in {"fr.dgal.section-i", "fr.dgal.section-ii"}:
        acquisition_path = source_dir / "acquisition" / source_id / run_id / "acquisition-metadata.json"
        if not acquisition_path.is_file() or acquisition_path.is_symlink():
            raise PreviewError("France lifecycle acquisition provenance is unavailable")
        acquisition_evidence = json.loads(acquisition_path.read_text(encoding="utf-8"))
        source_results = refresh_result.get("results") if isinstance(refresh_result, dict) else None
        source_result = next((item for item in source_results or []
                              if isinstance(item, dict) and item.get("source_id") == source_id), None)
        source_summary = source_result.get("summary") if isinstance(source_result, dict) else None
        if not isinstance(source_summary, dict):
            raise PreviewError("France lifecycle summary is unavailable for runtime ledger reconciliation")
        if any(not isinstance(value, str) or len(value) != 64 for value in
               (import_result.get("normalized_sha256"), source_summary.get("candidate_handoff_sha256"), source_summary.get("schema_fingerprint"))):
            raise PreviewError("France lifecycle hashes are incomplete for runtime ledger reconciliation")
        ledger.update({
            "acquisition": {key: acquisition_evidence.get(key) for key in (
                "source_id", "run_id", "requested_url", "final_url", "retrieved_at_utc", "effective_date",
                "sha256", "byte_size", "response_headers", "terms_review", "attempts", "rights_caveat",
                "privacy_caveat", "coverage", "adapter_version", "code_version", "config_version")},
            "schema_fingerprint": source_summary.get("schema_fingerprint"),
            "normalized_sha256": import_result.get("normalized_sha256"),
            "candidate_handoff_sha256": source_summary.get("candidate_handoff_sha256"),
            "quarantine": {"input_rows": source_summary.get("input_rows"),
                           "accepted_rows": source_summary.get("normalized_rows"),
                           "quarantined_rows": source_summary.get("quarantined_rows"),
                           "reasons": source_summary.get("quarantine_reasons", {})},
            "source_counts": {key: import_result.get(key) for key in (
                "observation_count", "facility_candidate_count", "numeric_coordinate_count",
                "city_postal_count", "unmapped_observation_count", "mapped_non_candidate_observation_count",
                "unmapped_map_candidate_count", "coarse_placeable_facility_count", "unmapped_facility_count",
                "public_release_count", "public_projection_count")},
            "coordinate_precision_breakdown": {"exact": 0, "city_or_postal_only": import_result.get("city_postal_count"),
                                                "approximate_city_display": import_result.get("coarse_placeable_facility_count"),
                                                "unmapped": import_result.get("unmapped_map_candidate_count")},
        })
    elif source_id == "us.fsis":
        source_results = refresh_result.get("results") if isinstance(refresh_result, dict) else None
        source_result = next((item for item in source_results or []
                              if isinstance(item, dict) and item.get("source_id") == source_id), None)
        source_summary = source_result.get("summary") if isinstance(source_result, dict) else None
        if not isinstance(source_summary, dict):
            raise PreviewError("FSIS lifecycle summary is unavailable for runtime ledger reconciliation")
        acquisition_evidence: dict[str, object] = {}
        for role, source in (("directory", "us.fsis.directory"), ("demographics", "us.fsis.demographics")):
            acquisition_path = source_dir / "acquisition" / source / run_id / "acquisition-metadata.json"
            if not acquisition_path.is_file() or acquisition_path.is_symlink():
                raise PreviewError("FSIS acquisition provenance is unavailable")
            artifact = json.loads(acquisition_path.read_text(encoding="utf-8"))
            if artifact.get("run_id") != run_id or artifact.get("source_id") != source:
                raise PreviewError("FSIS acquisition provenance does not match this preview run")
            acquisition_evidence[role] = {key: artifact.get(key) for key in (
                "source_id", "run_id", "requested_url", "final_url", "page_url",
                "requested_at_utc", "retrieved_at_utc", "effective_date", "publication_date",
                "sha256", "byte_size", "terms_review", "acquisition_authorization",
                "attempts", "browser", "navigation_mode", "code_version", "config_version",
                "rights_caveat", "privacy_caveat", "coverage")}
        if any(not isinstance(value, str) or len(value) != 64 for value in (
                import_result.get("normalized_sha256"), source_summary.get("candidate_handoff_sha256"),
                source_summary.get("schema_fingerprint"), source_summary.get("demographic_schema_fingerprint"))):
            raise PreviewError("FSIS lifecycle provenance hashes are incomplete")
        ledger.update({
            "acquisition": acquisition_evidence,
            "normalized_sha256": import_result.get("normalized_sha256"),
            "candidate_handoff_sha256": source_summary.get("candidate_handoff_sha256"),
            "schema_fingerprint": source_summary.get("schema_fingerprint"),
            "demographic_schema_fingerprint": source_summary.get("demographic_schema_fingerprint"),
            "quarantine": {"input_rows": source_summary.get("input_rows"),
                           "accepted_rows": source_summary.get("normalized_rows"),
                           "quarantined_rows": source_summary.get("quarantined_rows"),
                           "reasons": source_summary.get("quarantine_reasons", {})},
            "row_reconciliation": source_summary.get("row_reconciliation"),
            "source_counts": {key: import_result.get(key) for key in (
                "observation_count", "facility_candidate_count", "numeric_coordinate_count",
                "city_postal_count", "unmapped_observation_count", "mapped_non_candidate_observation_count",
                "unmapped_map_candidate_count", "public_release_count", "public_projection_count")},
            "coordinate_precision_breakdown": {
                "source_provided_unspecified": import_result.get("source_provided_coordinate_group_count"),
                "source_precision_unknown": import_result.get("source_precision_unknown_group_count"),
                "exact": 0, "city_or_postal_only": import_result.get("city_postal_count"),
            "unmapped": import_result.get("unmapped_map_candidate_count")},
        })
    elif source_id == "au.sa.epa.licensed-activities":
        acquisition_path = source_dir / "acquisition" / source_id / run_id / "acquisition-metadata.json"
        if not acquisition_path.is_file() or acquisition_path.is_symlink():
            raise PreviewError("SA EPA live acquisition provenance is unavailable")
        acquisition_evidence = json.loads(acquisition_path.read_text(encoding="utf-8"))
        source_results = refresh_result.get("results") if isinstance(refresh_result, dict) else None
        source_result = next((item for item in source_results or []
                              if isinstance(item, dict) and item.get("source_id") == source_id), None)
        source_summary = source_result.get("summary") if isinstance(source_result, dict) else None
        if not isinstance(source_summary, dict):
            raise PreviewError("SA EPA lifecycle summary is unavailable for runtime ledger reconciliation")
        if any(not isinstance(value, str) or len(value) != 64 for value in (
                import_result.get("normalized_sha256"), source_summary.get("candidate_handoff_sha256"),
                source_summary.get("schema_fingerprint"))):
            raise PreviewError("SA EPA lifecycle hashes are incomplete")
        ledger.update({
            "acquisition": {key: acquisition_evidence.get(key) for key in (
                "source_id", "source_title", "run_id", "catalog_url", "catalog_final_url",
                "catalog_sha256", "catalog_metadata_modified", "catalog_resource_updated_at",
                "requested_url", "final_url", "canonical_url", "requested_at_utc", "retrieved_at_utc",
                "publication_date", "effective_date", "license", "license_url", "sha256", "byte_size",
                "content_type", "response_headers", "adapter_version", "config_version", "terms_review")},
            "normalized_sha256": import_result.get("normalized_sha256"),
            "candidate_handoff_sha256": source_summary.get("candidate_handoff_sha256"),
            "schema_fingerprint": source_summary.get("schema_fingerprint"),
            "coverage_scope": "South Australia only",
            "activity_scope": {
                "method": "exact ACTIVITY category plus the source-title Schedule 1 term whitelist",
                "counts_by_candidate_family": source_summary.get("activity_counts", {}),
                "source_activity_categories_observed": source_summary.get("observed_activity_categories", []),
            },
            "quarantine": {
                "input_rows": source_summary.get("input_rows"),
                "accepted_rows": source_summary.get("accepted_rows"),
                "rejected_rows": source_summary.get("rejected_rows"),
                "quarantined_rows": source_summary.get("quarantined_rows"),
                "out_of_scope_rows": source_summary.get("out_of_scope_rows"),
                "quarantined_coordinate_claims": source_summary.get("quarantined_coordinate_claims"),
                "reasons": source_summary.get("quarantine_reasons", {}),
                "coordinate_reasons": source_summary.get("coordinate_quarantine_reasons", {}),
            },
            "source_counts": {key: import_result.get(key) for key in (
                "observation_count", "facility_candidate_count", "api_listable_count", "numeric_coordinate_count",
                "city_postal_count", "unmapped_facility_count", "unmapped_map_candidate_count",
                "public_release_count", "public_projection_count")},
            "coordinate_precision_breakdown": {
                "approximate_source_precision_unspecified": import_result.get("source_precision_unknown_group_count"),
                "source_provided_unspecified": import_result.get("source_provided_coordinate_group_count"),
                "exact": 0, "city_or_postal_only": import_result.get("city_postal_count"),
                "unmapped": import_result.get("unmapped_map_candidate_count"),
            },
            "graph_relationships_emitted": 0,
            "graph_relationships_reason": "No verified cross-source identity or relationship contract exists for these records.",
            "public_rows": 0,
        })
    ledger_path = output_root / runner_run_id / "source-preview-ledger.json"
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    job.update({"runner_run_id": runner_run_id, "observation_count": import_result.get("observation_count"),
                "facility_candidate_count": import_result.get("facility_candidate_count"),
                "map_visible_count": ledger["map_visible_count"], "public_rows": ledger["public_rows"]})
    write_job("succeeded", "preview_ready")
    return {"status": "imported", "source_id": source_id, "run_id": run_id,
            "observations": import_result.get("observation_count"),
            "facility_candidates": import_result.get("facility_candidate_count"),
            "map_visible_count": ledger["map_visible_count"],
            "ledger": str(ledger_path)}


def refresh_source(source_id: str = "be.locations", existing_runner_run_id: str | None = None) -> dict[str, object]:
    with source_lock(source_id):
        return _refresh_source_locked(source_id, existing_runner_run_id)


def strict_live_private_e2e(source_id: str) -> dict[str, object]:
    """Run one bounded live source acquisition through disposable private preview and certification."""
    global PROJECT, VOLUME, DB_PORT, API_PORT, WEB_PORT, PRIVATE_ROOT, ACTIVE_PREVIEW_TOKEN
    if source_id != "ca.cfia.federal-meat":
        raise PreviewError("strict-live-private-e2e currently supports only the assigned CFIA source")
    import uuid
    suffix = uuid.uuid4().hex[:10]
    project = f"uec-preview-cfia-{suffix}"
    private_root = ROOT / "data" / "staging" / "strict-preview" / suffix
    ports = ((55440, 55489), (38020, 38069), (34180, 34229))
    selected_ports: list[int] = []
    for low, high in ports:
        selected = next((port for port in range(low, high + 1)
                         if not _socket_busy(port) and port not in selected_ports), None)
        if selected is None:
            raise PreviewError("no free loopback port is available for the disposable source preview")
        selected_ports.append(selected)
    old = (PROJECT, VOLUME, DB_PORT, API_PORT, WEB_PORT, PRIVATE_ROOT,
           os.environ.get("UEC_DATABASE_URL"), os.environ.get("UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP"))
    PROJECT = project
    VOLUME = f"{project}-postgres"
    DB_PORT, API_PORT, WEB_PORT = selected_ports
    PRIVATE_ROOT = private_root
    if private_root.exists() and any(private_root.iterdir()):
        raise PreviewError("unique private preview workspace unexpectedly already contains data")
    private_root.mkdir(parents=True, exist_ok=True)
    os.environ.pop("UEC_DATABASE_URL", None)
    os.environ["UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP"] = "1"
    started = False
    primary_error: BaseException | None = None
    try:
        if _docker_json(["docker", "volume", "ls", "--filter", f"name={VOLUME}", "--format", "{{json .}}"]):
            raise PreviewError("unique disposable database volume already exists; refusing to reuse it")
        started = True
        up()
        token = ACTIVE_PREVIEW_TOKEN
        if not token:
            raise PreviewError("disposable preview startup did not retain its token in memory")
        preview = refresh_source(source_id)
        if preview.get("status") != "imported":
            raise PreviewError("source refresh did not complete the private preview import")
        ledger_path = Path(str(preview.get("ledger", "")))
        certificate_module_path = ROOT / "scripts" / "certify_real_preview.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("uec_cfia_certificate", certificate_module_path)
        if spec is None or spec.loader is None:
            raise PreviewError("strict preview certification module is unavailable")
        certificate_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = certificate_module
        spec.loader.exec_module(certificate_module)
        certificate = certificate_module.certify(
            source_id, ledger_path, _local_database_url(), f"http://127.0.0.1:{API_PORT}", token)
        certificate_path = ledger_path.with_name("source-preview-certificate.json")
        temporary = certificate_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(certificate, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        temporary.replace(certificate_path)
        return {"status": "certified", "source_id": source_id, "run_id": certificate["run_id"],
                "certificate": str(certificate_path), "counts": certificate["counts"],
                "checks": certificate["checks"], "publication": "not_authorized", "public_rows": 0}
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_error: BaseException | None = None
        if started:
            try:
                reset()
            except BaseException as error:
                cleanup_error = error
        PROJECT, VOLUME, DB_PORT, API_PORT, WEB_PORT, PRIVATE_ROOT = old[:6]
        if old[6] is None:
            os.environ.pop("UEC_DATABASE_URL", None)
        else:
            os.environ["UEC_DATABASE_URL"] = old[6]
        if old[7] is None:
            os.environ.pop("UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP", None)
        else:
            os.environ["UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP"] = old[7]
        ACTIVE_PREVIEW_TOKEN = None
        if cleanup_error is not None and primary_error is None:
            raise PreviewError("strict preview succeeded but its disposable database could not be removed") from cleanup_error

def strict_refresh(source_id: str) -> dict[str, object]:
    """Run one live source refresh and certificate inside a fresh local session."""
    global SESSION_TOKEN
    # Restart the exact owned development stack so refresh and read probes use
    # a token held only in this process, never on disk or in command output.
    current = status()
    if current.get("api") or current.get("database") == "running":
        down()
    SESSION_TOKEN = None
    startup = up()
    if SESSION_TOKEN is None:
        raise PreviewError("preview session token was not retained in process memory")
    try:
        refreshed = refresh_source(source_id)
        from scripts.certify_real_preview import certify
        ledger_path = Path(str(refreshed.get("ledger")))
        certificate = certify(source_id, ledger_path, _local_database_url(),
                              f"http://127.0.0.1:{API_PORT}", SESSION_TOKEN)
        certificate_path = ledger_path.parent / "certificate.json"
        temporary = certificate_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(certificate, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        temporary.replace(certificate_path)
        return {"status": "certified", "source_id": source_id,
                "run_id": certificate["run_id"], "counts": certificate["counts"],
                "checks": certificate["checks"], "claims": certificate["claims"],
                "certificate": str(certificate_path),
                "preview_status": startup.get("status")}
    finally:
        down()
        SESSION_TOKEN = None


def _operator_database_url(database_url: str | None) -> str:
    if not database_url:
        return _local_database_url()
    from urllib.parse import urlsplit
    if urlsplit(database_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise PreviewError("geospatial operations accept only a loopback database")
    return database_url


def enrich_locations(source_id: str | None, limit: int, database_url: str | None = None) -> dict[str, object]:
    """Resolve only from local source-owned references; never call a provider."""
    import psycopg
    from pipeline.sources.denmark.location import classify_location
    from pipeline.sources.canada.location import resolve_local_reference
    selected_source = None if source_id is None else source_id
    allowed = {"dk.smiley", "ca.cfia.federal-meat", "ca.ontario.meat-plants"}
    if selected_source is not None and selected_source not in allowed:
        raise PreviewError("source has no local-only enrichment adapter")
    db_url = _operator_database_url(database_url)
    resolved = blocked = unresolved = examined = 0
    with psycopg.connect(db_url) as connection:
        rows = connection.execute("""
            SELECT candidate.candidate_id, candidate.snapshot_sha256, candidate.source_id,
                   candidate.source_group_key, candidate.location_class, candidate.country_code,
                   candidate.city, candidate.postal_code, candidate.latitude, candidate.longitude,
                   COALESCE(current.state_code, CASE WHEN candidate.location_class='numeric_source_coordinate'
                     THEN 'source_coordinate' ELSE 'unresolved' END) AS current_state
            FROM real_preview.candidates candidate
            JOIN (SELECT DISTINCT ON (source_id) source_id,snapshot_sha256
                  FROM real_preview.source_preview_runs
                  ORDER BY source_id,created_at DESC,run_id DESC) latest
              USING(source_id,snapshot_sha256)
            LEFT JOIN real_preview.enrichment_state_current current USING(candidate_id)
            WHERE (%s::text IS NULL OR candidate.source_id=%s)
              AND (current.state_code IS NULL OR current.state_code IN ('coarse_eligible','exact_eligible','retryable'))
            ORDER BY candidate.source_id,candidate.candidate_id LIMIT %s
        """, (selected_source, selected_source, limit)).fetchall()
        for row in rows:
            candidate_id, snapshot, source, group_key, location_class, country, city, postal, lat, lon, current_state = row
            examined += 1
            state, reason, coarse = "unresolved", "local_reference_unavailable", None
            if location_class == "numeric_source_coordinate":
                state, reason = "source_coordinate", "source_coordinate_present"
            elif source == "dk.smiley":
                refs = connection.execute("""
                    SELECT city_name,postal_code,ST_Y(reference_location::geometry),
                           ST_X(reference_location::geometry),reference_source,source_reference_id,'DK'
                    FROM uec.city_reference_points WHERE country_code='DK'
                      AND reference_source IS NOT NULL AND source_reference_id IS NOT NULL
                      AND (postal_code IS NULL OR postal_code=%s)
                    ORDER BY city_name,postal_code NULLS LAST,source_reference_id
                """, (postal,)).fetchall()
                ref_rows = [dict(city_name=r[0], postal_code=r[1], reference_latitude=r[2],
                                 reference_longitude=r[3], reference_source=r[4],
                                 source_reference_id=r[5], country_code=r[6]) for r in refs]
                outcome = classify_location({"address": {"postal_code": postal, "city": city}}, ref_rows)
                coarse = outcome.get("coarse_display_reference")
                if coarse:
                    state, reason = "resolved", "local_coarse_reference_available"
                else:
                    state = "unresolved"
                    reason = "local_reference_ambiguous" if outcome.get("state") == "ambiguous_reference" else "local_reference_unavailable"
            elif source.startswith("ca."):
                refs = connection.execute("""
                    SELECT city_name,postal_code,ST_Y(reference_location::geometry),
                           ST_X(reference_location::geometry),reference_source,source_reference_id,'CA'
                    FROM uec.city_reference_points WHERE country_code='CA'
                      AND reference_source IS NOT NULL AND source_reference_id IS NOT NULL
                      AND ((%s::text IS NOT NULL AND lower(city_name)=lower(%s))
                           OR (%s::text IS NOT NULL AND postal_code=%s))
                    ORDER BY city_name,postal_code NULLS LAST,source_reference_id
                """, (city, city, postal, postal)).fetchall()
                ref_rows = [dict(city_name=r[0], postal_code=r[1], reference_latitude=r[2],
                                 reference_longitude=r[3], reference_source=r[4],
                                 source_reference_id=r[5], country_code=r[6]) for r in refs]
                coarse = resolve_local_reference(city, postal, ref_rows)
                if coarse:
                    state, reason = "resolved", "local_coarse_reference_available"
                else:
                    state, reason = "provider_blocked", "external_provider_disabled"
            else:
                state, reason = "unresolved", "no_usable_location_input"
            with connection.transaction():
                if coarse:
                    source_label = str(coarse.get("source") or "local Denmark locality reference")
                    source_ref_id = str(coarse.get("source_reference_id") or "unavailable")
                    source_text = f"{source_label}; approximate locality reference; not facility coordinates"
                    connection.execute("""
                        INSERT INTO real_preview.local_reference_display_evidence
                          (candidate_id,snapshot_sha256,source_id,reference_latitude,reference_longitude,
                           display_precision,display_geometry_source,reference_source_id,reference_source)
                        VALUES (%s,%s,%s,%s,%s,'locality_reference_coarse',%s,%s,%s)
                        ON CONFLICT DO NOTHING
                    """, (candidate_id, snapshot, source, coarse["latitude"], coarse["longitude"],
                          source_text, source_ref_id, source_label))
                connection.execute("""
                    INSERT INTO real_preview.enrichment_state_events
                      (candidate_id,snapshot_sha256,source_id,source_record_key,state_code,reason_code)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                """, (candidate_id, snapshot, source, group_key, state, reason))
            resolved += state == "resolved"
            blocked += state == "provider_blocked"
            unresolved += state == "unresolved"
    return {"status": "ok", "scope": "all_sources" if source_id is None else "one_source",
            "source_id": source_id, "examined": examined, "resolved": resolved,
            "provider_blocked": blocked, "unresolved": unresolved,
            "mode": "local_reference_only", "external_provider_calls": 0,
            "publication": "none", "privacy": "private_approximate"}


def geospatial_status(source_id: str | None, database_url: str | None = None) -> dict[str, object]:
    import psycopg
    db_url = _operator_database_url(database_url)
    with psycopg.connect(db_url) as connection:
        rows = connection.execute("""
            SELECT state_code,reason_code,count(*)::bigint
            FROM real_preview.candidate_enrichment_reconciliation
            WHERE (%s::text IS NULL OR source_id=%s)
            GROUP BY state_code,reason_code ORDER BY state_code,reason_code
        """, (source_id, source_id)).fetchall()
    return {"status": "ok", "scope": "all_sources" if source_id is None else "one_source",
            "source_id": source_id, "candidate_count": sum(int(r[2]) for r in rows),
            "states": [{"state": r[0], "reason": r[1], "count": int(r[2])} for r in rows],
            "privacy": "aggregate_only", "publication": "none"}


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("up", "status", "probe", "down", "reset", "refresh", "strict-live-private-e2e", "strict-refresh", "enrich-locations", "geospatial-status"))
    parser.add_argument("--source")
    parser.add_argument("--existing-run", help="complete a prior exact live lifecycle run without reacquisition")
    parser.add_argument("--all", action="store_true", help="enrich all source snapshots")
    parser.add_argument("--limit", type=int, default=100, help="maximum local candidates to inspect")
    parser.add_argument("--database-url", help="loopback database URL; defaults to the owned preview database")
    args = parser.parse_args(argv)
    try:
        if args.action == "enrich-locations":
            if bool(args.source) == bool(args.all):
                raise PreviewError("enrich-locations requires exactly one of --source or --all")
            if args.limit < 1 or args.limit > 10000:
                raise PreviewError("--limit must be between 1 and 10000")
            result = enrich_locations(args.source, args.limit, args.database_url)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.action == "geospatial-status":
            result = geospatial_status(args.source, args.database_url)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.action in {"refresh", "strict-live-private-e2e", "strict-refresh"} and not args.source:
            raise PreviewError(f"{args.action} requires an explicit --source")
        result = (strict_live_private_e2e(args.source) if args.action == "strict-live-private-e2e" else
                  strict_refresh(args.source) if args.action == "strict-refresh" else
                  refresh_source(args.source, args.existing_run) if args.action == "refresh" else
                  {"up": up, "status": status, "probe": probe, "down": down, "reset": reset}[args.action]())
        if result is None:
            result = {"status": "stopped", "database": "preserved"} if args.action == "down" else {"status": "reset", "database": "removed"}
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("ok", True) else 1
    except PreviewError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
