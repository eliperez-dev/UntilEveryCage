#!/usr/bin/env python3
"""Resumable, cached DAWA geocoder for the Denmark queue."""

import argparse
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger("uec.denmark.geocode")


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


def fetch(params: dict) -> tuple[int, object]:
    url = "https://api.dataforsyningen.dk/adresser?" + urllib.parse.urlencode(params)
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


def run(queue_path: Path, output_path: Path, limit: int | None, delay: float, retries: int) -> None:
    queue = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit:
        queue = queue[:limit]
    completed = {}
    if output_path.exists():
        for line in output_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                completed[item["queue_key"]] = item
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pending = [item for item in queue if item["queue_key"] not in completed]
    LOGGER.info("stage=geocode status=started queue=%d completed=%d pending=%d", len(queue), len(completed), len(pending))
    with output_path.open("a", encoding="utf-8", newline="\n") as output:
        for index, item in enumerate(pending, start=1):
            params = query_params(item["original_address"])
            result = {**item, "provider": "dawa", "queried_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "query_parameters": params, "response": None}
            for attempt in range(1, retries + 1):
                try:
                    status, payload = fetch(params)
                    result["http_status"] = status
                    result["response"] = payload
                    result["acceptance"] = acceptance(payload)
                    result["status"] = "success"
                    break
                except Exception as error:
                    result["status"] = "failed"
                    result["error"] = str(error)
                    LOGGER.warning("stage=geocode key=%s attempt=%d/%d error=%s", item["queue_key"], attempt, retries, error)
                    if attempt < retries:
                        time.sleep(min(30, 2 ** attempt))
            output.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            output.flush()
            LOGGER.info("stage=geocode item=%d/%d key=%s status=%s acceptance=%s", index, len(pending), item["queue_key"], result["status"], result.get("acceptance"))
            if index < len(pending):
                time.sleep(delay)
    LOGGER.info("stage=geocode status=complete total=%d newly_processed=%d output=%s", len(queue), len(pending), output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    run(args.queue, args.output, args.limit, args.delay, args.retries)
