"""Run a registered Italian 853 snapshot into private candidate staging."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from pipeline.common.orchestrator import run_registered_typed_input
from .it_853_adapter import Italy853Adapter

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("raw", type=Path); parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--url", required=True); parser.add_argument("--retrieved-at-utc", required=True)
    parser.add_argument("--publication-date", required=True)
    args=parser.parse_args(); raw=args.raw.read_bytes(); adapter=Italy853Adapter()
    config={"source_url":args.url,"retrieved_at_utc":args.retrieved_at_utc,"publication_date":args.publication_date,"checksum_sha256":hashlib.sha256(raw).hexdigest(),"byte_size":len(raw),"code_version":adapter.adapter_version,"config_version":adapter.schema_version,"source_id":adapter.source_id,"terms_status":"pending_confirmation"}
    status=run_registered_typed_input(args.raw,args.runs,config,adapter)
    print(json.dumps({"status":status["status"],"run_dir":status["run_dir"],"input_rows":status["manifest"]["input_rows"],"normalized_rows":status["manifest"]["normalized_rows"],"quarantined_rows":status["manifest"]["quarantined_rows"]},sort_keys=True))
    return 0 if status["status"] in {"candidate-ready","staged-restricted"} else 1
if __name__=="__main__": raise SystemExit(main())
