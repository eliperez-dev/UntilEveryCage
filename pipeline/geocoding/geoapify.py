"""Geoapify adapter for private, review-gated background geocoding.

The API key is read from the environment and is never included in outcomes,
logs, exceptions, or checked-in configuration. Provider matches are retained as
review-required evidence; a successful request is not publication approval.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from math import isfinite
from typing import Callable

from .base import GeocodeOutcome


class GeoapifyAdapter:
    provider_id = "geoapify"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 20,
        opener: Callable = urllib.request.urlopen,
    ):
        self.api_key = (api_key or os.environ.get("GEOAPIFY_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("GEOAPIFY_API_KEY is required")
        self.timeout = timeout
        self.opener = opener

    @staticmethod
    def _failed(reason: str, retryable: bool) -> GeocodeOutcome:
        return GeocodeOutcome(
            "failed", "unresolved", None, None, None, None,
            "geoapify_forward", retryable, {"error": reason},
        )

    def geocode(self, query: str) -> GeocodeOutcome:
        query = query.strip()
        if not query:
            return self._failed("empty_query", False)
        params = urllib.parse.urlencode({"text": query, "format": "geojson", "limit": 2, "apiKey": self.api_key})
        request = urllib.request.Request(
            "https://api.geoapify.com/v1/geocode/search?" + params,
            headers={"User-Agent": "UntilEveryCage/2 geocoding-worker"},
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                return self._failed("authentication_rejected", False)
            if error.code == 429:
                return self._failed("provider_rate_limited", True)
            return self._failed("provider_http_error", 500 <= error.code < 600)
        except (OSError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            return self._failed("provider_transport_or_payload_error", True)

        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            return self._failed("invalid_provider_schema", False)
        features = payload["features"]
        if not features:
            return GeocodeOutcome(
                "unresolved", "unresolved", None, None, None, None,
                "geoapify_forward", False, payload,
            )
        feature = features[0]
        if not isinstance(feature, dict):
            return self._failed("invalid_provider_feature", False)
        geometry = feature.get("geometry")
        properties = feature.get("properties")
        if not isinstance(geometry, dict) or not isinstance(properties, dict):
            return self._failed("invalid_provider_feature", False)
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            return self._failed("invalid_provider_coordinates", False)
        longitude, latitude = coordinates
        if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
            return self._failed("invalid_provider_coordinates", False)
        if not isfinite(longitude) or not isfinite(latitude) or not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
            return self._failed("invalid_provider_coordinates", False)

        result_type = properties.get("result_type")
        precision = result_type if isinstance(result_type, str) else "unknown"
        place_id = properties.get("place_id")
        if not isinstance(place_id, str):
            place_id = None
        acceptance = "review_multiple_points" if len(features) > 1 else "review_provider_candidate"
        return GeocodeOutcome(
            "review_required", acceptance, float(latitude), float(longitude),
            place_id, precision, "geoapify_forward", False, payload,
        )
