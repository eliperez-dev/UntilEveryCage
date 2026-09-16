"""Private FSIS refresh with a sanctioned assisted-acquisition boundary."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from pipeline.common.acquisition import AcquisitionError, fetch_source, utc_now
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json
from .adapter import CONFIG, FsisMpiAdapter

def assisted_capture_contract(*, source_url: str = CONFIG["directory_url"]) -> dict:
    return {"source_id": CONFIG["source_id"], "method": "operator-assisted-official-export", "steps": ["Open the official FSIS MPI Directory page in an authorized browser session.", "Select the current downloadable MPI Directory and Establishment Demographic CSV files shown on that page.", "Save the files without editing them; record the displayed edition/publication date and the final download URLs.", "Place the selected directory CSV at the --raw path or use --fetch only when a terms-reviewed direct URL is authorized.", "Run dry-run first and review schema, count, duplicate, privacy, and category results before any test-only handoff."], "controls": ["No credential or access-control bypass", "HTML, login, 403, and schema-drift responses fail closed", "No raw artifact in Git", "FSIS facility evidence is not joined to APHIS rows"], "source_url": source_url}

def _local_facts(path: Path, *, retrieved_at_utc: str, effective_date: str | None) -> dict:
    raw = path.read_bytes()
    return {"acquisition_method": "preserved_local_artifact", "source_id": CONFIG["source_id"], "artifact": path.name, "artifact_path": str(path), "requested_url": CONFIG["directory_url"], "final_url": CONFIG["directory_url"], "retrieved_at_utc": retrieved_at_utc, "effective_date": effective_date or "unknown", "publication_date": None, "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "code_version": CONFIG["adapter_version"], "config_version": CONFIG["contract_version"], "rights_caveat": "FSIS source terms and attribution require operator review before publication", "privacy_caveat": "private staging; address, phone, DUNS, and coordinate review pending", "coverage": "FSIS MPI edition only; state-inspection and APHIS populations excluded", "terms_review": "required before network acquisition or handoff"}

def refresh(*, run_dir: str | Path, raw_path: str | Path | None = None, fetch: bool = False, source_url: str = CONFIG["directory_url"], terms_review_path: str | Path | None = None, retrieved_at_utc: str | None = None, effective_date: str | None = None, mode: str = "dry-run", max_bytes: int = 128 * 1024 * 1024) -> dict:
    if fetch == (raw_path is not None): raise ValueError("specify exactly one of raw_path or fetch")
    if mode not in {"dry-run", "handoff"}: raise ValueError("mode must be dry-run or handoff")
    root = Path(run_dir)
    if fetch:
        if terms_review_path is None: raise ValueError("terms_review_path is required for network acquisition")
        try: acquisition = fetch_source(source_id=CONFIG["source_id"], url=source_url, output_root=root / "acquisition", artifact_name="source.csv", terms_review_path=terms_review_path, max_bytes=max_bytes, allowed_content_types=("text/csv", "application/csv", "application/octet-stream"), code_version=CONFIG["adapter_version"], config_version=CONFIG["contract_version"], coverage="FSIS MPI edition only; state-inspection and APHIS populations excluded", rights_caveat="terms review retained with run", privacy_caveat="private staging; privacy review pending", effective_date=effective_date)
        except AcquisitionError as exc: raise ValueError(str(exc)) from exc
        path = Path(acquisition["artifact_path"])
    else:
        path = Path(raw_path)  # type: ignore[arg-type]
        if not path.is_file(): raise ValueError(f"raw artifact does not exist: {path}")
        acquisition = _local_facts(path, retrieved_at_utc=retrieved_at_utc or utc_now(), effective_date=effective_date)
    raw = path.read_bytes(); acquired_at = acquisition.get("retrieved_at_utc") or retrieved_at_utc or utc_now()
    artifact = SourceArtifact(source_url=str(acquisition.get("final_url") or source_url), retrieved_at_utc=str(acquired_at), sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), publication_date=acquisition.get("publication_date"), effective_date=acquisition.get("effective_date") or effective_date, code_version=CONFIG["adapter_version"], config_version=CONFIG["contract_version"], rights_caveat=acquisition.get("rights_caveat"), privacy_caveat=acquisition.get("privacy_caveat"), coverage=acquisition.get("coverage"), redirects=tuple(acquisition.get("redirects") or ()))
    atomic_json(root / "acquisition-metadata.json", acquisition)
    status = run_private_lifecycle(path, root, artifact, FsisMpiAdapter(), health_as_of_utc=str(acquired_at))
    if mode == "handoff" and status.get("status") in {"candidate-ready", "success"}:
        lifecycle_run = Path(status["run_dir"])
        status["handoff"] = FsisMpiAdapter().write_candidate_handoff(lifecycle_run, artifact, output_dir=lifecycle_run / "handoff")
    status["mode"] = mode
    if status.get("run_dir"):
        atomic_json(Path(status["run_dir"]) / "run-status.json", status)
    status["assisted_capture_contract"] = assisted_capture_contract(source_url=source_url); atomic_json(root / "assisted-capture-contract.json", status["assisted_capture_contract"])
    return status

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); source = parser.add_mutually_exclusive_group(required=True); source.add_argument("--raw", type=Path); source.add_argument("--fetch", action="store_true")
    parser.add_argument("--run-dir", type=Path, required=True); parser.add_argument("--source-url", default=CONFIG["directory_url"]); parser.add_argument("--terms-review", type=Path); parser.add_argument("--retrieved-at-utc"); parser.add_argument("--effective-date"); parser.add_argument("--mode", choices=("dry-run", "handoff"), default="dry-run"); parser.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024); args = parser.parse_args()
    try: result = refresh(run_dir=args.run_dir, raw_path=args.raw, fetch=args.fetch, source_url=args.source_url, terms_review_path=args.terms_review, retrieved_at_utc=args.retrieved_at_utc, effective_date=args.effective_date, mode=args.mode, max_bytes=args.max_bytes)
    except (OSError, ValueError) as exc: print(json.dumps({"status": "failed", "error": str(exc)})); return 2
    print(json.dumps({"status": result.get("status"), "run_dir": result.get("run_dir"), "manifest": result.get("manifest", {}).get("source_id")}, sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
