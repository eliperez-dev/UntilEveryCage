#!/usr/bin/env python3
"""Geocode a small deterministic sample through DAWA for manual evaluation."""

import argparse
import json
import logging
import random
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger("uec.denmark.dawa_sample")


def lookup(address: dict) -> dict:
    street = address.get("street") or ""
    match = re.match(r"^(.*?\s+\d+[A-Za-z]?(?:[-/]\d+[A-Za-z]?)?)(?:\s+(?:st\.?|\d+\.?\s*(?:th|tv|mf|sal)?))?\s*$", street, re.IGNORECASE)
    if match:
        address_part = match.group(1)
        street_name = address_part.rsplit(" ", 1)[0]
        house_number = address_part.rsplit(" ", 1)[1].split("-", 1)[0].split("/", 1)[0]
    else:
        street_name = street
        house_number = None
    query_params = {"vejnavn": street_name, "postnr": address.get("postal_code"), "struktur": "mini", "fuzzy": "true"}
    if house_number:
        query_params["husnr"] = house_number
    params = urllib.parse.urlencode({key: value for key, value in query_params.items() if value})
    request = urllib.request.Request(
        "https://api.dataforsyningen.dk/adresser?" + params,
        headers={"User-Agent": "UntilEveryCage/2.0 data-pipeline development contact: untileverycageproject@protonmail.com"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return {"http_status": response.status, "query_parameters": query_params, "results": json.loads(response.read().decode("utf-8"))}


def run(input_path: Path, output_path: Path, sample_size: int, seed: int) -> None:
    rows = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    sample = random.Random(seed).sample(rows, min(sample_size, len(rows)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("stage=dawa_sample status=started candidates=%d seed=%d", len(sample), seed)
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for index, item in enumerate(sample, start=1):
            query = item["geocoder_query"]
            result = {**item, "queried_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "provider": "dawa", "response": None, "status": "failed"}
            try:
                response = lookup(item["original_address"])
                result["response"] = response
                result["status"] = "returned"
                result["match_count"] = len(response["results"]) if isinstance(response["results"], list) else 1
                LOGGER.info("stage=dawa_sample item=%d/%d key=%s status=returned matches=%d", index, len(sample), item["queue_key"], result["match_count"])
            except Exception as error:
                result["error"] = str(error)
                LOGGER.error("stage=dawa_sample item=%d/%d key=%s status=failed error=%s", index, len(sample), item["queue_key"], error)
            output.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            if index < len(sample):
                time.sleep(1.0)
    LOGGER.info("stage=dawa_sample status=success output=%s", output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260913)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    run(args.input, args.output, args.sample_size, args.seed)
