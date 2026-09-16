"""Assisted private refresh for APHIS public-search exports."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.common.acquisition import utc_now
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json
from .adapter import CONFIG, AphisPublicSearchAdapter

def assisted_capture_contract(profile: str) -> dict:
    if profile not in CONFIG["profiles"]: raise ValueError("unsupported APHIS profile")
    urls={"registrations":CONFIG["public_search_url"],"annual_reports":CONFIG["annual_reports_url"],"inspections":CONFIG["inspection_reports_url"]}
    return {"source_id": CONFIG["source_id"], "profile": profile, "method": "operator-assisted-public-search-export", "source_url": urls[profile], "steps": ["Open the APHIS Animal Care Public Search Tool or the documented annual-summary page.", f"Select the {profile.replace('_',' ')} view and use only its documented export/download control.", "Save the export without editing it; retain the query parameters, displayed date/year, and final URL in the run metadata.", "Run dry-run and review profile, schema, duplicate IDs, missing dates, privacy, and coverage before private test-only import."], "boundaries": ["No automation against hidden endpoints or access-control bypass", "Registrations/licenses, annual reports, inspections, laboratories, and aggregate summaries are separate evidence types", "Absence is not closure and an inspection is not a facility-master assertion"]}

def refresh(*, run_dir: str | Path, raw_path: str | Path, profile: str, source_url: str | None = None, retrieved_at_utc: str | None = None, effective_date: str | None = None) -> dict:
    path=Path(raw_path); raw=path.read_bytes(); adapter=AphisPublicSearchAdapter(); metadata={"acquisition_method":"preserved_local_artifact","source_id":CONFIG["source_id"],"profile":profile,"artifact":path.name,"artifact_path":str(path),"requested_url":source_url or CONFIG["public_search_url"],"final_url":source_url or CONFIG["public_search_url"],"retrieved_at_utc":retrieved_at_utc or utc_now(),"effective_date":effective_date or "unknown","sha256":hashlib.sha256(raw).hexdigest(),"byte_size":len(raw),"code_version":adapter.adapter_version,"config_version":adapter.schema_version,"rights_caveat":"APHIS export terms and attribution require operator review","privacy_caveat":"restricted private staging; address and coordinate review pending","coverage":f"APHIS {profile} export only; no facility merge","terms_review":"required before publication"}
    result=adapter.parse_bytes(raw)
    if result["profile"] != profile: raise ValueError(f"captured APHIS profile is {result['profile']}, expected {profile}")
    root=Path(run_dir); atomic_json(root/"acquisition-metadata.json",metadata)
    artifact=SourceArtifact(source_url=metadata["final_url"],retrieved_at_utc=metadata["retrieved_at_utc"],sha256=metadata["sha256"],byte_size=metadata["byte_size"],effective_date=effective_date or "unknown",code_version=adapter.adapter_version,config_version=adapter.schema_version,rights_caveat=metadata["rights_caveat"],privacy_caveat=metadata["privacy_caveat"],coverage=metadata["coverage"])
    status=run_private_lifecycle(path,root,artifact,adapter,health_as_of_utc=metadata["retrieved_at_utc"]); contract=assisted_capture_contract(profile); status["assisted_capture_contract"]=contract; atomic_json(root/"assisted-capture-contract.json",contract); return status

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--raw",type=Path,required=True); parser.add_argument("--run-dir",type=Path,required=True); parser.add_argument("--profile",choices=CONFIG["profiles"],required=True); parser.add_argument("--source-url"); parser.add_argument("--retrieved-at-utc"); parser.add_argument("--effective-date"); args=parser.parse_args()
    try: result=refresh(run_dir=args.run_dir,raw_path=args.raw,profile=args.profile,source_url=args.source_url,retrieved_at_utc=args.retrieved_at_utc,effective_date=args.effective_date)
    except (OSError,ValueError) as exc: print(json.dumps({"status":"failed","error":str(exc)})); return 2
    print(json.dumps({"status":result.get("status"),"run_dir":result.get("run_dir")},sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
