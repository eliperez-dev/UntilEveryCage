"""Acquire and stage one Italian 853/2004 snapshot privately.

The command ends at the shared lifecycle's candidate-ready boundary. Database
candidate import and guarded API checks remain explicit, separate commands.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json

from .acquire import CATALOG_URL, DEFAULT_MAX_BYTES, fetch
from .it_853_adapter import Italy853Adapter


REVIEW_BLOCKERS = {
    "terms": ["Italian Open Data Licence v2.0 is indicated by the Ministry catalogue; licence/attribution and project redistribution review remain open."],
    "privacy": ["Address, tax identifiers, and precise source coordinates stay in restricted source evidence; privacy classification and coordinate precision review are pending."],
    "completeness": ["The run covers the 853/2004 Ministry CSV only; the separate 1069/2009 by-products dataset is intentionally excluded and no national completeness claim is made."],
    "classification": ["Recognition number plus activity code is the provisional identity; repeated recognition/activity pairs quarantine, and source classification/activity text is preserved without collapsing categories."],
    "coverage": ["Catalog filename/publication date are recorded when supplied, but row-level effective dates and coded category coverage require review."],
}


def _metadata_for_local(raw_path: Path, metadata: dict, *, url: str, retrieved_at: str | None, adapter: Italy853Adapter) -> dict:
    import hashlib

    raw = raw_path.read_bytes()
    return {
        "source_id": adapter.source_id,
        "source_url": next((value for value in (metadata.get("final_url"), metadata.get("requested_url"), url) if value and value != "unknown"), url),
        "retrieved_at_utc": metadata.get("retrieved_at_utc") or retrieved_at,
        "checksum_sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "publication_date": (metadata.get("publication_metadata") or {}).get("catalog_last_updated") or metadata.get("filename_publication_date"),
        "effective_date": metadata.get("effective_date"),
        "code_version": adapter.adapter_version,
        "config_version": adapter.schema_version,
        "rights_caveat": "Italian Open Data Licence v2.0; terms evidence retained in acquisition metadata; publication review remains separate",
        "privacy_caveat": "restricted private staging; address, tax, and coordinate exposure pending privacy review",
        "coverage": "Italian Ministry 853/2004 CSV only; separate 1069/2009 by-products dataset excluded",
    }


def refresh(
    *,
    run_dir: str | Path,
    raw_path: str | Path | None = None,
    fetch_source: bool = False,
    catalog_url: str = CATALOG_URL,
    output_root: str | Path = "data/raw",
    run_id: str | None = None,
    terms_review: str | Path | None = None,
    retrieved_at_utc: str | None = None,
    timeout_seconds: float = 60.0,
    max_bytes: int = DEFAULT_MAX_BYTES,
    previous_normalized: str | Path | None = None,
) -> dict:
    """Run the shared private lifecycle from a preserved or acquired artifact."""
    if fetch_source == (raw_path is not None):
        raise ValueError("specify exactly one of raw_path or fetch_source")
    adapter = Italy853Adapter()
    raw_root = Path(output_root)
    if fetch_source:
        if terms_review is None:
            raise ValueError("terms_review is required for network acquisition")
        metadata = fetch(output_root=raw_root, run_id=run_id or "manual", terms_review_path=Path(terms_review),
                         catalog_url=catalog_url, timeout_seconds=timeout_seconds, max_bytes=max_bytes)
        input_path = raw_root / adapter.source_id / (run_id or "manual") / metadata["artifact"]
    else:
        input_path = Path(raw_path).resolve()  # type: ignore[arg-type]
        sidecar = input_path.parent / "acquisition-metadata.json"
        metadata = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else {}
    if not input_path.is_file():
        raise ValueError(f"raw artifact does not exist: {input_path}")
    facts = _metadata_for_local(input_path, metadata, url=catalog_url, retrieved_at=retrieved_at_utc, adapter=adapter)
    if not facts["retrieved_at_utc"]:
        raise ValueError("retrieved_at_utc is required for private health evidence")
    artifact = SourceArtifact(
        source_url=str(facts["source_url"]), retrieved_at_utc=str(facts["retrieved_at_utc"]),
        sha256=str(facts["checksum_sha256"]), byte_size=int(facts["byte_size"]),
        publication_date=facts.get("publication_date"), effective_date=facts.get("effective_date"),
        code_version=str(facts["code_version"]), config_version=str(facts["config_version"]),
        rights_caveat=facts["rights_caveat"], privacy_caveat=facts["privacy_caveat"], coverage=facts["coverage"],
    )
    status = run_private_lifecycle(input_path, run_dir, artifact, adapter, previous_normalized_path=previous_normalized, review_blockers=REVIEW_BLOCKERS)
    # Keep catalog/response/terms evidence beside the lifecycle run without
    # copying row payloads into QA, health, or API-shaped artifacts.
    if metadata:
        atomic_json(Path(run_dir) / "acquisition-metadata.json", metadata)
    status["acquisition"] = metadata
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw", type=Path)
    source.add_argument("--fetch", action="store_true")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--catalog-url", default=CATALOG_URL)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--run-id")
    parser.add_argument("--terms-review", type=Path)
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--previous-normalized", type=Path)
    args = parser.parse_args()
    try:
        status = refresh(run_dir=args.run_dir, raw_path=args.raw, fetch_source=args.fetch,
                         catalog_url=args.catalog_url, output_root=args.output_root, run_id=args.run_id,
                         terms_review=args.terms_review, retrieved_at_utc=args.retrieved_at_utc,
                         timeout_seconds=args.timeout_seconds, max_bytes=args.max_bytes,
                         previous_normalized=args.previous_normalized)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": status["status"], "run_dir": status["run_dir"],
                      "input_rows": status.get("manifest", {}).get("input_rows"),
                      "normalized_rows": status.get("manifest", {}).get("normalized_rows"),
                      "quarantined_rows": status.get("manifest", {}).get("quarantined_rows")}, sort_keys=True))
    return 0 if status["status"] in {"candidate-ready", "staged-restricted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
