"""Geoapify adapter for bounded, private AU address enrichment.

The API key is read from the environment and is never included in outcomes,
logs, exceptions, or checked-in configuration. Provider matches are retained as
Country filtering is explicit and IP-derived bias is disabled. The confidence
threshold is a conservative project heuristic, not a probability or review.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from math import isfinite
import re
from typing import Callable

from .base import GeocodeOutcome


class GeoapifyAdapter:
    provider_id = "geoapify"
    minimum_rank_confidence = 0.90

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 20,
        opener: Callable = urllib.request.urlopen,
        *,
        country_code: str | None = None,
        pilot_auto_display: bool = False,
    ):
        self.api_key = (api_key or os.environ.get("GEOAPIFY_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("GEOAPIFY_API_KEY is required")
        if country_code is not None and (len(country_code) != 2 or not country_code.isalpha() or not country_code.islower()):
            raise ValueError("country_code must be a lowercase ISO alpha-2 code")
        if pilot_auto_display and country_code != "au":
            raise ValueError("automatic preview display is only configured for the AU pilot")
        self.country_code = country_code
        self.pilot_auto_display = pilot_auto_display
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
        params = {
            "text": query,
            "format": "geojson",
            "limit": 2,
            "apiKey": self.api_key,
        }
        if self.country_code:
            params["filter"] = f"countrycode:{self.country_code}"
            params["bias"] = "countrycode:none"
        params = urllib.parse.urlencode(params)
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
        if self.pilot_auto_display and len(features) != 1:
            return GeocodeOutcome(
                "review_required", "ambiguous_multiple_results", None, None,
                None, None, "geoapify_forward", False,
                {"result_count": len(features)},
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

        if self.pilot_auto_display and str(properties.get("country_code", "")).lower() != self.country_code:
            return GeocodeOutcome(
                "review_required", "country_mismatch", None, None,
                None, None, "geoapify_forward", False,
                {"error": "country_mismatch"},
            )

        rank = properties.get("rank")
        rank = rank if isinstance(rank, dict) else {}
        confidence = rank.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not isfinite(confidence):
            confidence = None
        result_type = properties.get("result_type")
        precision = result_type if isinstance(result_type, str) else "unknown"
        place_id = properties.get("place_id")
        if not isinstance(place_id, str):
            place_id = None

        if not self.pilot_auto_display:
            acceptance = "review_multiple_points" if len(features) > 1 else "review_provider_candidate"
            return GeocodeOutcome(
                "review_required", acceptance, float(latitude), float(longitude),
                place_id, precision, "geoapify_forward", False, payload,
            )

        query_parts = [self._normalize(part) for part in query.split(",") if self._normalize(part)]
        address_line = properties.get("address_line1")
        street = properties.get("street")
        house_number = properties.get("housenumber")
        normalized_address = self._normalize(address_line) if isinstance(address_line, str) else ""
        if not normalized_address and isinstance(street, str) and isinstance(house_number, (str, int)):
            normalized_address = self._normalize(f"{house_number} {street}")
        if (
            result_type in {"building", "amenity"}
            and confidence is not None
            and confidence >= self.minimum_rank_confidence
            and query_parts
            and normalized_address == query_parts[0]
        ):
            return GeocodeOutcome(
                "accepted", "high_confidence_address_match", float(latitude), float(longitude),
                place_id, "geoapify_address_point", "geoapify_forward", False, payload,
            )

        locality = properties.get("city")
        locality = self._normalize(locality) if isinstance(locality, str) else ""
        if (
            result_type == "city"
            and confidence is not None
            and confidence >= self.minimum_rank_confidence
            and locality
            and locality in query_parts[1:]
        ):
            return GeocodeOutcome(
                "accepted", "approximate_locality_match", float(latitude), float(longitude),
                place_id, "geoapify_locality_point", "geoapify_forward", False, payload,
            )

        return GeocodeOutcome(
            "review_required", "address_or_locality_match_not_supported", None, None,
            None, precision, "geoapify_forward", False,
            {"error": "address_or_locality_match_not_supported"},
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())
