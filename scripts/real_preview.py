#!/usr/bin/env python3
"""Lifecycle for the private, disposable real V2 local preview."""
from __future__ import annotations

import json
import os
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
PROJECT = "uec-real-preview"
VOLUME = "uec-real-preview-postgres"
DB_PORT, API_PORT, WEB_PORT = 55432, 38000, 34173
PRIVATE_ROOT = Path(os.environ.get("UEC_REAL_PREVIEW_ROOT", r"D:\UntilEveryCage-private"))
IMPORTER = ROOT / "pipeline" / "scripts" / "maintenance" / "import-real-preview.py"
MIGRATIONS = ROOT / "pipeline" / "scripts" / "maintenance" / "apply-migrations.py"


class PreviewError(RuntimeError):
    pass


def compose(*args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    db_password = _password(create=False)
    if db_password:
        env["POSTGRES_PASSWORD"] = db_password
    return subprocess.run(["docker", "compose", "-p", PROJECT, "-f", str(ROOT / "docker-compose.real-preview.yml"), *args], cwd=ROOT, env=env, capture_output=capture, text=True)


def _password(*, create: bool) -> str | None:
    path = ROOT / "target" / "real-preview" / "db-password"
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
    return ROOT / "target" / "real-preview" / "processes.json"


def _read_state() -> dict[str, object]:
    path = _state()
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
        raise PreviewError(f"{label} failed; see private local diagnostic output")
    return result.stdout


def _build_api() -> None:
    # Let rustup/toolchain discovery use the invoking shell while building.
    # The long-lived API below still receives only its documented runtime env.
    result = subprocess.run([shutil.which("cargo") or "cargo", "build", "--quiet", "--bin", "uec-api"], cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True)
    if result.returncode:
        raise PreviewError("local API build failed; see private local diagnostic output")


def up() -> dict[str, object]:
    prerequisites()
    token = secrets.token_urlsafe(32)
    password = _password(create=True)
    assert password is not None
    db_url = f"postgresql://uec:{password}@127.0.0.1:{DB_PORT}/uec?sslmode=disable"
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "HOME": os.environ.get("HOME", ""),
           "UEC_DATABASE_URL": db_url, "UEC_DEV_PREVIEW_TOKEN": token, "UEC_RUNTIME_MODE": "development", "UEC_DEV_PREVIEW": "true",
           "UEC_BIND_HOST": "127.0.0.1", "PORT": str(API_PORT), "UEC_CORS_ORIGIN": f"http://127.0.0.1:{WEB_PORT}",
           "UEC_REAL_PREVIEW_ROOT": str(PRIVATE_ROOT), "UEC_PREVIEW_PROJECT": PROJECT}
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
        if list_status != 200 or not isinstance(page_data, list) or not page_data:
            raise PreviewError("authenticated real-preview candidate list probe failed")
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
    password_path = ROOT / "target" / "real-preview" / "db-password"
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


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("up", "status", "probe", "down", "reset"))
    args = parser.parse_args(argv)
    try:
        result = {"up": up, "status": status, "probe": probe, "down": down, "reset": reset}[args.action]()
        if result is None:
            result = {"status": "stopped", "database": "preserved"} if args.action == "down" else {"status": "reset", "database": "removed"}
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("ok", True) else 1
    except PreviewError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
