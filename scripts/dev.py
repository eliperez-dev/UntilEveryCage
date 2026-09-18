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

def run(args: list[str], *, cwd=ROOT, capture=False) -> int:
    result = subprocess.run(args, cwd=cwd, capture_output=capture, text=True)
    if capture and result.returncode != 0:
        SUMMARY["checks"].append({"name": "delegated-command", "ok": False, "detail": "failed"})
    return result.returncode

def check(name: str, ok: bool, detail: str) -> None:
    SUMMARY["checks"].append({"name": name, "ok": ok, "detail": detail})

def local_v2_database_running() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=uec-local-v2-postgres-1", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "uec-local-v2-postgres-1" in result.stdout.splitlines()

def doctor(_: argparse.Namespace) -> int:
    for name in ("docker", "python", "cargo", "node", "npm"):
        path = shutil.which(name)
        check(name, bool(path), "available" if path else "not found")
    compose = shutil.which("docker") is not None
    if compose:
        result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
        check("compose", result.returncode == 0, "available" if result.returncode == 0 else "unavailable")
    else: check("compose", False, "Docker not found")
    npm_manifest = ROOT / "node_modules" / "jest" / "bin" / "jest.js"
    check("root-js-dependencies", npm_manifest.is_file(), "installed" if npm_manifest.is_file() else "missing (run npm ci)")
    if sys.platform == "win32": check("powershell", bool(shutil.which("powershell") or shutil.which("pwsh")), "required by local-v2")
    local_db = local_v2_database_running()
    for port in (8000, 5433):
        sock = socket.socket(); sock.settimeout(.2)
        try: busy = sock.connect_ex(("127.0.0.1", port)) == 0
        finally: sock.close()
        if port == 5433 and busy and local_db:
            check(f"port:{port}", True, "in use by the expected uec-local-v2 Postgres")
        else:
            check(f"port:{port}", not busy, "free" if not busy else "in use by an unknown process")
    required = ("UEC_RUNTIME_MODE", "UEC_DATABASE_URL")
    for key in required:
        # Only report presence; never print values.
        check(f"env:{key}", True if os.environ.get(key) else None, "set" if os.environ.get(key) else "not set (local defaults may apply)")
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
    sub.add_parser("demo", help="run the safe synthetic/private tooling demo")
    sub.add_parser("preflight", help="alias for doctor: verify local prerequisites before a run")
    sub.add_parser("platform-registry", help="validate the joined country/source registry")
    rc = sub.add_parser("review-console-snapshot", help="build the row-free private review-console readiness snapshot")
    rc.add_argument("output", default=str(ROOT / "static" / "private-review" / "readiness-matrix.json"), nargs="?")
    pf = sub.add_parser("private-frontend", help="rehearse a candidate against the private frontend preview boundary")
    pf.add_argument("manifest"); pf.add_argument("output"); pf.add_argument("--root", default=str(ROOT)); pf.add_argument("--base-url"); pf.add_argument("--token")
    rp = sub.add_parser("review-packet", help="generate a private row-free review packet")
    rp.add_argument("run_dir"); rp.add_argument("--previous-normalized")
    re = sub.add_parser("review-export", help="export the private row-free review packet")
    re.add_argument("run_dir"); re.add_argument("--previous-normalized")
    diag = sub.add_parser("diagnostics", help="build a row-free manifest/source diagnostic")
    diag.add_argument("output"); diag.add_argument("--manifest-root", default="data/manifests")
    args = p.parse_args(); SUMMARY["command"] = args.command
    if args.command in ("doctor", "preflight"): code = doctor(args)
    elif args.command in ("up", "down", "status", "probe"): code = run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(LOCAL_V2), {"up":"start","down":"stop"}.get(args.command,args.command)], capture=args.json)
    elif args.command == "logs": code = run(["docker", "compose", "-p", "uec-local-v2", "-f", "docker-compose.pipeline.yml", "logs", "--tail=100"], capture=args.json)
    elif args.command == "test": code = run(["npm", "test", "--", *( ["--runInBand"] if not args.full else [])], capture=args.json)
    elif args.command == "pipeline":
        runner = "pytest" if shutil.which("pytest") else "unittest"
        code = run([sys.executable, "-m", runner, *(args.args or ["discover", "-s", "pipeline"])], capture=args.json)
    elif args.command == "contracts":
        runner = "pytest" if shutil.which("pytest") else "unittest"
        targets = ["pipeline/contracts", "pipeline/tests/test_database_contract.py", "pipeline/tests/test_graph_database_contract.py"] if runner == "pytest" else ["discover", "-s", "pipeline/contracts", "-t", str(ROOT)]
        code = run([sys.executable, "-m", runner, *targets], capture=args.json)
    elif args.command == "demo":
        # The demo is intentionally synthetic and read-only: it exercises the
        # contract/review boundary without acquiring, importing, or publishing.
        code = run([sys.executable, "-m", "unittest", "pipeline.common.test_graph_candidates", "pipeline.common.test_review_packet"], capture=args.json)
    elif args.command == "platform-registry":
        code = run([sys.executable, "-c", "import json; from pipeline.platform_registry import build_platform_registry; r=build_platform_registry(); print(json.dumps({'countries':r['country_count'],'sources':r['source_count'],'status':'validated'}))"], capture=args.json)
    elif args.command == "review-console-snapshot":
        code = run([sys.executable, str(ROOT / "pipeline/scripts/diagnostics/build-review-console-snapshot.py"), args.output], capture=args.json)
    elif args.command == "private-frontend":
        cmd = [sys.executable, str(ROOT / "pipeline/scripts/maintenance/rehearse_candidate_private_frontend.py"), "--manifest", args.manifest, "--root", args.root, "--output", args.output]
        if args.base_url: cmd.extend(["--base-url", args.base_url])
        if args.token: cmd.extend(["--token", args.token])
        code = run(cmd, capture=args.json)
    elif args.command == "diagnostics":
        code = run([sys.executable, str(ROOT / "pipeline/scripts/diagnostics/real_corpus_report.py"), "--manifest-root", args.manifest_root, "--output", args.output], capture=args.json)
    elif args.command in ("review-packet", "review-export"):
        cmd = [sys.executable, "-c", "from pipeline.common.review_packet import write_review_packet; import sys; write_review_packet(sys.argv[1], previous_normalized_path=sys.argv[2] if len(sys.argv)>2 else None)", args.run_dir]
        if args.previous_normalized: cmd.append(args.previous_normalized)
        code = run(cmd, capture=args.json)
    SUMMARY["ok"], SUMMARY["exit_code"] = code == 0, code
    print(json.dumps(SUMMARY) if args.json else ("OK" if code == 0 else "FAILED") + f": {args.command}")
    return code
if __name__ == "__main__": raise SystemExit(main())
