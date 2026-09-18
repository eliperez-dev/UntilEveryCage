#!/usr/bin/env python3
"""Normalize staged Find Smiley rows while preserving source values."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

LOGGER = logging.getLogger("uec.denmark.normalize")
SOURCE_TO_CANONICAL = {
    "ID_nummer": "source_record_key",
    "CVR_nummer": "organization_registration_id",
    "P_nummer": "production_unit_id",
    "Virksomhed": "name",
    "Adresse": "street_address",
    "Postnummer": "postal_code",
    "By": "city",
    "FVST_branchenummer": "industry_code",
    "FVST_branche": "industry_label",
    "Smileybranche": "category_label",
    "Virksomhedstype": "business_type",
    "URL": "source_url",
    "Geo_Lat": "source_latitude",
    "Geo_Lng": "source_longitude",
}


def iso_date(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def normalize_record(envelope: dict) -> dict:
    source = envelope.get("fields", {})
    normalized = {
        "source_id": envelope.get("source_id", "dk.smiley"),
        "source_row": envelope.get("source_row"),
        "source_record_key": source.get("ID_nummer") or source.get("navnelbnr"),
        "source_artifact_sha256": envelope.get("source_artifact_sha256"),
        "name": source.get("Virksomhed") or source.get("navn1"),
        "organization_registration_id": source.get("CVR_nummer") or source.get("cvrnr"),
        "production_unit_id": source.get("P_nummer") or source.get("pnr"),
        "address": {
            "street": source.get("Adresse") or source.get("adresse1"),
            "postal_code": source.get("Postnummer") or source.get("postnr"),
            "city": source.get("By"),
            "country_code": "DK",
        },
        "activity": {
            "code": source.get("FVST_branchenummer") or source.get("brancheKode"),
            "label": source.get("FVST_branche") or source.get("branche"),
            "category": source.get("Smileybranche") or source.get("Pixibranche"),
        },
        "business_type": source.get("Virksomhedstype") or source.get("virksomhedstype"),
        "coordinates": {
            "latitude": source.get("Geo_Lat"),
            "longitude": source.get("Geo_Lng"),
            "method": "source" if source.get("Geo_Lat") and source.get("Geo_Lng") else None,
            "review_status": "source" if source.get("Geo_Lat") and source.get("Geo_Lng") else "unresolved",
        },
        "latest_inspection_date": iso_date(source.get("Seneste_kontrol_dato") or source.get("seneste_kontrol_dato")),
        "source_url": source.get("URL"),
        "source_fields": source,
    }
    return normalized


def normalize_file(input_path: Path, output_dir: Path, progress_every: int = 10000) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "normalized-records.jsonl"
    report_path = output_dir / "field-mapping-report.json"
    count = 0
    missing_coords = 0
    keys = Counter()
    LOGGER.info("stage=normalize status=started input=%s", input_path)
    with input_path.open(encoding="utf-8") as source, output_path.open("w", encoding="utf-8", newline="\n") as output:
        for line in source:
            if not line.strip():
                continue
            record = normalize_record(json.loads(line))
            count += 1
            keys.update(record["source_fields"].keys())
            if record["coordinates"]["review_status"] == "unresolved":
                missing_coords += 1
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            if count % progress_every == 0:
                LOGGER.info("stage=normalize records=%d missing_coordinates=%d", count, missing_coords)
    report = {
        "status": "success",
        "input_path": input_path.as_posix(),
        "output_path": output_path.as_posix(),
        "records_normalized": count,
        "records_missing_coordinates": missing_coords,
        "source_to_canonical_mapping": SOURCE_TO_CANONICAL,
        "observed_source_fields": sorted(keys),
        "unmapped_source_fields": sorted(set(keys) - set(SOURCE_TO_CANONICAL)),
        "date_policy": "recognized dates are emitted as ISO dates; original values remain in source_fields",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("stage=normalize status=success records=%d missing_coordinates=%d report=%s", count, missing_coords, report_path)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    try:
        normalize_file(args.input, args.output_dir)
    except Exception as error:
        LOGGER.error("stage=normalize status=failed error=%s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
