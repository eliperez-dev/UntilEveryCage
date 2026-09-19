#!/usr/bin/env python3
"""Build a deterministic, manifest-bound release summary component.

The component is a prototype input to a candidate live-gated summary view. It
is never a public surface by itself. Rows and the ready metadata record are
inserted in one transaction; an interrupted build therefore exposes neither a
partial component nor an older component as current.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg


class ComponentBlocked(ValueError):
    """The component cannot be safely used for the requested release."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ComponentBlocked("component row timestamp lacks timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def content_digest(rows: list[tuple[Any, ...]]) -> str:
    digest = hashlib.sha256()
    for facility_id, observation_id, source_record_id, first_observed_at, observed_at, category in rows:
        payload = "\t".join((
            str(facility_id),
            str(observation_id),
            str(source_record_id),
            _timestamp(first_observed_at),
            _timestamp(observed_at),
            category,
        )) + "\n"
        digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def _release_manifest(connection: Any, release_id: str) -> tuple[str, str]:
    release = connection.execute(
        "SELECT status, test_only, profile FROM uec.releases WHERE release_id=%s",
        (release_id,),
    ).fetchone()
    if not release:
        raise ComponentBlocked("release is missing")
    if release[0] != "promoted" or release[1]:
        raise ComponentBlocked("only a non-test promoted release can build a component")
    stored = connection.execute(
        "SELECT manifest::text, manifest_sha256 FROM uec.release_manifests WHERE release_id=%s",
        (release_id,),
    ).fetchone()
    if not stored:
        raise ComponentBlocked("release manifest is missing")
    manifest = json.loads(stored[0])
    actual = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
    if actual != stored[1]:
        raise ComponentBlocked("release manifest checksum mismatch")
    if manifest.get("release_id") != release_id or manifest.get("profile") != release[2]:
        raise ComponentBlocked("release manifest identity mismatch")
    return stored[1], release[2]


def build(database_url: str, release_id: str, fail_after_rows: int | None = None) -> dict[str, Any]:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            manifest_sha256, _profile = _release_manifest(connection, release_id)
            rows = connection.execute(
                """
                SELECT member.facility_id, member.observation_id,
                       observation.source_record_id, observation.first_observed_at,
                       observation.observed_at, observation.classification_category
                FROM uec.release_members member
                JOIN uec.observations observation
                  ON observation.observation_id=member.observation_id
                WHERE member.release_id=%s AND member.default_visible=true
                ORDER BY member.facility_id, member.observation_id
                """,
                (release_id,),
            ).fetchall()
            content_sha256 = content_digest(rows)
            existing = connection.execute(
                "SELECT manifest_sha256, content_sha256, member_count FROM uec.release_summary_components WHERE release_id=%s",
                (release_id,),
            ).fetchone()
            if existing:
                if existing != (manifest_sha256, content_sha256, len(rows)):
                    raise ComponentBlocked("existing component does not match the current release content")
                stored_rows = connection.execute(
                    "SELECT count(*) FROM uec.release_summary_component_rows WHERE release_id=%s",
                    (release_id,),
                ).fetchone()[0]
                if stored_rows != len(rows):
                    raise ComponentBlocked("component metadata exists but row storage is incomplete")
                return {"status": "idempotent", "release_id": release_id, "manifest_sha256": manifest_sha256, "content_sha256": content_sha256, "member_count": len(rows)}

            for index, row in enumerate(rows, start=1):
                connection.execute(
                    "INSERT INTO uec.release_summary_component_rows (release_id,facility_id,observation_id,source_record_id,first_observed_at,observed_at,classification_category) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (release_id, *row),
                )
                if fail_after_rows is not None and index >= fail_after_rows:
                    raise RuntimeError("synthetic interrupted component build")
            connection.execute(
                "INSERT INTO uec.release_summary_components (release_id,manifest_sha256,content_sha256,member_count) VALUES (%s,%s,%s,%s)",
                (release_id, manifest_sha256, content_sha256, len(rows)),
            )
            return {"status": "built", "release_id": release_id, "manifest_sha256": manifest_sha256, "content_sha256": content_sha256, "member_count": len(rows)}


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
