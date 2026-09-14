"""Compatibility launcher for Denmark's existing stage implementations."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[3]
LEGACY_STAGES = ROOT / "pipeline" / "scripts" / "stages"
LEGACY_PIPELINE = ROOT / "pipeline"


def run_stage(script_name: str) -> None:
    """Execute a historical stage with unchanged argv semantics."""
    runpy.run_path(str(LEGACY_STAGES / script_name), run_name="__main__")


def main(script_name: str) -> None:
    base = LEGACY_PIPELINE if script_name == "run-denmark-pipeline.py" else LEGACY_STAGES
    script = (base / script_name).resolve()
    if not script.is_file():
        raise FileNotFoundError(script_name)
    runpy.run_path(str(script), run_name="__main__")
