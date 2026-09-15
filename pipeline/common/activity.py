"""Deterministic, non-geocoding activity classification shared by UK adapters."""
from __future__ import annotations

import re
from collections.abc import Iterable


_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("slaughter", ("slaughter", "abattoir", "killing")),
    ("cutting", ("cutting", "butchery", "deboning")),
    ("processing", ("processing", "meat product", "minced", "preparation", "manufactur")),
    ("logistics_and_storage", ("cold store", "cold-store", "coldstorage", "storage", "warehouse", "freezer", "refrigerat")),
)


def classify_activities(values: Iterable[str | None]) -> tuple[str, ...]:
    """Return stable API categories while leaving original activity text intact."""
    categories: list[str] = []
    for value in values:
        if not value:
            continue
        text = re.sub(r"\s+", " ", value).strip().casefold()
        # The FSA/FSS exports use these short activity codes in some monthly
        # snapshots.  Keep the raw code in source_values; this is only the
        # stable project interpretation used by candidate/API plumbing.
        aliases = {"sh": "slaughter", "cp": "cutting", "mp": "processing", "cs": "logistics_and_storage"}
        if text in aliases and aliases[text] not in categories:
            categories.append(aliases[text])
            continue
        if re.search(r"\bSH\s*\(", value, re.I) and "slaughter" not in categories:
            categories.append("slaughter")
        if re.search(r"\bCP\s*\(", value, re.I) and "cutting" not in categories:
            categories.append("cutting")
        if re.search(r"\b(?:PP|MP|MM|RPM|MMP)\s*\(", value, re.I) and "processing" not in categories:
            categories.append("processing")
        if re.search(r"\bCS\s*\(", value, re.I) and "logistics_and_storage" not in categories:
            categories.append("logistics_and_storage")
        for category, needles in _RULES:
            if any(needle in text for needle in needles) and category not in categories:
                categories.append(category)
    return tuple(categories)
