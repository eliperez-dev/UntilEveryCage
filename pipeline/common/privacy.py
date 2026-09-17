"""Shared conservative privacy signals for restricted source adapters.

These are screening signals, not privacy clearance.  A match blocks the
candidate row; a non-match leaves the row behind the explicit privacy gate.
"""
from __future__ import annotations

import re


# Do not classify ordinary facility names such as ``House Farm`` as private on
# their own.  Stronger residential/intermediary indicators still require a
# human decision before an address or point can be exposed.
ADDRESS_RISK = re.compile(r"\b(flat|apartment|residential|c/o|care\s+of|caravan)\b", re.I)


def address_privacy_risk(*values: object) -> bool:
    """Return whether concatenated source address values need quarantine."""
    return bool(ADDRESS_RISK.search(" ".join(str(value).strip() for value in values if value)))
