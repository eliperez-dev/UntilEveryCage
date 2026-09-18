#!/usr/bin/env python3
"""Parse an archived Find Smiley XML file into auditable JSONL staging output."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


LOGGER = logging.getLogger("uec.denmark.parse")
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_rows(path: Path) -> Iterator[dict[str, str | None]]:
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag.lower() != "row":
            continue
        values = {child.tag: (child.text or "").strip() or None for child in element}
        yield values
        element.clear()


def parse_file(input_path: Path, output_dir: Path, source_url: str, progress_every: int = 1000) -> Path:
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    output_path = output_dir / "parsed-rows.jsonl"
    metadata_path = output_dir / "run-metadata.json"
    started_at = utc_now()
    source_hash = sha256_file(input_path)
    LOGGER.info("run_id=%s stage=parse status=started input=%s", run_id, input_path)
    LOGGER.info("run_id=%s source_sha256=%s", run_id, source_hash)

    row_count = 0
    missing_coordinates = 0
    try:
        with output_path.open("w", encoding="utf-8", newline="\n") as output:
            for row_count, row in enumerate(iter_rows(input_path), start=1):
                latitude = row.get("Geo_Lat") or row.get("Geo_Latitude")
                longitude = row.get("Geo_Lng") or row.get("Geo_Longitude")
                if not latitude or not longitude:
                    missing_coordinates += 1
                output.write(json.dumps({
                    "source_id": "dk.smiley",
                    "source_row": row_count,
                    "source_record_key": row.get("ID_nummer") or row.get("navnelbnr"),
                    "source_artifact_sha256": source_hash,
                    "fields": row,
                }, ensure_ascii=False, sort_keys=True) + "\n")
                if row_count % progress_every == 0:
                    LOGGER.info("run_id=%s stage=parse rows=%d missing_coordinates=%d", run_id, row_count, missing_coordinates)
    except ET.ParseError:
        LOGGER.exception("run_id=%s stage=parse status=failed reason=invalid_xml", run_id)
        raise

    metadata = {
        "run_id": run_id,
        "source_id": "dk.smiley",
        "source_url": source_url,
        "input_path": input_path.as_posix(),
        "input_sha256": source_hash,
        "started_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "status": "success",
        "rows_parsed": row_count,
        "rows_missing_coordinates": missing_coordinates,
        "output_path": output_path.as_posix(),
        "parser": "parse-denmark-smiley.py",
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("run_id=%s stage=parse status=success rows=%d missing_coordinates=%d output=%s", run_id, row_count, missing_coordinates, output_path)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-url", default="https://pub.fvst.dk/publikationer/Smileydata.xml")
    parser.add_argument("--progress-every", type=int, default=1000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    try:
        parse_file(args.input, args.output_dir, args.source_url, args.progress_every)
    except Exception as error:
        LOGGER.error("stage=parse status=failed error=%s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
