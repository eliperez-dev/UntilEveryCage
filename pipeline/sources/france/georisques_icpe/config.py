"""Checked-in source contract loaded from the adjacent JSON configuration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG: dict[str, Any] = json.loads(Path(__file__).with_name("config.json").read_text(encoding="utf-8"))
