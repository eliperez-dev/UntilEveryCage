"""Recheck retained EEA acquisition provenance at the private import boundary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .adapter import SOURCE_ID, SOURCE_URL, WHERE, YEAR, bundle_digest


def validate_acquisition(root: Path, run_id: str, manifest: dict[str, Any],
                         summary: dict[str, Any], max_age_days: int) -> dict[str, Any]:
    parent = root / "acquisition" / SOURCE_ID / run_id
    path = parent / "acquisition-metadata.json"
    pages = parent / "source-pages"
    if path.is_symlink() or pages.is_symlink() or not path.is_file() or not pages.is_dir():
        raise ValueError("EEA acquisition evidence is missing")
    facts = json.loads(path.read_text(encoding="utf-8"))
    sha, size = bundle_digest(pages)
    timestamp = datetime.fromisoformat(str(facts.get("retrieved_at_utc")).replace("Z", "+00:00"))
    review = facts.get("terms_review", {})
    count = facts.get("feature_count")
    if (facts.get("source_id") != SOURCE_ID or facts.get("run_id") != run_id
            or facts.get("canonical_url") != SOURCE_URL or manifest.get("source_url") != SOURCE_URL
            or facts.get("where") != WHERE or facts.get("reporting_year") != YEAR
            or facts.get("source_native_crs") != "EPSG:3857" or facts.get("requested_geometry_crs") != "EPSG:4326"
            or not isinstance(count, int) or isinstance(count, bool) or count < 1
            or count != facts.get("object_id_count") or count != facts.get("retrieved_unique_object_id_count")
            or facts.get("source_membership_rechecked") is not True
            or count != summary.get("input_rows")
            or count != summary.get("normalized_rows", -1) + summary.get("quarantined_rows", -1)
            or facts.get("artifact_sha256") != sha or manifest.get("checksum_sha256") != sha
            or facts.get("artifact_byte_size") != size or manifest.get("byte_size") != size
            or manifest.get("retrieved_at_utc") != facts.get("retrieved_at_utc")
            or manifest.get("normalized_sha256") != summary.get("candidate_handoff_sha256")
            or timestamp.utcoffset() is None or timestamp > datetime.now(timezone.utc) + timedelta(minutes=5)
            or datetime.now(timezone.utc) - timestamp > timedelta(days=max_age_days)
            or review.get("source_id") != SOURCE_ID or review.get("decision") != "approved"
            or review.get("license") != "Creative Commons Attribution" or review.get("license_version") != "4.0"
            or review.get("private_preview_only") is not True):
        raise ValueError("EEA acquisition evidence does not reconcile")
    page_facts = facts.get("pages")
    files = sorted(pages.glob("page-*.geojson"))
    if not isinstance(page_facts, list) or len(page_facts) != len(files) or len(files) != facts.get("page_count"):
        raise ValueError("EEA acquisition page count changed")
    rows, ids = 0, set()
    for file, evidence in zip(files, page_facts):
        raw = file.read_bytes()
        if (file.is_symlink() or evidence.get("artifact") != file.name
                or evidence.get("sha256") != hashlib.sha256(raw).hexdigest() or evidence.get("byte_size") != len(raw)):
            raise ValueError("EEA retained page differs from acquisition")
        features = json.loads(raw)["features"]
        page_ids = [f["properties"]["OBJECTID"] for f in features]
        if len(features) != evidence.get("features") or ids.intersection(page_ids) or len(set(page_ids)) != len(page_ids):
            raise ValueError("EEA retained page identity differs from acquisition")
        rows += len(features)
        ids.update(page_ids)
    if rows != count or len(ids) != count:
        raise ValueError("EEA retained rows do not cover the scoped acquisition")
    for key, name in (("catalogue", "catalogue.xml"), ("layer", "layer.json"), ("count", "count.json"),
                      ("ids", "ids.json"), ("ids_after", "ids-after.json")):
        file = parent / name
        raw = file.read_bytes()
        if file.is_symlink() or facts[key]["sha256"] != hashlib.sha256(raw).hexdigest():
            raise ValueError("EEA retained source metadata changed")
    return {key: facts[key] for key in ("source_id", "run_id", "canonical_url", "retrieved_at_utc", "reporting_year",
            "where", "feature_count", "object_id_count", "retrieved_unique_object_id_count", "page_count",
            "artifact_sha256", "artifact_byte_size", "license", "license_version", "attribution")}
