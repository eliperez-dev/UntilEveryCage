"""Build a private, profile-aware APHIS investigation packet.

The Wave 2 runner produces source-local rows and identity candidates.  This
module adds the operator-facing evidence boundary on top of those artifacts:
it verifies explicitly supplied retained files, keeps periods (including
year-only annual reports) precise, and writes a row-bearing private packet
alongside a row-free report.  It intentionally does not acquire data,
geocode, publish, or infer ownership/current operation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, read_jsonl
from pipeline.sources.us.aphis.adapter import AphisContractError, AphisPublicSearchAdapter


PACKET_VERSION = "us-aphis-investigation-packet-v1"
HANDOFF_VERSION = "us-aphis-observation-handoff-v1"
PROFILES = ("registrations", "annual_reports", "inspections")
STATES = frozenset({"observed", "not_observed", "quarantined", "failed", "document_not_captured"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


class AphisEvidenceError(ValueError):
    """The retained-input or packet contract cannot be satisfied."""


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AphisEvidenceError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise AphisEvidenceError(f"manifest {path} must be a JSON object")
    return value


def _verified_lineage_pages(
    manifest_path: str | Path,
    page_root: str | Path,
    *,
    profile: str | None = None,
) -> dict[int, dict[str, Any]]:
    """Verify and parse the explicitly named original capture pages.

    A derived handoff may carry lineage metadata, but that metadata is not
    evidence by itself.  The capture manifest and page bytes are checked here
    so a correct-looking embedded hash cannot point at a missing, tampered, or
    wrong page.
    """
    manifest_file = Path(manifest_path).resolve()
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AphisEvidenceError(f"cannot read lineage manifest {manifest_file}: {exc}") from exc
    if isinstance(manifest, Mapping):
        pages = manifest.get("pages")
        if pages is None and isinstance(manifest.get("files"), list):
            pages = [
                item for item in manifest["files"]
                if isinstance(item, Mapping)
                and (profile is None or _text(item.get("profile")) == profile)
                and _text(item.get("relative_path"))
                and "/pages/" in str(item.get("relative_path"))
            ]
    else:
        pages = manifest
    if not isinstance(pages, list) or not pages:
        raise AphisEvidenceError(f"lineage manifest {manifest_file} lacks a non-empty pages list")
    root = Path(page_root).resolve()
    if not root.is_dir():
        raise AphisEvidenceError(f"lineage page root is not a directory: {root}")
    verified: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(pages, start=1):
        if not isinstance(item, Mapping):
            raise AphisEvidenceError(f"lineage manifest {manifest_file} has a malformed page entry")
        filename = _text(item.get("file") or item.get("source_filename"))
        if not filename and _text(item.get("relative_path")):
            filename = Path(str(item["relative_path"])).name
        ordinal = item.get("ordinal") or item.get("global_capture_ordinal")
        if not isinstance(ordinal, int) and filename:
            match = re.search(r"(?:page-|Page-)(\d+)", filename)
            ordinal = int(match.group(1)) if match else index
        declared_hash = _text(item.get("sha256"))
        declared_size = item.get("byte_size")
        source_url = _text(item.get("source_url"))
        if not isinstance(ordinal, int) or ordinal < 1 or not filename:
            raise AphisEvidenceError(f"lineage manifest {manifest_file} has invalid page identity")
        if ordinal in verified or not declared_hash or not _SHA256.fullmatch(declared_hash):
            raise AphisEvidenceError(f"lineage manifest {manifest_file} has invalid page hash")
        try:
            declared_size = int(declared_size)
        except (TypeError, ValueError) as exc:
            raise AphisEvidenceError(f"lineage manifest {manifest_file} has invalid page size") from exc
        if declared_size < 0:
            raise AphisEvidenceError(f"lineage manifest {manifest_file} has incomplete page metadata")
        candidate = (root / filename).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise AphisEvidenceError(f"lineage page escapes declared root: {filename}") from exc
        if not candidate.is_file():
            raise AphisEvidenceError(f"lineage page is missing: {filename}")
        actual_size = candidate.stat().st_size
        actual_hash = _sha256(candidate)
        if actual_size != declared_size or actual_hash.lower() != declared_hash.lower():
            raise AphisEvidenceError(f"lineage page bytes do not match capture manifest: {filename}")
        try:
            with candidate.open("r", encoding="utf-8-sig", newline="") as handle:
                text = handle.read()
            # APHIS exports can contain provider quoting irregularities.  The
            # retained bytes/hash remain authoritative; row-level equality
            # below is the fail-closed check against any parser recovery.
            reader = csv.DictReader(io.StringIO(text), strict=False)
            headers = reader.fieldnames
            rows = list(reader)
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            raise AphisEvidenceError(f"lineage page is not a UTF-8 CSV: {filename}") from exc
        if not headers or any(header is None or not str(header).strip() for header in headers):
            raise AphisEvidenceError(f"lineage page has invalid CSV headers: {filename}")
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise AphisEvidenceError(f"lineage page has malformed CSV rows: {filename}")
        declared_rows = item.get("row_count") if item.get("row_count") is not None else item.get("data_rows")
        if declared_rows is not None:
            try:
                declared_rows = int(declared_rows)
            except (TypeError, ValueError) as exc:
                raise AphisEvidenceError(f"lineage manifest {manifest_file} has invalid row count") from exc
            if declared_rows < 0 or len(rows) != declared_rows:
                raise AphisEvidenceError(f"lineage page row count does not match manifest: {filename}")
        verified[ordinal] = {
            "sha256": declared_hash.lower(),
            "byte_size": declared_size,
            "source_url": source_url,
            "page_retrieved_at_utc": _text(item.get("page_retrieved_at_utc")) or "unknown",
            "rows": rows,
        }
    return verified


def _string_row(value: Mapping[Any, Any]) -> dict[str, str]:
    return {str(key): "" if item is None else str(item) for key, item in value.items()}


def _verify_row_lineage(
    record: Mapping[str, Any],
    pages: Mapping[int, Mapping[str, Any]],
    *,
    handoff: Path,
) -> Mapping[str, Any]:
    normalized = record.get("normalized") if isinstance(record.get("normalized"), Mapping) else {}
    lineage = normalized.get("source_capture_lineage") if isinstance(normalized, Mapping) else None
    if not isinstance(lineage, Mapping):
        raise AphisEvidenceError(f"lineage-aware APHIS handoff row lacks source_capture_lineage: {handoff}")
    page_hash = _text(lineage.get("page_sha256"))
    page_url = _text(lineage.get("source_url"))
    page_ordinal = lineage.get("page_ordinal")
    page_row = lineage.get("page_row")
    page_size = lineage.get("page_byte_size")
    if not page_hash or not _SHA256.fullmatch(page_hash) or not page_url:
        raise AphisEvidenceError(f"lineage-aware APHIS handoff row has invalid page provenance: {handoff}")
    if not isinstance(page_ordinal, int) or page_ordinal < 1 or not isinstance(page_row, int) or page_row < 1:
        raise AphisEvidenceError(f"lineage-aware APHIS handoff row has invalid page position: {handoff}")
    try:
        page_size = int(page_size)
    except (TypeError, ValueError) as exc:
        raise AphisEvidenceError(f"lineage-aware APHIS handoff row has invalid page size: {handoff}") from exc
    if page_size < 0:
        raise AphisEvidenceError(f"lineage-aware APHIS handoff row has invalid page size: {handoff}")
    page = pages.get(page_ordinal)
    if page is None:
        raise AphisEvidenceError(f"lineage-aware APHIS handoff row references unknown page: {handoff}")
    if (
        page_hash.lower() != _text(page.get("sha256"))
        or page_size != page.get("byte_size")
        or (page.get("source_url") is not None and page_url != page.get("source_url"))
    ):
        raise AphisEvidenceError(f"lineage-aware APHIS handoff row disagrees with capture manifest: {handoff}")
    source_rows = page.get("rows")
    if not isinstance(source_rows, list) or page_row > len(source_rows):
        raise AphisEvidenceError(f"lineage-aware APHIS handoff row is outside original page: {handoff}")
    source_values = record.get("source_values")
    if not isinstance(source_values, Mapping):
        raise AphisEvidenceError(f"lineage-aware APHIS handoff row does not match original page row: {handoff}")
    source_values = _string_row(source_values)
    expected_capture_values = {
        "__capture_page_byte_size": str(page_size),
        "__capture_page_ordinal": str(page_ordinal),
        "__capture_page_retrieved_at_utc": str(_text(lineage.get("page_retrieved_at_utc")) or page.get("page_retrieved_at_utc") or "unknown"),
        "__capture_page_row": str(page_row),
        "__capture_page_sha256": page_hash.lower(),
        "__capture_source_url": page_url,
    }
    for key in (key for key in source_values if key.startswith("__capture_")):
        if key not in expected_capture_values or source_values[key] != expected_capture_values[key]:
            raise AphisEvidenceError(f"lineage-aware APHIS handoff row has invalid embedded capture metadata: {handoff}")
    source_values = {key: value for key, value in source_values.items() if not key.startswith("__capture_")}
    if source_values != _string_row(source_rows[page_row - 1]):
        raise AphisEvidenceError(f"lineage-aware APHIS handoff row does not match original page row: {handoff}")
    return {
        "artifact_sha256": page_hash.lower(),
        "source_url": page_url,
        "artifact_classification": "original_page",
        "page_sha256": page_hash.lower(),
        "page_ordinal": page_ordinal,
        "page_row": page_row,
        "page_byte_size": page_size,
        "page_retrieved_at_utc": _text(lineage.get("page_retrieved_at_utc")) or page.get("page_retrieved_at_utc") or "unknown",
    }


def _artifact_entries(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize Wave 1/Wave 2 artifact metadata without reading rows."""
    profiles = manifest.get("profiles")
    entries: list[dict[str, Any]] = []
    if isinstance(profiles, Mapping):
        for profile, value in profiles.items():
            if not isinstance(value, Mapping):
                continue
            artifacts = value.get("artifacts")
            if isinstance(artifacts, list):
                for item in artifacts:
                    if isinstance(item, Mapping):
                        entry = dict(item)
                        entry.setdefault("profile", profile)
                        entries.append(entry)
    retrieval = manifest.get("retrieval")
    # The tracked Wave 2 aggregate has no paths, so retain its profile-level
    # metadata as explicit unavailable entries instead of guessing locations.
    if isinstance(retrieval, Mapping) and not entries:
        for profile, value in retrieval.items():
            if isinstance(value, Mapping):
                entry = dict(value)
                entry["profile"] = profile
                entry["artifact"] = entry.get("artifact") or None
                entries.append(entry)
    return entries


def verify_retained_artifacts(
    manifest_path: str | Path,
    *,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve only manifest-named artifacts and verify bytes/hash/size.

    A missing path or a bad digest is a visible ``failed`` input.  The caller
    may still build a bounded packet from other profiles, but cannot label the
    failed profile observed.  No directory scan or credential lookup occurs.
    """
    path = Path(manifest_path).resolve()
    manifest = _json(path)
    root = Path(artifact_root).resolve() if artifact_root else path.parent
    checked: list[dict[str, Any]] = []
    for item in _artifact_entries(manifest):
        profile = _text(item.get("profile")) or "unknown"
        artifact_name = _text(item.get("artifact") or item.get("name"))
        declared_path = _text(item.get("path_private") or item.get("artifact_path") or item.get("path"))
        candidate = Path(declared_path) if declared_path else (root / artifact_name if artifact_name else None)
        if candidate is not None and not candidate.is_absolute():
            candidate = root / candidate
        result = {
            "profile": profile,
            "artifact": artifact_name,
            "declared_sha256": _text(item.get("sha256")),
            "declared_byte_size": item.get("byte_size") if item.get("byte_size") is not None else item.get("bytes"),
            "source_url": _text(item.get("source_url") or item.get("requested_url") or item.get("final_url")),
            "retrieved_at_utc": _text(item.get("retrieved_at_utc")),
            "path": str(candidate.resolve()) if candidate else None,
            "state": "failed",
            "failure": None,
        }
        if candidate is None:
            result["failure"] = "artifact_path_not_declared"
        elif not candidate.is_file():
            result["failure"] = "artifact_missing"
        else:
            actual_size = candidate.stat().st_size
            actual_hash = _sha256(candidate)
            result.update({"actual_sha256": actual_hash, "actual_byte_size": actual_size})
            expected_hash = result["declared_sha256"]
            expected_size = result["declared_byte_size"]
            if not expected_hash or not _SHA256.fullmatch(str(expected_hash)):
                result["failure"] = "artifact_hash_not_declared_or_invalid"
            elif actual_hash.lower() != str(expected_hash).lower():
                result["failure"] = "artifact_hash_mismatch"
            elif expected_size is None:
                result["failure"] = "artifact_size_not_declared"
            else:
                try:
                    size_matches = int(expected_size) == actual_size
                except (TypeError, ValueError):
                    size_matches = False
                if not size_matches:
                    result["failure"] = "artifact_size_mismatch"
                else:
                    result["state"] = "verified"
        checked.append(result)
    by_profile: dict[str, dict[str, int]] = {}
    for item in checked:
        stats = by_profile.setdefault(item["profile"], {"verified": 0, "failed": 0})
        stats["verified" if item["state"] == "verified" else "failed"] += 1
    return {
        "manifest_path": str(path),
        "manifest_sha256": _sha256(path),
        "artifacts": checked,
        "by_profile": by_profile,
        "all_verified": bool(checked) and all(item["state"] == "verified" for item in checked),
    }


def _normalized(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("normalized")
    return value if isinstance(value, Mapping) else {}


def _profile(record: Mapping[str, Any]) -> str:
    return str(_normalized(record).get("evidence_type") or record.get("profile") or "unknown")


def _record_key(record: Mapping[str, Any]) -> str:
    key = _text(record.get("source_record_key"))
    if not key:
        raise AphisEvidenceError("record lacks source_record_key")
    return key


def _period(record: Mapping[str, Any]) -> dict[str, str] | None:
    normalized = _normalized(record)
    year = _text(normalized.get("report_year"))
    if year and re.fullmatch(r"\d{4}", year):
        return {"start": f"{year}-01-01", "end": f"{year}-12-31", "precision": "year"}
    observed = _text(normalized.get("status_date") or normalized.get("observed_at"))
    if observed and re.fullmatch(r"\d{4}-\d{2}-\d{2}", observed):
        return {"start": observed, "end": observed, "precision": "day"}
    if observed and re.fullmatch(r"\d{4}-\d{2}", observed):
        year_num, month_num = (int(part) for part in observed.split("-"))
        last = date(year_num + (month_num == 12), 1 if month_num == 12 else month_num + 1, 1).toordinal() - 1
        return {"start": f"{observed}-01", "end": date.fromordinal(last).isoformat(), "precision": "month"}
    return None


def _provenance_for(
    provenance: Mapping[Any, Any],
    record: Mapping[str, Any],
    profile: str,
    *,
    verified_artifact_hashes: set[str] | None = None,
) -> dict[str, Any] | None:
    source_id = _text(record.get("source_id")) or "us.aphis"
    retained = record.get("_retained_artifact")
    profile_value = provenance.get((source_id, profile)) or provenance.get(f"{source_id}:{profile}") or provenance.get(source_id)
    if isinstance(retained, Mapping) and isinstance(profile_value, Mapping):
        value = {**profile_value, **retained}
    else:
        value = retained if isinstance(retained, Mapping) else profile_value
    if not isinstance(value, Mapping):
        return None
    digest = _text(value.get("artifact_sha256") or value.get("sha256"))
    url = _text(value.get("source_url") or value.get("final_url"))
    retrieved = _text(value.get("retrieved_at_utc"))
    if not digest or not _SHA256.fullmatch(digest) or not url or not retrieved:
        return None
    if verified_artifact_hashes is not None and digest.lower() not in verified_artifact_hashes:
        return None
    result = {"artifact_sha256": digest.lower(), "source_url": url, "retrieved_at_utc": retrieved}
    for key in (
        "artifact_classification", "page_sha256", "page_ordinal", "page_row",
        "page_byte_size", "page_retrieved_at_utc", "derived_artifact_sha256",
    ):
        if value.get(key) is not None:
            result[key] = value[key]
    return result


def _safe_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Private packet row; no generated URLs or external links are added."""
    return json.loads(json.dumps(record, ensure_ascii=False, default=list))


def _document_events(record_key: str, refs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, Mapping) or not _text(ref.get("document_key")):
            events.append({"state": "document_not_captured", "source_record_key": record_key, "reason": "document_key_missing"})
            continue
        # Document URLs are intentionally ignored. Only an explicitly named
        # source document key may associate a document with an observation.
        event = {"state": "observed" if ref.get("captured") else "document_not_captured", "source_record_key": record_key,
                 "document_key": _text(ref.get("document_key"))}
        if ref.get("captured") and _text(ref.get("artifact_sha256")):
            event["artifact_sha256"] = _text(ref.get("artifact_sha256"))
        elif not ref.get("captured"):
            event["reason"] = "referenced_document_unavailable"
        events.append(event)
    return events


def build_packet(
    *,
    records_by_profile: Mapping[str, Iterable[Mapping[str, Any]]],
    provenance: Mapping[Any, Any],
    graph: Mapping[str, Any] | None = None,
    registration_key: str | None = None,
    expected_rows: Mapping[str, int] | None = None,
    input_failures: Iterable[Mapping[str, Any]] = (),
    artifact_verification: Mapping[str, Any] | None = None,
    document_refs: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    previous_packet: Mapping[str, Any] | None = None,
    profile_input_rows: Mapping[str, int] | None = None,
    quarantine_rows_by_profile: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build deterministic private packet and row-free summary in memory."""
    failures = [dict(item) for item in input_failures]
    expected_rows = dict(expected_rows or {})
    explicit_input_rows = profile_input_rows is not None
    profile_input_rows = dict(profile_input_rows or {})
    quarantine_rows_by_profile = quarantine_rows_by_profile or {}
    document_refs = document_refs or {}
    accepted: dict[str, list[Mapping[str, Any]]] = {profile: list(records_by_profile.get(profile, ())) for profile in PROFILES}
    occurrences: Counter[str] = Counter(_record_key(record) for rows in accepted.values() for record in rows)
    timeline: list[dict[str, Any]] = []
    private_rows: list[dict[str, Any]] = []
    verified_hashes = {
        str(item.get("actual_sha256")).lower()
        for item in (artifact_verification or {}).get("artifacts", ())
        if isinstance(item, Mapping) and item.get("state") == "verified" and item.get("actual_sha256")
    } if artifact_verification else None
    profile_summary: dict[str, dict[str, Any]] = {}
    for profile in PROFILES:
        rows = accepted[profile]
        adapter_quarantine = [dict(item) for item in quarantine_rows_by_profile.get(profile, ())]
        captured_rows = int(profile_input_rows.get(profile, len(rows) + len(adapter_quarantine)))
        if captured_rows < 0:
            raise AphisEvidenceError(f"negative input row count for {profile}")
        if explicit_input_rows and profile in profile_input_rows and captured_rows != len(rows) + len(adapter_quarantine):
            raise AphisEvidenceError(
                f"input row reconciliation failed for {profile}: "
                f"declared={captured_rows}, accepted={len(rows)}, adapter_quarantined={len(adapter_quarantine)}"
            )
        expected = expected_rows.get(profile)
        if expected is not None and int(expected) < 0:
            raise AphisEvidenceError(f"negative expected row count for {profile}")
        if expected is not None and captured_rows > int(expected):
            raise AphisEvidenceError(
                f"expected row count underreported for {profile}: captured={captured_rows}, expected={expected}"
            )
        duplicate_keys = {key for key, count in occurrences.items() if count > 1}
        profile_failures = [item for item in failures if _text(item.get("profile")) == profile]
        observed = quarantined = 0
        periods: set[str] = set()
        for record in sorted(rows, key=lambda item: _record_key(item)):
            key = _record_key(record)
            record_provenance = _provenance_for(
                provenance, record, profile,
                verified_artifact_hashes=verified_hashes,
            )
            state = "quarantined" if key in duplicate_keys or _normalized(record).get("privacy_gate") in {"suppressed", "restricted"} or record_provenance is None else "observed"
            reason = (
                "duplicate_source_record_key" if key in duplicate_keys else
                "suppressed_or_restricted" if _normalized(record).get("privacy_gate") in {"suppressed", "restricted"} else
                "missing_or_invalid_provenance" if record_provenance is None else None
            )
            if state == "observed":
                observed += 1
            else:
                quarantined += 1
            period = _period(record)
            if period:
                periods.add(json.dumps(period, sort_keys=True))
            evidence = {
                "state": state,
                "source_id": _text(record.get("source_id")) or "us.aphis",
                "profile": profile,
                "source_record_key": key,
                "period": period,
                "provenance": record_provenance,
                "review_state": "review_required" if state == "observed" else "quarantined",
            }
            if reason:
                evidence["reason"] = reason
            timeline.append(evidence)
            private_rows.append({"evidence": evidence, "record": _safe_record(record)})
            timeline.extend(_document_events(key, document_refs.get(key, ())))
        for item in adapter_quarantine:
            record = item.get("record") if isinstance(item.get("record"), Mapping) else {}
            timeline.append({"state": "quarantined", "profile": profile,
                             "source_record_key": record.get("source_record_key"),
                             "reason": "adapter_quarantine", "reasons": list(item.get("reasons", ()))})
        if expected is not None and captured_rows < int(expected):
            timeline.append({"state": "not_observed", "profile": profile, "period": None,
                             "missing_count": int(expected) - captured_rows,
                             "reason": "expected_source_rows_not_captured"})
        if profile_failures:
            timeline.extend({"state": "failed", "profile": profile, "period": None, "failure": dict(item)} for item in profile_failures)
        profile_summary[profile] = {
            "input_rows": captured_rows, "observed_rows": observed, "quarantined_rows": quarantined + len(adapter_quarantine),
            "failed_inputs": len(profile_failures), "periods": [json.loads(value) for value in sorted(periods)],
            "coverage_state": "failed" if profile_failures else ("incomplete" if expected is not None and observed < int(expected) else "bounded"),
        }

    links: list[dict[str, Any]] = []
    link_quarantine: list[dict[str, Any]] = []
    if graph:
        for candidate in graph.get("candidates", ()) if isinstance(graph.get("candidates", ()), Iterable) else ():
            if not isinstance(candidate, Mapping):
                continue
            left = candidate.get("left") if isinstance(candidate.get("left"), Mapping) else {}
            right = candidate.get("right") if isinstance(candidate.get("right"), Mapping) else {}
            if registration_key and left.get("source_record_key") != registration_key:
                continue
            candidate_provenance = (candidate.get("evidence") or {}).get("provenance")
            has_provenance = isinstance(candidate_provenance, Mapping) and all(
                isinstance(value, Mapping)
                and _text(value.get("artifact_sha256"))
                and _text(value.get("source_url"))
                and _text(value.get("retrieved_at_utc"))
                and (verified_hashes is None or _text(value.get("artifact_sha256")).lower() in verified_hashes)
                for value in candidate_provenance.values()
            )
            review_state = _text(candidate.get("review_state"))
            assertion_status = _text(candidate.get("assertion_status"))
            conflict = bool(candidate.get("conflicting_official_identifiers") or candidate.get("identifier_conflicts"))
            reason = (
                "conflicting_official_identifiers" if conflict else
                "link_missing_or_invalid_provenance" if not has_provenance else
                "link_review_required" if review_state == "review_required" or assertion_status in {"candidate", "quarantined"} else None
            )
            item = {"candidate_id": candidate.get("candidate_id"),
                    "left": dict(left), "right": dict(right), "matched_identifiers": dict(candidate.get("matched_identifiers") or {}),
                    "review_state": review_state, "assertion_status": assertion_status,
                    "provenance": candidate_provenance}
            if reason:
                link_quarantine.append({"state": "quarantined", "reason": reason, **item})
            else:
                links.append({"state": "observed", **item})
        for candidate in graph.get("quarantined", ()) if isinstance(graph.get("quarantined", ()), Iterable) else ():
            if not isinstance(candidate, Mapping):
                continue
            if registration_key and candidate.get("left_source_record_key") != registration_key and (candidate.get("left") or {}).get("source_record_key") != registration_key:
                continue
            link_quarantine.append({"state": "quarantined", "reason": candidate.get("reason") or candidate.get("quarantine_reason") or "identity_review_required",
                                    "left_source_record_key": candidate.get("left_source_record_key") or (candidate.get("left") or {}).get("source_record_key"),
                                    "right_source_record_key": candidate.get("right_source_record_key") or (candidate.get("right") or {}).get("source_record_key"),
                                    "candidate_id": candidate.get("candidate_id")})
    timeline.sort(key=lambda item: (str(item.get("period") or ""), str(item.get("profile") or ""), str(item.get("source_record_key") or ""), str(item.get("state") or "")))
    summary = {
        "schema_version": PACKET_VERSION, "storage_state": "private", "publication_status": "not_eligible", "release_state": "not-created",
        "registration_source_record_key": registration_key, "profiles": profile_summary,
        "timeline_state_counts": dict(sorted(Counter(str(item.get("state")) for item in timeline).items())),
        "timeline_periods": sorted({json.dumps(item["period"], sort_keys=True) for item in timeline if isinstance(item.get("period"), Mapping)}),
        "links": {"candidate_count": len(links), "quarantined_count": len(link_quarantine), "excluded_reasons": dict(sorted(Counter(item["reason"] for item in link_quarantine).items()))},
        "input_failures": failures, "artifact_verification": dict(artifact_verification or {}),
        "coverage_boundary": "bounded retained APHIS source profiles; not a facility master, national census, current-operation, ownership, or animal-use total",
        "quarantine_semantics": "adapter quarantine reasons such as duplicate_observation_id are provisional source-identity collisions for review, not claims that retained rows are factually duplicate observations",
        "unknowns": ["location/current operation", "ownership/control", "unobserved source rows and reporting periods", "animal-use coverage outside the captured APHIS profiles"],
        "publication": {"api": False, "map": False, "export": False, "cache": False, "history": False},
    }
    private = {"schema_version": PACKET_VERSION, "summary": summary, "timeline": timeline, "links": links, "link_quarantine": link_quarantine, "rows": private_rows,
               "previous_packet_current": False if previous_packet else None}
    return {"private_packet": private, "row_free_summary": summary, "timeline": timeline, "links": links, "link_quarantine": link_quarantine}


def write_packet(run_dir: str | Path, packet: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically write row-bearing private files and a separate row-free report."""
    root = Path(run_dir)
    private = packet["private_packet"]
    summary = packet["row_free_summary"]
    atomic_json(root / "row-free-summary.json", dict(summary))
    atomic_json(root / "editorial-note.json", {
        "what_it_makes_visible": "A bounded, source-native view of registrations and their captured annual-report and inspection observations.",
        "why_it_matters": "It gives activists a traceable way to investigate regulatory records without turning partial evidence into a facility census or allegation.",
        "what_it_does_not_establish": "It does not establish current operation, ownership, wrongdoing, animal-use totals, closure, or absence.",
        "next_questions": ["Which missing periods or documents can be obtained through an authorized route?", "Which quarantined identities need human review?", "What source evidence can establish location or operation separately?"],
    })
    atomic_jsonl(root / "private" / "timeline.jsonl", list(private["timeline"]))
    atomic_jsonl(root / "private" / "rows.jsonl", list(private["rows"]))
    atomic_jsonl(root / "private" / "links.jsonl", list(private["links"]))
    atomic_jsonl(root / "private" / "link-quarantine.jsonl", list(private["link_quarantine"]))
    manifest = {"schema_version": PACKET_VERSION, "row_free_summary_sha256": hashlib.sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest(),
                "private_packet_sha256": hashlib.sha256(json.dumps(private, sort_keys=True, default=list).encode()).hexdigest(),
                "storage_state": "private", "publication_status": "not_eligible", "release_state": "not-created", "test_only": True}
    atomic_json(root / "packet-manifest.json", manifest)
    return manifest


def run_from_wave2(
    wave2_dir: str | Path,
    packet_dir: str | Path,
    *,
    registration_key: str | None = None,
    expected_rows: Mapping[str, int] | None = None,
    document_refs: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Reuse an existing Wave 2 private run as the packet input.

    This is deliberately a file boundary: the function does not reacquire or
    reinterpret source rows. A Wave 2 run with a failed input keeps that
    failure in the packet and never promotes an earlier packet to current.
    """
    root = Path(wave2_dir)
    report_path = root / "wave2-report.json"
    report = _json(report_path)
    input_manifest = root / "input-manifest.json"
    if not input_manifest.is_file():
        raise AphisEvidenceError(f"Wave 2 input manifest is missing: {input_manifest}")
    verification = verify_retained_artifacts(input_manifest)
    records = {
        profile: read_jsonl(root / "private-rows" / f"{profile}-accepted.jsonl")
        if (root / "private-rows" / f"{profile}-accepted.jsonl").is_file() else []
        for profile in PROFILES
    }
    graph_dir = root / "identity-graph"
    graph = {
        "candidates": read_jsonl(graph_dir / "candidate" / "identity-links.jsonl")
        if (graph_dir / "candidate" / "identity-links.jsonl").is_file() else [],
        "quarantined": read_jsonl(graph_dir / "quarantined" / "identity-links.jsonl")
        if (graph_dir / "quarantined" / "identity-links.jsonl").is_file() else [],
    }
    provenance = {}
    for profile, value in (report.get("profiles") or {}).items():
        if isinstance(value, Mapping):
            provenance[("us.aphis", profile)] = {
                # Wave 2's aggregate hash covers metadata strings, not source
                # bytes. Row-level hashes come from _retained_artifact tags.
                "source_url": value.get("source_url"),
                "retrieved_at_utc": value.get("retrieved_at_utc"),
            }
    completeness = report.get("completeness") if isinstance(report.get("completeness"), Mapping) else {}
    expected = dict(expected_rows or {})
    input_rows: dict[str, int] = {}
    for profile, value in completeness.items():
        if not isinstance(value, Mapping):
            continue
        if value.get("expected_displayed_rows") is not None and profile not in expected:
            expected[profile] = int(value["expected_displayed_rows"])
        if value.get("observed_input_rows") is not None:
            input_rows[profile] = int(value["observed_input_rows"])
    quarantine_rows = {
        profile: read_jsonl(root / "private-rows" / f"{profile}-adapter-quarantine.jsonl")
        if (root / "private-rows" / f"{profile}-adapter-quarantine.jsonl").is_file() else []
        for profile in PROFILES
    }
    packet = build_packet(
        records_by_profile=records, provenance=provenance, graph=graph,
        registration_key=registration_key, expected_rows=expected,
        input_failures=report.get("input_failures") or [], document_refs=document_refs,
        artifact_verification=verification, profile_input_rows=input_rows,
        quarantine_rows_by_profile=quarantine_rows,
    )
    manifest = write_packet(packet_dir, packet)
    return {"packet": packet, "manifest": manifest}


def _read_observation_handoff(handoff_dir: str | Path, expected_profile: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read one source-local APHIS handoff without scanning its parent tree.

    Acquisition lanes hand off normalized rows separately.  This boundary
    verifies the handoff payload and its private contract, while leaving raw
    artifact-byte verification to an optional manifest/artifact replay.
    """
    root = Path(handoff_dir).resolve()
    manifest_path = root / "manifest.json"
    records_path = root / "records.jsonl"
    if not manifest_path.is_file() or not records_path.is_file():
        raise AphisEvidenceError(f"APHIS handoff is incomplete: {root}")
    manifest = _json(manifest_path)
    required = {
        "contract_version": HANDOFF_VERSION,
        "source_id": "us.aphis",
        "profile": expected_profile,
        "release_state": "not-created",
        "publication_state": "private-candidate",
        "review_state": "review_required",
        "privacy_gate": "pending",
        "coordinate_gate": "review_required",
        "graph_candidate_emission": False,
        "auto_merge": False,
        "test_only": True,
        "row_payloads_included": True,
    }
    for key, value in required.items():
        if manifest.get(key) != value:
            raise AphisEvidenceError(f"APHIS handoff {root} violates {key} contract")
    payload = records_path.read_bytes()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != _text(manifest.get("normalized_sha256")):
        raise AphisEvidenceError(f"APHIS handoff payload checksum mismatch: {root}")
    try:
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AphisEvidenceError(f"APHIS handoff payload is malformed: {root}") from exc
    if len(rows) != int(manifest.get("normalized_rows", -1)):
        raise AphisEvidenceError(f"APHIS handoff row count mismatch: {root}")
    for row in rows:
        if not isinstance(row, Mapping) or _text(row.get("source_id")) != "us.aphis" or not _text(row.get("source_record_key")):
            raise AphisEvidenceError(f"APHIS handoff row lacks source identity: {root}")
        evidence_type = _profile(row)
        allowed = {expected_profile}
        if expected_profile == "annual_reports":
            allowed.add("amendments")
        if evidence_type not in allowed:
            raise AphisEvidenceError(f"APHIS handoff row profile mismatch: {root}")
    return rows, dict(manifest)


def run_from_handoffs(
    handoff_dirs: Mapping[str, str | Path],
    packet_dir: str | Path,
    *,
    registration_key: str | None = None,
    expected_rows: Mapping[str, int] | None = None,
    document_refs: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    profile_input_rows: Mapping[str, int] | None = None,
    quarantine_rows_by_profile: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    lineage_manifest_paths: Mapping[str, str | Path] | None = None,
    lineage_page_roots: Mapping[str, str | Path] | None = None,
) -> dict[str, Any]:
    """Consume lane-specific APHIS observation handoffs into one packet.

    ``handoff_dirs`` is explicit by profile and never discovered recursively.
    The source artifact checksum is retained as row provenance; callers that
    also retain the raw files can use the standalone artifact verifier before
    treating those bytes as independently verified.

    ``profile_input_rows`` and ``quarantine_rows_by_profile`` are explicit
    acquisition-lane accounting inputs. They allow an accepted-only handoff
    to retain adapter quarantine and source capture totals without guessing
    that excluded rows were absent.
    """
    records: dict[str, list[dict[str, Any]]] = {profile: [] for profile in PROFILES}
    quarantine_rows = {
        profile: list((quarantine_rows_by_profile or {}).get(profile, ()))
        for profile in PROFILES
    }
    lineage_manifest_paths = dict(lineage_manifest_paths or {})
    lineage_page_roots = dict(lineage_page_roots or {})
    provenance: dict[tuple[str, str], dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    observed_input_rows: dict[str, int] = {}
    evidence_origins: dict[str, str | None] = {profile: None for profile in PROFILES}
    capture_classifications: dict[str, str | None] = {profile: None for profile in PROFILES}
    lineage_rows: dict[str, int] = {profile: 0 for profile in PROFILES}
    lineage_unknown_retrieval_rows: dict[str, int] = {profile: 0 for profile in PROFILES}
    lineage_quarantine_rows: dict[str, int] = {profile: 0 for profile in PROFILES}
    artifact_classifications: dict[str, str | None] = {profile: None for profile in PROFILES}
    verified_pages: dict[str, dict[int, dict[str, Any]]] = {}
    for profile in PROFILES:
        handoff = handoff_dirs.get(profile)
        if handoff is None:
            failures.append({"profile": profile, "state": "failed", "failure": "handoff_missing"})
            continue
        try:
            rows, manifest = _read_observation_handoff(handoff, profile)
        except (OSError, TypeError, ValueError, AphisEvidenceError) as exc:
            failures.append({"profile": profile, "state": "failed", "failure": f"handoff_invalid:{type(exc).__name__}"})
            continue
        source_url = _text(manifest.get("source_url"))
        retrieved = _text(manifest.get("retrieved_at_utc"))
        digest = _text(manifest.get("source_artifact_sha256") or manifest.get("checksum_sha256"))
        origin = _text(manifest.get("evidence_origin"))
        classification = _text(manifest.get("capture_classification"))
        artifact_classification = _text(manifest.get("source_artifact_classification"))
        evidence_origins[profile] = origin
        capture_classifications[profile] = classification
        artifact_classifications[profile] = artifact_classification
        observed_input_rows[profile] = len(rows)
        provenance[("us.aphis", profile)] = {
            "artifact_sha256": digest,
            "source_url": source_url,
            "retrieved_at_utc": retrieved,
        }
        if artifact_classification == "derived_staging_with_original_page_lineage":
            lineage_manifest = lineage_manifest_paths.get(profile)
            lineage_root = lineage_page_roots.get(profile)
            if lineage_manifest is None or lineage_root is None:
                raise AphisEvidenceError(
                    f"lineage-aware APHIS handoff requires explicit capture manifest and page root: {handoff}"
                )
            verified_pages[profile] = _verified_lineage_pages(lineage_manifest, lineage_root, profile=profile)

        for row in rows:
            row_copy = dict(row)
            if artifact_classification == "derived_staging_with_original_page_lineage":
                row_copy["_retained_artifact"] = {
                    **_verify_row_lineage(row, verified_pages[profile], handoff=Path(handoff).resolve()),
                    "retrieved_at_utc": retrieved,
                    "derived_artifact_sha256": digest,
                }
                lineage_rows[profile] += 1
                if row_copy["_retained_artifact"]["page_retrieved_at_utc"] == "unknown":
                    lineage_unknown_retrieval_rows[profile] += 1
            else:
                row_copy["_retained_artifact"] = {
                    "artifact_sha256": digest,
                    "source_url": source_url,
                    "retrieved_at_utc": retrieved,
                    "artifact_classification": artifact_classification or "source_artifact",
                }
            records[profile].append(row_copy)
            if row_copy["_retained_artifact"].get("artifact_sha256"):
                provenance[("us.aphis", profile, str(row["source_record_key"]))] = dict(row_copy["_retained_artifact"])

        if artifact_classification == "derived_staging_with_original_page_lineage":
            for item in quarantine_rows[profile]:
                quarantined_record = item.get("record") if isinstance(item, Mapping) else None
                if not isinstance(quarantined_record, Mapping):
                    continue
                _verify_row_lineage(quarantined_record, verified_pages[profile], handoff=Path(handoff).resolve())
                lineage_quarantine_rows[profile] += 1

    from pipeline.sources.us.accountability.current_identity import build_current_identity_graph

    graph = build_current_identity_graph(
        aphis_records=records,
        fsis_records=(),
        fsis_observations=(),
        provenance=provenance,
    )
    packet = build_packet(
        records_by_profile=records,
        provenance=provenance,
        graph=graph,
        registration_key=registration_key,
        expected_rows=expected_rows,
        input_failures=failures,
        profile_input_rows=profile_input_rows or observed_input_rows,
        document_refs=document_refs,
        quarantine_rows_by_profile=quarantine_rows,
    )
    def _consensus(values: Mapping[str, str | None], fallback: str) -> str:
        if not values or any(not value for value in values.values()):
            return fallback
        distinct = set(values.values())
        return next(iter(distinct)) if len(distinct) == 1 else fallback

    # ``test_only`` is the existing private/no-publication gate on this
    # handoff contract. It does not establish source origin. Only explicit,
    # consistent handoff metadata may classify the evidence; otherwise retain
    # an unknown state rather than using a URL or source name as a heuristic.
    for value in (packet["row_free_summary"], packet["private_packet"]):
        value["evidence_origin"] = _consensus(evidence_origins, "unknown")
        value["capture_classification"] = _consensus(capture_classifications, "unknown-retained-handoff")
        value["lineage"] = {
            "rows_with_original_page_lineage": dict(lineage_rows),
            "rows_with_unknown_page_retrieval": dict(lineage_unknown_retrieval_rows),
            "quarantined_rows_with_original_page_lineage": dict(lineage_quarantine_rows),
            "source_artifact_classification": dict(artifact_classifications),
        }
    manifest = write_packet(packet_dir, packet)
    return {"packet": packet, "manifest": manifest, "graph": graph, "input_failures": failures}


def _load_verified_exports(
    verification: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[tuple[str, str], dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    """Parse only verified manifest-named exports for the standalone CLI."""
    records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    quarantined: dict[str, list[dict[str, Any]]] = defaultdict(list)
    provenance: dict[tuple[str, str], dict[str, Any]] = {}
    input_rows: dict[str, int] = defaultdict(int)
    failures: list[dict[str, Any]] = []
    adapter = AphisPublicSearchAdapter()
    report_profiles = manifest.get("profile_metadata") if isinstance(manifest.get("profile_metadata"), Mapping) else {}
    for item in verification.get("artifacts", ()):
        if not isinstance(item, Mapping) or item.get("state") != "verified":
            continue
        profile = _text(item.get("profile"))
        path = _text(item.get("path"))
        if not profile or profile not in PROFILES or not path:
            continue
        try:
            result = adapter.parse_bytes(Path(path).read_bytes())
        except (OSError, AphisContractError) as exc:
            failure = {"profile": profile, "artifact": item.get("artifact"), "state": "failed", "failure": f"adapter_error:{type(exc).__name__}"}
            failures.append(failure)
            quarantined[profile].append({"state": "failed", "reasons": [failure["failure"]]})
            continue
        if result.get("profile") != profile:
            failure = {"profile": profile, "artifact": item.get("artifact"), "state": "failed",
                       "failure": "manifest_profile_mismatch", "parsed_profile": result.get("profile")}
            failures.append(failure)
            quarantined[profile].append({"state": "failed", "reasons": [failure["failure"]],
                                         "parsed_profile": result.get("profile")})
            continue
        artifact = {"artifact_sha256": item.get("actual_sha256"), "source_url": item.get("source_url"),
                    "retrieved_at_utc": item.get("retrieved_at_utc")}
        profile_meta = report_profiles.get(profile) if isinstance(report_profiles, Mapping) else None
        if isinstance(profile_meta, Mapping):
            artifact["source_url"] = artifact.get("source_url") or profile_meta.get("source_url")
            artifact["retrieved_at_utc"] = artifact.get("retrieved_at_utc") or profile_meta.get("retrieved_at_utc")
        for record in result["accepted"]:
            records[profile].append({**record, "_retained_artifact": artifact})
        quarantined[profile].extend({**row, "record": {**row["record"], "_retained_artifact": artifact}} for row in result["quarantined"])
        input_rows[profile] += int(result["input_rows"])
        provenance[("us.aphis", profile)] = artifact
    expected = manifest.get("expected_rows") if isinstance(manifest.get("expected_rows"), Mapping) else {}
    return dict(records), dict(quarantined), provenance, dict(input_rows), failures


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest = _json(args.manifest)
    verification = verify_retained_artifacts(args.manifest, artifact_root=args.artifact_root)
    records, quarantined, provenance, input_rows, parse_failures = _load_verified_exports(verification, manifest)
    failures = [item for item in verification["artifacts"] if item.get("state") != "verified"] + parse_failures
    packet = build_packet(
        records_by_profile=records, provenance=provenance,
        expected_rows=manifest.get("expected_rows") if isinstance(manifest.get("expected_rows"), Mapping) else {},
        profile_input_rows=input_rows, quarantine_rows_by_profile=quarantined,
        artifact_verification=verification, input_failures=failures,
    )
    write_packet(args.run_dir, packet)
    summary = {"schema_version": PACKET_VERSION, "artifact_verification": verification,
               "input_failures": failures, "row_free_summary": packet["row_free_summary"]}
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
