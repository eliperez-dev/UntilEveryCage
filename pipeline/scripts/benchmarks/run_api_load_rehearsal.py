#!/usr/bin/env python3
"""Run a bounded synthetic concurrent-load rehearsal against the real API.

The harness owns its E2E environment, seeds only synthetic public data, and
never accepts a non-loopback target. Response bodies and graph rows are read to
completion and immediately discarded; the report contains aggregate metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import sys
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MAX_SEED = 20_000
MAX_CONCURRENCY = 16
MAX_REQUESTS_PER_LEVEL = 80
QUERY_MIX = (
    ("list", "http", "/api/v2/locations?profile=official&limit=50"),
    ("filters", "http", "/api/v2/locations?profile=official&country_code=DK&category=slaughter&limit=50"),
    ("bbox", "http", "/api/v2/locations?profile=official&min_lon=-10&min_lat=45&max_lon=-9.99&max_lat=45.01&limit=50"),
    ("radius", "http", "/api/v2/locations?profile=official&longitude=-5&latitude=50&radius_km=50&limit=50"),
    ("facets", "http", "/api/v2/discovery/facets?profile=official"),
    ("detail", "detail", None),
    ("graph_ready", "graph", None),
)


def deterministic_uuid(prefix: str, ordinal: int) -> str:
    return str(uuid.UUID(hex=hashlib.md5(f"{prefix}-{ordinal}".encode()).hexdigest()))


def validate_levels(levels: list[int]) -> tuple[int, ...]:
    if not levels or any(level < 1 or level > MAX_CONCURRENCY for level in levels):
        raise ValueError(f"concurrency levels must be between 1 and {MAX_CONCURRENCY}")
    if len(set(levels)) != len(levels):
        raise ValueError("concurrency levels must be unique")
    return tuple(levels)


def validate_loopback_url(base_url: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base URL must be an http loopback origin without credentials or query text")
    if not parsed.hostname:
        raise ValueError("base URL must include a loopback host")
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname.lower() == "localhost"
    if not loopback:
        raise ValueError("load rehearsal refuses non-loopback targets")
    if parsed.path not in ("", "/"):
        raise ValueError("base URL must not include a path prefix")
    return parsed


def seed_public_projection(connection: Any, count: int) -> str:
    """Create a deterministic, promoted, synthetic projection in the E2E DB."""
    release_id = "load-promoted"
    connection.execute("INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method) VALUES ('load.synthetic','DK','Synthetic load source','https://example.invalid/load','fixture') ON CONFLICT DO NOTHING")
    connection.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,profile,test_only,summary) VALUES ('load-promoted','promoted','load-v1','official',false,'{}') ON CONFLICT DO NOTHING")
    manifest = {
        "eligible_record_count": count,
        "manifest_version": "load-v1",
        "profile": "official",
        "release_id": release_id,
        "ruleset_version": "load-v1",
    }
    encoded_manifest = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    connection.execute(
        "INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256) VALUES (%s,%s::jsonb,%s) ON CONFLICT DO NOTHING",
        (release_id, encoded_manifest, hashlib.sha256(encoded_manifest.encode("utf-8")).hexdigest()),
    )
    connection.execute("INSERT INTO uec.city_reference_points (country_code,city_name,reference_location,reference_source,source_retrieved_at,source_reference_id) VALUES ('DK','Loadville',ST_SetSRID(ST_Point(-5,50),4326)::geography,'https://example.invalid/load-city',TIMESTAMPTZ '2026-01-01 00:00:00+00','load-city') ON CONFLICT DO NOTHING")
    connection.execute("""
        INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at)
        SELECT md5('load-artifact-' || n::text)::uuid, 'synthetic/load/' || n::text,
               repeat(md5('load-sha-' || n::text),2), 1, TIMESTAMPTZ '2026-01-01 00:00:00+00'
        FROM generate_series(1,%s) n ON CONFLICT DO NOTHING
    """, (count,))
    connection.execute("""
        INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at)
        SELECT md5('load-record-' || n::text)::uuid, 'load.synthetic', 'load-' || n::text,
               md5('load-artifact-' || n::text)::uuid, '{}'::jsonb,
               TIMESTAMPTZ '2026-01-01 00:00:00+00' + n * interval '1 second'
        FROM generate_series(1,%s) n ON CONFLICT DO NOTHING
    """, (count,))
    connection.execute("""
        INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city)
        SELECT md5('load-facility-' || n::text)::uuid, 'Synthetic load facility ' || n,
               CASE WHEN n %% 2 = 0 THEN 'DK' ELSE 'SE' END, 'Loadville'
        FROM generate_series(1,%s) n ON CONFLICT DO NOTHING
    """, (count,))
    connection.execute("""
        INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,coordinate_review_status,first_observed_at)
        SELECT md5('load-observation-' || n::text)::uuid, md5('load-facility-' || n::text)::uuid,
               md5('load-record-' || n::text)::uuid,
               TIMESTAMPTZ '2026-01-01 00:00:00+00' + n * interval '1 second', '{}'::jsonb, '{}'::jsonb,
               'load-v1','synthetic',
               CASE n %% 4 WHEN 0 THEN 'slaughter' WHEN 1 THEN 'fish_processing' WHEN 2 THEN 'logistics_and_storage' ELSE 'retail_and_prepared_food' END,
               'approved',true,'approved',TIMESTAMPTZ '2026-01-01 00:00:00+00' + n * interval '1 second'
        FROM generate_series(1,%s) n ON CONFLICT DO NOTHING
    """, (count,))
    connection.execute("""
        INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible)
        SELECT 'load-promoted',md5('load-facility-' || n::text)::uuid,md5('load-observation-' || n::text)::uuid,true
        FROM generate_series(1,%s) n ON CONFLICT DO NOTHING
    """, (count,))
    connection.execute("""
        INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at)
        SELECT md5('load-record-' || n::text)::uuid,'synthetic-fixture','synthetic load query','fixture','accepted',1,
               ST_SetSRID(ST_Point(-10 + (n %% 2000) / 100.0,45 + (n %% 1000) / 100.0),4326)::geography,
               TIMESTAMPTZ '2026-01-01 00:00:00+00' + n * interval '1 second'
        FROM generate_series(1,%s) n ON CONFLICT DO NOTHING
    """, (count,))
    connection.execute("""
        INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role,reviewed_at)
        SELECT md5('load-record-' || n::text)::uuid,'load-promoted','reviewed','passed','approved',true,'synthetic-reviewer',
               TIMESTAMPTZ '2026-01-02 00:00:00+00' + n * interval '1 second'
        FROM generate_series(1,%s) n ON CONFLICT DO NOTHING
    """, (count,))
    connection.execute("""
        INSERT INTO uec.organizations (organization_id,canonical_name,country_code,organization_type)
        SELECT md5('load-organization-' || n::text)::uuid,'Synthetic load organization ' || n,'DK','company'
        FROM generate_series(1,%s) n ON CONFLICT DO NOTHING
    """, (count,))
    connection.execute("""
        INSERT INTO uec.organization_relationship_observations
          (relationship_observation_id,source_id,source_record_id,from_organization_id,target_facility_id,relationship_type,observed_at,confidence,review_state,storage_state,privacy_status,publication_status,release_id)
        SELECT md5('load-relationship-' || n::text)::uuid,'load.synthetic',md5('load-record-' || n::text)::uuid,
               md5('load-organization-' || n::text)::uuid,md5('load-facility-' || n::text)::uuid,'operator',
               TIMESTAMPTZ '2026-01-02 00:00:00+00' + n * interval '1 second',0.9,'accepted','released','passed','released','load-promoted'
        FROM generate_series(1,%s) n ON CONFLICT DO NOTHING
    """, (count,))
    connection.execute("""
        INSERT INTO uec.claims
          (claim_id,source_id,source_record_id,facility_id,claim_domain,claim_kind,value_state,claim_value,observed_at,confidence,review_state,storage_state,privacy_status,publication_status,release_id)
        SELECT md5('load-claim-' || n::text)::uuid,'load.synthetic',md5('load-record-' || n::text)::uuid,
               md5('load-facility-' || n::text)::uuid,'operation','synthetic_status','known','{}'::jsonb,
               TIMESTAMPTZ '2026-01-02 00:00:00+00' + n * interval '1 second',0.9,'accepted','released','passed','released','load-promoted'
        FROM generate_series(1,%s) n ON CONFLICT DO NOTHING
    """, (count,))
    connection.commit()
    for table in ("uec.raw_artifacts", "uec.source_records", "uec.facilities", "uec.observations", "uec.release_members", "uec.geocode_results", "uec.publication_review_events", "uec.organization_relationship_observations", "uec.claims"):
        connection.execute(f"ANALYZE {table}")
    connection.commit()
    return deterministic_uuid("load-facility", 1)


@dataclass(frozen=True)
class Sample:
    route: str
    elapsed_ms: float
    status: int
    timed_out: bool
    error_kind: str | None
    response_bytes: int


def _http_request(parsed: urllib.parse.SplitResult, route: str, path: str, worker: int, timeout: float) -> Sample:
    started = time.perf_counter()
    try:
        source_ip = f"127.0.0.{10 + (worker % 200)}"
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout, source_address=(source_ip, 0))
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        body_size = len(response.read(2_000_001))
        status = response.status
        connection.close()
        return Sample(route, (time.perf_counter() - started) * 1000, status, False, None, body_size)
    except TimeoutError:
        return Sample(route, (time.perf_counter() - started) * 1000, 0, True, "timeout", 0)
    except OSError:
        return Sample(route, (time.perf_counter() - started) * 1000, 0, False, "connection_error", 0)


def _graph_request(database_url: str, route: str) -> Sample:
    started = time.perf_counter()
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=2) as connection:
            connection.execute("""
                SELECT count(*) FROM (
                  SELECT relationship.relationship_type
                  FROM uec.graph_public_relationships relationship
                  JOIN uec.graph_public_claims claim
                    ON claim.release_id = relationship.release_id
                   AND claim.facility_id = relationship.target_facility_id
                  WHERE relationship.release_id = 'load-promoted'
                  ORDER BY relationship.relationship_observation_id LIMIT 50
                ) bounded
            """).fetchone()[0]
        return Sample(route, (time.perf_counter() - started) * 1000, 200, False, None, 0)
    except TimeoutError:
        return Sample(route, (time.perf_counter() - started) * 1000, 0, True, "timeout", 0)
    except OSError:
        return Sample(route, (time.perf_counter() - started) * 1000, 0, False, "connection_error", 0)


def _run_sample(base: str, database_url: str, detail_id: str, job: tuple[str, str, str | None], worker: int, timeout: float) -> Sample:
    route, kind, path = job
    if kind == "detail":
        path = f"/api/v2/locations/{detail_id}?profile=official"
    if kind == "graph":
        return _graph_request(database_url, route)
    return _http_request(urllib.parse.urlsplit(base), route, path or "/", worker, timeout)


class DbSampler:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.stop = threading.Event()
        self.max_active = 0
        self.max_waiting = 0
        self.max_connections = None
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        try:
            import psycopg
            with psycopg.connect(self.database_url, connect_timeout=2) as connection:
                self.max_connections = int(connection.execute("SHOW max_connections").fetchone()[0])
                while not self.stop.is_set():
                    row = connection.execute("""
                        SELECT count(*) FILTER (WHERE datname=current_database() AND state='active'),
                               count(*) FILTER (WHERE datname=current_database() AND wait_event_type IS NOT NULL)
                        FROM pg_stat_activity
                    """).fetchone()
                    self.max_active = max(self.max_active, int(row[0]))
                    self.max_waiting = max(self.max_waiting, int(row[1]))
                    self.stop.wait(0.02)
        except Exception:
            return

    def __enter__(self) -> "DbSampler":
        self.thread.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop.set()
        self.thread.join(timeout=3)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def summarize(samples: list[Sample], elapsed_s: float, sampler: DbSampler) -> dict[str, Any]:
    latencies = [sample.elapsed_ms for sample in samples]
    by_route = {}
    for route in sorted({sample.route for sample in samples}):
        route_samples = [sample for sample in samples if sample.route == route]
        by_route[route] = {
            "requests": len(route_samples),
            "successes": sum(sample.status == 200 for sample in route_samples),
            "client_errors": sum(400 <= sample.status < 500 for sample in route_samples),
            "server_errors": sum(sample.status >= 500 for sample in route_samples),
            "timeouts": sum(sample.timed_out for sample in route_samples),
            "latency_ms": {"p50": percentile([s.elapsed_ms for s in route_samples], .50), "p95": percentile([s.elapsed_ms for s in route_samples], .95), "p99": percentile([s.elapsed_ms for s in route_samples], .99)},
        }
    return {
        "requests": len(samples),
        "successes": sum(sample.status == 200 for sample in samples),
        "client_errors": sum(400 <= sample.status < 500 for sample in samples),
        "server_errors": sum(sample.status >= 500 for sample in samples),
        "timeouts": sum(sample.timed_out for sample in samples),
        "connection_errors": sum(sample.error_kind == "connection_error" for sample in samples),
        "throughput_rps": round(len(samples) / elapsed_s, 3) if elapsed_s else 0.0,
        "latency_ms": {"p50": percentile(latencies, .50), "p95": percentile(latencies, .95), "p99": percentile(latencies, .99), "max": round(max(latencies), 3) if latencies else 0.0},
        "response_bytes_total": sum(sample.response_bytes for sample in samples),
        "by_route": by_route,
        "database_signals": {"max_active_sessions": sampler.max_active, "max_waiting_sessions": sampler.max_waiting, "max_connections": sampler.max_connections},
        "pool_pressure_signals": {"http_503_or_higher": sum(sample.status >= 503 for sample in samples), "timeouts_or_connection_errors": sum(sample.timed_out or sample.error_kind == "connection_error" for sample in samples)},
    }


def build_recommendations(results: list[dict[str, Any]], timeout_ms: int) -> dict[str, Any]:
    clean_levels = [
        result["concurrency"]
        for result in results
        if result["timeouts"] == 0
        and result["server_errors"] == 0
        and result["connection_errors"] == 0
    ]
    if clean_levels:
        pool = max(clean_levels)
        basis = "highest tested level without timeout, server, or connection errors; not production capacity evidence"
    else:
        pool = None
        basis = "no clean tested concurrency level; keep production capacity and pool sizing blocked pending an approved representative load test"
    return {
        "initial_api_pool_per_process": pool,
        "clean_tested_concurrency_levels": clean_levels,
        "request_timeout_ms": timeout_ms,
        "radius_query_budget_ms": 350,
        "basis": basis,
    }


def run_rehearsal(env: Any, observations: int, levels: tuple[int, ...], requests_per_level: int, timeout_ms: int) -> dict[str, Any]:
    import psycopg
    with psycopg.connect(env.database_url) as connection:
        detail_id = seed_public_projection(connection, observations)
    base = f"http://127.0.0.1:{env.api_port}"
    results = []
    for concurrency in levels:
        jobs = [QUERY_MIX[index % len(QUERY_MIX)] for index in range(requests_per_level)]
        started = time.perf_counter()
        with DbSampler(env.database_url) as sampler:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(_run_sample, base, env.database_url, detail_id, job, index % concurrency, timeout_ms / 1000) for index, job in enumerate(jobs)]
                samples = [future.result() for future in futures]
        results.append({"concurrency": concurrency, **summarize(samples, time.perf_counter() - started, sampler)})
    return {
        "schema_version": 1,
        "synthetic_only": True,
        "observations": observations,
        "requests_per_level": requests_per_level,
        "timeout_ms": timeout_ms,
        "levels": results,
        "recommendations": build_recommendations(results, timeout_ms),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=int, default=5_000)
    parser.add_argument("--concurrency", default="1,4,8,16")
    parser.add_argument("--requests-per-level", type=int, default=40)
    parser.add_argument("--timeout-ms", type=int, default=2_000)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.observations <= MAX_SEED:
        parser.error(f"observations must be between 1 and {MAX_SEED:,}")
    if not 1 <= args.requests_per_level <= MAX_REQUESTS_PER_LEVEL:
        parser.error(f"requests-per-level must be between 1 and {MAX_REQUESTS_PER_LEVEL}")
    if not 100 <= args.timeout_ms <= 5_000:
        parser.error("timeout-ms must be between 100 and 5000")
    try:
        levels = validate_levels([int(value) for value in args.concurrency.split(",")])
        from pipeline.tests.e2e.fixture import E2EEnvironment
        env = E2EEnvironment().start()
        try:
            report = run_rehearsal(env, args.observations, levels, args.requests_per_level, args.timeout_ms)
        finally:
            env.stop()
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
