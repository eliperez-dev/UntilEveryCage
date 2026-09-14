"""Compatibility shim for the Denmark source-owned stage."""
from pathlib import Path
_TARGET = Path(__file__).resolve().parents[2] / "sources/denmark/stages/normalize-denmark-smiley.py"
exec(compile(_TARGET.read_text(encoding="utf-8"), str(_TARGET), "exec"), globals(), globals())
