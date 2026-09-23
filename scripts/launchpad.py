#!/usr/bin/env python3
"""Safe, one-command local V2 development launchpad.

The launchpad owns only resources identified by its explicit compose project,
state directory, and process leases.  It never discovers or imports private
data.  A private development dataset is selected by an explicit manifest path
and is otherwise represented by the checked-in sanitized contract fixture.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


PROJECT = "uec-v2-launchpad"
DB_PORT = 5433
API_PORT = 8000
FRONTEND_PORT = 4173
STATE_NAME = "launchpad"
PRIVATE_MODE = "private"
FALLBACK_MODE = "sanitized-fallback"
ALLOWED_MODES = {PRIVATE_MODE, FALLBACK_MODE}
SAFE_RELEASE_ID = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
REAL_PREVIEW_FLAG = "UEC_LOCAL_REAL_PREVIEW"
REAL_PREVIEW_ENV = (
    "UEC_DEV_PREVIEW",
    "UEC_DEV_PREVIEW_TOKEN",
    "UEC_TEST_RELEASE_ID",
    "UEC_TEST_RELEASE_TOKEN",
)


class LaunchpadError(RuntimeError):
    """An actionable launchpad configuration or lifecycle error."""


@dataclass(frozen=True)
class DatasetSelection:
    mode: str
    release_id: str
    manifest_path: Path | None
    summary: dict[str, int]


@dataclass(frozen=True)
class LaunchpadPaths:
    root: Path

    @property
    def state_dir(self) -> Path:
        return self.root / "target" / STATE_NAME

    @property
    def process_state(self) -> Path:
        return self.state_dir / "processes.json"

    @property
    def frontend_log(self) -> Path:
        return self.state_dir / "frontend.log"

    @property
    def frontend_error_log(self) -> Path:
        return self.state_dir / "frontend-error.log"

    @property
    def compose_file(self) -> Path:
        return self.root / "docker-compose.pipeline.yml"

    @property
    def local_v2_script(self) -> Path:
        return self.root / "pipeline" / "scripts" / "maintenance" / "local-v2.ps1"


def _int_summary(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _release_id(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise LaunchpadError("private dataset manifest has an invalid release_id")
    if any(character not in SAFE_RELEASE_ID for character in value):
        raise LaunchpadError("private dataset manifest has an invalid release_id")
    return value


def _local_real_preview_env(values: Mapping[str, str]) -> dict[str, str]:
    """Return the narrowly allowlisted API preview configuration."""
    flag = values.get(REAL_PREVIEW_FLAG, "").strip().lower()
    if flag in ("", "false", "0", "no"):
        return {}
    if flag not in ("true", "1", "yes"):
        raise LaunchpadError(f"{REAL_PREVIEW_FLAG} must be true or false")
    missing = [name for name in REAL_PREVIEW_ENV if not values.get(name, "").strip()]
    if missing:
        raise LaunchpadError(f"{REAL_PREVIEW_FLAG}=true requires " + ", ".join(REAL_PREVIEW_ENV))
    if values["UEC_DEV_PREVIEW"].strip().lower() != "true":
        raise LaunchpadError("local real preview requires UEC_DEV_PREVIEW=true")
    return {name: values[name] for name in REAL_PREVIEW_ENV}


def select_dataset(root: Path, env: Mapping[str, str] | None = None) -> DatasetSelection:
    """Select an explicit dataset mode without searching the filesystem.

    Private mode is deliberately opt-in.  The manifest is an aggregate-only
    control document owned by the dataset lane; this function validates only
    the launchpad boundary and never opens a directory or raw data artifact.
    """
    values = os.environ if env is None else env
    mode = values.get("UEC_DEV_DATASET_MODE", FALLBACK_MODE).strip().lower()
    if mode not in ALLOWED_MODES:
        raise LaunchpadError("UEC_DEV_DATASET_MODE must be private or sanitized-fallback")

    if mode == FALLBACK_MODE:
        release_id = values.get("UEC_DEV_DATASET_RELEASE_ID", "standard-candidate")
        return DatasetSelection(
            mode=FALLBACK_MODE,
            release_id=_release_id(release_id),
            manifest_path=None,
            summary={"records": 1, "mapped_exact": 1, "mapped_approximate": 0, "unmapped": 0, "graph_edges": 0},
        )

    manifest_value = values.get("UEC_DEV_DATASET_MANIFEST")
    if not manifest_value:
        raise LaunchpadError("private dataset mode requires UEC_DEV_DATASET_MANIFEST")
    manifest = Path(manifest_value).expanduser()
    if not manifest.is_file():
        raise LaunchpadError("private dataset manifest is missing or is not a file")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LaunchpadError("private dataset manifest is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("mode") != PRIVATE_MODE:
        raise LaunchpadError("private dataset manifest must declare mode=private")
    if payload.get("ready") is not True:
        raise LaunchpadError("private dataset manifest is not marked ready")
    release_id = _release_id(payload.get("release_id"))
    raw_summary = payload.get("row_free_summary", {})
    if not isinstance(raw_summary, dict):
        raise LaunchpadError("private dataset row_free_summary must be an object")
    summary: dict[str, int] = {}
    for key in ("records", "mapped_exact", "mapped_approximate", "unmapped", "graph_edges"):
        value = _int_summary(raw_summary.get(key))
        if value is not None:
            summary[key] = value
    return DatasetSelection(PRIVATE_MODE, release_id, manifest, summary)


def required_tools() -> tuple[str, ...]:
    return ("docker", "python", "cargo", "node", "npm")


def check_prerequisites(root: Path) -> list[str]:
    missing = [tool for tool in required_tools() if shutil.which(tool) is None]
    if shutil.which("powershell") is None and shutil.which("pwsh") is None:
        missing.append("powershell")
    if shutil.which("docker") is not None:
        result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
        if result.returncode != 0:
            missing.append("docker compose")
    if not (root / "frontend" / "node_modules" / ".bin" / "vite").exists():
        missing.append("frontend dependencies (run npm --prefix frontend ci)")
    return missing


def port_busy(port: int, host: str = "127.0.0.1") -> bool:
    sock = socket.socket()
    sock.settimeout(0.2)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def _powershell() -> str:
    return shutil.which("powershell") or shutil.which("pwsh") or "powershell"


def process_command(pid: int) -> str:
    """Return a process command line without emitting it to users."""
    if pid <= 0:
        return ""
    if os.name != "nt":
        try:
            return (Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ")).decode(errors="replace")
        except OSError:
            return ""
    script = f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' -ErrorAction SilentlyContinue; if($p){{ $p.CommandLine }}"
    result = subprocess.run([_powershell(), "-NoProfile", "-Command", script], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def _owned_frontend(paths: LaunchpadPaths, pid: int) -> bool:
    command = process_command(pid).lower()
    root = str(paths.root).lower()
    # npm's Windows shim may not include the literal `vite` in its command
    # line; the explicit project root, frontend prefix, and stable port are
    # the ownership markers we control.
    command_has_root = root in command
    command_has_frontend = "frontend" in command and "4173" in command and ("npm" in command or "vite" in command)
    # Windows npm.cmd wrappers omit their working directory from CommandLine;
    # the recorded PID plus the exact launch markers are the ownership proof.
    return bool(command and command_has_frontend and (command_has_root or "--prefix frontend" in command))


def _read_state(paths: LaunchpadPaths) -> dict[str, object]:
    if not paths.process_state.is_file():
        return {}
    try:
        payload = json.loads(paths.process_state.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise LaunchpadError("launchpad process state is malformed; inspect it before removing it")
    return payload if isinstance(payload, dict) else {}


def _write_state(paths: LaunchpadPaths, payload: dict[str, object]) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    temporary = paths.process_state.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.replace(paths.process_state)


def _local_env(paths: LaunchpadPaths) -> dict[str, str]:
    env = os.environ.copy()
    # Prevent inherited credentials from accidentally enabling preview routes.
    for name in (REAL_PREVIEW_FLAG, *REAL_PREVIEW_ENV):
        env.pop(name, None)
    env.update(
        {
            "UEC_LOCAL_V2_PROJECT": PROJECT,
            "UEC_LOCAL_V2_STATE_DIR": str(paths.state_dir),
            "UEC_PIPELINE_DB_PORT": str(DB_PORT),
            "UEC_DATABASE_URL": f"postgresql://uec:uec-local-development-only@127.0.0.1:{DB_PORT}/uec?sslmode=disable",
            "PORT": str(API_PORT),
            "UEC_CORS_ORIGIN": f"http://127.0.0.1:{FRONTEND_PORT}",
            "UEC_RUNTIME_MODE": "development",
            "UEC_BIND_HOST": "127.0.0.1",
        }
    )
    env.update(_local_real_preview_env(os.environ))
    if env.get("UEC_DEV_PREVIEW") == "true":
        env[REAL_PREVIEW_FLAG] = "true"
    return env


def _run_local_v2(paths: LaunchpadPaths, command: str) -> None:
    powershell = _powershell()
    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(paths.local_v2_script), "-Command", command],
        cwd=paths.root,
        env=_local_env(paths),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Do not relay command output: it may contain machine-specific paths.
        raise LaunchpadError(f"local V2 {command} failed; inspect the owned local-v2 logs")


def _frontend_process(paths: LaunchpadPaths) -> subprocess.Popen[str]:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    stdout = paths.frontend_log.open("a", encoding="utf-8")
    stderr = paths.frontend_error_log.open("a", encoding="utf-8")
    node = shutil.which("node") or "node"
    vite = paths.root / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        frontend_env = os.environ.copy()
        for name in (REAL_PREVIEW_FLAG, *REAL_PREVIEW_ENV):
            frontend_env.pop(name, None)
        frontend_env["VITE_API_ORIGIN"] = f"http://127.0.0.1:{API_PORT}"
        process = subprocess.Popen(
            [node, str(vite), "--host", "127.0.0.1", "--port", str(FRONTEND_PORT)],
            cwd=paths.root,
            env=frontend_env,
            stdout=stdout,
            stderr=stderr,
            text=True,
            creationflags=creationflags,
        )
        # The child owns the inherited handles. Closing the parent's copies is
        # required for the launchpad command to exit cleanly on Windows.
        stdout.close()
        stderr.close()
        return process
    except Exception:
        stdout.close()
        stderr.close()
        raise


def _wait_for_port(port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_busy(port):
            return True
        time.sleep(0.25)
    return False


def _http_status(url: str) -> int | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status
    except (OSError, urllib.error.URLError):
        return None


def start(root: Path) -> DatasetSelection:
    paths = LaunchpadPaths(root)
    missing = check_prerequisites(root)
    if missing:
        raise LaunchpadError("missing prerequisites: " + ", ".join(missing))
    selection = select_dataset(root)
    state = _read_state(paths)
    if state.get("frontend_pid") and _owned_frontend(paths, int(state["frontend_pid"])):
        if _http_status(f"http://127.0.0.1:{API_PORT}/health/ready") == 200 and _wait_for_port(FRONTEND_PORT, 1):
            return selection
    for port in (API_PORT, FRONTEND_PORT):
        if port_busy(port):
            raise LaunchpadError(f"required port {port} is already in use by an unknown process")
    _run_local_v2(paths, "start")
    process = _frontend_process(paths)
    _write_state(paths, {"frontend_pid": process.pid, "project": PROJECT, "root": str(root), "ports": [API_PORT, FRONTEND_PORT]})
    if not _wait_for_port(FRONTEND_PORT):
        stop(root)
        raise LaunchpadError("frontend did not become ready on its owned port")
    if _http_status(f"http://127.0.0.1:{API_PORT}/health/ready") != 200:
        stop(root)
        raise LaunchpadError("API readiness probe failed")
    return selection


def stop(root: Path) -> None:
    paths = LaunchpadPaths(root)
    state = _read_state(paths)
    pid = state.get("frontend_pid")
    if isinstance(pid, int) and _owned_frontend(paths, pid):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    elif pid:
        raise LaunchpadError("refusing to stop an unverified frontend process")
    if paths.process_state.exists():
        paths.process_state.unlink()
    _run_local_v2(paths, "stop")


def reset(root: Path) -> None:
    """Explicitly destroy only the launchpad's disposable database volume."""
    paths = LaunchpadPaths(root)
    stop(root)
    result = subprocess.run(
        ["docker", "compose", "-p", PROJECT, "-f", str(paths.compose_file), "down", "-v", "--remove-orphans"],
        cwd=root,
        env=_local_env(paths),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise LaunchpadError("launchpad reset failed; no unrelated Compose project was targeted")


def status(root: Path) -> dict[str, object]:
    paths = LaunchpadPaths(root)
    state = _read_state(paths)
    pid = state.get("frontend_pid")
    return {
        "project": PROJECT,
        "database": "owned-port-open" if port_busy(DB_PORT) else "stopped",
        "api": _http_status(f"http://127.0.0.1:{API_PORT}/health/live") == 200,
        "frontend": bool(isinstance(pid, int) and _owned_frontend(paths, pid) and port_busy(FRONTEND_PORT)),
        "state": "present" if state else "absent",
    }


def probe(root: Path) -> dict[str, object]:
    selection = select_dataset(root)
    checks = {
        "api_live": _http_status(f"http://127.0.0.1:{API_PORT}/health/live") == 200,
        "api_ready": _http_status(f"http://127.0.0.1:{API_PORT}/health/ready") == 200,
        "frontend": _http_status(f"http://127.0.0.1:{FRONTEND_PORT}/v2-preview/") == 200,
    }
    return {"ok": all(checks.values()), "checks": checks, "data_mode": selection.mode, "release_id": selection.release_id}


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "stop", "status", "probe", "reset"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            selection = start(args.root)
            print(json.dumps({"status": "ready", "project": PROJECT, "api_url": f"http://127.0.0.1:{API_PORT}", "frontend_url": f"http://127.0.0.1:{FRONTEND_PORT}/v2-preview/", "data_mode": selection.mode, "release_id": selection.release_id, "row_free_summary": selection.summary}, sort_keys=True))
        elif args.command == "stop":
            stop(args.root)
            print(json.dumps({"status": "stopped", "project": PROJECT, "database": "preserved"}, sort_keys=True))
        elif args.command == "reset":
            reset(args.root)
            print(json.dumps({"status": "reset", "project": PROJECT, "database": "removed"}, sort_keys=True))
        elif args.command == "status":
            print(json.dumps(status(args.root), sort_keys=True))
        else:
            result = probe(args.root)
            print(json.dumps(result, sort_keys=True))
            return 0 if result["ok"] else 1
        return 0
    except LaunchpadError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
