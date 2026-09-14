"""Compatibility wrapper; shared coordination lives in ``pipeline/common``."""

from __future__ import annotations

try:
    from .adapter import run as _germany_adapter
    from common.orchestrator import register_input
    from common.orchestrator import run_registered_input as _run_registered_input
except ImportError:  # direct test invocation from this directory
    from adapter import run as _germany_adapter
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from common.orchestrator import register_input
    from common.orchestrator import run_registered_input as _run_registered_input


def run_registered_input(raw_path, runs_dir, config, prior_eligible_release=None, suppressed_ids=None, adapter_runner=None):
    return _run_registered_input(raw_path, runs_dir, config, prior_eligible_release, suppressed_ids, adapter_runner or _germany_adapter)
