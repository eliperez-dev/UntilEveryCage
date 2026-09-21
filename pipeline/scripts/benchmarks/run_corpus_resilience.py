"""Run a bounded, disposable large-corpus resilience rehearsal.

The rehearsal expands only row-free aggregate distribution metadata into a
synthetic corpus.  It exercises the real candidate importer in independently
committed batches, a post-commit interruption/resume, duplicate import, full
migration timing, database sizing, and a custom-format backup/restore with a
current suppression ledger replay.  Generated rows, dump files, ledger
references, and database contents stay in a temporary disposable environment.

The JSON report is deliberately aggregate-only.  It never includes a source
record key, identifier, address, coordinate, source value, or response body.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DISTRIBUTION = PROJECT_ROOT / "data/manifests/sprint4-real-corpus-regression.json"
MAX_RECORDS = 50_000
MAX_BATCH_SIZE = 2_000
DEFAULT_BATCH_SIZE = 500
MAX_INTERRUPTION_BATCHES = 4
SCHEMA_VERSION = "corpus-resilience-v1"


class ResilienceError(ValueError):
    """The rehearsal input or disposable safety boundary is invalid."""


class SimulatedInterruption(RuntimeError):
    """Raised by the post-commit hook to model a lost importer process."""


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ResilienceError(f"script is unavailable: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _distribution_counts(report: dict[str, Any]) -> dict[str, int]:
    coverage = report.get("coverage", {})
    counts = coverage.get("selected_records_by_source")
    if not isinstance(counts, dict):
        counts = report.get("source_counts")
    if not isinstance(counts, dict) or not counts:
        raise ResilienceError("distribution report has no aggregate source counts")
    parsed: dict[str, int] = {}
    for source, count in counts.items():
        if not isinstance(source, str) or not source:
            raise ResilienceError("distribution report contains an invalid source label")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ResilienceError(f"distribution report contains an invalid count for {source}")
        if count:
            parsed[source] = count
    if not parsed:
        raise ResilienceError("distribution report contains no positive source counts")
    return parsed


def _proportional_allocation(counts: dict[str, int], limit: int) -> dict[str, int]:
    available = sum(counts.values())
    if limit >= available:
        return dict(sorted(counts.items()))
    raw = {source: count * limit / available for source, count in counts.items()}
    allocation = {source: int(value) for source, value in raw.items()}
    remainder = limit - sum(allocation.values())
    order = sorted(raw, key=lambda source: (-(raw[source] - allocation[source]), source))
    for source in order[:remainder]:
        allocation[source] += 1
    return {source: allocation[source] for source in sorted(allocation) if allocation[source]}


def build_plan(distribution_path: Path, max_records: int = MAX_RECORDS) -> dict[str, Any]:
    """Build a deterministic row-free selection plan from aggregate metadata."""
    if max_records <= 0 or max_records > MAX_RECORDS:
        raise ResilienceError(f"max_records must be between 1 and {MAX_RECORDS}")
    try:
        report = json.loads(distribution_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResilienceError("distribution report cannot be read") from exc
    counts = _distribution_counts(report)
    selected = _proportional_allocation(counts, max_records)
    return {
        "selection_method": "proportional-largest-remainder-from-row-free-source-counts",
        "available_records": sum(counts.values()),
        "selected_records": sum(selected.values()),
        "source_profiles": len(selected),
        "selected_records_by_source": selected,
        "input_report": distribution_path.as_posix(),
    }


def _slug(source: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in source).strip("-")


def _country_code(source: str) -> str:
    parts = source.split(".")
    for part in parts:
        if len(part) == 2 and part.isalpha():
            return part.upper()
    return "ZZ"


def _synthetic_record(source: str, row_number: int) -> dict[str, Any]:
    slug = _slug(source)
    establishment_id = f"RES-{slug}-{row_number:06d}"
    category = ("slaughter", "processing", "cutting", "logistics_and_storage")[row_number % 4]
    return {
        "source_id": source,
        "source_row": row_number,
        "source_values": {
            "fixture_kind": "synthetic-resilience-shape",
            "source_partition": slug,
            "ordinal": row_number,
        },
        "normalized": {
            "establishment_id": establishment_id,
            "trading_name": f"Synthetic resilience facility {row_number}",
            "city": f"Synthetic city {row_number % 97}",
            "country_code": _country_code(source),
            "nation": _country_code(source),
            "activity_categories": [category],
            "coordinates": None,
            "coordinate_state": "unknown",
            "privacy_gate": "pending-review",
            "coordinate_gate": "review_required",
            "publication_gate": "blocked",
            "source_origin": "synthetic-fixture",
        },
    }


def write_synthetic_corpus(root: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Write temporary partition files and return only metadata about them."""
    partitions: list[dict[str, Any]] = []
    for source, count in plan["selected_records_by_source"].items():
        partition = root / _slug(source)
        partition.mkdir(parents=True, exist_ok=True)
        raw_path = partition / "source.bin"
        raw = f"synthetic resilience artifact for {source}\n".encode("utf-8")
        raw_path.write_bytes(raw)
        raw_digest = hashlib.sha256(raw).hexdigest()
        normalized_path = partition / "normalized.jsonl"
        normalized_digest = hashlib.sha256()
        with normalized_path.open("wb") as handle:
            for row_number in range(1, count + 1):
                line = (json.dumps(_synthetic_record(source, row_number), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                handle.write(line)
                normalized_digest.update(line)
        manifest = {
            "source_id": f"resilience.{_slug(source)}",
            "source_url": f"https://example.invalid/resilience/{_slug(source)}",
            "retrieved_at_utc": "2026-09-16T00:00:00Z",
            "checksum_sha256": raw_digest,
            "byte_size": len(raw),
            "normalized_rows": count,
            "normalized_sha256": normalized_digest.hexdigest(),
            "release_state": "not-created",
            "publication_state": "private-candidate",
            "country_code": _country_code(source),
            "code_version": SCHEMA_VERSION,
            "config_version": "synthetic-shape-v1",
            "profile": "private-resilience-test-only",
        }
        manifest_path = partition / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        partitions.append({
            "source": source,
            "source_id": manifest["source_id"],
            "rows": count,
            "manifest": manifest_path,
            "normalized": normalized_path,
            "raw": raw_path,
        })
    return partitions


def _compose(root: Path, project: str) -> list[str]:
    return ["docker", "compose", "-p", project, "-f", str(root / "docker-compose.e2e.yml")]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run(command: list[str], *, env: dict[str, str], check: bool = True, **kwargs: Any) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, env=env, check=check, **kwargs)
    except FileNotFoundError as exc:
        raise ResilienceError("Docker Compose is required for the database rehearsal") from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or "").strip()
        detail = output.splitlines()[-1] if output else "no command output"
        raise ResilienceError(f"disposable command failed with exit {exc.returncode}: {detail}") from exc


def _counts(connection, release_id: str, source_ids: list[str]) -> dict[str, int]:
    return {
        "source_records": connection.execute(
            "SELECT count(*) FROM uec.source_records WHERE source_id = ANY(%s)", (source_ids,)
        ).fetchone()[0],
        "facilities": connection.execute(
            """SELECT count(*) FROM uec.facilities facility
               WHERE EXISTS (
                 SELECT 1 FROM uec.observations observation
                 JOIN uec.source_records record ON record.source_record_id = observation.source_record_id
                 WHERE observation.facility_id = facility.facility_id AND record.source_id = ANY(%s)
               )""", (source_ids,)
        ).fetchone()[0],
        "observations": connection.execute(
            """SELECT count(*) FROM uec.observations observation
               JOIN uec.source_records record ON record.source_record_id = observation.source_record_id
               WHERE record.source_id = ANY(%s)""", (source_ids,)
        ).fetchone()[0],
        "release_members": connection.execute(
            "SELECT count(*) FROM uec.release_members WHERE release_id=%s", (release_id,)
        ).fetchone()[0],
        "review_events": connection.execute(
            """SELECT count(*) FROM uec.publication_review_events event
               JOIN uec.source_records record ON record.source_record_id = event.source_record_id
               WHERE record.source_id = ANY(%s)""", (source_ids,)
        ).fetchone()[0],
    }


def _database_size(connection) -> int:
    return int(connection.execute("SELECT pg_database_size(current_database())").fetchone()[0])


def _make_ledger(path: Path, source_id: str, source_record_key: str, revision: str) -> dict[str, Any]:
    ledger_module = _load_script(
        "restriction_ledger_gate_for_resilience",
        PROJECT_ROOT / "pipeline/scripts/maintenance/restriction-ledger-gate.py",
    )
    ledger = {
        "schema_version": 1,
        "revision": revision,
        "active_restrictions": [{
            "source_id": source_id,
            "source_record_key": source_record_key,
            "scope": "whole_record",
            "action": "suppress",
        }],
    }
    ledger["ledger_sha256"] = ledger_module.ledger_digest(ledger)
    path.write_text(json.dumps(ledger, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return ledger


def _row_key(source: str) -> str:
    return f"1:RES-{_slug(source)}-000001"


def _aggregate_report(plan: dict[str, Any], *, status: str, generated_peak_bytes: int, limitations: list[str]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "corpus": {
            "selection_method": plan["selection_method"],
            "available_records": plan["available_records"],
            "selected_records": plan["selected_records"],
            "source_profiles": plan["source_profiles"],
            "selected_records_by_source": plan["selected_records_by_source"],
        },
        "limits": {
            "max_records": MAX_RECORDS,
            "max_batch_size": MAX_BATCH_SIZE,
            "max_interruption_batches": MAX_INTERRUPTION_BATCHES,
            "database": "loopback-only disposable PostGIS compose project",
            "report": "aggregate-only; generated rows and opaque ledger references are excluded",
        },
        "memory_observation": {
            "method": "Python tracemalloc peak during temporary synthetic generation",
            "peak_bytes": generated_peak_bytes,
        },
        "privacy": {
            "source_payloads_committed": False,
            "generated_rows_persisted": False,
            "database_disposable": True,
        },
        "limitations": limitations,
    }


def run_rehearsal(
    *,
    root: Path = PROJECT_ROOT,
    distribution: Path = DEFAULT_DISTRIBUTION,
    max_records: int = MAX_RECORDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    interrupt_after_batches: int = 1,
    plan_only: bool = False,
) -> dict[str, Any]:
    if batch_size <= 0 or batch_size > MAX_BATCH_SIZE:
        raise ResilienceError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    if interrupt_after_batches < 0 or interrupt_after_batches > MAX_INTERRUPTION_BATCHES:
        raise ResilienceError(f"interrupt_after_batches must be between 0 and {MAX_INTERRUPTION_BATCHES}")
    plan = build_plan(distribution, max_records)
    with tempfile.TemporaryDirectory(prefix="uec-corpus-resilience-") as temporary:
        temporary_root = Path(temporary)
        tracemalloc.start()
        partitions = write_synthetic_corpus(temporary_root / "corpus", plan)
        _, generated_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if plan_only:
            report = _aggregate_report(
                plan,
                status="plan-only",
                generated_peak_bytes=generated_peak,
                limitations=[
                    "Database migration/import/backup/restore timings require Docker Desktop and were not run in plan-only mode.",
                    "Synthetic rows are generated from aggregate distribution counts; no real row payload is used.",
                ],
            )
            return report

        psycopg = _load_script("psycopg_for_corpus_resilience", PROJECT_ROOT / "pipeline/scripts/maintenance/import-candidate.py").psycopg
        importer = _load_script("import_candidate_for_corpus_resilience", PROJECT_ROOT / "pipeline/scripts/maintenance/import-candidate.py")
        migrations = _load_script("apply_migrations_for_corpus_resilience", PROJECT_ROOT / "pipeline/scripts/maintenance/apply-migrations.py")
        ledger_replay = _load_script("replay_ledger_for_corpus_resilience", PROJECT_ROOT / "pipeline/scripts/maintenance/replay-restriction-ledger.py")
        ledger_gate = _load_script("ledger_gate_for_corpus_resilience", PROJECT_ROOT / "pipeline/scripts/maintenance/restriction-ledger-gate.py")

        project = f"uec-resilience-{os.getpid()}-{int(time.time())}"
        port = _free_port()
        database_url = f"postgresql://uec:uec-e2e@127.0.0.1:{port}/uec?sslmode=disable"
        compose = _compose(root, project)
        environment = os.environ.copy()
        environment["UEC_E2E_DB_PORT"] = str(port)
        release_id = "candidate-corpus-resilience"
        source_ids = [partition["source_id"] for partition in partitions]
        rehearsal_started = time.perf_counter()
        migration_started = None
        import_started = None
        duplicate_started = None
        backup_started = None
        restore_started = None
        replay_started = None
        interrupted = False
        interrupted_rows = 0
        resumed_rows = 0
        duplicate_new_rows = 0
        peak_loaded_bytes = 0
        max_loaded_rows = 0
        initial_counts: dict[str, int] | None = None
        final_counts: dict[str, int] | None = None
        dump_bytes = 0
        migration_versions: list[str] = []
        try:
            _run(compose + ["up", "-d", "--wait"], env=environment, cwd=root, capture_output=True, text=True)
            migration_started = time.perf_counter()
            migration_versions = migrations.apply(database_url, root / "pipeline/migrations")
            migration_seconds = time.perf_counter() - migration_started
            import_started = time.perf_counter()
            interruption_partition = max(range(len(partitions)), key=lambda index: partitions[index]["rows"])
            for index, partition in enumerate(partitions):
                tracemalloc.start()
                manifest, rows = importer.load_inputs(partition["manifest"], partition["normalized"], partition["raw"])
                max_loaded_rows = max(max_loaded_rows, len(rows))

                def interrupt_after_commit(batch_number: int, _offset: int, batch_count: int) -> None:
                    nonlocal interrupted, interrupted_rows
                    interrupted_rows += batch_count
                    if batch_number >= interrupt_after_batches and interrupt_after_batches:
                        interrupted = True
                        raise SimulatedInterruption("synthetic process interruption after committed batch")

                if index == interruption_partition and interrupt_after_batches:
                    try:
                        importer.import_candidate(
                            database_url, manifest, rows, release_id, False, batch_size,
                            on_batch_committed=interrupt_after_commit,
                        )
                    except SimulatedInterruption:
                        pass
                    resumed_rows += importer.import_candidate(database_url, manifest, rows, release_id, False, batch_size)
                else:
                    importer.import_candidate(database_url, manifest, rows, release_id, False, batch_size)
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                peak_loaded_bytes = max(peak_loaded_bytes, peak)
            import_seconds = time.perf_counter() - import_started

            with psycopg.connect(database_url) as connection:
                initial_counts = _counts(connection, release_id, source_ids)
                initial_size = _database_size(connection)
            duplicate_started = time.perf_counter()
            for partition in partitions:
                manifest, rows = importer.load_inputs(partition["manifest"], partition["normalized"], partition["raw"])
                duplicate_new_rows += importer.import_candidate(database_url, manifest, rows, release_id, False, batch_size)
            duplicate_seconds = time.perf_counter() - duplicate_started
            with psycopg.connect(database_url) as connection:
                duplicate_counts = _counts(connection, release_id, source_ids)
            if duplicate_counts != initial_counts:
                raise ResilienceError("duplicate import changed corpus row counts")

            dump_path = temporary_root / "corpus.dump"
            backup_started = time.perf_counter()
            with dump_path.open("wb") as handle:
                _run(compose + ["exec", "-T", "postgres", "pg_dump", "-U", "uec", "-d", "uec", "--format=custom"], env=environment, cwd=root, stdout=handle, stderr=subprocess.PIPE)
            dump_bytes = dump_path.stat().st_size
            backup_seconds = time.perf_counter() - backup_started

            restricted_source = partitions[interruption_partition]["source_id"]
            restricted_key = _row_key(partitions[interruption_partition]["source"])
            ledger_path = temporary_root / "current-ledger.json"
            ledger = _make_ledger(ledger_path, restricted_source, restricted_key, "resilience-current-r1")
            replay_started = time.perf_counter()
            replay_before_backup = ledger_replay.replay(database_url, ledger_path)
            replay_before_backup_seconds = time.perf_counter() - replay_started
            with psycopg.connect(database_url) as connection:
                restricted_before_restore = connection.execute(
                    """SELECT count(*) FROM uec.public_access_restricted restricted
                       JOIN uec.source_records record ON record.source_record_id = restricted.source_record_id
                       WHERE record.source_id=%s AND record.source_record_key=%s""",
                    (restricted_source, restricted_key),
                ).fetchone()[0]

            _run(compose + ["cp", str(dump_path), "postgres:/tmp/uec-corpus-resilience.dump"], env=environment, cwd=root, capture_output=True, text=True)
            restore_started = time.perf_counter()
            _run(compose + ["exec", "-T", "postgres", "pg_restore", "-U", "uec", "-d", "uec", "--clean", "--if-exists", "--exit-on-error", "/tmp/uec-corpus-resilience.dump"], env=environment, cwd=root, capture_output=True, text=True)
            restore_seconds = time.perf_counter() - restore_started
            with psycopg.connect(database_url) as connection:
                after_restore_counts = _counts(connection, release_id, source_ids)
                restricted_after_restore = connection.execute(
                    """SELECT count(*) FROM uec.public_access_restricted restricted
                       JOIN uec.source_records record ON record.source_record_id = restricted.source_record_id
                       WHERE record.source_id=%s AND record.source_record_key=%s""",
                    (restricted_source, restricted_key),
                ).fetchone()[0]
            if after_restore_counts != initial_counts or restricted_after_restore != 0:
                raise ResilienceError("restored database did not match the pre-suppression backup state")

            stale_snapshot = {
                "ledger_revision": ledger["revision"],
                "ledger_sha256": ledger["ledger_sha256"],
                "active_restrictions": [],
            }
            stale_gate_rejected = False
            try:
                ledger_gate.pre_service_gate(ledger_path, stale_snapshot)
            except ledger_gate.RestrictionLedgerError:
                stale_gate_rejected = True
            if not stale_gate_rejected:
                raise ResilienceError("pre-service gate accepted a restored database before replay")

            replay_started = time.perf_counter()
            replay_after_restore = ledger_replay.replay(database_url, ledger_path)
            replay_after_restore_seconds = time.perf_counter() - replay_started
            replayed_snapshot_path = temporary_root / "replayed-snapshot.json"
            replayed_snapshot = ledger_replay.write_replayed_snapshot(database_url, ledger_path, replayed_snapshot_path)
            ledger_gate.pre_service_gate(ledger_path, json.loads(replayed_snapshot_path.read_text(encoding="utf-8")))
            with psycopg.connect(database_url) as connection:
                restricted_after_replay = connection.execute(
                    """SELECT count(*) FROM uec.public_access_restricted restricted
                       JOIN uec.source_records record ON record.source_record_id = restricted.source_record_id
                       WHERE record.source_id=%s AND record.source_record_key=%s""",
                    (restricted_source, restricted_key),
                ).fetchone()[0]
                final_counts = _counts(connection, release_id, source_ids)
                final_size = _database_size(connection)
            if restricted_after_replay != 1 or final_counts != initial_counts:
                raise ResilienceError("current suppression replay did not restore the fail-closed state")
            total_seconds = time.perf_counter() - rehearsal_started
            report = _aggregate_report(
                plan,
                status="pass",
                generated_peak_bytes=generated_peak,
                limitations=[
                    "The corpus is synthetic and represents row-count/source-shape distribution only; it is not a real acquisition or quality claim.",
                    "tracemalloc observes Python allocations, not PostgreSQL shared buffers, container RSS, or OS-level peak memory.",
                    "Backup/restore uses a local custom-format pg_dump inside a disposable PostGIS container; cloud storage, WAL, operator access, and disaster recovery are out of scope.",
                ],
            )
            report.update({
                "migrations": {"applied": len(migration_versions), "elapsed_seconds": round(migration_seconds, 3)},
                "import": {
                    "elapsed_seconds": round(import_seconds, 3),
                    "interruption_triggered": interrupted,
                    "interrupted_committed_rows_observed": interrupted_rows,
                    "resumed_new_rows": resumed_rows,
                    "expected_rows": plan["selected_records"],
                    "batch_size": batch_size,
                },
                "duplicate_import": {
                    "elapsed_seconds": round(duplicate_seconds, 3),
                    "new_rows": duplicate_new_rows,
                    "counts_unchanged": duplicate_counts == initial_counts,
                },
                "backup_restore": {
                    "backup_elapsed_seconds": round(backup_seconds, 3),
                    "restore_elapsed_seconds": round(restore_seconds, 3),
                    "replay_before_backup_elapsed_seconds": round(replay_before_backup_seconds, 3),
                    "replay_after_restore_elapsed_seconds": round(replay_after_restore_seconds, 3),
                    "custom_dump_bytes": dump_bytes,
                    "pre_restore_suppressed_rows": restricted_before_restore,
                    "restored_suppressed_rows_before_replay": restricted_after_restore,
                    "stale_pre_service_gate_rejected": stale_gate_rejected,
                    "replay_before_restore_new_events": replay_before_backup["new_events"],
                    "replay_after_restore_new_events": replay_after_restore["new_events"],
                    "replayed_snapshot_reference_count": replayed_snapshot["reference_count"],
                    "suppressed_rows_after_replay": restricted_after_replay,
                },
                "database": {
                    "initial_size_bytes": initial_size,
                    "final_size_bytes": final_size,
                    "row_counts": final_counts,
                },
                "runtime_seconds": round(total_seconds, 3),
                "memory_observation": {
                    "method": "Python tracemalloc peak during one-partition load/import",
                    "synthetic_generation_peak_bytes": generated_peak,
                    "load_import_peak_bytes": peak_loaded_bytes,
                    "max_loaded_partition_rows": max_loaded_rows,
                },
            })
            return report
        finally:
            try:
                _run(compose + ["down", "-v", "--remove-orphans"], env=environment, cwd=root, capture_output=True, text=True, check=False)
            except ResilienceError:
                # If startup failed because Docker is unavailable there is no
                # disposable project to tear down; preserve the useful error.
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", type=Path, default=DEFAULT_DISTRIBUTION)
    parser.add_argument("--max-records", type=int, default=MAX_RECORDS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--interrupt-after-batches", type=int, default=1)
    parser.add_argument("--plan-only", action="store_true", help="generate and measure the disposable synthetic plan without Docker/Postgres")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    report = run_rehearsal(
        distribution=args.distribution,
        max_records=args.max_records,
        batch_size=args.batch_size,
        interrupt_after_batches=args.interrupt_after_batches,
        plan_only=args.plan_only,
    )
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(encoded, encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "selected_records": report["corpus"]["selected_records"],
        "source_profiles": report["corpus"]["source_profiles"],
        "runtime_seconds": report.get("runtime_seconds"),
        "database_size_bytes": report.get("database", {}).get("final_size_bytes"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
