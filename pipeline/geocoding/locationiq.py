"""LocationIQ adapter for narrowly scoped private address matching."""

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
from . import spanish_addresses


class LocationIqAdapter:
    provider_id = "locationiq"
    endpoint = "https://eu1.locationiq.com/v1/search"

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    def __init__(self, api_key: str | None = None, timeout: int = 20,
                 opener: Callable = urllib.request.urlopen, *, country_code: str | None = None,
                 private_source_profile: bool = False, query_kind: str | None = None,
                 first_pass_source: bool = False):
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
        self.query_kind = query_kind
        self.first_pass_source = first_pass_source

    @staticmethod
    def _parse_first_pass_query(query: str, country_code: str):
        """Decode the bounded structured first-pass request and provider query."""
        try:
            payload = json.loads(query)
        except (TypeError, json.JSONDecodeError):
            return None
        if (not isinstance(payload, dict) or payload.get("schema_version") != "uec-address-query-v1"
                or set(payload) != {"schema_version", "address", "locality", "postcode", "region", "country_code"}
                or payload.get("country_code") != country_code.upper()):
            return None
        address = payload.get("address")
        locality = payload.get("locality")
        postcode = payload.get("postcode")
        region = payload.get("region")
        if (not isinstance(address, str) or not address.strip() or len(address) > 1200
                or not isinstance(locality, str) or len(locality) > 200
                or (postcode is not None and (not isinstance(postcode, str) or len(postcode) > 20))
                or (region is not None and (not isinstance(region, str) or len(region) > 200))):
            return None
        address = " ".join(address.split())
        locality = " ".join(locality.split())
        postcode = " ".join(postcode.split()) if isinstance(postcode, str) else None
        region = " ".join(region.split()) if isinstance(region, str) else None
        postcode = postcode or None
        region = region or None
        country_name = {"es": "Spain", "gb": "United Kingdom", "nz": "New Zealand"}.get(country_code)
        if country_name is None:
            return None
        if not locality and not ((country_code == "es" and region) or (country_code == "gb" and postcode)):
            return None
        provider_address = spanish_addresses.provider_address(address) if country_code == "es" else address
        provider_parts = [provider_address, locality, postcode, region, country_name]
        provider_query = ", ".join(part for part in provider_parts if part)
        if len(provider_query) > 1000:
            return None
        return address, locality, postcode, region, provider_query

    @classmethod
    def _first_pass_address_matches(cls, source_address: str, road, number) -> bool:
        """Require one exact comma-delimited source fragment for house + road."""
        if not isinstance(road, str) or not isinstance(number, (str, int)):
            return False
        expected = {cls._normalize(f"{number} {road}"), cls._normalize(f"{road} {number}")}
        matches = [part for part in source_address.split(",")
                   if cls._normalize(part.strip()) in expected]
        return len(matches) == 1

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
    def _parse_nz_query(cls, query: str):
        """Parse a street+number, locality, optional postcode, New Zealand query."""
        parts = [part.strip() for part in query.split(",") if part.strip()]
        if len(parts) not in (3, 4) or parts[-1].casefold() != "new zealand":
            return None
        street = parts[0]
        number_match = re.fullmatch(r"(\d+[a-zA-Z]?)\s+(.+)", street)
        if number_match:
            number, road = number_match.group(1), number_match.group(2).strip()
        else:
            number_match = re.fullmatch(r"(.+?)\s+(\d+[a-zA-Z]?)", street)
            if not number_match:
                return None
            road, number = number_match.group(1).strip(), number_match.group(2)
        if not road or not number:
            return None

        context = " ".join(parts[1:-1])
        postcode_matches = list(re.finditer(r"(?<!\d)(\d{4})(?!\d)", context))
        if len(postcode_matches) > 1:
            return None
        postcode = postcode_matches[0].group(1) if postcode_matches else None
        if postcode_matches:
            context = (context[:postcode_matches[0].start()] + " "
                       + context[postcode_matches[0].end():])
        locality = " ".join(context.split()).strip(" ,")
        if not locality:
            return None
        return road, number, locality, postcode

    @staticmethod
    def _parse_gb_query(query: str):
        """Parse canonical source-address query: house road, locality, postcode, UK."""
        parts = [part.strip() for part in query.split(",")]
        if (len(parts) != 4 or any(not part for part in parts)
                or parts[3].casefold() != "united kingdom"):
            return None
        match = re.fullmatch(r"(\d+[A-Za-z]?(?:[-/]\d+[A-Za-z]?)?)\s+(.+)", parts[0])
        postcode = re.sub(r"\s+", "", parts[2]).upper()
        if (not match or not re.fullmatch(r"(?:GIR0AA|[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2})", postcode)
                or len(parts[1]) > 200):
            return None
        return match.group(2), match.group(1), parts[1], postcode

    @classmethod
    def canonical_uk_query(cls, address_lines, locality: str, postcode: str) -> str | None:
        """Make a name-free UK query only from an unambiguous numbered road line.

        Other address-line text is intentionally omitted from provider queries.
        """
        if not isinstance(address_lines, (list, tuple)) or not address_lines:
            return None
        if not isinstance(locality, str) or not locality.strip() or len(locality.strip()) > 200:
            return None
        if not isinstance(postcode, str):
            return None
        canonical_postcode = re.sub(r"\s+", "", postcode).upper()
        if not re.fullmatch(r"(?:GIR0AA|[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2})", canonical_postcode):
            return None
        suffix = (r"(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|way|close|crescent|cres|"
                  r"court|ct|terrace|ter|place|pl|square|sq|gardens?|grove|green|hill|row|walk|mews|"
                  r"wharf|parade|high street|high road)")
        road_atom = r"[\w'’.\-]+"
        road_pattern = rf"{road_atom}(?:\s+{road_atom})*\s+{suffix}"
        house = r"\d+[A-Za-z]?(?:[-/]\d+[A-Za-z]?)?"
        found: set[tuple[str, str]] = set()
        for line in address_lines:
            if not isinstance(line, str):
                continue
            # Consider only comma-delimited subfields. Never copy nonmatching
            # fragments (which may contain establishment or contact names).
            for part in line.split(","):
                candidate = " ".join(part.split())
                match = re.fullmatch(rf"({house})\s+({road_pattern})", candidate, re.IGNORECASE)
                if not match:
                    match = re.fullmatch(rf"({road_pattern})\s+({house})", candidate, re.IGNORECASE)
                    if match:
                        road, number = match.group(1), match.group(2)
                    else:
                        continue
                else:
                    number, road = match.group(1), match.group(2)
                found.add((" ".join(road.split()), number))
        if len(found) != 1:
            return None
        road, number = next(iter(found))
        # Canonical number-first order is part of the migration/replay contract.
        query = f"{number} {road}, {' '.join(locality.split())}, {canonical_postcode[:-3]} {canonical_postcode[-3:]}, United Kingdom"
        return query if cls._parse_gb_query(query) is not None else None

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
        address_keys = {"house_number", "road", "postcode", "city", "town", "municipality", "village", "suburb", "state", "state_code", "county", "province", "state_district", "country_code"}
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
        is_first_pass_profile = self.query_kind == "source_address_first_pass"
        is_first_pass = is_first_pass_profile and query.lstrip().startswith("{")
        if len(query) > (2500 if is_first_pass else 1000):
            return self._outcome("review_required", "invalid_source_address", {"error": "invalid_source_address"})
        is_nz = self.country_code == "nz"
        is_gb = self.country_code == "gb"
        parsed = (self._parse_first_pass_query(query, self.country_code)
                  if is_first_pass else
                  self._parse_gb_query(query) if is_gb else
                  self._parse_nz_query(query) if is_nz else self._parse_query(query))
        if parsed is None:
            return self._outcome("review_required", "invalid_source_address", {"error": "invalid_source_address"})
        if is_first_pass:
            source_address, locality, postcode, region, query = parsed
        request_country = (self.country_code if is_first_pass else
                           "nz" if is_nz else "gb" if is_gb else "de")
        language = "es" if is_first_pass and self.country_code == "es" else (
            "en" if (is_nz or is_gb or is_first_pass) else "de")
        request_params = {
            "key": self.api_key, "q": query, "format": "json", "countrycodes": request_country,
            "addressdetails": 1, "normalizeaddress": 0 if is_first_pass and self.country_code == "es" else 1, "normalizecity": 1,
            "statecode": 1, "limit": 2,
        }
        endpoint = self.endpoint
        # Keep explicit Spanish street/house and municipality in separate fields.
        # Free-form search can silently fall back to a town when parsing an
        # industrial address. This makes one request, with unchanged acceptance
        # checks and no fallback/retry that would spend another credit.
        numbered_spanish_roads = ({(road, house) for road, house in
                                  spanish_addresses.address_parts(source_address)
                                  if road.partition(" ")[0] in
                                  {"street", "avenue", "road", "path", "promenade", "square"}}
                                 if is_first_pass and self.country_code == "es" else set())
        if (is_first_pass and self.country_code == "es" and locality
                and len(numbered_spanish_roads) == 1):
            endpoint += "/structured"
            del request_params["q"]
            request_params.update(street=spanish_addresses.provider_address(source_address),
                                  city=locality, country="Spain")
            if postcode:
                request_params["postalcode"] = postcode
            if region:
                request_params["state"] = region
        params = urllib.parse.urlencode(request_params)
        request = urllib.request.Request(endpoint + "?" + params,
                                         headers={"User-Agent": "UntilEveryCage/2 geocoding-worker", "Accept-Language": language})
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

        if is_first_pass:
            pass
        elif is_nz:
            source_street, source_number, locality, postcode = parsed
        elif is_gb:
            source_street, source_number, locality, postcode = parsed
        else:
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
            road, number = address.get("road"), address.get("house_number")
            address_type = str(safe.get("addresstype", "")).casefold()
            result_type = str(safe.get("type", "")).casefold()
            result_is_address = (address_type not in {"road", "city", "town", "village", "municipality", "postcode"}
                                 and safe.get("class") not in {"highway", "boundary", "place", "landuse"}
                                 and result_type not in {"road", "city", "town", "village", "municipality", "postcode"})
            if is_first_pass:
                house_address_node = (safe.get("class") == "place" and result_type == "house"
                                      and address_type in {"", "house", "building"})
                result_is_address = ((result_is_address and result_type != "houses"
                                      and address_type != "houses") or house_address_node)
                country = self.country_code
                in_bounds = ((-19 <= coords[1] <= 5 and 27 <= coords[0] <= 44.5)
                             if country == "es" else
                             (-8.7 <= coords[1] <= 2.1 and 49.8 <= coords[0] <= 60.9)
                             if country == "gb" else
                             (166 <= coords[1] <= 179.9 and -47.5 <= coords[0] <= -34.0))
                locality_values = [address.get(key) for key in
                                   ("city", "town", "municipality", "village", "suburb")]
                locality_match = ((not locality and country == "gb" and bool(postcode)) or any(
                    isinstance(value, str) and self._normalize(value) == self._normalize(locality)
                    for value in locality_values if locality))
                source_address_match = self._first_pass_address_matches(source_address, road, number)
                if country == "es":
                    source_address_match = spanish_addresses.street_matches(source_address, road, number)
                    locality_match = bool(locality) and any(
                        spanish_addresses.locality_key(value) == spanish_addresses.locality_key(locality)
                        for value in locality_values if isinstance(value, str))
                provider_postcode = re.sub(r"\s+", "", str(address.get("postcode", ""))).upper()
                postcode_match = (postcode is None or provider_postcode ==
                                  re.sub(r"\s+", "", postcode).upper())
                region_values = [address.get(key) for key in ("state", "state_code", "county")]
                region_match = (region is None or any(
                    isinstance(value, str) and self._normalize(value) == self._normalize(region)
                    for value in region_values))
                if country == "es":
                    region_match = spanish_addresses.province_matches(address, region, postcode)
                if (str(address.get("country_code", "")).lower() == country and in_bounds
                        and result_is_address and source_address_match and locality_match
                        and postcode_match and region_match):
                    viable.append((len(candidates) - 1, coords, safe))
            elif is_nz:
                # LocationIQ/Nominatim returns address-node results as
                # class=place,type=house with house-like/absent addresstype.
                # Keep this NZ-only exception; interpolated `houses` and
                # place/city results remain non-address candidates.
                nz_house_place = (safe.get("class") == "place" and result_type == "house"
                                  and address_type in {"", "house", "building"})
                result_is_address = result_is_address or nz_house_place
                locality_values = [address.get(key) for key in ("city", "town", "municipality", "village", "suburb")]
                locality_match = any(isinstance(value, str)
                                     and self._normalize(value) == self._normalize(locality)
                                     for value in locality_values)
                in_nz_bounds = 166 <= coords[1] <= 179.9 and -47.5 <= coords[0] <= -34.0
                if (str(address.get("country_code", "")).lower() == "nz" and in_nz_bounds
                        and result_is_address and isinstance(road, str)
                        and isinstance(number, (str, int))
                        and self._normalize(source_street) == self._normalize(road)
                        and self._normalize(str(number)) == self._normalize(source_number)
                        and locality_match
                        and (postcode is None or str(address.get("postcode", "")).strip() == postcode)):
                    viable.append((len(candidates) - 1, coords, safe))
            elif is_gb:
                in_gb_bounds = -8.7 <= coords[1] <= 2.1 and 49.8 <= coords[0] <= 60.9
                nz_house_place = (safe.get("class") == "place" and result_type == "house"
                                  and address_type in {"", "house", "building"})
                result_is_address = result_is_address or nz_house_place
                locality_values = [address.get(key) for key in ("city", "town", "municipality", "village")]
                locality_match = any(isinstance(value, str)
                                     and self._normalize(value) == self._normalize(locality)
                                     for value in locality_values)
                candidate_postcode = re.sub(r"\s+", "", str(address.get("postcode", ""))).upper()
                if (str(address.get("country_code", "")).lower() == "gb" and in_gb_bounds
                        and result_is_address and isinstance(road, str)
                        and isinstance(number, (str, int))
                        and self._normalize(road) == self._normalize(source_street)
                        and self._normalize(str(number)) == self._normalize(source_number)
                        and locality_match and candidate_postcode == postcode):
                    viable.append((len(candidates) - 1, coords, safe))
            else:
                if (str(address.get("country_code", "")).lower() != "de"
                        or not (5 <= coords[1] <= 16 and 47 <= coords[0] <= 56)):
                    continue
                pc = address.get("postcode")
                place_locality = next((address.get(key) for key in ("city", "town", "municipality", "village") if address.get(key)), "")
                place_states = [value for value in (address.get("state_code"), address.get("state"))
                                if isinstance(value, str) and value.strip()]
                if (result_is_address and isinstance(road, str) and isinstance(number, (str, int))
                        and self._street_matches(source_street, road, str(number))
                        and str(pc) == postcode and self._normalize(str(place_locality)) == self._normalize(locality)
                        and (not state or (place_states and all(
                            GeoapifyAdapter._germany_state_code(value) == GeoapifyAdapter._germany_state_code(state)
                            for value in place_states)))):
                    viable.append((len(candidates) - 1, coords, safe))

        envelope = {"results": candidates}
        profile_can_accept = (self.private_source_profile and
                              self.country_code in {"de", "nz", "gb"})
        profile_can_accept = profile_can_accept or (
            is_first_pass and self.private_source_profile and self.first_pass_source)
        if len(viable) != 1 or not profile_can_accept:
            reason = "ambiguous_multiple_viable_results" if len(viable) > 1 else "address_components_match_required"
            return self._outcome("review_required", reason, envelope)
        index, (lat, lon), candidate = viable[0]
        envelope["_uec_selected_result_index"] = index
        place_id = candidate.get("place_id")
        return self._outcome("accepted", "address_components_match", envelope,
                             lat=lat, lon=lon, place_id=str(place_id) if place_id is not None else None,
                             precision="locationiq_address_point")
