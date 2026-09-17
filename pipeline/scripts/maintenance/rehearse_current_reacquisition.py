"""Validate and summarize the current-source private candidate handoff set.

This command never copies rows into the repository.  It reads ignored private
handoffs, verifies their raw and normalized checksums, and writes a row-free
aggregate report suitable for checked-in evidence.  Database/API stages are
reported as operator-supplied observations; this command does not connect to
or promote a release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED = (
    "dk.smiley", "it.853-2004", "fr.dgal.section-i", "fr.dgal.section-ii",
    "fsa_approved_establishments", "fss_approved_establishments",
    "ca.ontario.meat-plants", "ca.cfia.federal-meat",
)
FORBIDDEN_KEYS = {"source_values", "address", "coordinates", "raw_fields", "trading_name", "establishment_id"}


def _sha(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk); size += len(chunk)
    return digest.hexdigest(), size


def _jsonl_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _resolve(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def _missing_result(profile: dict[str, Any], errors: list[str], missing: list[str], *, status: str) -> dict[str, Any]:
    return {
        "source_id": profile["source_id"],
        "status": status,
        "input": profile.get("input_rows"),
        "normalized": profile.get("normalized_rows"),
        "quarantined": profile.get("quarantined_rows"),
        "errors": errors,
        "missing_artifacts": missing,
    }


def _validate_profile(profile: dict[str, Any], root: Path) -> dict[str, Any]:
    source_id = profile["source_id"]
    missing: list[str] = []
    raw_only = profile.get("normalized_rows") is None
    manifest_path = _resolve(root, profile.get("private_manifest"))
    handoff_manifest = _resolve(root, profile.get("candidate_handoff_manifest"))
    if manifest_path is None or not manifest_path.is_file():
        missing.append(str(profile.get("private_manifest") or "private_manifest"))
    if not raw_only and (handoff_manifest is None or not handoff_manifest.is_file()):
        missing.append(str(profile.get("candidate_handoff_manifest") or "candidate_handoff_manifest"))
    raw_path = _resolve(root, profile.get("raw_artifact"))
    if raw_path is None or not raw_path.is_file():
        missing.append(str(profile.get("raw_artifact") or "raw_artifact"))

    if raw_only:
        if missing:
            return _missing_result(profile, ["raw-only artifact is unavailable locally"], missing, status="unavailable_raw_only")
        raw_hash, raw_bytes = _sha(raw_path)
        if raw_hash != profile.get("raw_sha256") or raw_bytes != profile.get("raw_bytes"):
            return _missing_result(profile, ["raw artifact integrity mismatch"], [], status="raw_only_integrity_error")
        return {
            "source_id": source_id, "status": "validated-raw-only", "input": None,
            "normalized": None, "quarantined": None, "raw_bytes": raw_bytes,
            "raw_sha256": raw_hash, "errors": [], "missing_artifacts": [],
        }

    if missing:
        return _missing_result(profile, ["private normalized handoff is unavailable locally"], missing, status="unavailable_private_handoff")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    handoff = json.loads(handoff_manifest.read_text(encoding="utf-8"))
    if manifest.get("source_id") != source_id or handoff.get("source_id") != source_id:
        raise ValueError(f"{source_id}: manifest source mismatch")
    if manifest.get("release_state") != "not-created" or manifest.get("publication_state") != "private-candidate":
        raise ValueError(f"{source_id}: candidate is not private and unpromoted")
    raw_hash, raw_bytes = _sha(raw_path)
    if raw_hash != profile["raw_sha256"] or raw_bytes != profile["raw_bytes"]:
        raise ValueError(f"{source_id}: raw artifact integrity mismatch")
    normalized_path = (handoff_manifest.parent / "normalized" / "records.jsonl")
    if not normalized_path.is_file():
        normalized_path = manifest_path.parent / "candidate-handoff" / "normalized" / "records.jsonl"
    if not normalized_path.is_file():
        raise ValueError(f"{source_id}: normalized handoff is missing")
    normalized_hash, _ = _sha(normalized_path)
    expected_hash = handoff.get("normalized_sha256")
    if expected_hash and normalized_hash != expected_hash:
        raise ValueError(f"{source_id}: normalized checksum mismatch")
    rows = _jsonl_count(normalized_path)
    if rows != int(profile["normalized_rows"]):
        raise ValueError(f"{source_id}: normalized row count mismatch")
    quarantined = int(profile["quarantined_rows"])
    if int(profile["input_rows"]) != rows + quarantined:
        raise ValueError(f"{source_id}: reconciliation mismatch")
    warnings: list[str] = []
    private_normalized_path = manifest_path.parent / "normalized" / "records.jsonl"
    private_stage = "not-declared"
    private_hash = manifest.get("normalized_sha256")
    if private_hash:
        if private_normalized_path.is_file():
            private_actual, _ = _sha(private_normalized_path)
            if private_actual != private_hash:
                raise ValueError(f"{source_id}: private normalized checksum mismatch")
            private_stage = "verified"
        else:
            private_stage = "artifact-not-retained"
            warnings.append("private-stage normalized artifact is not retained locally; candidate handoff verified separately")
    return {"source_id": source_id, "input": int(profile["input_rows"]), "normalized": rows,
            "quarantined": quarantined, "raw_bytes": raw_bytes, "raw_sha256": raw_hash,
            "retrieved_at_utc": profile.get("retrieved_at_utc"), "status": "validated-private-candidate",
            "handoff_sha256": normalized_hash, "private_stage": private_stage,
            "warnings": warnings, "errors": [], "missing_artifacts": []}


def build_report(manifest_path: Path, root: Path, output: Path) -> dict[str, Any]:
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profiles = source_manifest.get("sources", [])
    selected = [p for p in profiles if p.get("source_id") in EXPECTED]
    if {p.get("source_id") for p in selected} != set(EXPECTED):
        raise ValueError("current manifest does not contain exactly the seven normalized sources plus the CFIA raw-only profile")
    results = []
    for profile in selected:
        try:
            results.append(_validate_profile(profile, root))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            results.append(_missing_result(profile, [str(exc)], [], status="validation_error"))
    complete = [item for item in results if item["status"] == "validated-private-candidate"]
    totals = {key: sum(int(item[key]) for item in complete) for key in ("input", "normalized", "quarantined")}
    unavailable = [item["source_id"] for item in results if item["status"] in {"unavailable_private_handoff", "unavailable_raw_only"}]
    raw_only = [item["source_id"] for item in results if item["status"] == "validated-raw-only"]
    failed = [item["source_id"] for item in results if item["status"] not in {"validated-private-candidate", "validated-raw-only", "unavailable_private_handoff", "unavailable_raw_only"}]
    passed = not unavailable and not failed and len(complete) == len(EXPECTED) - 1
    report = {"schema_version": "current-reacquisition-rehearsal-v1",
              "privacy_boundary": "aggregate-only; private rows, raw artifacts, and location fields are excluded",
              "release_id": source_manifest["publication"]["candidate_release"],
              "publication": {"release_created": False, "release_promoted": False, "public_api_rows": 0,
                              "candidate_only": True},
              "sources": results, "totals": totals,
              "availability": {"expected_profiles": len(EXPECTED), "validated_private_profiles": len(complete),
                               "validated_raw_only_profiles": len(raw_only), "unavailable_profiles": unavailable,
                               "failed_profiles": failed},
              "reconciliation": {"passed": passed, "quarantine_accounted": passed,
                                  "reason": "all required private handoffs must be present and integrity-checked"},
              "rerun": {"status": "not-run; private handoffs unavailable" if not passed else "operator-required",
                        "expected_new_rows": 0, "deterministic_ids": True},
              "api_checks": {"status": "not-run; private handoffs unavailable" if not passed else "operator-required",
                             "pagination": "not-run", "facets": "not-run",
                             "bounded_export": "not-run", "suppression": "not-run"},
              "limitations": ["Database/API observations require the disposable loopback rehearsal.",
                              "Validation does not approve or publish any source.",
                              "CFIA XLS remains raw-only and is intentionally excluded.",
                              "Missing private artifacts are reported as unavailable, never as zero rows."]}
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if any(key in text for key in FORBIDDEN_KEYS):
        raise ValueError("row-bearing key leaked into aggregate report")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/current-reacquisition-2026-09-16.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.manifest, args.root, args.output)
    print(json.dumps({"sources": len(report["sources"]), "totals": report["totals"],
                      "reconciliation_passed": report["reconciliation"]["passed"],
                      "unavailable": report["availability"]["unavailable_profiles"],
                      "output": str(args.output)}, sort_keys=True))
    return 0 if report["reconciliation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
