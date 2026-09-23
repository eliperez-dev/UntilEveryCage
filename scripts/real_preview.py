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
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
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


def prerequisites() -> None:
    missing = [name for name in ("docker", "cargo", "node", "npm") if not shutil.which(name)]
    if shutil.which("docker") and subprocess.run(["docker", "compose", "version"], capture_output=True).returncode:
        missing.append("docker compose")
    if missing:
        raise PreviewError("missing prerequisites: " + ", ".join(missing))
    if not PRIVATE_ROOT.is_dir():
        raise PreviewError("private preview handoff root is unavailable")
    if not IMPORTER.is_file():
        raise PreviewError("lane 1 importer is not installed; expected pipeline/scripts/maintenance/import-real-preview.py")
    if not (ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js").is_file():
        raise PreviewError("frontend dependencies are missing (run npm --prefix frontend ci)")
    for port in (DB_PORT, API_PORT, WEB_PORT):
        if _socket_busy(port):
            raise PreviewError(f"required loopback port {port} is occupied by a foreign service")
    verify_resources()


def _run_checked(args: list[str], env: dict[str, str], label: str) -> str:
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode:
        raise PreviewError(f"{label} failed; see private local diagnostic output")
    return result.stdout


def up() -> dict[str, object]:
    prerequisites()
    token = secrets.token_urlsafe(32)
    password = _password(create=True)
    assert password is not None
    db_url = f"postgresql://uec:{password}@127.0.0.1:{DB_PORT}/uec?sslmode=disable"
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "HOME": os.environ.get("HOME", ""),
           "UEC_DATABASE_URL": db_url, "UEC_DEV_PREVIEW_TOKEN": token, "UEC_RUNTIME_MODE": "development", "UEC_ENABLE_DEV_PREVIEW": "true",
           "UEC_BIND_HOST": "127.0.0.1", "PORT": str(API_PORT), "UEC_CORS_ORIGIN": f"http://127.0.0.1:{WEB_PORT}",
           "UEC_REAL_PREVIEW_ROOT": str(PRIVATE_ROOT), "UEC_PREVIEW_PROJECT": PROJECT}
    started: list[subprocess.Popen[str]] = []
    try:
        result = compose("up", "-d", "--wait")
        if result.returncode:
            raise PreviewError("isolated preview database failed to start")
        verify_resources(require_container=True)
        _run_checked([sys.executable, str(MIGRATIONS), "--database-url", db_url], env, "preview migrations")
        output = _run_checked([sys.executable, str(IMPORTER), "--root-env", "UEC_REAL_PREVIEW_ROOT", "--database-url-env", "UEC_DATABASE_URL", "--json"], env, "private preview import")
        try:
            summary = json.loads(output)
            if not isinstance(summary, dict) or not all(isinstance(v, int) and v >= 0 for v in summary.values()):
                raise ValueError
        except (ValueError, json.JSONDecodeError) as exc:
            raise PreviewError("lane 1 importer violated the aggregate-only JSON contract") from exc
        api_log = (ROOT / "target" / "real-preview" / "api.log").open("a", encoding="utf-8")
        api = subprocess.Popen([shutil.which("cargo") or "cargo", "run", "--quiet", "--bin", "uec-api"], cwd=ROOT, env=env, stdout=api_log, stderr=subprocess.STDOUT)
        api_log.close(); started.append(api)
        vite_log = (ROOT / "target" / "real-preview" / "vite.log").open("a", encoding="utf-8")
        vite_env = {"PATH": env["PATH"], "SYSTEMROOT": env["SYSTEMROOT"], "VITE_API_ORIGIN": f"http://127.0.0.1:{API_PORT}"}
        vite = subprocess.Popen([shutil.which("node") or "node", str(ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"), "--host", "127.0.0.1", "--port", str(WEB_PORT), "--strictPort"], cwd=ROOT, env=vite_env, stdout=vite_log, stderr=subprocess.STDOUT)
        vite_log.close(); started.append(vite)
        _write_state({"project": PROJECT, "api_pid": api.pid, "vite_pid": vite.pid, "ports": [API_PORT, WEB_PORT]})
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if api.poll() is not None or vite.poll() is not None:
                raise PreviewError("preview process exited during startup")
            if _http(f"http://127.0.0.1:{API_PORT}/health/ready")[0] == 200 and _socket_busy(WEB_PORT):
                break
            time.sleep(.3)
        else:
            raise PreviewError("preview startup probe timed out")
        return {"status": "ready", "url": f"http://127.0.0.1:{WEB_PORT}/", "aggregates": summary}
    except Exception:
        for process in reversed(started):
            if process.poll() is None:
                process.terminate()
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
    api_port, web_port = _socket_busy(API_PORT), _socket_busy(WEB_PORT)
    api_owned = isinstance(state.get("api_pid"), int) and _process_owned(int(state["api_pid"]), "uec-api")
    web_owned = isinstance(state.get("vite_pid"), int) and _process_owned(int(state["vite_pid"]), "vite.js")
    if (api_port and not api_owned) or (web_port and not web_owned):
        raise PreviewError("a preview port is occupied by a process without verified real-preview ownership")
    running_containers = _docker_json(["docker", "ps", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{json .}}"])
    if db and not any(c.get("Names") == f"{PROJECT}-postgres-1" for c in running_containers):
        raise PreviewError("the database port is occupied without the verified real-preview container")
    return {"project": PROJECT, "database": "running" if db else "stopped", "api": api_port and _http(f"http://127.0.0.1:{API_PORT}/health/live")[0] == 200,
            "frontend": web_port, "owned_process_state": bool(state)}


def probe() -> dict[str, object]:
    ready = _http(f"http://127.0.0.1:{API_PORT}/health/ready")[0] == 200
    web = _socket_busy(WEB_PORT)
    return {"ok": ready and web, "api_ready": ready, "frontend_loopback": web}


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
