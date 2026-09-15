#!/usr/bin/env python3
"""Compatibility shim for Denmark's source-owned staging runner."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.sources.denmark import pipeline as _canonical

# Existing tests and operator scripts may patch these names. Real behavior
# lives in the source-owned module so Denmark has one canonical implementation.
run_stage = _canonical.run_stage
artifact_manifest = _canonical.artifact_manifest


def main() -> int:
    return _canonical.main(run_stage_fn=run_stage, artifact_manifest_fn=artifact_manifest)


if __name__ == "__main__":
    raise SystemExit(main())
