#!/usr/bin/env python3
"""Create an auditable geocoding queue from classified Denmark records."""

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger("uec.denmark.geocode_queue")


def normalize_query(address: dict) -> str | None:
    parts = [address.get("street"), address.get("postal_code"), address.get("city"), "Denmark"]
    parts = [re.sub(r"\s+", " ", str(part)).strip() for part in parts if part]
    return ", ".join(parts) if len(parts) > 1 else None


def create_queue(input_path: Path, output_dir: Path, progress_every: int = 10000) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "geocode-queue.jsonl"
    metadata_path = output_dir / "geocode-queue-metadata.json"
    total = 0
    queued = 0
    no_address = 0
    already_coordinates = 0
    LOGGER.info("stage=geocode_queue status=started input=%s", input_path)
    with input_path.open(encoding="utf-8") as source, output_path.open("w", encoding="utf-8", newline="\n") as output:
        for total, line in enumerate(source, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            coordinates = record.get("coordinates", {})
            if coordinates.get("latitude") and coordinates.get("longitude"):
                already_coordinates += 1
                continue
            query = normalize_query(record.get("address", {}))
            if not query:
                no_address += 1
                continue
            queued += 1
            output.write(json.dumps({
                "queue_key": f"dk.smiley:{record.get('source_record_key')}",
                "source_id": record.get("source_id"),
                "source_record_key": record.get("source_record_key"),
                "source_artifact_sha256": record.get("source_artifact_sha256"),
                "source_url": record.get("source_url"),
                "original_address": record.get("address"),
                "geocoder_query": query,
                "status": "pending",
            }, ensure_ascii=False, sort_keys=True) + "\n")
            if total % progress_every == 0:
                LOGGER.info("stage=geocode_queue records=%d queued=%d", total, queued)
    metadata = {
        "status": "success",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_path": input_path.as_posix(),
        "output_path": output_path.as_posix(),
        "records_seen": total,
        "records_queued": queued,
        "records_with_source_coordinates": already_coordinates,
        "records_without_usable_address": no_address,
        "geocoder_status_policy": "pending; no external geocoder has been called",
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("stage=geocode_queue status=success seen=%d queued=%d no_address=%d", total, queued, no_address)
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    create_queue(args.input, args.output_dir)
