#!/usr/bin/env python3
"""Cross-platform developer entrypoint for UntilEveryCage V2.

This is intentionally a thin dispatcher: project-specific behavior remains in
the existing PowerShell and Python scripts.
"""
from __future__ import annotations
import argparse, json, os, shutil, socket, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_V2 = ROOT / "pipeline" / "scripts" / "maintenance" / "local-v2.ps1"
SUMMARY = {"command": None, "ok": False, "exit_code": None, "checks": []}

def run(args: list[str], *, cwd=ROOT) -> int:
    return subprocess.run(args, cwd=cwd).returncode

def check(name: str, ok: bool, detail: str) -> None:
    SUMMARY["checks"].append({"name": name, "ok": ok, "detail": detail})

def doctor(_: argparse.Namespace) -> int:
    for name in ("docker", "python", "cargo", "node"):
        path = shutil.which(name)
        check(name, bool(path), "available" if path else "not found")
    compose = shutil.which("docker") is not None
    if compose:
        result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
        check("compose", result.returncode == 0, "available" if result.returncode == 0 else "unavailable")
    else: check("compose", False, "Docker not found")
    if sys.platform == "win32": check("powershell", bool(shutil.which("powershell") or shutil.which("pwsh")), "required by local-v2")
    for port in (8000, 5433):
        sock = socket.socket(); sock.settimeout(.2)
        try: busy = sock.connect_ex(("127.0.0.1", port)) == 0
        finally: sock.close()
        check(f"port:{port}", not busy, "free" if not busy else "in use")
    required = ("UEC_RUNTIME_MODE", "UEC_DATABASE_URL")
    for key in required:
        # Only report presence; never print values.
        check(f"env:{key}", bool(os.environ.get(key)), "set" if os.environ.get(key) else "not set (local defaults may apply)")
    state = ROOT / "target" / "local-v2"
    check("local-v2-state", not (state.exists() and (state / "uec-api.pid").exists() and not (state / "uec-api.log").exists()), "consistent or absent")
    db = os.environ.get("UEC_DATABASE_URL")
    if db:
        try:
            import psycopg
            with psycopg.connect(db, connect_timeout=2): pass
            check("database", True, "reachable")
        except Exception: check("database", False, "unreachable or driver unavailable")
    else: check("database", None, "not probed; UEC_DATABASE_URL is unset")
    return 0 if all(c["ok"] is not False for c in SUMMARY["checks"]) else 1

def main() -> int:
    p = argparse.ArgumentParser(prog="dev.py", description="UntilEveryCage V2 developer tools")
    p.add_argument("--json", action="store_true", help="emit a machine-readable final summary")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check local prerequisites and safe configuration")
    for name in ("up", "down", "status", "logs", "probe"):
        sub.add_parser(name, help=f"local V2 {name}")
    sub.add_parser("test", help="root legacy static/Jest tests").add_argument("--full", action="store_true")
    sub.add_parser("pipeline", help="run Python pipeline tests").add_argument("args", nargs=argparse.REMAINDER)
    sub.add_parser("contracts", help="run contract tests")
    rp = sub.add_parser("review-packet", help="generate a private row-free review packet")
    rp.add_argument("run_dir"); rp.add_argument("--previous-normalized")
    args = p.parse_args(); SUMMARY["command"] = args.command
    if args.command == "doctor": code = doctor(args)
    elif args.command in ("up", "down", "status", "probe"): code = run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(LOCAL_V2), {"up":"start","down":"stop"}.get(args.command,args.command)])
    elif args.command == "logs": code = run(["docker", "compose", "-p", "uec-local-v2", "-f", "docker-compose.pipeline.yml", "logs", "--tail=100"])
    elif args.command == "test": code = run(["npm", "test", "--", *( ["--runInBand"] if not args.full else [])])
    elif args.command == "pipeline":
        runner = "pytest" if shutil.which("pytest") else "unittest"
        code = run([sys.executable, "-m", runner, *(args.args or ["discover", "-s", "pipeline"])])
    elif args.command == "contracts":
        runner = "pytest" if shutil.which("pytest") else "unittest"
        targets = ["pipeline/contracts", "pipeline/tests/test_database_contract.py", "pipeline/tests/test_graph_database_contract.py"] if runner == "pytest" else ["discover", "-s", "pipeline/contracts"]
        code = run([sys.executable, "-m", runner, *targets])
    else:
        cmd = [sys.executable, "-c", "from pipeline.common.review_packet import write_review_packet; import sys; write_review_packet(sys.argv[1], previous_normalized_path=sys.argv[2] if len(sys.argv)>2 else None)", args.run_dir]
        if args.previous_normalized: cmd.append(args.previous_normalized)
        code = run(cmd)
    SUMMARY["ok"], SUMMARY["exit_code"] = code == 0, code
    print(json.dumps(SUMMARY) if args.json else ("OK" if code == 0 else "FAILED") + f": {args.command}")
    return code
if __name__ == "__main__": raise SystemExit(main())
