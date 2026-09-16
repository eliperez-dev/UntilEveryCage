"""Deterministic, fail-closed packaging for public UEC release projections.

This module deliberately accepts already projected rows rather than raw evidence.
It is also strict about the release gate so a caller cannot turn a candidate,
suppressed record, or source with unknown reuse rights into a public snapshot by
omitting a filter.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


DATA_PRODUCT_VERSION = "uec-public-data-product-v1"
SCHEMA_VERSION = "uec-location-projection-v1"
MANIFEST_VERSION = "uec-release-manifest-v2"
SUPPORTED_PROFILES = frozenset(("official", "secondary", "community"))
ALLOWED_RIGHTS = frozenset(("cleared", "attribution_required"))
FORMULA_PREFIXES = ("=", "+", "-", "@")

CSV_FIELDS = (
    "facility_id",
    "canonical_name",
    "country_code",
    "city",
    "category",
    "display_precision",
    "latitude",
    "longitude",
    "lifecycle_status",
    "first_observed_at",
    "last_observed_at",
    "observation_count",
    "source_type",
    "factual_review_status",
    "privacy_screening_status",
    "project_approval",
    "reviewer_role",
    "publication_warning",
    "publication_profile",
    "release_id",
    "release_ruleset_version",
    "provenance_source_id",
    "provenance_source_name",
    "provenance_source_url",
    "provenance_retrieved_at",
    "source_rights_status",
)

PUBLIC_ROW_FIELDS = frozenset(CSV_FIELDS)
FORBIDDEN_ROW_FIELDS = frozenset(
    (
        "raw_fields",
        "raw_payload",
        "source_values",
        "street_address",
        "postal_code",
        "phone",
        "private_address",
        "geocoding_query",
        "attachment_url",
        "suppression_reason",
    )
)


class DataProductError(ValueError):
    """A release or row is not eligible for public data-product packaging."""


def canonical_json(value: Any) -> str:
    """Serialize JSON in the repository-wide stable form."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _required_string(metadata: Mapping[str, Any], field: str) -> str:
    value = metadata.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DataProductError(f"release metadata field is missing: {field}")
    return value


def validate_release_metadata(
    metadata: Mapping[str, Any],
    profile: str | None = None,
    *,
    require_projection_checksum: bool = False,
) -> dict[str, Any]:
    """Validate the explicit publication contract and return a plain copy.

    ``eligible`` is intentionally required.  A caller must obtain this value
    from a release-scoped public projection query or an equivalent reviewed
    release process; packaging never infers eligibility from row presence.
    """

    result = dict(metadata)
    release_id = _required_string(result, "release_id")
    selected_profile = profile or result.get("profile")
    if selected_profile not in SUPPORTED_PROFILES:
        raise DataProductError("release profile is unsupported")
    if result.get("profile") != selected_profile:
        raise DataProductError("selected profile does not match release metadata")
    if result.get("eligible") is not True:
        raise DataProductError("release is not explicitly eligible for public packaging")
    if result.get("test_only") is True:
        raise DataProductError("test-only releases cannot be packaged")
    if result.get("status") not in ("promoted", "project-published"):
        raise DataProductError("release must be promoted before packaging")
    if result.get("publication_state") not in ("project-published", "eligible"):
        raise DataProductError("release publication state is not eligible")
    _required_string(result, "ruleset_version")
    _required_string(result, "schema_version")
    _required_string(result, "generated_at")
    if not isinstance(result.get("retrieved_at"), str) or not result["retrieved_at"].strip():
        raise DataProductError("release metadata field is missing: retrieved_at")
    if not isinstance(result.get("limitations"), list) or not all(isinstance(v, str) and v for v in result["limitations"]):
        raise DataProductError("release limitations must be a list of non-empty strings")
    if result.get("supersedes") is not None and not isinstance(result["supersedes"], str):
        raise DataProductError("release supersedes must be null or a release ID")
    if not isinstance(result.get("source_coverage"), list):
        raise DataProductError("release source coverage must be a list")
    coverage_ids = set()
    for item in result["source_coverage"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("source_id"), str) or not item["source_id"]:
            raise DataProductError("release source coverage is malformed")
        if item["source_id"] in coverage_ids:
            raise DataProductError("release source coverage contains duplicate source IDs")
        coverage_ids.add(item["source_id"])
        if not isinstance(item.get("row_count"), int) or item["row_count"] < 0:
            raise DataProductError("release source coverage row count is invalid")
    if not isinstance(result.get("row_counts"), Mapping):
        raise DataProductError("release row counts are missing")
    if not isinstance(result["row_counts"].get("eligible_rows"), int) or result["row_counts"]["eligible_rows"] < 0:
        raise DataProductError("release eligible row count is invalid")
    if not isinstance(result.get("checksums"), Mapping):
        raise DataProductError("release checksums are missing")
    if require_projection_checksum and not re.fullmatch(r"[0-9a-f]{64}", str(result["checksums"].get("projection_sha256", ""))):
        # The projection digest is calculated before the final manifest exists,
        # so it is a stable input-level checksum rather than a self-reference.
        raise DataProductError("release projection checksum is invalid")
    result["release_id"] = release_id
    result["profile"] = selected_profile
    return result


def csv_safe_value(value: Any) -> Any:
    """Prevent spreadsheet formula execution while preserving source values."""

    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    return csv_safe_value(value) if isinstance(value, str) else value


def _coordinates(row: Mapping[str, Any]) -> list[float] | None:
    precision = row.get("display_precision")
    latitude, longitude = row.get("latitude"), row.get("longitude")
    if precision not in ("exact", "city") or latitude is None or longitude is None:
        return None
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        raise DataProductError("public coordinates must be numeric")
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise DataProductError("public coordinates are outside valid bounds")
    return [lon, lat]


def validate_public_rows(rows: Iterable[Mapping[str, Any]], metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Validate, whitelist, and deterministically order public projection rows."""

    release = validate_release_metadata(metadata)
    selected_profile = release["profile"]
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, original in enumerate(rows):
        row = dict(original)
        if row.get("suppressed") is True or row.get("public_access_revoked") is True:
            raise DataProductError(f"row {index} is suppressed")
        forbidden = sorted(FORBIDDEN_ROW_FIELDS.intersection(row))
        if forbidden:
            raise DataProductError(f"row {index} contains restricted fields: {', '.join(forbidden)}")
        facility_id = _required_string(row, "facility_id")
        if facility_id in seen:
            raise DataProductError(f"duplicate facility_id in release projection: {facility_id}")
        seen.add(facility_id)
        if row.get("release_id") != release["release_id"] or row.get("publication_profile") != selected_profile:
            raise DataProductError(f"row {index} does not match the selected release/profile")
        if row.get("publication_eligible") is not True or row.get("privacy_screening_status") != "passed":
            raise DataProductError(f"row {index} is not publication-eligible and privacy-screened")
        if selected_profile != "community" and row.get("project_approval") != "approved":
            raise DataProductError(f"row {index} is not project-approved")
        if row.get("source_rights_status") not in ALLOWED_RIGHTS:
            raise DataProductError(f"row {index} has unclear or restricted source reuse rights")
        if row.get("source_type") == "user_submitted" and selected_profile != "community":
            raise DataProductError(f"row {index} user-submitted claim is outside the community profile")
        projection = {field: row.get(field) for field in CSV_FIELDS}
        projection["release_ruleset_version"] = row.get("release_ruleset_version", release["ruleset_version"])
        projection["publication_warning"] = row.get("publication_warning") or (
            "Unreviewed community claim — not verified by Until Every Cage"
            if selected_profile == "community" and row.get("factual_review_status") == "unreviewed"
            else None
        )
        validated.append(projection)
    expected = release["row_counts"]["eligible_rows"]
    if len(validated) != expected:
        raise DataProductError(f"row count does not match release metadata: expected {expected}, got {len(validated)}")
    return sorted(validated, key=lambda row: (row["facility_id"], row["provenance_source_id"] or ""))


def paginate_rows(rows: Iterable[Mapping[str, Any]], limit: int = 100, cursor: str | None = None) -> tuple[list[Mapping[str, Any]], str | None]:
    """Apply the same stable facility-id traversal used by API consumers.

    Callers should pass rows returned by :func:`validate_public_rows`; this
    helper does not grant publication eligibility on its own.
    """

    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise DataProductError("page limit must be between 1 and 1000")
    ordered = sorted(rows, key=lambda row: (str(row.get("facility_id", "")), str(row.get("provenance_source_id", ""))))
    if cursor is not None:
        ordered = [row for row in ordered if str(row.get("facility_id", "")) > cursor]
    page = ordered[:limit]
    return page, (str(page[-1]["facility_id"]) if len(ordered) > limit else None)


def render_csv(rows: Iterable[Mapping[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_cell(row.get(field)) for field in CSV_FIELDS})
    return output.getvalue().encode("utf-8")


def render_geojson(rows: Iterable[Mapping[str, Any]], metadata: Mapping[str, Any]) -> bytes:
    features = []
    for row in rows:
        properties = {field: row.get(field) for field in CSV_FIELDS if field not in {"latitude", "longitude"}}
        geometry = None
        coordinates = _coordinates(row)
        if coordinates is not None:
            geometry = {"coordinates": coordinates, "type": "Point"}
        features.append({"geometry": geometry, "properties": properties, "type": "Feature"})
    document = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "data_product_version": DATA_PRODUCT_VERSION,
            "release_id": metadata["release_id"],
            "profile": metadata["profile"],
            "schema_version": metadata["schema_version"],
            "limitations": metadata["limitations"],
        },
    }
    return (canonical_json(document) + "\n").encode("utf-8")


def data_dictionary() -> dict[str, Any]:
    descriptions = {
        "facility_id": "Stable project facility identifier.",
        "canonical_name": "Project-normalized facility name; may be null when unknown.",
        "country_code": "ISO 3166-1 alpha-2 country code.",
        "city": "Public city or region label; not a street address.",
        "category": "Project classification category under the release ruleset.",
        "display_precision": "Public location precision: exact, city, or unmapped.",
        "latitude": "Public latitude; blank when unmapped or not allowed by display precision.",
        "longitude": "Public longitude; blank when unmapped or not allowed by display precision.",
        "lifecycle_status": "Observed lifecycle label; disappearance is not closure.",
        "first_observed_at": "Earliest retained observation included in this public release.",
        "last_observed_at": "Latest retained observation included in this public release.",
        "observation_count": "Count of eligible observations in this release, not an animal count.",
        "source_type": "Evidence origin, separate from review and approval.",
        "factual_review_status": "Scoped factual review outcome or unreviewed state.",
        "privacy_screening_status": "Publication-safety screening outcome.",
        "project_approval": "Scoped maintainer decision for this release/profile.",
        "reviewer_role": "Role label for the recorded review, not a personal identity.",
        "publication_warning": "Persistent context required for community-unreviewed claims.",
        "publication_profile": "Selected publication context: official, secondary, or community.",
        "release_id": "Immutable release identifier.",
        "release_ruleset_version": "Classification and projection ruleset identifier.",
        "provenance_source_id": "Stable source registry identifier.",
        "provenance_source_name": "Human-readable source name.",
        "provenance_source_url": "Official source URL recorded for provenance.",
        "provenance_retrieved_at": "UTC retrieval time for the source artifact.",
        "source_rights_status": "Reuse review: cleared or attribution_required; unknown rights are excluded.",
    }
    return {
        "data_product_version": DATA_PRODUCT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "coordinate_policy": "Coordinates are emitted only for exact or city display precision; city points are coarse/approximate and no guessed point is substituted.",
        "unknown_values": "Blank/null means unknown or unavailable and is not an assertion of absence.",
        "fields": [
            {"name": field, "description": descriptions[field], "nullable": field not in {"facility_id", "country_code", "category", "display_precision", "source_type", "publication_profile", "release_id"}}
            for field in CSV_FIELDS
        ],
    }


def build_manifest(metadata: Mapping[str, Any], rows: list[Mapping[str, Any]], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    release = validate_release_metadata(metadata, require_projection_checksum=True)
    return {
        "manifest_version": MANIFEST_VERSION,
        "data_product_version": DATA_PRODUCT_VERSION,
        "release_id": release["release_id"],
        "profile": release["profile"],
        "release_status": release["status"],
        "test_only": release["test_only"],
        "ruleset_version": release["ruleset_version"],
        "schema_version": release["schema_version"],
        "generated_at": release["generated_at"],
        "retrieved_at": release["retrieved_at"],
        "source_coverage": release["source_coverage"],
        "row_counts": {**release["row_counts"], "packaged_rows": len(rows)},
        "review_state": release.get("review_state", "release-scoped review required"),
        "publication_state": release["publication_state"],
        "checksums": {**release["checksums"], "algorithm": "sha256", "distributed_artifacts": sorted(artifacts, key=lambda item: item["name"])},
        "limitations": release["limitations"],
        "supersedes": release.get("supersedes"),
        "distributed_artifacts": sorted(artifacts, key=lambda item: item["name"]),
        "checksum_algorithm": "sha256",
    }


def write_package(output_dir: Path, metadata: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Write a deterministic CSV/GeoJSON snapshot and verification metadata."""

    output_dir.mkdir(parents=True, exist_ok=True)
    validated = validate_public_rows(rows, metadata)
    rows_by_source = Counter(row["provenance_source_id"] for row in validated)
    coverage_by_source = {item["source_id"]: item["row_count"] for item in metadata["source_coverage"]}
    if any(count != coverage_by_source.get(source_id) for source_id, count in rows_by_source.items()):
        raise DataProductError("source coverage does not match packaged rows")
    if validated and set(rows_by_source) != set(coverage_by_source):
        raise DataProductError("source coverage does not match packaged sources")
    csv_bytes = render_csv(validated)
    geojson_bytes = render_geojson(validated, metadata)
    dictionary_bytes = (canonical_json(data_dictionary()) + "\n").encode("utf-8")
    projection_digest = sha256_bytes(csv_bytes + b"\n" + geojson_bytes)
    enriched = dict(metadata)
    enriched["checksums"] = {**dict(metadata["checksums"]), "projection_sha256": projection_digest}
    artifacts = [
        {"name": "locations.csv", "sha256": sha256_bytes(csv_bytes), "byte_size": len(csv_bytes)},
        {"name": "locations.geojson", "sha256": sha256_bytes(geojson_bytes), "byte_size": len(geojson_bytes)},
        {"name": "data-dictionary.json", "sha256": sha256_bytes(dictionary_bytes), "byte_size": len(dictionary_bytes)},
    ]
    manifest = build_manifest(enriched, validated, artifacts)
    manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")
    files = {
        "locations.csv": csv_bytes,
        "locations.geojson": geojson_bytes,
        "data-dictionary.json": dictionary_bytes,
        "manifest.json": manifest_bytes,
    }
    checksums = {name: sha256_bytes(content) for name, content in files.items()}
    checksums_bytes = (canonical_json({"algorithm": "sha256", "files": checksums}) + "\n").encode("utf-8")
    files["SHA256SUMS.json"] = checksums_bytes
    for name, content in files.items():
        (output_dir / name).write_bytes(content)
    return {"manifest": manifest, "manifest_sha256": checksums["manifest.json"], "files": checksums}


def verify_package(output_dir: Path, expected_manifest_sha256: str | None = None) -> dict[str, Any]:
    checksums_path = output_dir / "SHA256SUMS.json"
    if not checksums_path.is_file():
        raise DataProductError("checksum sidecar is missing")
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    if checksums.get("algorithm") != "sha256" or not isinstance(checksums.get("files"), dict):
        raise DataProductError("checksum sidecar is malformed")
    for name, expected in checksums["files"].items():
        if not isinstance(name, str) or Path(name).name != name or name in {"", ".", ".."} or not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
            raise DataProductError("checksum sidecar contains an unsafe entry")
        path = output_dir / name
        if not path.is_file() or sha256_bytes(path.read_bytes()) != expected:
            raise DataProductError(f"checksum verification failed: {name}")
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != MANIFEST_VERSION or manifest.get("release_status") != "promoted" or manifest.get("test_only") is not False:
        raise DataProductError("manifest is not an eligible data-product release")
    if manifest.get("publication_state") != "project-published" or manifest.get("profile") not in SUPPORTED_PROFILES:
        raise DataProductError("manifest publication metadata is invalid")
    row_counts = manifest.get("row_counts")
    if not isinstance(row_counts, dict) or row_counts.get("eligible_rows") != row_counts.get("packaged_rows"):
        raise DataProductError("manifest row counts are inconsistent")
    actual_manifest_sha256 = checksums["files"].get("manifest.json")
    if expected_manifest_sha256 is not None and expected_manifest_sha256 != actual_manifest_sha256:
        raise DataProductError("trusted manifest checksum does not match")
    listed = {artifact["name"]: artifact for artifact in manifest.get("distributed_artifacts", [])}
    for name, artifact in listed.items():
        if checksums["files"].get(name) != artifact.get("sha256"):
            raise DataProductError(f"manifest artifact checksum mismatch: {name}")
    return {"status": "verified", "manifest_sha256": actual_manifest_sha256, "artifact_count": len(listed)}
