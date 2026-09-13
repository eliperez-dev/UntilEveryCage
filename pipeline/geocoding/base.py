from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class GeocodeOutcome:
    status: str
    acceptance: str
    latitude: float | None
    longitude: float | None
    provider_address_id: str | None
    precision: str | None
    match_method: str
    retryable: bool
    response: Any


class GeocoderAdapter(Protocol):
    provider_id: str

    def geocode(self, query: str) -> GeocodeOutcome:
        ...
