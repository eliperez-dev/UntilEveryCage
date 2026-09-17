#!/usr/bin/env python3
"""Build the manifest-bound public discovery read model atomically."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg


class ReadModelBlocked(ValueError):
    """The read model cannot safely be activated."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ReadModelBlocked("read model timestamp lacks timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def content_digest(rows: list[tuple[Any, ...]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        values = []
        for value in row:
            if isinstance(value, memoryview):
                value = value.tobytes().hex()
            elif isinstance(value, bytes):
                value = value.hex()
            elif isinstance(value, datetime):
                value = _timestamp(value)
            values.append("" if value is None else str(value))
        digest.update(("\t".join(values) + "\n").encode("utf-8"))
    return digest.hexdigest()


def _release_manifest(connection: Any, release_id: str) -> str:
    release = connection.execute(
        "SELECT status, test_only, profile FROM uec.releases WHERE release_id=%s",
        (release_id,),
    ).fetchone()
    if not release:
        raise ReadModelBlocked("release is missing")
    if release[0] != "promoted" or release[1]:
        raise ReadModelBlocked("only a non-test promoted release can build a read model")
    stored = connection.execute(
        "SELECT manifest::text, manifest_sha256 FROM uec.release_manifests WHERE release_id=%s",
        (release_id,),
    ).fetchone()
    if not stored:
        raise ReadModelBlocked("release manifest is missing")
    manifest = json.loads(stored[0])
    actual = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
    if actual != stored[1]:
        raise ReadModelBlocked("release manifest checksum mismatch")
    if manifest.get("release_id") != release_id or manifest.get("profile") != release[2]:
        raise ReadModelBlocked("release manifest identity mismatch")
    return stored[1]


SELECT_ROWS = """
SELECT h.facility_id, h.observation_id, h.source_record_id,
       h.canonical_name, h.country_code, h.postal_code, h.city,
       ST_AsText(h.display_location::geometry), h.display_precision,
       h.display_label, h.geocoding_status, h.geocoder_provider,
       h.geocoded_at, h.classification_category, o.observed_at,
       o.first_observed_at, h.provenance_origin_type, h.provenance_source_id,
       h.provenance_source_name, h.provenance_source_url,
       h.provenance_retrieved_at,
       CASE WHEN source.attribution IS NULL OR btrim(source.attribution) = ''
            THEN 'unknown' ELSE 'attribution_required' END
FROM uec.map_facilities_display_history h
JOIN uec.observations o ON o.observation_id = h.observation_id
JOIN uec.sources source ON source.source_id = h.provenance_source_id
WHERE h.release_id=%s
ORDER BY h.facility_id, h.observation_id
"""


def build(database_url: str, release_id: str, fail_after_rows: int | None = None) -> dict[str, Any]:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            manifest_sha256 = _release_manifest(connection, release_id)
            rows = connection.execute(SELECT_ROWS, (release_id,)).fetchall()
            content_sha256 = content_digest(rows)
            existing = connection.execute(
                "SELECT manifest_sha256, content_sha256, row_count FROM uec.public_discovery_read_models WHERE release_id=%s",
                (release_id,),
            ).fetchone()
            if existing:
                if existing != (manifest_sha256, content_sha256, len(rows)):
                    raise ReadModelBlocked("existing read model does not match the current release content")
                stored_rows = connection.execute(
                    "SELECT count(*) FROM uec.public_discovery_read_model_rows WHERE release_id=%s",
                    (release_id,),
                ).fetchone()[0]
                if stored_rows != len(rows):
                    raise ReadModelBlocked("read model metadata exists but row storage is incomplete")
                return {"status": "idempotent", "release_id": release_id, "manifest_sha256": manifest_sha256, "content_sha256": content_sha256, "row_count": len(rows)}

            insert_sql = """
                INSERT INTO uec.public_discovery_read_model_rows
                (release_id,facility_id,observation_id,source_record_id,canonical_name,
                 country_code,postal_code,city,display_location,display_precision,
                 display_label,geocoding_status,geocoder_provider,geocoded_at,
                 classification_category,observed_at,first_observed_at,
                 provenance_origin_type,provenance_source_id,provenance_source_name,
                 provenance_source_url,provenance_retrieved_at,source_rights_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,ST_GeogFromText(%s),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
            with connection.cursor() as cursor:
                for index, row in enumerate(rows, start=1):
                    cursor.execute(insert_sql, (release_id, *row))
                    if fail_after_rows is not None and index >= fail_after_rows:
                        raise RuntimeError("synthetic interrupted read model build")
            connection.execute(
                "INSERT INTO uec.public_discovery_read_models (release_id,manifest_sha256,content_sha256,row_count) VALUES (%s,%s,%s,%s)",
                (release_id, manifest_sha256, content_sha256, len(rows)),
            )
            return {"status": "built", "release_id": release_id, "manifest_sha256": manifest_sha256, "content_sha256": content_sha256, "row_count": len(rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_id")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.database_url, args.release_id), sort_keys=True))
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
