"""Validate source-linked aggregate statistics independently of facilities.

The catalog is deliberately conservative.  It accepts a count only when its
scope, units, estimate semantics, provenance, revision, and citations are
explicit.  It does not turn an annual estimate into a live observation.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CATALOG_SCHEMA_VERSION = "aggregate-statistics-catalog-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REQUIRED_ENTRY_FIELDS = {
    "statistic_id",
    "version_id",
    "label",
    "source",
    "population_scope",
    "geography",
    "period",
    "unit",
    "estimate",
    "method",
    "exclusions",
    "uncertainty",
    "provenance",
    "revision",
    "citations",
    "status",
}


class StatisticsCatalogError(ValueError):
    """The catalog is malformed or contains an unsafe aggregate claim."""


def _fail(path: str, message: str) -> None:
    raise StatisticsCatalogError(f"{path}: {message}")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, "must be a non-empty string")
    return value


def _nonnegative_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        _fail(path, "must be a non-negative number")
    return float(value)


def _date(value: Any, path: str) -> None:
    _nonempty_string(value, path)
    if not _DATE.fullmatch(value):
        _fail(path, "must be YYYY-MM-DD")


def _timestamp(value: Any, path: str) -> None:
    _nonempty_string(value, path)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StatisticsCatalogError(f"{path}: must be ISO-8601") from exc
    if parsed.tzinfo is None:
        _fail(path, "must include a timezone")


def _https_url(value: Any, path: str) -> None:
    _nonempty_string(value, path)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        _fail(path, "must be an HTTPS URL")


def _validate_estimate(entry: dict[str, Any]) -> None:
    estimate = _object(entry["estimate"], "estimate")
    if estimate.get("type") not in {"point", "range", "point-with-qualitative-uncertainty"}:
        _fail("estimate.type", "must declare point, range, or point-with-qualitative-uncertainty")
    central = _nonnegative_number(estimate.get("central"), "estimate.central")
    low = estimate.get("low")
    high = estimate.get("high")
    if (low is None) != (high is None):
        _fail("estimate", "low and high must be supplied together")
    if low is not None and high is not None:
        low_number = _nonnegative_number(low, "estimate.low")
        high_number = _nonnegative_number(high, "estimate.high")
        if low_number > central or central > high_number:
            _fail("estimate", "must satisfy low <= central <= high")
    if entry["unit"].get("kind") == "count" and not float(central).is_integer():
        _fail("estimate.central", "count estimates must be whole units")


def _validate_components(entry: dict[str, Any]) -> None:
    components = entry.get("components")
    if components is None:
        return
    if not isinstance(components, list) or not components:
        _fail("components", "must be a non-empty list when present")
    ids: set[str] = set()
    overlap_groups: set[str] = set()
    converted_total = 0.0
    for index, component in enumerate(components):
        path = f"components[{index}]"
        component = _object(component, path)
        component_id = _nonempty_string(component.get("component_id"), f"{path}.component_id")
        if component_id in ids:
            _fail(path, "component_id must be unique")
        ids.add(component_id)
        _nonempty_string(component.get("population"), f"{path}.population")
        _nonempty_string(component.get("source_item"), f"{path}.source_item")
        _nonempty_string(component.get("source_unit"), f"{path}.source_unit")
        if component.get("source_flag") is not None:
            _nonempty_string(component["source_flag"], f"{path}.source_flag")
        source_value = _nonnegative_number(component.get("source_value"), f"{path}.source_value")
        conversion = _nonnegative_number(component.get("conversion_to_central_unit"), f"{path}.conversion_to_central_unit")
        converted = source_value * conversion
        if not float(converted).is_integer():
            _fail(path, "converted component must be a whole count")
        converted_total += converted
        group = component.get("overlap_group")
        if group is not None:
            group = _nonempty_string(group, f"{path}.overlap_group")
            if group in overlap_groups:
                _fail(path, "overlap_group repeats; overlapping components must be reconciled before summing")
            overlap_groups.add(group)
    aggregation = _object(entry.get("aggregation"), "aggregation")
    if aggregation.get("operation") != "sum":
        _fail("aggregation.operation", "component aggregates must declare sum")
    if aggregation.get("overlap_status") != "resolved-non-overlapping":
        _fail("aggregation.overlap_status", "must explicitly resolve overlap before summing")
    _nonempty_string(aggregation.get("basis"), "aggregation.basis")
    central = float(entry["estimate"]["central"])
    if abs(converted_total - central) > 0.000001:
        _fail("components", "converted component total does not equal estimate.central")


def _validate_entry(entry: Any, index: int) -> None:
    path = f"statistics[{index}]"
    entry = _object(entry, path)
    missing = _REQUIRED_ENTRY_FIELDS - entry.keys()
    if missing:
        _fail(path, "missing " + ", ".join(sorted(missing)))
    _nonempty_string(entry["statistic_id"], f"{path}.statistic_id")
    _nonempty_string(entry["version_id"], f"{path}.version_id")
    _nonempty_string(entry["label"], f"{path}.label")
    if entry["status"] != "validated-private":
        _fail(f"{path}.status", "must be validated-private until an authorized release approves publication")

    source = _object(entry["source"], f"{path}.source")
    _nonempty_string(source.get("source_id"), f"{path}.source.source_id")
    _nonempty_string(source.get("publisher"), f"{path}.source.publisher")
    _https_url(source.get("dataset_url"), f"{path}.source.dataset_url")
    _nonempty_string(source.get("dataset_name"), f"{path}.source.dataset_name")
    _nonempty_string(source.get("origin"), f"{path}.source.origin")

    scope = _object(entry["population_scope"], f"{path}.population_scope")
    _nonempty_string(scope.get("scope_id"), f"{path}.population_scope.scope_id")
    included = scope.get("included")
    if not isinstance(included, list) or not included or any(not isinstance(item, str) or not item.strip() for item in included):
        _fail(f"{path}.population_scope.included", "must be a non-empty list of named populations")
    _nonempty_string(scope.get("activity"), f"{path}.population_scope.activity")
    _nonempty_string(scope.get("animal_class"), f"{path}.population_scope.animal_class")

    geography = _object(entry["geography"], f"{path}.geography")
    _nonempty_string(geography.get("level"), f"{path}.geography.level")
    _nonempty_string(geography.get("area"), f"{path}.geography.area")
    period = _object(entry["period"], f"{path}.period")
    _nonempty_string(period.get("kind"), f"{path}.period.kind")
    _date(period.get("start"), f"{path}.period.start")
    _date(period.get("end"), f"{path}.period.end")
    if period["start"] > period["end"]:
        _fail(f"{path}.period", "start must not be after end")
    if period.get("calendar_year") is not None and period["start"][:4] != str(period["calendar_year"]):
        _fail(f"{path}.period.calendar_year", "must match period.start")

    unit = _object(entry["unit"], f"{path}.unit")
    if unit.get("kind") not in {"count", "mass", "rate"}:
        _fail(f"{path}.unit.kind", "must be count, mass, or rate")
    _nonempty_string(unit.get("name"), f"{path}.unit.name")
    _nonempty_string(unit.get("numerator"), f"{path}.unit.numerator")
    if unit.get("scale") is not None:
        _nonnegative_number(unit["scale"], f"{path}.unit.scale")
    _validate_estimate(entry)

    method = _object(entry["method"], f"{path}.method")
    if method.get("type") not in {"direct-source-observation", "derived-from-components", "converted-from-source"}:
        _fail(f"{path}.method.type", "must declare a supported method")
    _nonempty_string(method.get("description"), f"{path}.method.description")
    _nonempty_string(method.get("formula"), f"{path}.method.formula")
    exclusions = entry["exclusions"]
    if not isinstance(exclusions, list) or any(not isinstance(item, str) or not item.strip() for item in exclusions):
        _fail(f"{path}.exclusions", "must be a list of explicit strings")
    uncertainty = _object(entry["uncertainty"], f"{path}.uncertainty")
    _nonempty_string(uncertainty.get("kind"), f"{path}.uncertainty.kind")
    _nonempty_string(uncertainty.get("statement"), f"{path}.uncertainty.statement")
    if entry["estimate"]["low"] is None and uncertainty["kind"] == "numeric-range":
        _fail(f"{path}.uncertainty", "numeric-range requires low and high estimate bounds")

    provenance = _object(entry["provenance"], f"{path}.provenance")
    _nonempty_string(provenance.get("artifact_id"), f"{path}.provenance.artifact_id")
    _nonempty_string(provenance.get("artifact_path"), f"{path}.provenance.artifact_path")
    if not _SHA256.fullmatch(str(provenance.get("sha256", "")).lower()):
        _fail(f"{path}.provenance.sha256", "must be a lowercase SHA-256 checksum")
    byte_size = provenance.get("byte_size")
    if not isinstance(byte_size, int) or byte_size <= 0:
        _fail(f"{path}.provenance.byte_size", "must be a positive integer")
    _timestamp(provenance.get("retrieved_at_utc"), f"{path}.provenance.retrieved_at_utc")
    _date(provenance.get("effective_date"), f"{path}.provenance.effective_date")
    if provenance.get("publication_date") is not None:
        _date(provenance["publication_date"], f"{path}.provenance.publication_date")
    if provenance.get("public_artifact") is not False:
        _fail(f"{path}.provenance.public_artifact", "must be false for retained raw evidence")

    revision = _object(entry["revision"], f"{path}.revision")
    _nonempty_string(revision.get("revision_id"), f"{path}.revision.revision_id")
    _date(revision.get("released_date"), f"{path}.revision.released_date")
    if revision.get("released_at_utc") is not None:
        _timestamp(revision["released_at_utc"], f"{path}.revision.released_at_utc")
    if revision.get("supersedes") is not None:
        _nonempty_string(revision["supersedes"], f"{path}.revision.supersedes")
    _nonempty_string(revision.get("change_note"), f"{path}.revision.change_note")

    citations = entry["citations"]
    if not isinstance(citations, list) or not citations:
        _fail(f"{path}.citations", "must be a non-empty list")
    citation_ids: set[str] = set()
    for citation_index, citation in enumerate(citations):
        citation_path = f"{path}.citations[{citation_index}]"
        citation = _object(citation, citation_path)
        citation_id = _nonempty_string(citation.get("citation_id"), f"{citation_path}.citation_id")
        if citation_id in citation_ids:
            _fail(citation_path, "citation_id must be unique")
        citation_ids.add(citation_id)
        _nonempty_string(citation.get("title"), f"{citation_path}.title")
        _https_url(citation.get("url"), f"{citation_path}.url")
        _nonempty_string(citation.get("locator"), f"{citation_path}.locator")
        _date(citation.get("accessed_date"), f"{citation_path}.accessed_date")
    references = entry.get("citation_ids", [citation["citation_id"] for citation in citations])
    if not isinstance(references, list) or not references or any(reference not in citation_ids for reference in references):
        _fail(f"{path}.citation_ids", "must reference declared citations")
    _validate_components(entry)


def validate_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """Validate a catalog and return a row-free report suitable for CI."""
    catalog = _object(catalog, "catalog")
    if catalog.get("schema_version") != CATALOG_SCHEMA_VERSION:
        _fail("catalog.schema_version", f"must be {CATALOG_SCHEMA_VERSION}")
    entries = catalog.get("statistics")
    if not isinstance(entries, list) or not entries:
        _fail("catalog.statistics", "must be a non-empty list")
    ids: set[str] = set()
    versions: set[str] = set()
    for index, entry in enumerate(entries):
        _validate_entry(entry, index)
        if entry["statistic_id"] in ids:
            _fail(f"statistics[{index}].statistic_id", "must be unique")
        if entry["version_id"] in versions:
            _fail(f"statistics[{index}].version_id", "must be unique")
        ids.add(entry["statistic_id"])
        versions.add(entry["version_id"])
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "status": "passed",
        "statistics_count": len(entries),
        "statistic_ids": sorted(ids),
    }


def load_catalog(path: str | Path) -> dict[str, Any]:
    catalog_path = Path(path)
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StatisticsCatalogError(f"cannot read catalog {catalog_path}: {exc}") from exc
    validate_catalog(catalog)
    return catalog


def sha256_file(path: str | Path) -> tuple[str, int]:
    """Return the checksum and size used by an acquisition metadata record."""
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size
