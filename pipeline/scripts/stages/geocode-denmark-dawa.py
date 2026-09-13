#!/usr/bin/env python3
"""Resumable, cached DAWA geocoder for the Denmark queue."""

import argparse
import json
import logging
import re
import hashlib
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger("uec.denmark.geocode")
MAX_BATCH = 100


def query_params(address: dict) -> dict:
    street = address.get("street") or ""
    match = re.match(r"^(.*?\s+\d+[A-Za-z]?(?:[-/]\d+[A-Za-z]?)?)(?:\s+(?:st\.?|\d+\.?\s*(?:th|tv|mf|sal)?))?\s*$", street, re.IGNORECASE)
    if match:
        address_part = match.group(1)
        street_name = address_part.rsplit(" ", 1)[0]
        house_number = address_part.rsplit(" ", 1)[1].split("-", 1)[0].split("/", 1)[0]
    else:
        street_name, house_number = street, None
    params = {"vejnavn": street_name, "postnr": address.get("postal_code"), "struktur": "mini", "fuzzy": "true"}
    if house_number:
        params["husnr"] = house_number
    return {key: value for key, value in params.items() if value}


def fetch(params: dict, base_url: str = "https://api.dataforsyningen.dk/adresser") -> tuple[int, object]:
    url = base_url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage/2.0 data-pipeline; contact: untileverycageproject@protonmail.com"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def acceptance(results: object) -> str:
    if not isinstance(results, list) or not results:
        return "unresolved"
    points = {(item.get("x"), item.get("y")) for item in results if item.get("x") is not None and item.get("y") is not None}
    if len(points) == 1:
        return "accepted_single_point"
    if len(points) > 1:
        return "review_multiple_points"
    return "unresolved"


def load_suppression_keys(path: Path | None) -> set[tuple[str, str]]:
    if not path:
        return set()
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        source_id, source_key = item.get("source_id"), item.get("source_record_key")
        if not isinstance(source_id, str) or not source_id.strip() or not isinstance(source_key, str) or not source_key.strip():
            raise ValueError("suppression entries require non-empty source_id and source_record_key")
        keys.add((source_id, source_key))
    return keys


def require_terms_review(path: Path | None) -> dict:
    if path is None:
        raise ValueError("network mode requires an approved terms review")
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("terms review cannot be read") from error
    required = {"reviewer", "reference", "reviewed_at", "decision", "notes"}
    if not isinstance(review, dict) or required - review.keys():
        raise ValueError("terms review requires reviewer, reference, reviewed_at, decision, and notes")
    if any(not isinstance(review[field], str) or not review[field].strip() for field in required):
        raise ValueError("terms review fields must be non-empty strings")
    try:
        datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("terms review reviewed_at must be ISO-8601") from error
    if review["decision"] != "approved":
        raise ValueError("terms review decision must be 'approved'")
    return {field: review[field] for field in sorted(required)}


def validate_provider_config(path: Path, network: bool, terms_review_path: Path | None) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = ("provider_id", "base_url", "mode", "status", "rate_limit_requests_per_second")
    if any(key not in config for key in required):
        raise ValueError("provider config is missing required approval/terms fields")
    if network:
        if config["status"] != "approved_for_development" or config["mode"] != "development_only":
            raise ValueError("network mode requires an explicitly development-approved provider")
        config["terms_review"] = require_terms_review(terms_review_path)
        config["terms_review_sha256"] = hashlib.sha256(terms_review_path.read_bytes()).hexdigest()
    if not isinstance(config["rate_limit_requests_per_second"], (int, float)) or config["rate_limit_requests_per_second"] <= 0:
        raise ValueError("provider rate limit must be positive")
    return config


def acquire_lock(output_path: Path) -> Path:
    lock = output_path.with_suffix(output_path.suffix + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid()}) + "\n")
    except FileExistsError as error:
        raise RuntimeError(f"geocode output is locked: {lock}; inspect and remove it only after confirming the owner is gone") from error
    return lock


def run(queue_path: Path, output_path: Path, limit: int, delay: float, retries: int, provider_config: Path, suppression_path: Path | None, terms_review_path: Path | None, network: bool = False) -> None:
    lock = acquire_lock(output_path)
    try:
        _run_locked(queue_path, output_path, limit, delay, retries, provider_config, suppression_path, terms_review_path, network)
    finally:
        lock.unlink(missing_ok=True)


def _run_locked(queue_path: Path, output_path: Path, limit: int, delay: float, retries: int, provider_config: Path, suppression_path: Path | None, terms_review_path: Path | None, network: bool = False) -> None:
    if limit <= 0 or limit > MAX_BATCH:
        raise ValueError(f"limit must be between 1 and {MAX_BATCH}; full-queue runs are not permitted")
    if not network:
        raise ValueError("network mode must be explicitly enabled; no provider requests were made")
    config = validate_provider_config(provider_config, network, terms_review_path)
    suppressed = load_suppression_keys(suppression_path)
    queue = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit:
        queue = queue[:limit]
    completed = {}
    if output_path.exists():
        for line in output_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                if item["queue_key"] in completed:
                    raise RuntimeError(f"duplicate queue entries detected in existing output; refusing resume: {output_path}")
                completed[item["queue_key"]] = item
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pending = [item for item in queue if item["queue_key"] not in completed and (item.get("source_id"), item.get("source_record_key")) not in suppressed]
    skipped = len(queue) - len(pending) - len([item for item in queue if item["queue_key"] in completed])
    LOGGER.info("stage=geocode status=started batch=%d completed=%d suppressed=%d pending=%d provider=%s", len(queue), len(completed), skipped, len(pending), config["provider_id"])
    with output_path.open("a", encoding="utf-8", newline="\n") as output:
        for index, item in enumerate(pending, start=1):
            params = query_params(item["original_address"])
            queried_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            result = {**item, "provider": config["provider_id"], "queried_at_utc": queried_at, "query_parameters": params, "response": None}
            for attempt in range(1, retries + 1):
                try:
                    status, payload = fetch(params, config["base_url"])
                    result["http_status"] = status
                    result["response"] = payload
                    result["response_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    result["acceptance"] = acceptance(payload)
                    result["status"] = "review_required" if result["acceptance"] == "accepted_single_point" else result["acceptance"]
                    result["precision"] = "review_required"
                    result["coordinate_review_status"] = "review_required"
                    break
                except Exception as error:
                    result["status"] = "failed"
                    result["error"] = str(error)
                    LOGGER.warning("stage=geocode status=failed attempt=%d/%d", attempt, retries)
                    if attempt < retries:
                        time.sleep(min(30, 2 ** attempt))
            output.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            output.flush()
            LOGGER.info("stage=geocode item=%d/%d status=%s acceptance=%s", index, len(pending), result["status"], result.get("acceptance"))
            if index < len(pending):
                time.sleep(delay)
    report = output_path.with_name("geocode-review-report.json")
    report.write_text(json.dumps({"status": "complete", "provider": config["provider_id"], "provider_base_url": config["base_url"], "terms_review_sha256": config["terms_review_sha256"], "batch_size": len(queue), "newly_processed": len(pending), "suppressed": skipped, "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest()}, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("stage=geocode status=complete batch=%d newly_processed=%d suppressed=%d", len(queue), len(pending), skipped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--provider-config", type=Path, default=Path("pipeline/config/geocoding-dev.json"))
    parser.add_argument("--suppression-keys", type=Path)
    parser.add_argument("--terms-review", type=Path, help="Approved per-run terms review required with --network.")
    parser.add_argument("--network", action="store_true", help="Permit provider requests after config approval validation")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    run(args.queue, args.output, args.limit, args.delay, args.retries, args.provider_config, args.suppression_keys, args.terms_review, args.network)
