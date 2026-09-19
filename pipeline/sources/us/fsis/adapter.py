"""Fail-closed private adapter for the FSIS MPI directory bundle.

The official page exposes directory and supplemental demographic exports as
separate artifacts. This adapter preserves each artifact's source values and
joins them only on exact source-native establishment identifiers. It never
uses names, addresses, phones, or coordinates as identity keys.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
ALLOWED_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR VI GU AS MP".split()
)


class FsisContractError(ValueError):
    """The captured artifact is not a supported FSIS profile."""


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _header_key(value: str) -> str:
    """Make header matching tolerant of punctuation/case, not row identity."""
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _schema_fingerprint(headers: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _csv(content: bytes, *, role: str) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        headers = tuple(reader.fieldnames or ())
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise FsisContractError(f"malformed or unsupported UTF-8 {role} CSV") from exc
    if not headers:
        raise FsisContractError(f"missing FSIS {role} header")
    if None in headers or len(set(headers)) != len(headers):
        raise FsisContractError(f"duplicate or unnamed FSIS {role} columns")
    if not rows:
        raise FsisContractError(f"FSIS {role} CSV contains no data rows")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise FsisContractError(f"FSIS {role} schema drift: row has extra columns")
    normalized_headers = {_header_key(header) for header in headers}
    if role == "directory" and not ({"establishment_id", "establishment_number"} & normalized_headers):
        raise FsisContractError("unsupported FSIS directory: missing establishment identity fields")
    if role == "demographics" and not ({"establishment_id", "establishment_number", "number"} & normalized_headers):
        raise FsisContractError("unsupported FSIS demographics: missing establishment identity fields")
    return headers, rows


def _field(row: dict[str, Any], *aliases: str) -> str | None:
    wanted = {_header_key(alias) for alias in aliases}
    for key, value in row.items():
        if _header_key(str(key)) in wanted:
            return _clean(value)
    return None


def _key_candidates(row: dict[str, Any]) -> tuple[str, ...]:
    """Return source-native aliases, preserving ID-vs-number distinctions."""
    values: list[str] = []
    for alias in (
        "establishment_id", "establishment id", "mpi id", "establishment_number",
        "establishment number", "establishment no", "establishment no.", "number",
    ):
        value = _field(row, alias)
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _identity_values(row: dict[str, Any]) -> dict[str, str | None]:
    """Return identity values by source-native kind, not just raw value."""
    return {
        "establishment_id": _field(row, "establishment_id", "establishment id", "mpi id"),
        "establishment_number": _field(
            row, "establishment_number", "establishment number", "establishment no", "establishment no.", "number"
        ),
    }


def _identity_key(row: dict[str, Any]) -> str | None:
    candidates = _key_candidates(row)
    return candidates[0] if candidates else None


def _coordinate(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str, str | None]:
    latitude = _field(row, "latitude", "lat", "y")
    longitude = _field(row, "longitude", "lon", "lng", "long", "x")
    if latitude is None and longitude is None:
        return None, "unknown", None
    try:
        lat = float(latitude) if latitude is not None else None
        lon = float(longitude) if longitude is not None else None
    except ValueError:
        return None, "source-value-invalid", "invalid_coordinates"
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None, "source-value-invalid", "invalid_coordinates"
    return (
        {
            "latitude": lat,
            "longitude": lon,
            "provider": "FSIS source-provided coordinate",
            "query": None,
            "precision": "source-provided",
            "review_state": "pending-review",
        },
        "source-value-present-pending-review",
        None,
    )


def _activity_maps(rows: Iterable[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    slaughter: dict[str, str] = {}
    processing: dict[str, str] = {}
    inspection: dict[str, str] = {}
    all_activities: dict[str, str] = {}
    for row in rows:
        for raw_key, raw_value in row.items():
            value = _clean(raw_value)
            key = _header_key(str(raw_key))
            if not value or key in {"establishment_id", "establishment_number", "establishment_name", "name"}:
                continue
            if "slaughter" in key:
                slaughter[key] = value
                all_activities[key] = value
            elif "processing" in key or key in {"egg_product", "egg_products"}:
                processing[key] = value
                all_activities[key] = value
            elif key.startswith("inspection") or "inspection_system" in key:
                inspection[key] = value
    return (
        dict(sorted(slaughter.items())),
        dict(sorted(processing.items())),
        dict(sorted(inspection.items())),
        dict(sorted(all_activities.items())),
    )


def _record(directory: dict[str, Any], line: int, demographic: dict[str, Any] | None = None, demographic_line: int | None = None) -> dict[str, Any]:
    source_rows: list[dict[str, Any]] = [directory]
    if demographic:
        source_rows.append(demographic)
    slaughter, processing, inspection, all_activities = _activity_maps(source_rows)
    inspection_attributes = dict(inspection)
    for attribute, aliases in {
        "establishment_type": ("type", "establishment_type"),
        "district": ("district",),
        "circuit": ("circuit",),
        "size": ("size", "haccp_size", "establishment_size"),
        "grant_date": ("grant_date", "grant date"),
    }.items():
        value = _field(directory, *aliases)
        if value:
            inspection_attributes[attribute] = value
    coordinates, coordinate_state, coordinate_reason = _coordinate(directory)
    # Editions may place coordinates in the supplemental file. Use them only
    # when the directory has no coordinate value; a malformed directory value
    # remains an anomaly rather than being silently repaired.
    if coordinates is None and coordinate_reason is None and demographic:
        coordinates, coordinate_state, coordinate_reason = _coordinate(demographic)
    establishment_id = _field(directory, "establishment_id", "establishment id", "mpi id")
    establishment_number = _field(directory, "establishment_number", "establishment number", "establishment no", "establishment no.", "number")
    # Some official directory editions expose only the establishment number.
    # It is source-native, so retain it as the fallback ID rather than
    # inventing a project UUID or dropping the row.
    identity = establishment_id or establishment_number
    normalized = {
        "establishment_id": identity,
        "establishment_number": establishment_number,
        "canonical_name": _field(directory, "establishment_name", "establishment name", "name", "facility_name"),
        "country_code": "US",
        "city": _field(directory, "city", "town"),
        "state": (_field(directory, "state", "st") or "").upper() or None,
        "postal_code": _field(directory, "zip", "zipcode", "zip_code", "postal_code"),
        "county": _field(directory, "county"),
        "fips_code": _field(directory, "fips_code", "fips"),
        "district": _field(directory, "district"),
        "circuit": _field(directory, "circuit"),
        "size": _field(directory, "size", "haccp_size", "establishment_size"),
        "source_type": _field(directory, "type", "establishment_type", "activities", "activity"),
        "grant_date": _field(directory, "grant_date", "grant date"),
        "coordinates": coordinates,
        "coordinate_state": coordinate_state,
        "address_state": "source-address-retained-private-pending-review" if _field(directory, "street", "address", "address_line_1") else "unknown",
        "species_slaughtered": slaughter,
        "processing_activities": processing,
        "inspection_attributes": dict(sorted(inspection_attributes.items())),
        "activities": tuple(sorted(all_activities)),
        "activity_categories": tuple(category for category, values in (("slaughter", slaughter), ("processing", processing)) if values),
        "privacy_gate": "pending-review",
        "coordinate_gate": "review_required",
        "publication_gate": "blocked",
    }
    directory_values = {str(key): value for key, value in directory.items()}
    return {
        "source_id": CONFIG["source_id"],
        "source_row": line,
        "source_record_key": identity,
        "source_values": {
            # Keep the directory-only shape available to existing private
            # rehearsals while the role-qualified keys make bundle provenance
            # explicit for new consumers.
            **directory_values,
            "directory": directory_values,
            "demographics": {str(key): value for key, value in demographic.items()} if demographic else None,
        },
        "source_rows": {"directory": line, "demographics": demographic_line},
        "normalized": normalized,
        "coordinate_anomaly": coordinate_reason,
    }


def _quarantine(record: dict[str, Any], reasons: Iterable[str]) -> dict[str, Any]:
    record = dict(record)
    record.pop("coordinate_anomaly", None)
    return {"reasons": tuple(dict.fromkeys(reasons)), "record": record}


def _demo_matches(row: dict[str, Any], directory: dict[str, Any]) -> bool:
    demo_values = _identity_values(row)
    directory_values = _identity_values(directory)
    shared = any(
        demo_values[k] and directory_values[k] and demo_values[k] == directory_values[k]
        for k in demo_values
    )
    conflicting = any(
        demo_values[k] and directory_values[k] and demo_values[k] != directory_values[k]
        for k in demo_values
    )
    return shared and not conflicting


def _demo_identity_conflict(row: dict[str, Any], directory: dict[str, Any]) -> bool:
    demo_values = _identity_values(row)
    directory_values = _identity_values(directory)
    shared = any(
        demo_values[k] and directory_values[k] and demo_values[k] == directory_values[k]
        for k in demo_values
    )
    conflicting = any(
        demo_values[k] and directory_values[k] and demo_values[k] != directory_values[k]
        for k in demo_values
    )
    return shared and conflicting


class FsisMpiAdapter:
    source_id = CONFIG["source_id"]
    adapter_version = CONFIG["adapter_version"]
    schema_version = CONFIG["contract_version"]

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        """Parse a directory-only capture for compatibility with old callers."""
        return self.parse_sources(content)

    def parse_sources(self, directory: bytes, demographics: bytes | None = None) -> dict[str, Any]:
        directory_headers, directory_rows = _csv(directory, role="directory")
        demographic_headers: tuple[str, ...] = ()
        demographic_rows: list[dict[str, Any]] = []
        if demographics is not None:
            demographic_headers, demographic_rows = _csv(demographics, role="demographics")
        directory_alias_counts = Counter(alias for row in directory_rows for alias in _key_candidates(row))
        duplicate_directory_aliases = {alias for alias, count in directory_alias_counts.items() if count > 1}
        demographic_alias_counts = Counter(alias for row in demographic_rows for alias in _key_candidates(row))
        duplicate_demographic_aliases = {alias for alias, count in demographic_alias_counts.items() if count > 1}
        demographic_indices_by_alias: dict[str, set[int]] = {}
        for demographic_index, demographic in enumerate(demographic_rows):
            for alias in _key_candidates(demographic):
                demographic_indices_by_alias.setdefault(alias, set()).add(demographic_index)

        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        matched_demographics: set[int] = set()
        identity_conflicts = 0
        for index, row in enumerate(directory_rows):
            line = index + 2
            aliases = set(_key_candidates(row))
            reasons: list[str] = []
            if not aliases:
                reasons.append("missing_establishment_id")
                reasons.append("missing_establishment_identity")
            if aliases & duplicate_directory_aliases:
                reasons.append("duplicate_establishment_id")
                reasons.append("duplicate_establishment_identity")
            state = (_field(row, "state", "st") or "").upper()
            if state and state not in ALLOWED_STATES:
                reasons.append("unknown_state")
            if not _field(row, "establishment_name", "establishment name", "name", "facility_name"):
                reasons.append("missing_establishment_name")
            candidate_demo_indices = {
                demo_index for alias in aliases
                for demo_index in demographic_indices_by_alias.get(alias, ())
            }
            matching_demo = [
                demo_index for demo_index in candidate_demo_indices
                if _demo_matches(demographic_rows[demo_index], row)
            ]
            demographic: dict[str, Any] | None = None
            demographic_line: int | None = None
            if any(
                _demo_identity_conflict(demographic_rows[demo_index], row)
                for demo_index in candidate_demo_indices
            ):
                reasons.append("conflicting_demographic_identity")
                identity_conflicts += 1
            if len(matching_demo) > 1:
                reasons.append("ambiguous_demographic_identity")
                identity_conflicts += 1
            elif matching_demo:
                demo_index = matching_demo[0]
                matched_demographics.add(demo_index)
                demographic = demographic_rows[demo_index]
                demographic_line = demo_index + 2
                if set(_key_candidates(demographic)) & duplicate_demographic_aliases:
                    reasons.append("duplicate_demographic_identity")
            record = _record(row, line, demographic, demographic_line)
            if record.pop("coordinate_anomaly", None):
                reasons.append("invalid_coordinates")
            (quarantined if reasons else accepted).append(_quarantine(record, reasons) if reasons else record)

        orphan_demographics = 0
        for index, row in enumerate(demographic_rows):
            if index in matched_demographics:
                continue
            orphan_demographics += 1
            record = _record({}, index + 2, row, index + 2)
            record["source_record_key"] = _identity_key(row)
            record["normalized"]["establishment_id"] = _identity_key(row)
            record["source_values"] = {
                "directory": None,
                "demographics": {str(key): value for key, value in row.items()},
            }
            record["source_rows"] = {"directory": None, "demographics": index + 2}
            quarantined.append(_quarantine(record, ("unmatched_demographic_identity",)))

        return {
            "accepted": accepted,
            "quarantined": quarantined,
            "source_sha256": hashlib.sha256(directory).hexdigest(),
            "schema_fingerprint": _schema_fingerprint(directory_headers),
            "demographic_schema_fingerprint": _schema_fingerprint(demographic_headers) if demographic_headers else None,
            "headers": directory_headers,
            "demographic_headers": demographic_headers,
            "input_rows": len(accepted) + len(quarantined),
            "directory_rows": len(directory_rows),
            "demographic_rows": len(demographic_rows),
            "matched_demographic_rows": len(matched_demographics),
            "orphan_demographic_rows": orphan_demographics,
            "identity_conflicts": identity_conflicts,
        }

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if artifact.sha256 != digest or artifact.byte_size != len(raw):
            raise ValueError("artifact provenance mismatch")
        return self.run_sources({"directory": raw}, run_dir, {"directory": artifact})

    def run_sources(self, raw_paths: dict[str, bytes | str | Path], run_dir: str | Path, artifacts: dict[str, SourceArtifact]) -> dict[str, Any]:
        if "directory" not in raw_paths or "directory" not in artifacts:
            raise ValueError("FSIS bundle requires a directory artifact")
        directory = _bytes(raw_paths["directory"])
        demographics = _bytes(raw_paths["demographics"]) if "demographics" in raw_paths else None
        for role, content in (("directory", directory), ("demographics", demographics)):
            if content is None:
                continue
            artifact = artifacts.get(role)
            if artifact is None or artifact.sha256 != hashlib.sha256(content).hexdigest() or artifact.byte_size != len(content):
                raise ValueError(f"{role} artifact provenance mismatch")
        result = self.parse_sources(directory, demographics)
        accepted = result["accepted"]
        quarantined = result["quarantined"]
        parsed = accepted + [item["record"] for item in quarantined]
        root = Path(run_dir)
        _, parsed_sha, _ = atomic_jsonl(root / "parsed/records.jsonl", parsed)
        _, normalized_sha, _ = atomic_jsonl(root / "normalized/records.jsonl", accepted)
        atomic_jsonl(root / "quarantined/records.jsonl", quarantined)
        anomalies = Counter(reason for item in quarantined for reason in item["reasons"])
        directory_artifact = artifacts["directory"]
        bundle_digest = hashlib.sha256("".join(f"{role}:{artifacts[role].sha256}\n" for role in sorted(artifacts)).encode()).hexdigest()
        bundle_artifact = SourceArtifact(
            source_url=directory_artifact.source_url,
            retrieved_at_utc=directory_artifact.retrieved_at_utc,
            sha256=bundle_digest,
            byte_size=sum(artifact.byte_size for artifact in artifacts.values()),
            publication_date=directory_artifact.publication_date,
            effective_date=directory_artifact.effective_date,
            code_version=directory_artifact.code_version,
            config_version=directory_artifact.config_version,
            rights_caveat=directory_artifact.rights_caveat,
            privacy_caveat=directory_artifact.privacy_caveat,
            coverage=directory_artifact.coverage,
            redirects=directory_artifact.redirects,
        )
        manifest = private_manifest(
            source_id=self.source_id, adapter_version=self.adapter_version, schema_version=self.schema_version,
            artifact=bundle_artifact, input_rows=result["input_rows"], normalized_rows=len(accepted),
            quarantined_rows=len(quarantined), normalized_sha256=normalized_sha, parsed_sha256=parsed_sha,
            anomaly_counts=dict(sorted(anomalies.items())),
        )
        manifest.update({
            "source_profile": "fsis-mpi-directory-plus-demographics" if demographics is not None else "fsis-mpi-directory-only",
            "schema_fingerprint": result["schema_fingerprint"],
            "demographic_schema_fingerprint": result["demographic_schema_fingerprint"],
            "source_artifacts": {
                role: {"source_url": artifacts[role].source_url, "retrieved_at_utc": artifacts[role].retrieved_at_utc,
                       "sha256": artifacts[role].sha256, "byte_size": artifacts[role].byte_size,
                       "effective_date": artifacts[role].effective_date}
                for role in sorted(artifacts)
            },
            "row_reconciliation": {
                "directory_rows": result["directory_rows"], "demographic_rows": result["demographic_rows"],
                "matched_demographic_rows": result["matched_demographic_rows"],
                "orphan_demographic_rows": result["orphan_demographic_rows"],
                "identity_conflicts": result["identity_conflicts"], "unmatched_demographic_is_not_closure": True,
            },
            "geocoding": "disabled",
            "coverage": "FSIS-regulated meat, poultry, and egg establishments in the captured edition; state-inspection programs and non-FSIS populations excluded",
            "publication_state": "private-candidate",
        })
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(
        self,
        run_dir: str | Path,
        artifact: SourceArtifact,
        *,
        output_dir: str | Path | None = None,
        bundle_artifact: SourceArtifact | None = None,
        source_artifacts: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        root = Path(run_dir)
        rows = [json.loads(line) for line in (root / "normalized/records.jsonl").read_text(encoding="utf-8").splitlines() if line]
        handoff_root = Path(output_dir or root)
        handoff = write_handoff(handoff_root, rows, artifact, source_id=self.source_id, profile="us-fsis-test-only")
        if bundle_artifact is not None or source_artifacts is not None:
            path = handoff_root / "manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["handoff_artifact_role"] = "directory"
            if bundle_artifact is not None:
                manifest["bundle_artifact"] = {
                    "sha256": bundle_artifact.sha256,
                    "byte_size": bundle_artifact.byte_size,
                    "source_url": bundle_artifact.source_url,
                    "retrieved_at_utc": bundle_artifact.retrieved_at_utc,
                }
            if source_artifacts is not None:
                manifest["source_artifacts"] = source_artifacts
            atomic_json(path, manifest)
            handoff.update({key: manifest[key] for key in ("handoff_artifact_role", "bundle_artifact", "source_artifacts") if key in manifest})
        return handoff


def _bytes(value: bytes | str | Path) -> bytes:
    return value if isinstance(value, bytes) else Path(value).read_bytes()
