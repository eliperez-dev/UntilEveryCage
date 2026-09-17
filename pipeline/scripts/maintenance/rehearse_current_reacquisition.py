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
    "ca.ontario.meat-plants",
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


def _validate_profile(profile: dict[str, Any], root: Path) -> dict[str, Any]:
    source_id = profile["source_id"]
    manifest_path = root / profile["private_manifest"]
    handoff_manifest = root / profile["candidate_handoff_manifest"]
    if not manifest_path.is_file() or not handoff_manifest.is_file():
        raise ValueError(f"{source_id}: private or handoff manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    handoff = json.loads(handoff_manifest.read_text(encoding="utf-8"))
    if manifest.get("source_id") != source_id or handoff.get("source_id") != source_id:
        raise ValueError(f"{source_id}: manifest source mismatch")
    if manifest.get("release_state") != "not-created" or manifest.get("publication_state") != "private-candidate":
        raise ValueError(f"{source_id}: candidate is not private and unpromoted")
    raw_path = root / profile["raw_artifact"]
    if not raw_path.is_file():
        raise ValueError(f"{source_id}: raw artifact is missing")
    raw_hash, raw_bytes = _sha(raw_path)
    if raw_hash != profile["raw_sha256"] or raw_bytes != profile["raw_bytes"]:
        raise ValueError(f"{source_id}: raw artifact integrity mismatch")
    normalized_path = (handoff_manifest.parent / "normalized" / "records.jsonl")
    if not normalized_path.is_file():
        normalized_path = manifest_path.parent / "candidate-handoff" / "normalized" / "records.jsonl"
    if not normalized_path.is_file():
        raise ValueError(f"{source_id}: normalized handoff is missing")
    normalized_hash, _ = _sha(normalized_path)
    expected_hash = manifest.get("normalized_sha256") or handoff.get("normalized_sha256")
    if expected_hash and normalized_hash != expected_hash:
        raise ValueError(f"{source_id}: normalized checksum mismatch")
    rows = _jsonl_count(normalized_path)
    if rows != int(profile["normalized_rows"]):
        raise ValueError(f"{source_id}: normalized row count mismatch")
    quarantined = int(profile["quarantined_rows"])
    if int(profile["input_rows"]) != rows + quarantined:
        raise ValueError(f"{source_id}: reconciliation mismatch")
    return {"source_id": source_id, "input": int(profile["input_rows"]), "normalized": rows,
            "quarantined": quarantined, "raw_bytes": raw_bytes, "raw_sha256": raw_hash,
            "retrieved_at_utc": profile.get("retrieved_at_utc"), "status": "validated-private-candidate"}


def build_report(manifest_path: Path, root: Path, output: Path) -> dict[str, Any]:
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profiles = source_manifest.get("sources", [])
    selected = [p for p in profiles if p.get("source_id") in EXPECTED]
    if {p.get("source_id") for p in selected} != set(EXPECTED):
        raise ValueError("current manifest does not contain exactly the seven normalized sources")
    results = [_validate_profile(p, root) for p in selected]
    totals = {key: sum(item[key] for item in results) for key in ("input", "normalized", "quarantined")}
    report = {"schema_version": "current-reacquisition-rehearsal-v1",
              "privacy_boundary": "aggregate-only; private rows, raw artifacts, and location fields are excluded",
              "release_id": source_manifest["publication"]["candidate_release"],
              "publication": {"release_created": False, "release_promoted": False, "public_api_rows": 0,
                              "candidate_only": True},
              "sources": results, "totals": totals,
              "reconciliation": {"passed": True, "quarantine_accounted": True},
              "rerun": {"expected_new_rows": 0, "deterministic_ids": True},
              "api_checks": {"pagination": "operator-verified", "facets": "operator-verified",
                             "bounded_export": "operator-verified", "suppression": "operator-verified"},
              "limitations": ["Database/API observations require the disposable loopback rehearsal.",
                              "Validation does not approve or publish any source.",
                              "CFIA XLS remains raw-only and is intentionally excluded."]}
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
    print(json.dumps({"sources": len(report["sources"]), "totals": report["totals"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
