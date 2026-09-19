"""Test-only adapter injection for the real worker image.

This module is mounted as ``sitecustomize.py`` only by the disposable Docker
worker acceptance test. The production image has no synthetic provider entry.
"""

import json
import os
import urllib.parse
import urllib.request

from pipeline.geocoding.base import GeocodeOutcome
from pipeline.geocoding import registry


class SyntheticDockerAdapter:
    provider_id = "synthetic-docker"

    def geocode(self, query: str) -> GeocodeOutcome:
        base_url = os.environ["UEC_SYNTHETIC_PROVIDER_URL"]
        request_url = f"{base_url}?{urllib.parse.urlencode({'q': query})}"
        with urllib.request.urlopen(request_url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") != "ok":
            return GeocodeOutcome(
                "failed", "synthetic_failure", None, None, None, None,
                "synthetic_http", False, {"error": "synthetic_failure"},
            )
        return GeocodeOutcome(
            "accepted", "synthetic_point", 55.0, 12.0, "synthetic-point",
            "address_point", "synthetic_http", False, {"source": "synthetic"},
        )


registry.ADAPTER_FACTORIES["synthetic-docker"] = SyntheticDockerAdapter
