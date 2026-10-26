"""LocationIQ adapter for the German private address matching pilot."""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from math import isfinite
from typing import Callable

from .base import GeocodeOutcome
from .geoapify import GeoapifyAdapter


class LocationIqAdapter:
    provider_id = "locationiq"
    endpoint = "https://eu1.locationiq.com/v1/search"

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    def __init__(self, api_key: str | None = None, timeout: int = 20,
                 opener: Callable = urllib.request.urlopen, *, country_code: str | None = None,
                 private_source_profile: bool = False):
        self.api_key = (api_key or os.environ.get("LOCATIONIQ_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("LOCATIONIQ_API_KEY is required")
        if country_code is not None and (not isinstance(country_code, str) or len(country_code) != 2
                                         or not country_code.isalpha() or country_code != country_code.lower()):
            raise ValueError("country_code must be a lowercase ISO alpha-2 code")
        self.timeout = timeout
        self.opener = opener
        self.country_code = country_code
        self.private_source_profile = private_source_profile

    @staticmethod
    def _normalize(value: str) -> str:
        return GeoapifyAdapter._normalize(value)

    @staticmethod
    def _outcome(status: str, acceptance: str, response: dict, *, lat=None, lon=None,
                 place_id=None, precision=None, retryable=False) -> GeocodeOutcome:
        return GeocodeOutcome(status, acceptance, lat, lon, place_id, precision,
                              "locationiq_forward", retryable, response)

    @staticmethod
    def _parse_query(query: str):
        parts = [part.strip() for part in query.split(",") if part.strip()]
        if len(parts) == 4 and parts[-1].casefold() == "germany" and re.fullmatch(r"\d{5}", parts[1]):
            return parts[0], parts[1], parts[2], ""
        if len(parts) in (3, 4) and parts[-1].casefold() == "germany":
            street, context = parts[:2]
            match = re.fullmatch(r"(\d{5})\s+(.+)", context)
            if not match:
                return None
            return street, match.group(1), match.group(2), parts[2] if len(parts) == 4 else ""
        if len(parts) == 2:
            street, context = parts
            match = re.fullmatch(r"(\d{5})\s+(.+)", context)
            if not match:
                return None
            return street, match.group(1), match.group(2), ""
        if len(parts) == 5 and parts[-1].casefold() == "germany":
            if not re.fullmatch(r"\d{5}", parts[1]):
                return None
            return parts[0], parts[1], parts[2], parts[3]
        return None

    @classmethod
    def _street_matches(cls, source: str, road: str, number: str) -> bool:
        source_n = cls._normalize(source)
        road_n = cls._normalize(road)
        number_n = cls._normalize(number)
        return source_n in {f"{road_n} {number_n}", f"{number_n} {road_n}"}

    @classmethod
    def _candidate(cls, item):
        if not isinstance(item, dict) or not isinstance(item.get("address"), dict):
            return None
        safe = {}
        for key in ("place_id", "lat", "lon", "class", "type", "addresstype", "licence", "license", "attribution"):
            value = item.get(key)
            if key == "place_id" and isinstance(value, str) and len(value) <= 300:
                safe[key] = value
            elif key == "place_id" and isinstance(value, int) and not isinstance(value, bool) and len(str(value)) <= 60:
                safe[key] = value
            elif key in {"lat", "lon"} and isinstance(value, str) and len(value) <= 32:
                safe[key] = value
            elif key not in {"place_id", "lat", "lon"} and isinstance(value, str):
                safe[key] = value[:300]
        address_keys = {"house_number", "road", "postcode", "city", "town", "municipality", "village", "state", "state_code", "country_code"}
        address = {key: (item["address"][key][:300] if isinstance(item["address"][key], str) else item["address"][key])
                   for key in address_keys if isinstance(item["address"].get(key), (str, int))
                   and not isinstance(item["address"].get(key), bool)}
        safe["address"] = address
        # Coordinates are retained only in their original string form after strict validation.
        if "lat" not in safe or "lon" not in safe:
            return safe, None
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            return safe, None
        if not isfinite(lat) or not isfinite(lon) or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return safe, None
        return safe, (lat, lon)

    def geocode(self, query: str) -> GeocodeOutcome:
        query = query.strip() if isinstance(query, str) else ""
        if not query:
            return self._outcome("unresolved", "empty_query", {"error": "empty_query"})
        if len(query) > 1000:
            return self._outcome("review_required", "invalid_source_address", {"error": "invalid_source_address"})
        parsed = self._parse_query(query)
        if parsed is None:
            return self._outcome("review_required", "invalid_source_address", {"error": "invalid_source_address"})
        params = urllib.parse.urlencode({
            "key": self.api_key, "q": query, "format": "json", "countrycodes": "de",
            "addressdetails": 1, "normalizeaddress": 1, "normalizecity": 1,
            "statecode": 1, "limit": 2,
        })
        request = urllib.request.Request(self.endpoint + "?" + params,
                                         headers={"User-Agent": "UntilEveryCage/2 geocoding-worker", "Accept-Language": "de"})
        try:
            if self.opener is urllib.request.urlopen:
                opener = urllib.request.build_opener(self._NoRedirect())
                response_context = opener.open(request, timeout=self.timeout)
            else:
                response_context = self.opener(request, timeout=self.timeout)
            with response_context as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    return self._outcome("failed", "provider_response_too_large", {"error": "provider_response_too_large"})
                payload = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return self._outcome("unresolved", "no_results", {"results": []})
            if error.code in (401, 403):
                return self._outcome("failed", "authentication_rejected", {"error": "authentication_rejected"})
            if error.code == 429:
                return self._outcome("failed", "provider_rate_limited", {"error": "provider_rate_limited"}, retryable=True)
            return self._outcome("failed", "provider_http_error", {"error": "provider_http_error"}, retryable=500 <= error.code < 600)
        except (OSError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            return self._outcome("failed", "provider_transport_or_payload_error", {"error": "provider_transport_or_payload_error"}, retryable=True)
        if not isinstance(payload, list):
            return self._outcome("failed", "invalid_provider_schema", {"error": "invalid_provider_schema"})
        if not payload:
            return self._outcome("unresolved", "no_results", {"results": []})

        source_street, postcode, locality, state = parsed
        candidates, viable = [], []
        for item in payload[:2]:
            projected = self._candidate(item)
            if projected is None:
                return self._outcome("failed", "invalid_provider_schema", {"error": "invalid_provider_schema"})
            safe, coords = projected
            for key, value in tuple(safe.items()):
                if isinstance(value, str):
                    safe[key] = value.replace(self.api_key, "[redacted]")
                elif isinstance(value, dict):
                    safe[key] = {nested_key: nested_value.replace(self.api_key, "[redacted]")
                                 if isinstance(nested_value, str) else nested_value
                                 for nested_key, nested_value in value.items()}
            candidates.append(safe)
            if coords is None:
                continue
            address = safe["address"]
            if (str(address.get("country_code", "")).lower() != "de"
                    or not (5 <= coords[1] <= 16 and 47 <= coords[0] <= 56)):
                continue
            road, number = address.get("road"), address.get("house_number")
            pc = address.get("postcode")
            place_locality = next((address.get(key) for key in ("city", "town", "municipality", "village") if address.get(key)), "")
            place_states = [value for value in (address.get("state_code"), address.get("state"))
                            if isinstance(value, str) and value.strip()]
            address_type = str(safe.get("addresstype", "")).casefold()
            result_type = str(safe.get("type", "")).casefold()
            if (address_type not in {"road", "city", "town", "village", "municipality", "postcode"}
                    and safe.get("class") not in {"highway", "boundary", "place", "landuse"}
                    and result_type not in {"road", "city", "town", "village", "municipality", "postcode"}
                    and isinstance(road, str) and isinstance(number, (str, int))
                    and self._street_matches(source_street, road, str(number))
                    and str(pc) == postcode and self._normalize(str(place_locality)) == self._normalize(locality)
                    and (not state or (place_states and all(
                        GeoapifyAdapter._germany_state_code(value) == GeoapifyAdapter._germany_state_code(state)
                        for value in place_states)))):
                viable.append((len(candidates) - 1, coords, safe))

        envelope = {"results": candidates}
        if len(viable) != 1 or not (self.private_source_profile and self.country_code == "de"):
            reason = "ambiguous_multiple_viable_results" if len(viable) > 1 else "address_components_match_required"
            return self._outcome("review_required", reason, envelope)
        index, (lat, lon), candidate = viable[0]
        envelope["_uec_selected_result_index"] = index
        place_id = candidate.get("place_id")
        return self._outcome("accepted", "address_components_match", envelope,
                             lat=lat, lon=lon, place_id=str(place_id) if place_id is not None else None,
                             precision="locationiq_address_point")
