"""Source-owned entry point for the Denmark vertical slice."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.sources.denmark.pipeline import main


if __name__ == "__main__":
    raise SystemExit(main())
