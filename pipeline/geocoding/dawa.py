import json
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
        except Exception as error:
            return GeocodeOutcome("failed", "unresolved", None, None, None, None, "dawa_request", True, {"error": str(error), "query": query})
        if len(payload) == 1:
            result = payload[0]
            return GeocodeOutcome("accepted", "accepted_single_point", result.get("y"), result.get("x"), result.get("id"), "address_point", "structured_address", False, payload)
        if len(payload) > 1:
            return GeocodeOutcome("review_required", "review_multiple_points", None, None, None, None, "structured_address", False, payload)
        return GeocodeOutcome("unresolved", "unresolved", None, None, None, None, "structured_address", False, payload)
