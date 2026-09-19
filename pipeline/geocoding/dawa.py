import json
import math
import urllib.error
import urllib.parse
import urllib.request

from .base import GeocodeOutcome


class DawaAdapter:
    provider_id = "dawa"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def geocode(self, query: str) -> GeocodeOutcome:
        parts = [part.strip() for part in query.split(",")]
        street = parts[0] if parts else query
        postal_code = parts[1] if len(parts) > 1 else ""
        city = parts[2] if len(parts) > 2 else ""
        params = {"vejnavn": street, "postnr": postal_code, "struktur": "mini", "fuzzy": "true"}
        url = "https://api.dataforsyningen.dk/adresser?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage/0.1 (open data pipeline)"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code <= 599
            reason = "provider_rate_limited" if error.code == 429 else "provider_http_error"
            if error.code in (401, 403):
                reason = "authentication_rejected"
            return GeocodeOutcome("failed", "unresolved", None, None, None, None, "dawa_request", retryable, {"error": reason, "status": error.code})
        except Exception as error:
            return GeocodeOutcome("failed", "unresolved", None, None, None, None, "dawa_request", True, {"error": type(error).__name__})
        if not isinstance(payload, list):
            return GeocodeOutcome("failed", "unresolved", None, None, None, None, "dawa_response", False, {"error": "invalid_provider_schema"})
        if len(payload) == 1:
            result = payload[0]
            latitude = result.get("y") if isinstance(result, dict) else None
            longitude = result.get("x") if isinstance(result, dict) else None
            valid = all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in (latitude, longitude))
            if not valid or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return GeocodeOutcome("unresolved", "invalid_coordinates", None, None, None, None, "structured_address", False, payload)
            return GeocodeOutcome("accepted", "accepted_single_point", latitude, longitude, result.get("id"), "address_point", "structured_address", False, payload)
        if len(payload) > 1:
            return GeocodeOutcome("review_required", "review_multiple_points", None, None, None, None, "structured_address", False, payload)
        return GeocodeOutcome("unresolved", "unresolved", None, None, None, None, "structured_address", False, payload)
