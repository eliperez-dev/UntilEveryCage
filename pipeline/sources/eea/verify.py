"""Compatibility entrypoint for EEA's shared spatial-source acceptance."""
from pipeline.common.source_acceptance import check, run, validate_target

__all__ = ["check", "run", "validate_target"]
