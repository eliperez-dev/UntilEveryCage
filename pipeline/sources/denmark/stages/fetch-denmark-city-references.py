#!/usr/bin/env python3
"""Fetch and normalize DAWA's official Denmark city reference points."""

import argparse
import hashlib
import json
import logging
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger("uec.denmark.city-references")
URL = "https://api.dataforsyningen.dk/steder?hovedtype=Bebyggelse&undertype=by"
HEADERS = {"User-Agent": "UntilEveryCage/2.0 data-pipeline; contact: untileverycageproject@protonmail.com"}


def normalize(payload: object, retrieved_at: str, source_url: str) -> list[dict]:
    """Convert DAWA records into stable, database-loadable reference records."""
    if not isinstance(payload, list):
        raise ValueError("DAWA city response must be a JSON array")
    records = []
    for item in payload:
        center = item.get("visueltcenter")
        if not isinstance(center, list) or len(center) != 2:
            continue
        records.append({
            "source_reference_id": item.get("id"),
            "country_code": "DK",
            "city_name": item.get("primærtnavn"),
            "postal_code": None,
            "reference_longitude": center[0],
            "reference_latitude": center[1],
            "reference_source": source_url,
            "source_retrieved_at": retrieved_at,
        })
    return records


def run(output_root: Path, url: str = URL) -> Path:
    retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = retrieved.replace("-", "").replace(":", "").replace(".", "")
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    request = urllib.request.Request(url, headers=HEADERS)
    LOGGER.info("stage=city-references status=fetching source=%s", url)
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
    artifact = run_dir / "steder.json"
    artifact.write_bytes(raw)
    records = normalize(payload, retrieved, url)
    staging = run_dir / "city-reference-points.jsonl"
    with staging.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    metadata = {"source_url": url, "retrieved_at": retrieved, "artifact": artifact.name,
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                "records": len(records), "status": "fetched"}
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("stage=city-references status=complete records=%d artifact=%s", len(records), artifact)
    return run_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw/denmark-city-references"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(run(args.output_root))
