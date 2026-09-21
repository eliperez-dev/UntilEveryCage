"""Run the private US legacy V2 and accountability-graph rehearsal."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.sources.us.accountability.adapter import UsAccountabilityAdapter
from pipeline.sources.us.real_rehearsal import (
    APHIS_ROUTE,
    FSIS_ROUTE,
    build_ledger_rows,
    row_free_metrics,
    write_ledger,
)


def _artifact(path: Path, url: str, code: str, schema: str) -> SourceArtifact:
    raw = path.read_bytes()
    return SourceArtifact(
        source_url=url,
        retrieved_at_utc="2026-09-17T00:00:00Z",
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        effective_date="unknown",
        code_version=code,
        config_version=schema,
        rights_caveat="Legacy snapshot; source terms and field-level publication review remain open",
        privacy_caveat="Private staging; addresses, coordinates, contacts, and names require review",
        coverage="Legacy V1 snapshot only; not a current-source claim",
    )


def run(*, root: Path, output: Path, private_dir: Path) -> dict:
    fsis = root / "static_data/us/locations.csv"
    inspections = root / "static_data/us/inspection_reports.csv"
    annual = root / "static_data/us/aphis_data_final.csv"
    for path in (fsis, inspections, annual):
        if not path.is_file():
            raise ValueError(f"missing US legacy input: {path}")

    from pipeline.sources.us.fsis.adapter import FsisMpiAdapter
    from pipeline.sources.us.aphis.adapter import AphisPublicSearchAdapter

    lifecycle = {}
    for name, path, adapter, url in (
        ("fsis-locations", fsis, FsisMpiAdapter(), FSIS_ROUTE),
        ("aphis-inspections", inspections, AphisPublicSearchAdapter(), APHIS_ROUTE),
        ("aphis-annual-reports", annual, AphisPublicSearchAdapter(), APHIS_ROUTE),
    ):
        run_dir = private_dir / "v2" / name
        lifecycle[name] = run_private_lifecycle(path, run_dir, _artifact(path, url, adapter.adapter_version, adapter.schema_version), adapter, health_as_of_utc="2026-09-17T00:00:00Z")

    ledger_rows, skipped = build_ledger_rows(
        __import__("csv").DictReader(fsis.open(newline="", encoding="utf-8-sig")),
        __import__("csv").DictReader(inspections.open(newline="", encoding="utf-8-sig")),
        __import__("csv").DictReader(annual.open(newline="", encoding="utf-8-sig")),
    )
    ledger = private_dir / "graph" / "link-ledger.csv"
    write_ledger(ledger, ledger_rows)
    graph = UsAccountabilityAdapter(reference_date=datetime(2026, 9, 15, tzinfo=timezone.utc).date()).run(
        ledger, private_dir / "graph" / "candidate", _artifact(ledger, "https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory", "us-accountability-real-rehearsal-v1", "us-accountability-real-rehearsal-v1")
    )
    report = row_free_metrics(fsis_path=fsis, inspection_path=inspections, annual_path=annual, ledger_rows=ledger_rows, skipped=skipped)
    report["lifecycle"] = {
        name: {key: value for key, value in status.get("manifest", {}).items() if key in {"source_id", "input_rows", "normalized_rows", "quarantined_rows", "sha256", "schema_fingerprint", "release_state", "publication_state", "review_state", "privacy_gate", "coordinate_gate"}}
        | {"status": status.get("status"), "candidate_created": status.get("candidate_created", False)}
        for name, status in lifecycle.items()
    }
    report["graph"]["accepted_relationships"] = graph["relationship_rows"]
    report["graph"]["quarantined_relationships"] = graph["quarantined_relationship_rows"]
    report["graph"]["accepted_relationship_counts"] = graph["relationship_types"]
    report["graph"]["quarantine_reason_counts"] = graph["anomaly_counts"]
    report["graph"]["graph_manifest_sha256"] = hashlib.sha256(json.dumps(graph, sort_keys=True, default=list).encode()).hexdigest()
    report["generated_at_utc"] = "2026-09-17T00:00:00Z"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path)
    args = parser.parse_args()
    private_dir = args.private_dir or Path(tempfile.mkdtemp(prefix="uec-us-real-graph-"))
    report = run(root=args.root, output=args.output, private_dir=private_dir)
    print(json.dumps({"input_rows": sum(report["strata"].values()), "ledger_rows": report["graph"]["ledger_input_rows"], "accepted_relationships": report["graph"]["accepted_relationships"], "quarantined_relationships": report["graph"]["quarantined_relationships"], "publication_eligibility": report["publication_eligibility"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
